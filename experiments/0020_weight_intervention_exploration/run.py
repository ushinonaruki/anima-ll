"""探索 0020 の実行（探索の設計 v0.1 に従う。判定を置かない。実行の前に固定する）。

1 個体（seed）ごとに world.explore_seed：ordered・shuffled を 12000 まで経験させ、12000 の終わりに ordered を 2 腕に分け
（control ＝ ordered の本体、intervention ＝ 4 本だけを shuffled の 12000 の値にした複製）、両腕を 24000 まで
1 Pulse ずつ並べて無入力で進める。生の記録だけを保存し、記録の量は analyze.py が計算する。

使い方（リポジトリ直下で）:
  python experiments/0020_weight_intervention_exploration/run.py                           # 探索（seed 13001〜13100）
  python experiments/0020_weight_intervention_exploration/run.py --check 13199 --out <scratch>   # 道具の通しの確認（合成・確認専用の範囲）
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

HERE = Path("experiments/0020_weight_intervention_exploration")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0020")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0020", HERE / "alignment.py")
W = load("world_0020", HERE / "world.py")


def run_seed(seed: int) -> dict:
    return W.explore_seed(PROTOCOL, seed)


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
    parser.add_argument("--check", type=int, nargs="*", default=None,
                        help="合成・確認専用の範囲の seed で道具の通しの確認だけをする（README §6）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    if args.check is not None and args.out is None:
        raise SystemExit("--check のときは --out に作業用のフォルダを指定する（探索のデータと混ぜない）")
    ALIGN.check(PROTOCOL)
    if args.check is not None:
        syn = PROTOCOL["synthetic_seeds"]
        if not args.check or any(not syn["first"] <= s <= syn["last"] for s in args.check):
            raise SystemExit("--check の seed は合成・確認専用の範囲から選ぶ")
        seeds = list(args.check)
    else:
        s = PROTOCOL["seeds"]
        seeds = list(range(s["first"], s["last"] + 1))
    out = args.out or OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    with ProcessPoolExecutor(max_workers=min(len(seeds), os.cpu_count() or 1)) as pool:
        runs = []
        for seed, result in zip(seeds, pool.map(run_seed, seeds)):
            runs.append(result)
            print(f"seed {seed} done / {time.time() - started:.0f}s", flush=True)
    data = {"meta": {"experiment": "0020", "kind": "exploration", "check": args.check is not None,
                     "git_commit": git_commit(), "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL),
                     "seeds": seeds},
            "runs": runs}
    with gzip.open(out / "runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'runs.json.gz'} ({len(runs)} individuals, {time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
