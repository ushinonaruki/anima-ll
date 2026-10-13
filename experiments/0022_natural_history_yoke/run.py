"""実験 0022 の実行（確定した事前登録 v0.2 に従う。一度限り。README §7.2）。

1 個体（seed）ごとに world.measure_seed：ordered・shuffled を 12000 まで経験させ、12000 の終わりに 8 つの腕
（O・S・Y_O_from_S・Y_S_from_O・twin_O・twin_S・Y_O_from_O・Y_S_from_S）に分け、W（12001〜24000）を入力なしで 1 Pulse ずつ
並べて進める。O・S は ordered・shuffled の本体そのもの。yoke の腕は可塑性の更新にだけ同じ Pulse の相手の自然な個体の発火を使う
（全 6 接続 yoke。痕跡は自分の基準の t0 の値から）。生の記録だけを保存し、観測の量は analyze.py が計算する。

実験の ID・本番の出力先・protocol のパス・seed の範囲は、この実験の protocol.yaml から読む（ほかの実験を参照しない）。

一度限りの実行の保護（guard.py。0020・0021 の契約を継承）：
  1. seed に触れる前に、HEAD が 40 桁の commit で作業ツリーがそれと一致することを確かめる（本番では --measurement-commit と一致も）
  2. 出力先に排他的な開始の記録を作る。既に開始・終了の記録・結果があれば実行しない
  3. 同時に動かすプロセスは protocol の execution.max_workers（2）まで。CPU 数に合わせて増やさない
  4. 保存の前に、結果の seed の列が期待の列と完全に一致すること（欠落・重複・別の seed は failed）
  5. 終わりに HEAD・作業ツリーが開始時の commit のままかを確かめ直す
  6. 結果と終了の記録を原子的に保存する。失敗したら終了の記録に status ＝ failed を残す（seed は使用済み）

使い方（リポジトリ直下で）:
  python experiments/0022_natural_history_yoke/run.py --measurement-commit <40 桁>   # 本番（出力先は protocol の execution.output_dir に固定）
  python experiments/0022_natural_history_yoke/run.py --check 15200 --out <scratch>     # 道具の通しの確認（合成・確認専用の範囲）
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
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path(PROTOCOL["execution"]["output_dir"])
DATA_ROOT = Path("data/experiments")
MODES = ("formal", "check")
MAX_WORKERS = PROTOCOL["execution"]["max_workers"]   # 実行前に固定（README §7.2）。CPU 数では決めない


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load(f"alignment_{EXPERIMENT}", REPO / HERE / "alignment.py")
W = load(f"world_{EXPERIMENT}", REPO / HERE / "world.py")
G = load(f"guard_{EXPERIMENT}", REPO / HERE / "guard.py")


def run_seed(seed: int) -> dict:
    return W.measure_seed(PROTOCOL, seed)


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


def allowed_seeds(mode: str) -> range:
    s = PROTOCOL["seeds"] if mode == "formal" else PROTOCOL["synthetic_seeds"]
    return range(s["first"], s["last"] + 1)


def execute(mode: str, seeds: list[int], out: Path, repo: Path, expected_commit: str | None,
            runner: Callable[[int], dict] = run_seed,
            mapper: Callable[[Callable[[int], dict], list[int]], Iterable[dict]] = _pool_map) -> dict:
    """一度限りの実行の本体（README §7.2）。runner・mapper は契約テストで差し替えるためにある（本番は既定のまま）。
    返す値：終了の記録。失敗したら終了の記録に failed を残してから例外を投げ直す。"""
    if mode not in MODES:
        raise G.GuardError(f"未知の mode（{mode}）")
    if not seeds or len(set(seeds)) != len(seeds):
        raise G.GuardError("seed の列が空か、重複がある")
    if any(s not in allowed_seeds(mode) for s in seeds):
        raise G.GuardError(f"{mode} の seed の範囲の外の seed がある")
    commit = G.verify_clean_commit(repo, expected_commit)            # seed に触れる前
    protocol_sha = G.sha256_file(repo / PROTOCOL_PATH)
    ek = {"experiment": EXPERIMENT, "kind": KIND}
    start = ek | {"mode": mode, "git_commit": commit, "seeds": seeds, "protocol_sha256": protocol_sha,
                  "max_workers": MAX_WORKERS, "environment": G.environment()}
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
        data = {"meta": ek | {"mode": mode, "git_commit": commit, "protocol": PROTOCOL,
                              "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
                "runs": runs}
        payload = gzip.compress(json.dumps(data).encode("utf-8"), mtime=0)
        G.atomic_write(out / G.RUNS, payload)
        record = ek | {"status": "completed", "mode": mode, "git_commit_start": commit, "git_commit_end": end_commit,
                       "max_workers": MAX_WORKERS, "seeds": seeds, "runs_sha256": G.sha256_bytes(payload),
                       "seconds": time.time() - started}
        G.finish(out, record)
        print(f"saved {out / G.RUNS} ({len(runs)} individuals, {time.time() - started:.0f}s)")
        return record
    except BaseException as e:
        G.finish(out, ek | {"status": "failed", "mode": mode, "git_commit_start": commit, "seeds_touched": seeds,
                            "max_workers": MAX_WORKERS, "reason": repr(e), "seconds": time.time() - started})
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurement-commit", default=None, help="本番：実行する commit（HEAD と一致しなければ実行しない）")
    parser.add_argument("--check", type=int, nargs="*", default=None,
                        help="合成・確認専用の範囲の seed で道具の通しの確認だけをする")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    ALIGN.check(PROTOCOL)
    if args.check is None:
        if args.measurement_commit is None:
            raise SystemExit("本番では --measurement-commit <40 桁の commit> を指定する（README §7.2）")
        if args.out is not None:
            raise SystemExit(f"本番の出力先は {OUT_DIR} に固定（--out は使えない）")
        mode, seeds, out = "formal", list(allowed_seeds("formal")), REPO / OUT_DIR
    else:
        if not args.check or any(s not in allowed_seeds("check") for s in args.check):
            raise SystemExit("--check の seed は合成・確認専用の範囲から選ぶ")
        if args.out is None:
            raise SystemExit("--check のときは --out に作業用のフォルダを指定する（本番のデータと混ぜない）")
        resolved = args.out.resolve()
        if resolved == (REPO / DATA_ROOT).resolve() or (REPO / DATA_ROOT).resolve() in resolved.parents:
            raise SystemExit(f"--check の出力先に {DATA_ROOT} の下（本番・他の実験のデータの場所）は使えない")
        mode, seeds, out = "check", list(args.check), args.out
    try:
        execute(mode, seeds, out, REPO, args.measurement_commit)
    except G.GuardError as e:
        raise SystemExit(f"実行しない：{e}") from e


if __name__ == "__main__":
    main()
