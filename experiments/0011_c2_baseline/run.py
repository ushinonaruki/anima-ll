"""実験 0011 の実行（事前登録の一部。測定の前にコミットする）。

条件・個体・手順の値は protocol.yaml から読む（このファイルに直接書かない）。設計図は minimal-v3。

- B1：Kernel の振る舞いだけを変えた 6 条件（protocol の b1.kernel_conditions）× seed × 2 通りの入力
      （入力なし・0004 のパート B と同じ入力）。発火の記録は、ログの activity の出来事をすべて保存する
      - 入力なし：b1.silent_pulses
      - パート B：0004 のパート B の adapted の枝と同じ台本（conditioning 600〜620 に 5 回 ＋ probe 650）、
                  700 Pulse、receptor.console → u0 の重みは設計図のまま（1.0）
- B2・B4：0005 と同じ手順。0005 の run.py の run_once を、設計図だけ minimal-v3 に替えて使う
- B3：0004 のパート A と同じ手順（順応の条件 × seed、入力なし）。記録の取り出しは 0008 の run.py の extract

使い方（リポジトリ直下で）:
  python experiments/0011_c2_baseline/run.py
  python experiments/0011_c2_baseline/run.py --seeds 1 --out <scratch>   # 動作確認だけ（結果は使わない）
Docker:
  docker compose run --rm --no-deps anima python experiments/0011_c2_baseline/run.py
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

HERE = Path("experiments/0011_c2_baseline")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0011")


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0011", str(HERE / "alignment.py"))
R4 = load("run_0004", "experiments/0004_adaptation/run.py")
R5 = load("run_0005", "experiments/0005_response_threshold/run.py")
R8 = load("run_0008", "experiments/0008_baseline_new_runtime/run.py")


def seeds(limit: int | None = None) -> list[int]:
    s = list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))
    return s[:limit] if limit else s


def conditions() -> list[tuple[float, float]]:
    return [(float(a), t) for a, t in PROTOCOL["adaptation_conditions"]]


def base_raw() -> dict:
    return yaml.safe_load(Path(PROTOCOL["base_neuroarchitecture"]).read_text(encoding="utf-8"))


def with_adaptation(raw: dict, alpha: float, tau: float) -> dict:
    raw = copy.deepcopy(raw)
    dyn = raw["defaults"]["dynamics"]
    dyn["adaptation_increment"] = alpha
    dyn["adaptation_tau"] = tau
    return raw


def pool_raw(kernel: dict | None = None) -> dict:
    env = PROTOCOL["environment"]
    pool = {"capacity": env["workers"], "kernel": env["kernel"], "delay_seconds": env["delay_seconds"]}
    if kernel is not None:
        pool.update({"delay_seconds": kernel["delay_seconds"],
                     "delay_jitter_seconds": kernel["delay_jitter_seconds"],
                     "result": kernel["result"]})
    if env["queue_capacity"] is not None:
        pool["queue_capacity"] = env["queue_capacity"]
    return pool


def environment_raw(script: dict, kernel: dict | None = None) -> dict:
    return {
        "resources": {"llm_pool": pool_raw(kernel)},
        "receptors": {"receptor.console": {"kind": "scripted", "script": script}},
        "effectors": {"effector.console": {"kind": "recording"}},
    }


def build(neuro: dict, env: dict, seed: int, log: InMemoryEventLog):
    return build_application(
        parse_neuroarchitecture(neuro),
        parse_environment(env),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0),
        event_log=log,
        effector_overrides={"effector.console": RecordingEffector("effector.console")},
        state_sample_interval=1,
    )


# ---- B1 -------------------------------------------------------------------------

def part_b_script() -> dict[int, str]:
    """0004 のパート B の adapted の枝と同じ台本。"""
    return {**{p: R4.INPUT_TEXT for p in R4.CONDITIONING}, R4.PROBE: R4.INPUT_TEXT}


def b1_once(kernel: dict, inputs: str, seed: int) -> dict:
    alpha, tau = PROTOCOL["b1"]["adaptation_condition"]
    if inputs == "silent":
        script, pulses = {}, PROTOCOL["b1"]["silent_pulses"]
    elif inputs == "part_b":
        script, pulses = part_b_script(), R4.PROBE_PULSES
    else:
        raise ValueError(inputs)
    log = InMemoryEventLog()
    app = build(with_adaptation(base_raw(), float(alpha), tau), environment_raw(script, kernel), seed, log)
    asyncio.run(app.lifecycle.run(max_pulses=pulses))
    activity = [[e.pulse, e.data["unit_id"]] for e in log.events if e.type == "activity"]
    # 操作の確認用：Kernel が実際に返した結果の種類ごとの件数
    outcomes = {"ok_nonempty": 0, "ok_empty": 0, "error": 0}
    for e in log.events:
        if e.type == "intent_completed":
            outcomes["ok_empty" if e.data["output"] in (None, "") else "ok_nonempty"] += 1
        elif e.type == "intent_kernel_error":
            outcomes["error"] += 1
    return {"activity": activity, "pulses": pulses, "kernel_outcomes": outcomes,
            "effects": sum(e.type == "effect" for e in log.events)}


def run_b1(args: tuple[int | None, str]) -> str:
    seed_limit, out_dir = args
    started = time.time()
    data = {"meta": {"experiment": "0011-B1", "git_commit": git_commit(),
                     "base_neuroarchitecture": PROTOCOL["base_neuroarchitecture"],
                     "b1": PROTOCOL["b1"], "seeds": seeds(seed_limit)},
            "runs": []}
    for kernel in PROTOCOL["b1"]["kernel_conditions"]:
        for inputs in PROTOCOL["b1"]["inputs"]:
            for seed in seeds(seed_limit):
                data["runs"].append({"kernel": kernel["id"], "inputs": inputs, "seed": seed,
                                     **b1_once(kernel, inputs, seed)})
    with gzip.open(Path(out_dir) / "b1.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return f"B1 done ({time.time() - started:.0f}s)"


# ---- B3 -------------------------------------------------------------------------

def unit_rho(app) -> list[float]:
    out = []
    for u in app.units.all():
        d = u.export_state()["dynamics"]
        out.append(d["intrinsic_drive_per_second"] / ((1 - d["decay_per_second"]) * d["threshold"]))
    return out


def b3_once(alpha: float, tau: float, seed: int) -> dict:
    log = InMemoryEventLog()
    app = build(with_adaptation(base_raw(), alpha, tau), environment_raw({}), seed, log)
    rho = unit_rho(app)
    asyncio.run(app.lifecycle.run(max_pulses=PROTOCOL["b3"]["silent_pulses"]))
    return {**R8.extract(log), "unit_rho": rho}


def run_b3(args: tuple[int | None, str]) -> str:
    seed_limit, out_dir = args
    started = time.time()
    data = {"meta": {"experiment": "0011-B3", "git_commit": git_commit(),
                     "base_neuroarchitecture": PROTOCOL["base_neuroarchitecture"],
                     "conditions": conditions(), "seeds": seeds(seed_limit),
                     "silent_pulses": PROTOCOL["b3"]["silent_pulses"]},
            "runs": []}
    for alpha, tau in conditions():
        for seed in seeds(seed_limit):
            data["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, **b3_once(alpha, tau, seed)})
    with gzip.open(Path(out_dir) / "b3.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return f"B3 done ({time.time() - started:.0f}s)"


# ---- B2・B4（0005 の手順） ---------------------------------------------------------

def run_b2(args: tuple[int | None, str]) -> str:
    seed_limit, out_dir = args
    started = time.time()
    # 0005 の手順の環境が protocol と同じであることの確認（0005 の run.py は環境を直接書いている）
    pool = R5.environment_raw(False)["resources"]["llm_pool"]
    env = PROTOCOL["environment"]
    assert (pool["capacity"], pool["kernel"], pool["delay_seconds"]) == (
        env["workers"], env["kernel"], env["delay_seconds"]), "0005 の手順の環境が protocol と違う"
    R5.NEURO = Path(PROTOCOL["base_neuroarchitecture"])
    data = {"meta": {"experiment": "0011-B2B4", "git_commit": git_commit(),
                     "neuroarchitecture": str(R5.NEURO), "conditions": R5.CONDITIONS,
                     "seeds": seeds(seed_limit),
                     "protocol": {"conditioning": R5.CONDITIONING, "probe": R5.PROBE, "pulses": R5.PULSES,
                                  "probe_weights": R5.PROBE_WEIGHTS, "conditioning_weight": 1.0}},
            "runs": []}
    for alpha, tau in R5.CONDITIONS:
        for seed in seeds(seed_limit):
            for branch, conditioning in (("rested", False), ("adapted", True)):
                for w in R5.PROBE_WEIGHTS:
                    run = R5.run_once(alpha, tau, w, seed, conditioning)
                    data["runs"].append({"alpha": alpha, "tau": tau, "seed": seed, "branch": branch,
                                         "weight": w, **run})
    with gzip.open(Path(out_dir) / "b2b4.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return f"B2/B4 done ({time.time() - started:.0f}s)"


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
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ALIGN.check(PROTOCOL)   # protocol と再利用する旧の実装がずれていたら止める
    started = time.time()
    jobs = [(run_b1, (args.seeds, str(args.out))), (run_b2, (args.seeds, str(args.out))),
            (run_b3, (args.seeds, str(args.out)))]
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [pool.submit(fn, a) for fn, a in jobs]
        for f in futures:
            print(f"{f.result()} / total {time.time() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
