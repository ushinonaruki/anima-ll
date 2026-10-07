"""実験 0007 の実行（事前登録の一部。測定の前にコミットする）。

計算資源境界の実装確認。偽 Kernel・時計の早送りで回し、判定に必要な要素だけを保存する。
発火・計算・発話の量は保存しない（0007 は工学の検証で、それらは 0008 で扱う）。

- stop  ：Kernel が結果を返さない（遅延 10⁹ 秒）、300 Pulse、入力なし。OLD・NEW-1・NEW-4
          → A0（Unit の状態の推移の一致）と A2（意図の列の一致）、A1（消えない）
- smoke ：遅延 3 秒、3600 Pulse、入力なし。NEW-1・NEW-4 → 意図の一生の整合（正式な判定ではない）

列の上限は「上限なし」（事前登録：構造上の最大値 3 × N より大きい値、または上限なし）。

OLD（main 3ae66e7、意図を捨てる旧基盤）は、その commit の src を取り出して別プロセスで動かす。

使い方（リポジトリ直下で）:
  python experiments/0007_compute_boundary/run.py
  python experiments/0007_compute_boundary/run.py --seeds 2 --quick   # 動作確認だけ

Docker（.git がコンテナに無いので、OLD の src は先に取り出しておく）:
  git archive 3ae66e7 src | tar -x -C data/experiments/0007/old
  docker compose run --rm --no-deps anima python experiments/0007_compute_boundary/run.py \
      --old-src data/experiments/0007/old/src
"""

import argparse
import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OLD_COMMIT = "3ae66e7"
NEURO = Path("config/neuroarchitecture/minimal-v1.yaml")
OUT = Path("data/experiments/0007/results.json.gz")
NEW_SRC = Path("src")

SEEDS = tuple(range(1, 21))
STOP_PULSES = 300
STOP_DELAY = 1e9
SMOKE_PULSES = 3600
SMOKE_DELAY = 3

# (名前, 実装, Worker の数)
STOP_CONDITIONS = (("OLD", "old", 1), ("NEW-1", "new", 1), ("NEW-4", "new", 4))
SMOKE_CONDITIONS = (("NEW-1", "new", 1), ("NEW-4", "new", 4))


# ---- 子プロセス（OLD・NEW どちらの src でも動くように、両方にある API だけを使う） ----------

def worker(spec: dict) -> dict:
    import asyncio

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

    neuro = yaml.safe_load(Path(spec["neuro"]).read_text(encoding="utf-8"))
    env = {
        "resources": {"llm_pool": {"capacity": spec["workers"], "kernel": "fake_delayed",
                                   "delay_seconds": spec["delay"]}},
        "receptors": {"receptor.console": {"kind": "scripted", "script": {}}},
        "effectors": {"effector.console": {"kind": "recording"}},
    }
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(neuro),
        parse_environment(env),
        parse_birth_state({"individual_id": "anima", "seed": spec["seed"]}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=1 if spec["kind"] == "stop" else 0,
    )
    error = None
    try:
        asyncio.run(app.lifecycle.run(max_pulses=spec["pulses"]))
    except Exception as exc:  # smoke の「例外が出ない」の確認のため、捕まえて記録する
        error = repr(exc)
    return {**extract(log, spec["kind"]), "error": error}


def extract(log, kind: str) -> dict:
    types = [e.type for e in log.events]
    out: dict = {"event_types": sorted(set(types))}
    if kind == "stop":
        # A0：全 Unit の状態の推移（Pulse ごと）
        out["states"] = [
            [e.pulse, e.data["unit_id"], repr(e.data["state"]["activity"]),
             repr(e.data["state"]["adaptation"]), e.data["state"]["refractory_remaining"],
             e.data["state"]["fire_count"]]
            for e in log.events if e.type == "unit_state"
        ]
    # A1・A2：意図の一生（新基盤だけにある）
    created = [e for e in log.events if e.type == "intent_created"]
    out["intents"] = [
        [e.pulse, e.data["intent_id"], e.data["unit_id"], e.data["origin_snapshot_id"],
         list(e.data["input_delta_ids"]), e.data["draft_hash"]]
        for e in created
    ] if kind == "stop" else None
    out["lifecycle"] = lifecycle_checks(log) if created else None
    return out


def lifecycle_checks(log) -> dict:
    """意図の一生の整合（A1・A3 の結合での確認と smoke）。量ではなく、破れた件数だけを返す。"""
    terminal = {"intent_completed", "intent_kernel_error", "intent_rejected_overflow"}
    created: dict[str, str] = {}
    admitted: set[str] = set()
    started: dict[str, int] = {}
    ended: dict[str, int] = {}
    outstanding: set[str] = set()
    running: dict[str, int] = {}
    max_running_per_unit = 0
    order_violations = 0
    last_started_seq: dict[str, int] = {}
    seq_of: dict[str, int] = {}
    for e in log.events:
        d = e.data
        if e.type == "intent_created":
            created[d["intent_id"]] = d["unit_id"]
            seq_of[d["intent_id"]] = d["intent_seq"]
        elif e.type == "intent_admitted":
            admitted.add(d["intent_id"])
        elif e.type == "intent_started":
            started[d["intent_id"]] = started.get(d["intent_id"], 0) + 1
            unit = d["unit_id"]
            running[unit] = running.get(unit, 0) + 1
            max_running_per_unit = max(max_running_per_unit, running[unit])
            if seq_of[d["intent_id"]] < last_started_seq.get(unit, 0):
                order_violations += 1
            last_started_seq[unit] = seq_of[d["intent_id"]]
        elif e.type in terminal:
            ended[d["intent_id"]] = ended.get(d["intent_id"], 0) + 1
            if e.type != "intent_rejected_overflow":
                running[d["unit_id"]] -= 1
        elif e.type == "intent_outstanding":
            outstanding.add(d["intent_id"])
    unaccounted = [i for i in created if ended.get(i, 0) + (i in outstanding) != 1]
    return {
        "created": len(created),
        "unaccounted": len(unaccounted),            # どの終わり方でもなく、残ってもいない＝消えた
        "not_admitted_without_overflow": sum(
            1 for i in created if i not in admitted and ended.get(i) is None),
        "started_twice": sum(1 for n in started.values() if n > 1),
        "max_running_per_unit": max_running_per_unit,
        "order_violations": order_violations,
        "overflow": sum(1 for e in log.events if e.type == "intent_rejected_overflow"),
        "degraded": any(e.type == "runtime_degraded" for e in log.events),
    }


# ---- 親プロセス -------------------------------------------------------------------

def run_in_subprocess(src: Path, spec: dict) -> dict:
    env = {**os.environ, "PYTHONPATH": str(src.resolve())}
    proc = subprocess.run(
        [sys.executable, __file__, "--worker", json.dumps(spec)],
        capture_output=True, text=True, env=env, check=True,
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def prepare_old_src(given: Path | None) -> Path:
    if given is not None:
        return given
    target = Path("data/experiments/0007/old")
    if not (target / "src").exists():
        target.mkdir(parents=True, exist_ok=True)
        archive = subprocess.run(["git", "archive", OLD_COMMIT, "src"], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(target)], input=archive.stdout, check=True)
    return target / "src"


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
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--seeds", type=int, default=len(SEEDS), help="先頭から何個体使うか（動作確認用）")
    parser.add_argument("--quick", action="store_true", help="smoke を 1/12 にする（動作確認用。結果は使わない）")
    parser.add_argument("--old-src", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return

    seeds = SEEDS[: args.seeds]
    srcs = {"old": prepare_old_src(args.old_src), "new": NEW_SRC}
    smoke_pulses = SMOKE_PULSES // (12 if args.quick else 1)
    started = time.time()
    results: dict = {
        "meta": {"experiment": "0007", "git_commit": git_commit(), "old_commit": OLD_COMMIT,
                 "neuroarchitecture": str(NEURO), "seeds": seeds, "quick": args.quick,
                 "stop": {"pulses": STOP_PULSES, "delay": STOP_DELAY, "conditions": STOP_CONDITIONS},
                 "smoke": {"pulses": smoke_pulses, "delay": SMOKE_DELAY, "conditions": SMOKE_CONDITIONS},
                 "queue_capacity": None},
        "stop": [],
        "smoke": [],
    }
    for name, impl, workers in STOP_CONDITIONS:
        for seed in seeds:
            spec = {"kind": "stop", "neuro": str(NEURO), "workers": workers, "delay": STOP_DELAY,
                    "seed": seed, "pulses": STOP_PULSES}
            results["stop"].append({"condition": name, "seed": seed, **run_in_subprocess(srcs[impl], spec)})
        print(f"[stop] {name} done ({time.time() - started:.0f}s)", flush=True)
    for name, impl, workers in SMOKE_CONDITIONS:
        for seed in seeds:
            spec = {"kind": "smoke", "neuro": str(NEURO), "workers": workers, "delay": SMOKE_DELAY,
                    "seed": seed, "pulses": smoke_pulses}
            results["smoke"].append({"condition": name, "seed": seed, **run_in_subprocess(srcs[impl], spec)})
        print(f"[smoke] {name} done ({time.time() - started:.0f}s)", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wt", encoding="utf-8") as f:
        json.dump(results, f)
    print(f"saved {args.out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
