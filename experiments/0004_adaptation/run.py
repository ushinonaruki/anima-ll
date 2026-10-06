"""実験 0004 の実行（事前登録の一部。実行前にコミットする）。

偽 Kernel・時計の早送りで、全条件を同じプロセスの中で回し、集計に必要な要素だけを保存する。
（全イベントのログは 1 本あたり数 MB になるため保存しない。実行時の非決定的な乱数は使わず、
 Birth State の seed 付き擬似乱数だけなので、同じ commit・seed・条件ならいつでも再現できる）

使い方（リポジトリ直下で）:
  python experiments/0004_adaptation/run.py                    # 全条件（数分〜十数分）
  python experiments/0004_adaptation/run.py --seeds 2 --quick  # 動作確認だけ

Docker:
  docker compose run --rm --no-deps anima python experiments/0004_adaptation/run.py
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
OUT = Path("data/experiments/0004/results.json.gz")

# ---- 事前登録した条件 ----------------------------------------------------------

ALPHAS = (0.005, 0.01, 0.02)
TAUS = (30, 300, 1200)
CONDITIONS = [(0.0, 0)] + [(a, t) for a in ALPHAS for t in TAUS]  # α = 0 は τ に無関係なので 1 条件
SEEDS = tuple(range(1, 21))

# パート A：入力なし
SILENT_PULSES = 3600

# パート B：同じ seed から分岐させた 2 条件（conditioning の有無）に、同じ probe を与える
WARMUP = 600                                     # 入力なしで落ち着かせる
CONDITIONING = tuple(range(600, 621, 5))         # 600, 605, 610, 615, 620（5 回。不応期 3 より間隔を空ける）
PROBE = 650                                      # 最後の conditioning から 30 Pulse 後
PROBE_PULSES = 700
PROBE_WEIGHTS = (0.6, 1.0)                       # receptor → u0 の結合の重み（閾値付近／強い）
INPUT_TEXT = "x"                                 # 中身は使わない（偽 Kernel も Unit も読まない）


def neuro_raw(alpha: float, tau: float, probe_weight: float | None = None) -> dict:
    raw = yaml.safe_load(NEURO.read_text(encoding="utf-8"))
    raw = copy.deepcopy(raw)
    dyn = raw["defaults"]["dynamics"]
    dyn["adaptation_increment"] = alpha
    dyn["adaptation_tau"] = tau
    if probe_weight is not None:
        for p in raw["projections"]:
            if str(p["from"]).startswith("receptor.console"):
                p["weight"] = probe_weight
    return raw


def environment_raw(script: dict[int, str]) -> dict:
    return {
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed", "delay_seconds": 3}},
        "receptors": {"receptor.console": {"kind": "scripted", "script": script}},
        "effectors": {"effector.console": {"kind": "recording"}},
    }


def run_once(neuro: dict, script: dict[int, str], seed: int, pulses: int) -> dict:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(neuro),
        parse_environment(environment_raw(script)),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=1,
    )
    asyncio.run(app.lifecycle.run(max_pulses=pulses))
    return extract(log)


def extract(log: InMemoryEventLog) -> dict:
    """集計に必要な要素だけを取り出す。"""
    fires: dict[str, list[int]] = {}
    last_count: dict[str, int] = {}
    adaptation: dict[str, list[list[float]]] = {}
    claims: dict[str, list[int]] = {}
    accepted: dict[str, int] = {}
    rejected: dict[str, int] = {}
    effects: list[int] = []
    for e in log.events:
        d = e.data
        if e.type == "unit_state":
            u, st = d["unit_id"], d["state"]
            if st["fire_count"] > last_count.get(u, 0):
                fires.setdefault(u, []).append(e.pulse)
            last_count[u] = st["fire_count"]
            if e.pulse % 10 == 0:
                adaptation.setdefault(u, []).append([e.pulse, round(st["adaptation"], 6)])
        elif e.type == "claim":
            claims.setdefault(d["unit_id"], []).append(e.pulse)
        elif e.type == "schedule":
            for u in d["accepted"]:
                accepted[u] = accepted.get(u, 0) + 1
            for u in d["rejected"]:
                rejected[u] = rejected.get(u, 0) + 1
        elif e.type == "effect":
            effects.append(e.pulse)
    return {"fires": fires, "claims": claims, "accepted": accepted, "rejected": rejected,
            "effects": effects, "adaptation": adaptation}


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
    parser.add_argument("--seeds", type=int, default=len(SEEDS), help="先頭から何個体使うか（動作確認用）")
    parser.add_argument("--quick", action="store_true", help="パルス数を 1/6 にする（動作確認用。結果は使わない）")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    seeds = SEEDS[: args.seeds]
    scale = 6 if args.quick else 1
    started = time.time()
    results: dict = {
        "meta": {
            "experiment": "0004",
            "git_commit": git_commit(),
            "neuroarchitecture": str(NEURO),
            "conditions": CONDITIONS,
            "seeds": seeds,
            "quick": args.quick,
            "silent_pulses": SILENT_PULSES // scale,
            "protocol": {"warmup": WARMUP, "conditioning": CONDITIONING, "probe": PROBE,
                         "pulses": PROBE_PULSES, "probe_weights": PROBE_WEIGHTS},
        },
        "silent": [],
        "probe": [],
    }

    for alpha, tau in CONDITIONS:
        for seed in seeds:
            data = run_once(neuro_raw(alpha, tau), {}, seed, SILENT_PULSES // scale)
            results["silent"].append({"alpha": alpha, "tau": tau, "seed": seed, **data})
        print(f"[silent] α={alpha} τ={tau} done ({time.time() - started:.0f}s)", flush=True)

    if not args.quick:
        for weight in PROBE_WEIGHTS:
            for alpha, tau in CONDITIONS:
                for seed in seeds:
                    neuro = neuro_raw(alpha, tau, weight)
                    rested = run_once(neuro, {PROBE: INPUT_TEXT}, seed, PROBE_PULSES)
                    adapted = run_once(
                        neuro, {**{p: INPUT_TEXT for p in CONDITIONING}, PROBE: INPUT_TEXT}, seed, PROBE_PULSES
                    )
                    results["probe"].append({"weight": weight, "alpha": alpha, "tau": tau, "seed": seed,
                                             "rested": rested, "adapted": adapted})
                print(f"[probe w={weight}] α={alpha} τ={tau} done ({time.time() - started:.0f}s)", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(results, f)
    print(f"saved {args.out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
