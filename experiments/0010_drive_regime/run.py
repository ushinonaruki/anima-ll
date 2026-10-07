"""実験 0010 の実行（事前登録の一部。測定の前にコミットする）。

条件・個体・手順の値は protocol.yaml から読む（このファイルに直接書かない）。
内在的駆動の値（protocol.yaml の intrinsic_drive_values）ごとに、設計図 minimal-v2 の駆動だけを差し替えて回す。

- K1：0004 のパート A と同じ手順（順応の条件 × seed、入力なし）。記録の取り出しは 0008 の run.py の extract
- K2：0005 と同じ手順。0005 の run.py の run_once を使い、設計図の作り方（neuro_raw）だけを
      「minimal-v2 を元に、駆動を差し替えたもの」に替える

使い方（リポジトリ直下で）:
  python experiments/0010_drive_regime/run.py
  python experiments/0010_drive_regime/run.py --seeds 1 --drives 0.08 --out <scratch>   # 動作確認だけ
Docker:
  docker compose run --rm --no-deps anima python experiments/0010_drive_regime/run.py
"""

import argparse
import asyncio
import copy
import gzip
import importlib.util
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
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

HERE = Path("experiments/0010_drive_regime")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0010")


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R5 = load("run_0005", "experiments/0005_response_threshold/run.py")
R8 = load("run_0008", "experiments/0008_baseline_new_runtime/run.py")


def seeds(limit: int | None = None) -> list[int]:
    s = list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))
    return s[:limit] if limit else s


def conditions() -> list[tuple[float, float]]:
    return [(float(a), t) for a, t in PROTOCOL["adaptation_conditions"]]


def base_raw() -> dict:
    return yaml.safe_load(Path(PROTOCOL["base_neuroarchitecture"]).read_text(encoding="utf-8"))


def with_drive_and_adaptation(raw: dict, drive: float, alpha: float, tau: float) -> dict:
    raw = copy.deepcopy(raw)
    dyn = raw["defaults"]["dynamics"]
    dyn["intrinsic_drive"] = drive
    dyn["adaptation_increment"] = alpha
    dyn["adaptation_tau"] = tau
    return raw


def environment_raw() -> dict:
    env = PROTOCOL["environment"]
    pool = {"capacity": env["workers"], "kernel": env["kernel"], "delay_seconds": env["delay_seconds"]}
    if env["queue_capacity"] is not None:
        pool["queue_capacity"] = env["queue_capacity"]
    return {
        "resources": {"llm_pool": pool},
        "receptors": {"receptor.console": {"kind": "scripted", "script": {}}},
        "effectors": {"effector.console": {"kind": "recording"}},
    }


def unit_rho(app) -> list[float]:
    """出生時のばらつきを入れたあとの、Unit ごとの ρ。"""
    out = []
    for u in app.units.all():
        d = u.export_state()["dynamics"]
        out.append(d["intrinsic_drive_per_second"] / ((1 - d["decay_per_second"]) * d["threshold"]))
    return out


def k1_once(drive: float, alpha: float, tau: float, seed: int) -> dict:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(with_drive_and_adaptation(base_raw(), drive, alpha, tau)),
        parse_environment(environment_raw()),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=1,
    )
    rho = unit_rho(app)
    asyncio.run(app.lifecycle.run(max_pulses=PROTOCOL["k1"]["silent_pulses"]))
    return {**R8.extract(log), "unit_rho": rho}


def run_drive(args: tuple[float, int | None, str]) -> str:
    drive, seed_limit, out_dir = args
    out = Path(out_dir)
    started = time.time()
    commit = git_commit()

    # 0005 の手順の環境が protocol と同じであることの確認（0005 の run.py は環境を直接書いている）
    pool = R5.environment_raw(False)["resources"]["llm_pool"]
    env = PROTOCOL["environment"]
    assert (pool["capacity"], pool["kernel"], pool["delay_seconds"]) == (
        env["workers"], env["kernel"], env["delay_seconds"]), "0005 の手順の環境が protocol と違う"

    k1 = {"meta": {"experiment": "0010-K1", "git_commit": commit, "intrinsic_drive": drive,
                   "base_neuroarchitecture": PROTOCOL["base_neuroarchitecture"],
                   "conditions": conditions(), "seeds": seeds(seed_limit),
                   "silent_pulses": PROTOCOL["k1"]["silent_pulses"]},
          "runs": []}
    for alpha, tau in conditions():
        for seed in seeds(seed_limit):
            k1["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, **k1_once(drive, alpha, tau, seed)})
    with gzip.open(out / f"k1_drive{drive:.4f}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(k1, f)

    # K2：0005 の run_once を、minimal-v2 ＋ 駆動の差し替えで回す
    R5.NEURO = Path(PROTOCOL["base_neuroarchitecture"])
    original = R5.neuro_raw

    def neuro_raw(alpha: float, tau: float, weight: float) -> dict:
        raw = original(alpha, tau, weight)
        raw["defaults"]["dynamics"]["intrinsic_drive"] = drive
        return raw

    R5.neuro_raw = neuro_raw
    k2 = {"meta": {"experiment": "0010-K2", "git_commit": commit, "intrinsic_drive": drive,
                   "neuroarchitecture": str(R5.NEURO), "conditions": R5.CONDITIONS,
                   "seeds": seeds(seed_limit),
                   "protocol": {"conditioning": R5.CONDITIONING, "probe": R5.PROBE, "pulses": R5.PULSES,
                                "probe_weights": R5.PROBE_WEIGHTS, "conditioning_weight": 1.0}},
          "runs": []}
    for alpha, tau in R5.CONDITIONS:
        for seed in seeds(seed_limit):
            for branch, conditioning in (("rested", False), ("adapted", True)):
                for w in R5.PROBE_WEIGHTS:
                    data = R5.run_once(alpha, tau, w, seed, conditioning)
                    k2["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, "branch": branch,
                                       "weight": w, **data})
    with gzip.open(out / f"k2_drive{drive:.4f}.json.gz", "wt", encoding="utf-8") as f:
        json.dump(k2, f)
    return f"drive={drive:.4f} done ({time.time() - started:.0f}s)"


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
    parser.add_argument("--seeds", type=int, default=None, help="先頭から何個体使うか（動作確認用）")
    parser.add_argument("--drives", type=float, nargs="*", default=None, help="一部の駆動だけ回す（動作確認用）")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    drives = args.drives or [float(d) for d in PROTOCOL["intrinsic_drive_values"]]
    started = time.time()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for message in pool.map(run_drive, [(d, args.seeds, str(args.out)) for d in drives]):
            print(f"{message} / total {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
