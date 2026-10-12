"""探索 0020 の実行（探索の設計 v0.3 に従う。判定を置かない。一度限り。README §7.1）。

1 個体（seed）ごとに world.explore_seed：ordered・shuffled を 12000 まで経験させ、12000 の終わりに ordered を 2 腕に分け
（control ＝ ordered の本体、intervention ＝ 4 本だけを shuffled の 12000 の値にした複製）、両腕を 24000 まで
1 Pulse ずつ並べて無入力で進める。生の記録だけを保存し、記録の量は analyze.py が計算する。

一度限りの実行の保護（guard.py）：
  1. seed に触れる前に、HEAD が 40 桁の commit で作業ツリーがそれと一致することを確かめる（探索では --measurement-commit と一致も）
  2. 出力先に排他的な開始の記録を作る。既に開始・終了の記録・結果があれば実行しない
  3. 同時に動かすプロセスは protocol の execution.max_workers（2）まで。CPU 数に合わせて増やさない
  4. 保存の前に、結果の seed の列が期待の列と完全に一致すること（欠落・重複・別の seed は failed）
  5. 終わりに HEAD・作業ツリーが開始時の commit のままかを確かめ直す
  6. 結果と終了の記録を原子的に保存する。失敗したら終了の記録に status ＝ failed を残す（seed は使用済み）

使い方（リポジトリ直下で）:
  python experiments/0020_weight_intervention_exploration/run.py --measurement-commit <40 桁>   # 探索（13001〜13100、出力は data/experiments/0020 に固定）
  python experiments/0020_weight_intervention_exploration/run.py --check 13199 --out <scratch>     # 道具の通しの確認（合成・確認専用の範囲）
"""

import argparse
import gzip
import importlib.util
import json
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path("experiments/0020_weight_intervention_exploration")
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
OUT_DIR = Path("data/experiments/0020")
MODES = ("exploration", "check")
MAX_WORKERS = PROTOCOL["execution"]["max_workers"]   # 実行前に固定（README §7.1）。CPU 数では決めない


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0020", REPO / HERE / "alignment.py")
W = load("world_0020", REPO / HERE / "world.py")
G = load("guard_0020", REPO / HERE / "guard.py")


def run_seed(seed: int) -> dict:
    return W.explore_seed(PROTOCOL, seed)


def _pool_map(fn: Callable[[int], dict], seeds: list[int]) -> Iterable[dict]:
    """seed ごとに fn を別のプロセスで呼ぶ。同時に動くプロセスは MAX_WORKERS まで（CPU 数に合わせて増やさない）。"""
    with ProcessPoolExecutor(max_workers=min(len(seeds), MAX_WORKERS)) as pool:
        yield from pool.map(fn, seeds)


def check_results(runs: list, seeds: list[int]) -> None:
    """保存の前の完全性：結果の seed の列が期待の列と、件数・順序・重複なしで完全に一致すること。"""
    got = [r.get("seed") if isinstance(r, dict) else None for r in runs]
    if len(got) != len(seeds):
        raise G.GuardError(f"結果の件数（{len(got)}）が seed の数（{len(seeds)}）と違う")
    if len(set(got)) != len(got):
        raise G.GuardError("結果に同じ seed が重複している")
    if got != seeds:
        raise G.GuardError("結果の seed の列が期待の列と違う（別の seed・順序の違い）")


def execute(mode: str, seeds: list[int], out: Path, repo: Path, expected_commit: str | None,
            runner: Callable[[int], dict] = run_seed,
            mapper: Callable[[Callable[[int], dict], list[int]], Iterable[dict]] = _pool_map) -> dict:
    """一度限りの実行の本体（README §7.1）。runner・mapper は契約テストで差し替えるためにある（本番は既定のまま）。
    返す値：終了の記録。失敗したら終了の記録に failed を残してから例外を投げ直す。"""
    if mode not in MODES:
        raise G.GuardError(f"未知の mode（{mode}）")
    if not seeds or len(set(seeds)) != len(seeds):
        raise G.GuardError("seed の列が空か、重複がある")
    commit = G.verify_clean_commit(repo, expected_commit)            # seed に触れる前
    protocol_sha = G.sha256_file(repo / PROTOCOL_PATH)
    start = {"experiment": "0020", "kind": "exploration", "mode": mode, "git_commit": commit, "seeds": seeds,
             "protocol_sha256": protocol_sha, "max_workers": MAX_WORKERS, "environment": G.environment()}
    G.begin(out, start)                                              # 排他的な開始の記録（seed に触れる前）
    started = time.time()
    try:
        runs = []
        for result in mapper(runner, seeds):                          # zip で黙って短くしない
            runs.append(result)
            seed = result.get("seed") if isinstance(result, dict) else None
            print(f"seed {seed} done ({len(runs)}/{len(seeds)}) / {time.time() - started:.0f}s", flush=True)
        check_results(runs, seeds)                                    # 保存の前に全件の一致を確かめる
        end_commit = G.verify_clean_commit(repo, commit)              # 終わりに確かめ直す
        if G.sha256_file(repo / PROTOCOL_PATH) != protocol_sha:
            raise G.GuardError("実行中に protocol.yaml が変わった")
        data = {"meta": {"experiment": "0020", "kind": "exploration", "mode": mode, "git_commit": commit,
                         "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
                "runs": runs}
        payload = gzip.compress(json.dumps(data).encode("utf-8"), mtime=0)
        G.atomic_write(out / G.RUNS, payload)
        record = {"experiment": "0020", "kind": "exploration", "status": "completed", "mode": mode,
                  "git_commit_start": commit, "git_commit_end": end_commit, "max_workers": MAX_WORKERS,
                  "seeds": seeds, "runs_sha256": G.sha256_bytes(payload), "seconds": time.time() - started}
        G.finish(out, record)
        print(f"saved {out / G.RUNS} ({len(runs)} individuals, {time.time() - started:.0f}s)")
        return record
    except BaseException as e:
        G.finish(out, {"experiment": "0020", "kind": "exploration", "status": "failed", "mode": mode,
                       "git_commit_start": commit, "seeds_touched": seeds, "max_workers": MAX_WORKERS,
                       "reason": repr(e), "seconds": time.time() - started})
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurement-commit", default=None, help="探索：実行する commit（HEAD と一致しなければ実行しない）")
    parser.add_argument("--check", type=int, nargs="*", default=None,
                        help="合成・確認専用の範囲の seed で道具の通しの確認だけをする（README §6）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    ALIGN.check(PROTOCOL)
    if args.check is None:
        if args.measurement_commit is None:
            raise SystemExit("探索では --measurement-commit <40 桁の commit> を指定する（README §7.1）")
        if args.out is not None:
            raise SystemExit("探索の出力先は data/experiments/0020 に固定（--out は使えない）")
        s = PROTOCOL["seeds"]
        mode, seeds, out = "exploration", list(range(s["first"], s["last"] + 1)), REPO / OUT_DIR
    else:
        syn = PROTOCOL["synthetic_seeds"]
        if not args.check or any(not syn["first"] <= s <= syn["last"] for s in args.check):
            raise SystemExit("--check の seed は合成・確認専用の範囲から選ぶ")
        if args.out is None:
            raise SystemExit("--check のときは --out に作業用のフォルダを指定する（探索のデータと混ぜない）")
        if args.out.resolve() == (REPO / OUT_DIR).resolve():
            raise SystemExit("--check の出力先に探索の出力先は使えない")
        mode, seeds, out = "check", list(args.check), args.out
    try:
        execute(mode, seeds, out, REPO, args.measurement_commit)
    except G.GuardError as e:
        raise SystemExit(f"実行しない：{e}") from e


if __name__ == "__main__":
    main()
