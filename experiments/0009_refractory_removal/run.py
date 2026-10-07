"""実験 0009 の実行（事前登録の一部。測定の前にコミットする）。

不応期を 3 → 0 にした（ほかの値は変えない）脳で、元の実験と同じ手順を回す。

- K1：0004 のパート A と同じ（minimal-v0 ＋ 順応の 10 条件 × seed 1〜20、入力なし 3600 Pulse、
      偽 Kernel 遅延 3 秒、Worker 1）。設定は 0004 の run.py、記録の取り出しは 0008 の run.py の extract を使う
- K2：0005 と同じ（10 条件 × 20 個体 × 2 枝 × 10 強さ）。0005 の run.py の run_once を使い、
      設計図の作り方（neuro_raw）だけを「不応期 0 にしたもの」に差し替える

実行基盤は今の main（新しい基盤）。不応期 3 の比較の基準は 0008 の NEW（同じ基盤）を使う。

使い方（リポジトリ直下で）:
  python experiments/0009_refractory_removal/run.py
  python experiments/0009_refractory_removal/run.py --seeds 2 --out <scratch>   # 動作確認だけ
Docker:
  docker compose run --rm --no-deps anima python experiments/0009_refractory_removal/run.py
"""

import argparse
import asyncio
import gzip
import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.adapter.effector.recording_effector import RecordingEffector
from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
from anima_ll.bootstrap import build_application

OUT_DIR = Path("data/experiments/0009")
REFRACTORY = 0


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R4 = load("run_0004", "experiments/0004_adaptation/run.py")
R5 = load("run_0005", "experiments/0005_response_threshold/run.py")
R8 = load("run_0008", "experiments/0008_baseline_new_runtime/run.py")


def without_refractory(raw: dict) -> dict:
    raw["defaults"]["dynamics"]["refractory_pulses"] = REFRACTORY
    for unit in raw["units"]:
        if isinstance(unit.get("dynamics"), dict) and "refractory_pulses" in unit["dynamics"]:
            unit["dynamics"]["refractory_pulses"] = REFRACTORY
    return raw


def k1_once(alpha: float, tau: float, seed: int) -> dict:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(without_refractory(R4.neuro_raw(alpha, tau))),
        parse_environment(R4.environment_raw({})),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=1,
    )
    # 設定が効いていることの確認（全 Unit の不応期が 0）
    assert all(u.export_state()["dynamics"]["refractory_pulses"] == REFRACTORY for u in app.units.all())
    asyncio.run(app.lifecycle.run(max_pulses=R4.SILENT_PULSES))
    return R8.extract(log)


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
    parser.add_argument("--seeds", type=int, default=20, help="先頭から何個体使うか（動作確認用）")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    seeds = list(R4.SEEDS[: args.seeds])
    started = time.time()
    commit = git_commit()
    args.out.mkdir(parents=True, exist_ok=True)

    # ---- K1 ----
    k1 = {"meta": {"experiment": "0009-K1", "git_commit": commit, "refractory_pulses": REFRACTORY,
                   "neuroarchitecture": str(R4.NEURO), "conditions": R4.CONDITIONS, "seeds": seeds,
                   "silent_pulses": R4.SILENT_PULSES, "queue_capacity": None},
          "runs": []}
    for alpha, tau in R4.CONDITIONS:
        for seed in seeds:
            k1["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, **k1_once(alpha, tau, seed)})
        print(f"[K1] α={alpha} τ={tau} done ({time.time() - started:.0f}s)", flush=True)
    with gzip.open(args.out / "k1.json.gz", "wt", encoding="utf-8") as f:
        json.dump(k1, f)

    # ---- K2（0005 の run_once を、不応期 0 の設計図で回す） ----
    original = R5.neuro_raw
    R5.neuro_raw = lambda alpha, tau, weight: without_refractory(original(alpha, tau, weight))
    k2 = {"meta": {"experiment": "0009-K2", "git_commit": commit, "refractory_pulses": REFRACTORY,
                   "neuroarchitecture": str(R5.NEURO), "conditions": R5.CONDITIONS, "seeds": seeds,
                   "protocol": {"conditioning": R5.CONDITIONING, "probe": R5.PROBE, "pulses": R5.PULSES,
                                "probe_weights": R5.PROBE_WEIGHTS, "conditioning_weight": 1.0}},
          "runs": []}
    for alpha, tau in R5.CONDITIONS:
        for seed in seeds:
            for branch, conditioning in (("rested", False), ("adapted", True)):
                for w in R5.PROBE_WEIGHTS:
                    data = R5.run_once(alpha, tau, w, seed, conditioning)
                    k2["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, "branch": branch,
                                       "weight": w, **data})
        print(f"[K2] α={alpha} τ={tau} done ({time.time() - started:.0f}s)", flush=True)
    with gzip.open(args.out / "k2.json.gz", "wt", encoding="utf-8") as f:
        json.dump(k2, f)
    print(f"saved {args.out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
