"""実験 0012 の実行（事前登録の一部。測定の前にコミットする）。

条件・個体・手順の値は protocol.yaml から読む（このファイルに直接書かない）。設計図は neuroarchitecture.yaml、
人工世界と複製・試しの道具は world.py。

1 個体・1 条件（seed × ordered / shuffled / silent）ごとに：
  1. 個体を作り、本体を 1 Pulse ずつ途切れなく進める（区切って進めても同じになることは契約テストで確認）
  2. 経験の前の試し（pre_probes）：t0 − 1 まで進めた本体を複製し、複製にだけ t0 に A を与えて clone_pulses 進め、
     発火を記録して捨てる。試しの直前の重みも記録する
  3. Pulse 1799（経験の開始の直前）の接続の状態（重み・痕跡）を記録する
  4. 複製の操作の確認（各個体・各条件で 1 回）：Pulse 1799 の本体を複製し、試しを与えずに clone_pulses 進める。
     本体も同じ Pulse まで進め、発火の記録・接続の状態・Unit の状態が完全に一致するかを記録する
  5. 経験（条件ごとの刺激。Receptor の予定は個体を作るときに入れてある）
  6. 経験の後の試し（post_probes）。最初の試しの直前（Pulse 13799 の終わり）の重みを
     「経験の後の重み」として記録する（M の W はこれを使う。README §5.2 の「経験の後」をこの時点と読む）
  7. 総 Pulse まで進め、最後の重みを記録する

本体の発火の記録（activity の出来事）・感覚の出来事・刺激の列もすべて保存する（analyze.py が操作の確認に使う）。

使い方（リポジトリ直下で）:
  python experiments/0012_passive_world/run.py                       # 本番（seed 1〜20）
  python experiments/0012_passive_world/run.py --smoke --out <scratch>  # 動作確認だけ（範囲外の seed 1001。結果は使わない）
Docker:
  docker compose run --rm --no-deps anima python experiments/0012_passive_world/run.py
"""

import argparse
import gzip
import importlib.util
import json
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

HERE = Path("experiments/0012_passive_world")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0012")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0012", HERE / "alignment.py")
W = load("world_0012", HERE / "world.py")


def formal_seeds() -> list[int]:
    return list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))


def full_state(app) -> dict:
    return {
        "units": {u.unit_id: u.export_state() for u in app.units.all()},
        "connections": app.connections.export_state(),
        "drives": [[d.source_id, d.target_id, d.weight, d.created_pulse]
                   for d in app.pulse_runtime.brain_state.drives],
    }


def run_once(seed: int, condition: str) -> dict:
    tl, pr = PROTOCOL["timeline"], PROTOCOL["probe"]
    roles = W.role_receptors(PROTOCOL, seed)
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, condition, seed, log)
    probes = []

    def do_probes(phase: str) -> None:
        for t0 in W.probe_times(PROTOCOL, phase):
            W.advance_to(app, t0 - 1)
            weights = W.weights_of(app)
            fires = W.probe(PROTOCOL, app, log, roles["A"], t0)
            probes.append({"phase": phase, "t0": t0, "weights": weights, "fires": fires})

    initial_weights = W.weights_of(app)
    do_probes("pre")

    split = PROTOCOL["judgment"]["manipulation"]["identical_before_pulse"]
    W.advance_to(app, split - 1)
    connections_before = app.connections.export_state()

    # 複製の操作の確認：試しを与えない複製が本体と完全に一致するか
    copied, clone_log = W.clone(app, log)
    end = split - 1 + pr["clone_pulses"]
    W.advance_to(copied, end)
    W.advance_to(app, end)
    main_part = [a for a in log.activity() if split <= a[0] <= end]
    clone_identity = {
        "from_pulse": split - 1, "to_pulse": end,
        "identical": main_part == clone_log.activity() and full_state(copied) == full_state(app),
    }
    del copied, clone_log

    post_first = W.probe_times(PROTOCOL, "post")[0]
    W.advance_to(app, post_first - 1)
    weights_after = W.weights_of(app)
    do_probes("post")
    W.advance_to(app, tl["total_pulses"])

    return {
        "seed": seed, "condition": condition,
        "roles": roles, "role_units": W.role_units(PROTOCOL, seed),
        "role_order_index": (seed - 1) % 6,
        "stimuli": [[t, label] for t, label in W.stimuli(PROTOCOL, condition, seed)],
        "activity": log.activity(),
        "sensory": log.sensory(),
        "probes": probes,
        "weights_initial": initial_weights,
        "connections_before_split": connections_before,
        "weights_after_experience": weights_after,
        "weights_after_experience_pulse": post_first - 1,
        "weights_end": W.weights_of(app),
        "clone_identity": clone_identity,
        "pulses": app.lifecycle.pulse,
    }


def run_seed(seed: int) -> list[dict]:
    return [run_once(seed, c) for c in PROTOCOL["stimulus"]["conditions"]]


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
    parser.add_argument("--smoke", action="store_true",
                        help="範囲外の smoke_seed だけで動作確認する（判定の seed を先に見ない）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.smoke and args.out is None:
        raise SystemExit("--smoke のときは --out に作業用のフォルダを指定する（本番のデータと混ぜない）")
    out = args.out or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    ALIGN.check(PROTOCOL)   # protocol と設計図・道具がずれていたら止める
    seeds = [PROTOCOL["smoke_seed"]] if args.smoke else formal_seeds()
    started = time.time()
    runs: list[dict] = []
    with ProcessPoolExecutor(max_workers=min(len(seeds), os.cpu_count() or 1)) as pool:
        for seed, result in zip(seeds, pool.map(run_seed, seeds)):
            runs += result
            print(f"seed {seed} done / {time.time() - started:.0f}s", flush=True)
    data = {
        "meta": {"experiment": "0012", "smoke": args.smoke, "git_commit": git_commit(),
                 "protocol": PROTOCOL, "neuroarchitecture": W.manifest_raw(), "seeds": seeds},
        "runs": runs,
    }
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} runs, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
