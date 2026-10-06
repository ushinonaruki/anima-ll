"""実験 0006 の実行（事前登録の一部。実行前にコミットする）。

minimal-v1（順応あり）に、計算の要求の持ち越し（L2-2）だけを足して比べる。
偽 Kernel・時計の早送り・入力なし。全条件を同じプロセスの中で回し、集計に必要な要素だけを保存する。

使い方（リポジトリ直下で）:
  python experiments/0006_pending_compute/run.py
Docker:
  docker compose run --rm --no-deps anima python experiments/0006_pending_compute/run.py
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

NEURO = Path("config/neuroarchitecture/minimal-v1.yaml")
OUT = Path("data/experiments/0006/results.json.gz")

# ---- 事前登録した条件 ----------------------------------------------------------
PENDING_TAUS = (0, 2, 5, 10)       # τ_p（秒）。0 は持ち越しなし（minimal-v1 と同じ）
PENDING_FLOOR = 0.1                # p_min（Engineering cutoff として固定）
KERNEL_DELAYS = (1, 3)             # 偽 Kernel の推論時間（秒）。1 は L1 の Ollama（1〜2 秒）に近い
SEEDS = tuple(range(1, 21))
PULSES = 3600
STATE_SAMPLE = 60                  # 発火回数の推移を見るための Unit 状態の標本間隔


def neuro_raw(pending_tau: float) -> dict:
    raw = copy.deepcopy(yaml.safe_load(NEURO.read_text(encoding="utf-8")))
    for unit in raw["units"]:
        out = unit["output"]
        if isinstance(out, dict) and out.get("kind") == "kernel_request":
            out["pending_tau"] = pending_tau
            out["pending_floor"] = PENDING_FLOOR
    return raw


def environment_raw(delay: float) -> dict:
    return {
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed", "delay_seconds": delay}},
        "receptors": {"receptor.console": {"kind": "scripted", "script": {}}},
        "effectors": {"effector.console": {"kind": "recording"}},
    }


def run_once(pending_tau: float, delay: float, seed: int) -> dict:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(neuro_raw(pending_tau)),
        parse_environment(environment_raw(delay)),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=STATE_SAMPLE,
    )
    asyncio.run(app.lifecycle.run(max_pulses=PULSES))

    claims, started, effects, fire_counts = [], [], 0, {}
    for e in log.events:
        d = e.data
        if e.type == "compute_outcome":
            claims.append([e.pulse, d["unit_id"], d["origin"], round(d["strength"], 6), d["outcome"]])
        elif e.type == "task_started":
            started.append([e.pulse, d["unit_id"], d["without_evidence"]])
        elif e.type == "effect":
            effects += 1
        elif e.type == "unit_state":
            fire_counts.setdefault(d["unit_id"], []).append([e.pulse, d["state"]["fire_count"]])
    return {"claims": claims, "started": started, "effects": effects, "fire_counts": fire_counts}


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
        "meta": {"experiment": "0006", "git_commit": git_commit(), "neuroarchitecture": str(NEURO),
                 "pending_taus": PENDING_TAUS, "pending_floor": PENDING_FLOOR, "kernel_delays": KERNEL_DELAYS,
                 "seeds": seeds, "pulses": PULSES},
        "runs": [],
    }
    for delay in KERNEL_DELAYS:
        for tau in PENDING_TAUS:
            for seed in seeds:
                results["runs"].append({"delay": delay, "pending_tau": tau, "seed": seed,
                                        **run_once(tau, delay, seed)})
            print(f"delay={delay} τ_p={tau} done ({time.time() - started:.0f}s)", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(results, f)
    print(f"saved {args.out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
