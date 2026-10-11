"""0012 の事後の解析用のデータを、範囲外の seed で作る（判定の seed 1〜20 は使わない）。

本番と同じ手順（run.py の run_once。設計図・protocol・道具は 0012 v0.3 のまま）で、seed 1001〜1020 を走らせる。
使い方（リポジトリ直下で）: python experiments/0012_passive_world/post/generate.py <出力フォルダ>
"""

import gzip
import importlib.util
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SEEDS = list(range(1001, 1021))


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


R = load("run_0012", "experiments/0012_passive_world/run.py")


def run_seed(seed: int) -> list[dict]:
    """プロセスをまたいで渡すための包み（run.py は importlib で読むので、その関数は直接 pickle できない）。"""
    return R.run_seed(seed)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    R.ALIGN.check(R.PROTOCOL)
    assert not any(R.PROTOCOL["seeds"]["first"] <= s <= R.PROTOCOL["seeds"]["last"] for s in SEEDS)
    with ProcessPoolExecutor() as pool:
        runs = [r for rs in pool.map(run_seed, SEEDS) for r in rs]
    data = {"meta": {"purpose": "0012 post analysis (out-of-range seeds)", "git_commit": R.git_commit(),
                     "seeds": SEEDS}, "runs": runs}
    with gzip.open(out / "post_runs.json.gz", "wt", encoding="utf-8") as f:
        json.dump(data, f)
    print(f"saved {out / 'post_runs.json.gz'} ({len(runs)} runs)")


if __name__ == "__main__":
    main()
