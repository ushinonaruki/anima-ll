"""実験 0008 の実行（事前登録の一部。測定の前にコミットする）。

- silent：0004 のパート A と同じ（minimal-v0 ＋ 順応の 10 条件 × seed 1〜20、入力なし 3600 Pulse、
          偽 Kernel 遅延 3 秒、Worker 1）を、OLD（main 3ae66e7）と NEW（この commit）で回す。
          設定は 0004 の run.py の neuro_raw・environment_raw をそのまま使う（手順を 0004 とそろえるため）
- 0005  ：0005 の run.py を NEW の src でそのまま回す（全 4000 本）

OLD は 3ae66e7 の src を取り出して別プロセスで動かす（0007 と同じ方法）。

使い方（リポジトリ直下で）:
  python experiments/0008_baseline_new_runtime/run.py
  python experiments/0008_baseline_new_runtime/run.py --seeds 2 --skip-0005 --out <scratch>   # 動作確認だけ

Docker（.git がコンテナに無いので、OLD の src は先に取り出しておく）:
  mkdir -p data/experiments/0008/old && git archive 3ae66e7 src | tar -x -C data/experiments/0008/old
  docker compose run --rm --no-deps anima python experiments/0008_baseline_new_runtime/run.py \
      --old-src data/experiments/0008/old/src
"""

import argparse
import gzip
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

OLD_COMMIT = "3ae66e7"
OUT_DIR = Path("data/experiments/0008")
NEW_SRC = Path("src")
RUN_0004 = Path("experiments/0004_adaptation/run.py")
RUN_0005 = Path("experiments/0005_response_threshold/run.py")


def load_0004():
    spec = importlib.util.spec_from_file_location("run_0004", RUN_0004)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- 子プロセス（OLD・NEW どちらの src でも動く） ----------------------------------------

def worker(spec: dict) -> list[dict]:
    import asyncio

    from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
    from anima_ll.adapter.config.yaml_config_source import (
        parse_birth_state,
        parse_environment,
        parse_neuroarchitecture,
    )
    from anima_ll.adapter.effector.recording_effector import RecordingEffector
    from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
    from anima_ll.bootstrap import build_application

    r4 = load_0004()
    out = []
    for seed in spec["seeds"]:
        log = InMemoryEventLog()
        app = build_application(
            parse_neuroarchitecture(r4.neuro_raw(spec["alpha"], spec["tau"])),
            parse_environment(r4.environment_raw({})),
            parse_birth_state({"individual_id": "anima", "seed": seed}),
            clock=FixedStepClock(1.0),
            event_log=log,
            effector_overrides={"effector.console": RecordingEffector("effector.console")},
            state_sample_interval=1,
        )
        asyncio.run(app.lifecycle.run(max_pulses=spec["pulses"]))
        out.append({"alpha": spec["alpha"], "tau": spec["tau"], "seed": seed, **extract(log)})
    return out


def extract(log) -> dict:
    """発火（0004 と同じ取り出し方）と、計算の要求・意図の記録。"""
    fires: dict[str, list[int]] = {}
    last_count: dict[str, int] = {}
    adaptation: dict[str, list[list[float]]] = {}
    effects: list[int] = []
    # OLD
    claims: dict[str, int] = {}
    accepted: dict[str, int] = {}
    rejected: dict[str, int] = {}
    busy_dropped: dict[str, int] = {}
    claim_units_this_pulse: list[str] = []
    # NEW
    created: dict[str, int] = {}
    started: dict[str, int] = {}
    completed: dict[str, int] = {}
    waits: list[int] = []
    waiting_by_pulse: dict[int, int] = {}
    waiting = 0
    outstanding = 0
    overflow = 0
    for e in log.events:
        d = e.data
        if e.type == "pulse":
            claim_units_this_pulse = []
        elif e.type == "unit_state":
            u, st = d["unit_id"], d["state"]
            if st["fire_count"] > last_count.get(u, 0):
                fires.setdefault(u, []).append(e.pulse)
            last_count[u] = st["fire_count"]
            if e.pulse % 10 == 0:
                adaptation.setdefault(u, []).append([e.pulse, round(st["adaptation"], 6)])
            waiting_by_pulse[e.pulse] = waiting
        elif e.type == "effect":
            effects.append(e.pulse)
        elif e.type == "claim":
            claims[d["unit_id"]] = claims.get(d["unit_id"], 0) + 1
            claim_units_this_pulse.append(d["unit_id"])
        elif e.type == "schedule":
            for u in d["accepted"]:
                accepted[u] = accepted.get(u, 0) + 1
            for u in d["rejected"]:
                rejected[u] = rejected.get(u, 0) + 1
            for u in d["busy"]:
                if u in claim_units_this_pulse:
                    busy_dropped[u] = busy_dropped.get(u, 0) + 1
        elif e.type == "intent_created":
            created[d["unit_id"]] = created.get(d["unit_id"], 0) + 1
        elif e.type == "intent_admitted":
            waiting += 1
        elif e.type == "intent_started":
            started[d["unit_id"]] = started.get(d["unit_id"], 0) + 1
            waits.append(e.pulse - d["created_pulse"])
            waiting -= 1
        elif e.type in ("intent_completed", "intent_kernel_error"):
            completed[d["unit_id"]] = completed.get(d["unit_id"], 0) + 1
        elif e.type == "intent_rejected_overflow":
            overflow += 1
        elif e.type == "intent_outstanding":
            outstanding += 1
    return {
        "fires": fires, "adaptation": adaptation, "effects": effects,
        # 0004 の analyze_silent が読む「計算が実行された回数」（OLD は採択、NEW は開始）
        "accepted": accepted if claims else started,
        "old": {"claims": claims, "accepted": accepted, "rejected": rejected,
                "busy_dropped": busy_dropped} if claims else None,
        "new": {"created": created, "started": started, "completed": completed,
                "waits": waits, "waiting": [waiting_by_pulse[p] for p in sorted(waiting_by_pulse)],
                "outstanding": outstanding, "overflow": overflow} if created else None,
    }


# ---- 親プロセス -------------------------------------------------------------------

def run_in_subprocess(src: Path, spec: dict) -> list[dict]:
    env = {**os.environ, "PYTHONPATH": str(src.resolve())}
    proc = subprocess.run([sys.executable, __file__, "--worker", json.dumps(spec)],
                          capture_output=True, text=True, env=env, check=True)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def prepare_old_src(given: Path | None) -> Path:
    if given is not None:
        return given
    target = OUT_DIR / "old"
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
    parser.add_argument("--seeds", type=int, default=20, help="先頭から何個体使うか（動作確認用）")
    parser.add_argument("--skip-0005", action="store_true", help="0005 の再実行を省く（動作確認用）")
    parser.add_argument("--old-src", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return

    r4 = load_0004()
    seeds = list(r4.SEEDS[: args.seeds])
    srcs = {"OLD": prepare_old_src(args.old_src), "NEW": NEW_SRC}
    started = time.time()
    results: dict = {
        "meta": {"experiment": "0008", "git_commit": git_commit(), "old_commit": OLD_COMMIT,
                 "neuroarchitecture": str(r4.NEURO), "conditions": r4.CONDITIONS, "seeds": seeds,
                 "silent_pulses": r4.SILENT_PULSES, "queue_capacity": None},
        "OLD": [],
        "NEW": [],
    }
    for impl in ("OLD", "NEW"):
        for alpha, tau in r4.CONDITIONS:
            spec = {"alpha": alpha, "tau": tau, "seeds": seeds, "pulses": r4.SILENT_PULSES}
            results[impl] += run_in_subprocess(srcs[impl], spec)
            print(f"[{impl}] α={alpha} τ={tau} done ({time.time() - started:.0f}s)", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out / "results.json.gz", "wt", encoding="utf-8") as f:
        json.dump(results, f)
    print(f"saved {args.out / 'results.json.gz'} ({time.time() - started:.0f}s)", flush=True)

    if not args.skip_0005:
        env = {**os.environ, "PYTHONPATH": str(NEW_SRC.resolve())}
        subprocess.run([sys.executable, str(RUN_0005), "--out", str(args.out / "0005_new.json.gz")],
                       env=env, check=True)
        print(f"saved {args.out / '0005_new.json.gz'} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
