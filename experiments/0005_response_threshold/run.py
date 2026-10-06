"""実験 0005 の実行（事前登録の一部。実行前にコミットする）。

0004 と同じ条件・同じ手順で、probe の強さだけを段階的に変えた独立の実行を回し、
u0 をすぐに発火させるのに必要な最小の強さ（w*）を個体ごとに求める。

conditioning と probe の強さを分けるため、実験用に receptor.probe（→ u0）を 1 本足した設計図を使う。
conditioning は receptor.console（→ u0、重み 1.0）から、probe は receptor.probe（→ u0、重み w）から入る。

使い方（リポジトリ直下で）:
  python experiments/0005_response_threshold/run.py
Docker:
  docker compose run --rm --no-deps anima python experiments/0005_response_threshold/run.py
"""

import argparse
import asyncio
import copy
import gzip
import json
import os
import subprocess
import time
from pathlib import Path

import yaml

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.adapter.effector.recording_effector import RecordingEffector
from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
from anima_ll.bootstrap import build_application

NEURO = Path("config/neuroarchitecture/minimal-v0.yaml")
OUT = Path("data/experiments/0005/results.json.gz")

# ---- 事前登録した条件（0004 と同じ） -------------------------------------------------
CONDITIONS = [(0.0, 0)] + [(a, t) for a in (0.005, 0.01, 0.02) for t in (30, 300, 1200)]
SEEDS = tuple(range(1, 21))
CONDITIONING = tuple(range(600, 621, 5))   # receptor.console（重み 1.0）から 5 回
PROBE = 650                                # receptor.probe（重み w）から 1 回。651 Pulse から u0 に見える
PULSES = 700
PROBE_WEIGHTS = (0.0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60)
INPUT_TEXT = "x"                           # 中身は使わない
KEEP_FROM = 640                            # 保存する発火はこの Pulse 以降だけ


def neuro_raw(alpha: float, tau: float, probe_weight: float) -> dict:
    raw = copy.deepcopy(yaml.safe_load(NEURO.read_text(encoding="utf-8")))
    dyn = raw["defaults"]["dynamics"]
    dyn["adaptation_increment"] = alpha
    dyn["adaptation_tau"] = tau
    raw["interfaces"]["receptors"] = list(raw["interfaces"]["receptors"]) + ["receptor.probe"]
    raw["projections"].append({"from": "receptor.probe.main", "to": "u0", "weight": probe_weight})
    for p in raw["projections"]:
        if str(p["from"]).startswith("receptor.console"):
            p["weight"] = 1.0
    return raw


def environment_raw(conditioning: bool) -> dict:
    console = {p: INPUT_TEXT for p in CONDITIONING} if conditioning else {}
    return {
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed", "delay_seconds": 3}},
        "receptors": {
            "receptor.console": {"kind": "scripted", "script": console},
            "receptor.probe": {"kind": "scripted", "script": {PROBE: INPUT_TEXT}},
        },
        "effectors": {"effector.console": {"kind": "recording"}},
    }


def run_once(alpha: float, tau: float, weight: float, seed: int, conditioning: bool) -> dict:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(neuro_raw(alpha, tau, weight)),
        parse_environment(environment_raw(conditioning)),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=1,
    )
    asyncio.run(app.lifecycle.run(max_pulses=PULSES))

    fires: dict[str, list[int]] = {}
    last: dict[str, int] = {}
    state_650: dict = {}
    for e in log.events:
        if e.type != "unit_state":
            continue
        u, st = e.data["unit_id"], e.data["state"]
        if st["fire_count"] > last.get(u, 0) and e.pulse >= KEEP_FROM:
            fires.setdefault(u, []).append(e.pulse)
        last[u] = st["fire_count"]
        if e.pulse == PROBE and u == "u0":
            state_650 = st
    return {"fires": fires, "u0_state_650": state_650}


def git_commit() -> str:
    env = os.environ.get("ANIMA_GIT_COMMIT", "").strip()
    if env:
        return env
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=len(SEEDS), help="先頭から何個体使うか（動作確認用。判定は不能になる）")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    seeds = SEEDS[: args.seeds]
    started = time.time()
    results: dict = {
        "meta": {
            "experiment": "0005",
            "git_commit": git_commit(),
            "neuroarchitecture": str(NEURO),
            "conditions": CONDITIONS,
            "seeds": seeds,
            "protocol": {"conditioning": CONDITIONING, "probe": PROBE, "pulses": PULSES,
                         "probe_weights": PROBE_WEIGHTS, "conditioning_weight": 1.0},
        },
        "runs": [],
    }
    for alpha, tau in CONDITIONS:
        for seed in seeds:
            for branch, conditioning in (("rested", False), ("adapted", True)):
                for w in PROBE_WEIGHTS:
                    data = run_once(alpha, tau, w, seed, conditioning)
                    results["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, "branch": branch,
                                            "weight": w, **data})
        print(f"α={alpha} τ={tau} done ({time.time() - started:.0f}s)", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(results, f)
    print(f"saved {args.out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
