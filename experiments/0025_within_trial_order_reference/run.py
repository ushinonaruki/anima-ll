"""実験 0025 の実行（確定した事前登録 v0.1 に従う。一度限り。README §9、protocol の execution・execution.per_seed）。

0023・0024 の実行の契約（PR #104・#108）をそのまま引き継ぐ（ほかの実験の run.py は読み込まない）。脳は C0（protocol の brain.manifest）。
本体は O・M・W1〜W19（試行の中の並べ替え）。

seed ごとに world.measure_seed：同じ seed から 21 の本体（O・M・W1〜W19）を 12000 まで経験させ、各本体の 12001〜12300 の
各 t0 で A の複製を作って窓の終わりまで進め、本体を 12601 まで進める。確認のための複製（空の側・O の双子）も作る。
生の記録だけを seed ごとのファイルに保存する。観測の量（ℓ・L・外にあるか・h・補助の量）は計算しない（analyze.py）。

実験の ID・本番の出力先・protocol のパス・seed の範囲は、この実験の protocol.yaml から読む（ほかの実験を参照しない）。

seed を単位にした一度限りの実行（guard.py）：
  1. 実行の前に、HEAD が 40 桁の commit で作業ツリーがそれと一致することを確かめる（本番は --measurement-commit と一致も）。
     同じ出力先で同時に動く実行は 1 つだけ（run.lock）
  2. 出力先に、失敗（failed）・中断（開始の記録だけ）・破損（broken）の seed が 1 つでもあれば、どの seed も始めない
     （実験は invalid か未完了。新しい seed で穴埋めしない）。範囲の外の seed、別の測定の commit・protocol の seed があっても始めない
  3. 各 seed の前に、その seed の開始の記録を排他的に作る。開始の記録がある seed は二度と始めない
  4. 計算は別のプロセス（同時に protocol の execution.max_workers ＝ 2 まで。CPU 数に合わせて増やさない）。
     生の記録は seed のフォルダに原子的に書く
  5. 各 seed の後に、結果の seed の一致、raw の SHA-256・バイト数、HEAD・作業ツリー・protocol が開始時のままかを確かめ、
     終了の記録（completed）を一度だけ書く。どれかが成り立たなければ終了の記録に failed と理由を残す（seed は使用済み）。
     1 つでも失敗したら、まだ始めていない seed は始めない
  6. 集計（判定の量の計算）は、20 個の seed すべてが completed になってから analyze.py で一度だけ行う

使い方（リポジトリ直下で）:
  python experiments/0025_within_trial_order_reference/run.py --measurement-commit <40 桁> [--seeds 18001 18002 ...]   # 本番（出力先は固定）
  python experiments/0025_within_trial_order_reference/run.py --smoke --out <作業用のフォルダ> [--seeds 18101 ...]    # smoke（操作の確認だけ）
"""

import argparse
import gzip
import importlib.util
import json
import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path(PROTOCOL["execution"]["output_dir"])
DATA_ROOT = Path("data/experiments")
MODES = ("formal", "smoke", "synthetic")        # synthetic は契約テストの関数呼び出しだけ（コマンドからは使えない）
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
MAX_WORKERS = PROTOCOL["execution"]["max_workers"]   # 実行前に固定。CPU 数では決めない


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load(f"alignment_{EXPERIMENT}", REPO / HERE / "alignment.py")
W = load(f"world_{EXPERIMENT}", REPO / HERE / "world.py")
G = load(f"guard_{EXPERIMENT}", REPO / HERE / "guard.py")


def allowed_seeds(mode: str) -> range:
    s = PROTOCOL[SEED_RANGES[mode]]
    return range(s["first"], s["last"] + 1)


def measure(seed: int) -> dict:
    """本番・smoke の計算：protocol の Plan だけを使う（Plan を受け取らない）。"""
    return W.measure_seed(PROTOCOL, seed)


def compute_and_write(seed: int, raw_path: str, meta: dict, runner: Callable[[int], dict] = measure) -> dict:
    """（別のプロセスで）1 つの seed を計算し、生の記録を原子的に書く。返す値：seed と raw の SHA-256・バイト数。"""
    result = runner(seed)
    if not isinstance(result, dict) or result.get("seed") != seed:
        raise G.GuardError(f"seed {seed} の結果の seed が違う（{result.get('seed') if isinstance(result, dict) else type(result)}）")
    payload = gzip.compress(json.dumps({"meta": meta, "run": result}, separators=(",", ":")).encode("utf-8"), mtime=0)
    G.atomic_write(Path(raw_path), payload)
    return {"seed": seed, "raw_file_sha256": G.sha256_bytes(payload), "raw_file_bytes": len(payload)}


def preflight(out: Path, mode: str, seeds: list[int], commit: str, protocol_sha: str) -> None:
    """seed に触れる前の確認（このあと seed ごとに開始の記録を排他的に作る）。"""
    found = G.scan(out)
    problems = list(found["anomalies"])
    allowed = allowed_seeds(mode)
    for s, (status, why) in found["seeds"].items():
        if s not in allowed:
            problems.append(f"出力先に {mode} の範囲の外の seed {s} がある")
        if status in ("started", "failed", "broken"):
            problems.append(f"seed {s} が {status}（{'; '.join(why)}）。実験は invalid か未完了で、ほかの seed も始めない"
                            "（新しい seed で穴埋めしない。開示して新しい事前登録・新しい seed の範囲で行う）")
        if status == "completed":
            st = G.read_seed(out, s)["start"]
            if (st.get("measurement_commit"), st.get("protocol_sha256")) != (commit, protocol_sha):
                problems.append(f"seed {s} は別の測定の commit・protocol で実行されている（同じ出力先に混ぜない）")
            if (st.get("experiment"), st.get("kind"), st.get("mode")) != (EXPERIMENT, KIND, mode):
                problems.append(f"seed {s} の開始の記録の experiment・kind・mode が違う")
    for s in seeds:
        if found["seeds"].get(s, ("absent", []))[0] != "absent":
            problems.append(f"seed {s} は既に開始している（再実行しない）")
    if problems:
        raise G.GuardError("実行しない：\n- " + "\n- ".join(problems))


def execute(mode: str, seeds: list[int], out: Path, repo: Path, expected_commit: str | None,
            runner: Callable[[int], dict] = measure,
            executor_factory: Callable[[int], object] = lambda n: ProcessPoolExecutor(max_workers=n)) -> dict:
    """seed を単位にした一度限りの実行の本体。runner・executor_factory は契約テストで差し替えるためにある
    （本番・smoke の main は既定のまま）。返す値：{completed: [...], failed: [...], not_started: [...]}。
    1 つでも失敗したら、記録を残してから GuardError を投げる。"""
    if mode not in MODES:
        raise G.GuardError(f"未知の mode（{mode}）")
    if not seeds or len(set(seeds)) != len(seeds):
        raise G.GuardError("seed の列が空か、重複がある")
    if any(s not in allowed_seeds(mode) for s in seeds):
        raise G.GuardError(f"{mode} の seed の範囲の外の seed がある（失敗した seed を範囲の外の seed で穴埋めしない）")
    if mode == "formal" and expected_commit is None:
        raise G.GuardError("本番は --measurement-commit が要る")
    commit = G.verify_clean_commit(repo, expected_commit)               # seed に触れる前
    protocol_sha = G.sha256_file(repo / PROTOCOL_PATH)
    ek = {"experiment": EXPERIMENT, "kind": KIND, "mode": mode}
    done: dict[str, list[int]] = {"completed": [], "failed": [], "not_started": []}
    started: dict[int, float] = {}
    first_failure: tuple[int | None, BaseException] | None = None

    def fail(seed: int, reason: str) -> None:
        d = G.seed_dir(out, seed)
        if not (d / G.FINISH).exists():
            raw = d / G.RAW                                             # 書けていれば開示のために SHA-256 を残す
            G.finish_seed(out, seed, ek | {"seed": seed, "status": "failed", "finished_at": G.now_iso(),
                                           "raw_file_sha256": G.sha256_file(raw) if raw.exists() else None,
                                           "raw_file_bytes": raw.stat().st_size if raw.exists() else None,
                                           "reason": reason, "seconds": time.time() - started.get(seed, time.time())})
        done["failed"].append(seed)

    def complete(seed: int, res: dict) -> None:
        raw = G.seed_dir(out, seed) / G.RAW
        if not isinstance(res, dict) or res.get("seed") != seed:
            raise G.GuardError(f"seed {seed} の結果の seed が違う")
        if not raw.exists() or G.sha256_file(raw) != res["raw_file_sha256"] or raw.stat().st_size != res["raw_file_bytes"]:
            raise G.GuardError(f"seed {seed} の raw の SHA-256・バイト数が、書いた値と違う")
        G.verify_clean_commit(repo, commit)                            # 終わりに確かめ直す
        if G.sha256_file(repo / PROTOCOL_PATH) != protocol_sha:
            raise G.GuardError("実行中に protocol.yaml が変わった")
        G.finish_seed(out, seed, ek | {"seed": seed, "status": "completed", "finished_at": G.now_iso(),
                                       "raw_file_sha256": res["raw_file_sha256"], "raw_file_bytes": res["raw_file_bytes"],
                                       "measurement_commit_end": commit, "seconds": time.time() - started[seed]})
        done["completed"].append(seed)

    with G.session_lock(out):
        preflight(out, mode, seeds, commit, protocol_sha)
        queue = list(seeds)
        inflight: dict = {}
        try:
            with executor_factory(min(len(seeds), MAX_WORKERS)) as pool:
                while queue or inflight:
                    while queue and first_failure is None and len(inflight) < MAX_WORKERS:
                        s = queue.pop(0)
                        try:
                            G.verify_clean_commit(repo, commit)          # seed に触れる前
                            G.begin_seed(out, s, ek | {"seed": s, "measurement_commit": commit,
                                                       "protocol_sha256": protocol_sha, "started_at": G.now_iso(),
                                                       "max_workers": MAX_WORKERS, "environment": G.environment()})
                        except BaseException as e:
                            first_failure = (s, e)
                            if (G.seed_dir(out, s) / G.START).exists():   # 開始の記録が残ったなら、その seed は使用済み
                                started[s] = time.time()
                            else:
                                queue.insert(0, s)
                            break
                        started[s] = time.time()
                        meta = ek | {"seed": s, "measurement_commit": commit, "protocol_sha256": protocol_sha,
                                     "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)}
                        inflight[pool.submit(compute_and_write, s, str(G.seed_dir(out, s) / G.RAW), meta, runner)] = s
                    if not inflight:
                        break
                    finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
                    for fut in finished:
                        s = inflight.pop(fut)
                        try:
                            complete(s, fut.result())
                            print(f"seed {s} completed ({len(done['completed'])}/{len(seeds)}) / "
                                  f"{time.time() - started[s]:.0f}s", flush=True)
                        except BaseException as e:
                            fail(s, repr(e))
                            first_failure = first_failure or (s, e)
        except BaseException as e:                                     # 中断・プールの破損
            first_failure = first_failure or (None, e)
            raise
        finally:
            for s in started:                                           # 始めたのに終了の記録がない seed
                if s not in done["completed"] and s not in done["failed"]:
                    fail(s, repr(first_failure[1]) if first_failure else "終了の記録がないまま実行が終わった")
            done["not_started"] = [s for s in seeds if s not in started]
            done["completed"].sort()
            done["failed"].sort()
    if first_failure is not None:
        s, e = first_failure
        raise G.GuardError(f"失敗（seed {s}：{e!r}）。失敗・中断した seed は再実行しない。まだ始めていない seed "
                           f"{done['not_started']} も、この出力先では始めない") from e
    return done


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measurement-commit", default=None, help="本番：実行する commit（HEAD と一致しなければ実行しない）")
    parser.add_argument("--smoke", action="store_true", help="smoke の範囲の seed で操作の確認のための実行だけをする")
    parser.add_argument("--seeds", type=int, nargs="+", default=None, help="この呼び出しで実行する seed（範囲の中だけ）")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    ALIGN.check(PROTOCOL)
    if not args.smoke:
        if args.measurement_commit is None:
            raise SystemExit("本番では --measurement-commit <40 桁の commit> を指定する")
        if args.out is not None:
            raise SystemExit(f"本番の出力先は {OUT_DIR} に固定（--out は使えない）")
        mode, out = "formal", REPO / OUT_DIR
    else:
        if args.out is None:
            raise SystemExit("--smoke のときは --out に作業用のフォルダを指定する（本番のデータと混ぜない）")
        resolved = args.out.resolve()
        if resolved == (REPO / DATA_ROOT).resolve() or (REPO / DATA_ROOT).resolve() in resolved.parents:
            raise SystemExit(f"smoke の出力先に {DATA_ROOT} の下（本番・他の実験のデータの場所）は使えない")
        mode, out = "smoke", args.out
    seeds = args.seeds if args.seeds is not None else list(allowed_seeds(mode))
    try:
        result = execute(mode, seeds, out, REPO, args.measurement_commit)
    except G.GuardError as e:
        raise SystemExit(f"実行しない・失敗：{e}") from e
    print(f"completed: {result['completed']}")


if __name__ == "__main__":
    main()
