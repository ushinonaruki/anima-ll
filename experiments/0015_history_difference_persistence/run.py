"""実験 0015 の実行（事前登録 v0.2 に従う。測定の前にコミットする）。

条件・個体・手順の値は protocol.yaml から読む。設計図は 0012 v0.3 のもの（0014 と同じ）。
1 個体（seed）ごとに、順序あり・順序を崩した の 2 条件：
  1. 出生時の Unit の状態を記録する
  2. 札が最初に違う Pulse d の直前（d − 1 の終わり）の Unit・接続の状態を記録する（分かれる前の一致の材料）
  3. 標本の時刻（0 から総 Pulse まで sample_every ごと。経験の終わり・総 Pulse を含む）ごとに接続の状態を記録する
  4. 本体の発火・感覚の出来事の記録をすべて保存する
経験の終わりの後は、Receptor の予定が空なので、外からの入力なしで進む。判定の量（D0・DT・P）は analyze.py が計算する。

使い方（リポジトリ直下で）:
  python experiments/0015_history_difference_persistence/run.py                         # 本番（seed 6001〜6020）
  python experiments/0015_history_difference_persistence/run.py --smoke --out <scratch>  # 動作確認（seed 7001〜7006）
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

HERE = Path("experiments/0015_history_difference_persistence")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0015")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0015", HERE / "alignment.py")
W = load("world_0015", HERE / "world.py")


def run_condition(seed: int, condition: str, diverge: int | None) -> dict:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, condition, seed, log)
    birth = W.unit_states(app)
    before = None
    samples = {}
    # 標本の時刻と、札が最初に違う Pulse の直前（d − 1）を、時刻の順に通る（d − 1 が最初の標本より後でも戻らない）
    stops = sorted(set(W.sample_times(PROTOCOL)) | ({diverge - 1} if diverge is not None else set()))
    for t in stops:
        W.advance_to(app, t)
        if diverge is not None and t == diverge - 1:
            before = W.snapshot(app)
        if t in W.sample_times(PROTOCOL):
            samples[str(t)] = app.connections.export_state()
    return {"birth": birth, "before_divergence": before, "samples": samples,
            "activity": log.activity(), "sensory": log.sensory()}


def run_seed(seed: int) -> dict:
    diverge = W.first_divergence(PROTOCOL, seed)
    return {"seed": seed, "first_divergence": diverge,
            "roles": {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)},
            "conditions": {c: run_condition(seed, c, diverge) for c in PROTOCOL["stimulus"]["conditions"]}}


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
    parser.add_argument("--smoke", action="store_true", help="範囲外の smoke.seeds だけで動作確認する（README §7）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.smoke and args.out is None:
        raise SystemExit("--smoke のときは --out に作業用のフォルダを指定する（本番のデータと混ぜない）")
    out = args.out or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    ALIGN.check(PROTOCOL)
    s = PROTOCOL["smoke"]["seeds"] if args.smoke else PROTOCOL["seeds"]
    seeds = list(range(s["first"], s["last"] + 1))
    started = time.time()
    with ProcessPoolExecutor(max_workers=min(len(seeds), os.cpu_count() or 1)) as pool:
        runs = []
        for seed, result in zip(seeds, pool.map(run_seed, seeds)):
            runs.append(result)
            print(f"seed {seed} done / {time.time() - started:.0f}s", flush=True)
    data = {"meta": {"experiment": "0015", "smoke": args.smoke, "git_commit": git_commit(), "protocol": PROTOCOL,
                     "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
            "runs": runs}
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} individuals, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
