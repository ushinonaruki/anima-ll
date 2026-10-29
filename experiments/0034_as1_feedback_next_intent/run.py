"""実験 0034 の実行（確定した事前登録 v0.2 に従う。一度限り。README §9）。

0023〜0033 の実行の契約（seed を単位にした一度限りの実行、guard.py）をそのまま引き継ぐ（ほかの実験の run.py は読み込まない）。
0033 の run.py（PR #140）と同じ作りで、違うのは次だけ：
- 計算は measure.measure_seed（AS1 の本体と、区間 W のすべての出来事の系 N・補助の系。README §2・§6）
- 0034 の protocol.yaml には execution の節がないので、本番の出力先（data/experiments/0034）と並列数（2）はこのファイルの定数で持つ
  （判定の条件ではない。CPU 数では決めない）

本番は生の記録だけを seed ごとのファイルに保存する（smoke は下の盲検の記録）。判定の量・補助の量は計算しない（analyze.py）。

seed を単位にした一度限りの実行（guard.py）：
  1. 実行の前に、HEAD が 40 桁の commit で作業ツリーがそれと一致することを確かめる（本番は --measurement-commit と一致も）。
     同じ出力先で同時に動く実行は 1 つだけ（run.lock）
  2. 出力先に、失敗（failed）・中断（開始の記録だけ）・破損（broken）の seed が 1 つでもあれば、どの seed も始めない
     （実験は invalid か未完了。新しい seed で穴埋めしない）。範囲の外の seed、別の測定の commit・protocol の seed があっても始めない
  3. 各 seed の前に、その seed の開始の記録を排他的に作る。開始の記録がある seed は二度と始めない
  4. 計算は別のプロセス（同時に 2 まで）。生の記録は seed のフォルダに原子的に書く
  5. 各 seed の後に、結果の seed の一致、raw の SHA-256・バイト数、HEAD・作業ツリー・protocol が開始時のままかを確かめ、
     終了の記録（completed）を一度だけ書く。どれかが成り立たなければ終了の記録に failed と理由を残す（seed は使用済み）。
     1 つでも失敗したら、まだ始めていない seed は始めない
  6. 集計（判定の量の計算）は、20 個の seed すべてが completed になってから analyze.py で一度だけ行う

**smoke は盲検**（#150 のレビューの必須 1）：生の記録は保存せず、本番と同じ確認を実行の場で当てた ok・fail と、生の記録の SHA-256
だけを残す（blinded）。実行の時間・失敗の理由の文（Pulse の番号を含みうる）も残さず、表示もしない。smoke は必ず盲検、本番は必ず盲検でない。
seed ごとの実行の時間を戻せないように（#150 の再レビュー 5692062243）、盲検では、開始・終了の記録の時刻の欄に非公開の値（BLINDED_TIME）を
明示して入れ、seed を 1 つずつ順に実行し（終わる順を残さない）、seed ごとの進み具合を表示せず、実行の最後に出力先のすべてのファイル・
フォルダの時刻を揃える（conceal_times）。開始・終了の記録そのものと一度限りの実行の保護は、本番と同じ。
**O1**：seed に触れる前に、測定の commit で契約テストを走らせ、その結果を出力先の o1_contract_tests.json に一度だけ残す
（record_contract_tests。通らなければ実行しない）。
**結果の写し**：本番の出力先（data/experiments/0034）は、解析の後の結果の PR で experiments/0034_as1_feedback_next_intent/results/ に
バイトのまま写し、analyze.py --verify-copy で照合してから commit する（protocol の records.save の results/<seed>.json に当たるのは
results/seeds/<seed>/raw.json.gz。analyze.verify_results_copy の説明を見る）。

**④ 正式な実験の実行は、改めて承認を得てから行う（README の Status・§14）。** smoke（27101〜27106）も、この道具の PR の
マージの後に、改めて承認を得てから操作の確認としてだけ行う。

使い方（リポジトリ直下で）:
  python experiments/0034_as1_feedback_next_intent/run.py --measurement-commit <40 桁> [--seeds <本番の seed> ...]   # 本番
  python experiments/0034_as1_feedback_next_intent/run.py --smoke --out <作業用のフォルダ> [--seeds <smoke の seed> ...]   # smoke
"""

import argparse
import gzip
import importlib.util
import json
import os
import subprocess
import sys
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
OUT_DIR = Path("data/experiments/0034")
DATA_ROOT = Path("data/experiments")
MODES = ("formal", "smoke", "synthetic")        # synthetic は契約テストの関数呼び出しだけ（コマンドからは使えない）
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
MAX_WORKERS = 2                                 # 実行前に固定。CPU 数では決めない
# 盲検（smoke）の時刻の扱い（#150 の再レビュー 5692062243 の修正必須）：開始・終了の時刻の欄には、この非公開の値を明示して入れる。
# 盲検では 1 つずつ順に実行し（終わる順 ＝ 始める順 ＝ seed の順。どの seed が先に終わったかを残さない）、実行の最後に、出力先の
# すべてのファイル・フォルダの更新時刻を CONCEALED_MTIME に揃える（ファイルの時刻からも、seed ごとの時間を戻せないようにする）
BLINDED_TIME = "blinded"
CONCEALED_MTIME = 0


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load(f"alignment_{EXPERIMENT}", REPO / HERE / "alignment.py")
W = load(f"measure_{EXPERIMENT}", REPO / HERE / "measure.py")
G = load(f"guard_{EXPERIMENT}", REPO / HERE / "guard.py")
AN = load(f"analyze_{EXPERIMENT}_run", REPO / HERE / "analyze.py")
# O1 の証拠（README §7）：測定の commit で、この契約テストを実際に走らせた結果を出力先に一度だけ残す
CONTRACT_TESTS, O1_FILE = AN.CONTRACT_TESTS, AN.O1_FILE


def allowed_seeds(mode: str) -> range:
    s = PROTOCOL[SEED_RANGES[mode]]
    return range(s["first"], s["last"] + 1)


def measure(seed: int) -> dict:
    """本番・smoke の計算：protocol の Plan だけを使う（Plan を受け取らない）。"""
    return W.measure_seed(PROTOCOL, seed)


def blinded(raw: dict, mode: str, seed: int, check_plan=None) -> dict:
    """盲検の記録（smoke。#150 のレビューの必須 1）：生の記録はメモリの中だけに置き、本番と同じ解析の確認（analyze.check_seed）を
    その場で生の記録に当て、確認ごとの ok・fail と、生の記録の SHA-256（中身を戻せない整合の記録）だけを残す。
    発火・意図・感覚・τ・重み・出来事の数・理由の文（Pulse の番号を含みうる）は保存しない。"""
    as_saved = json.loads(json.dumps(raw))                 # 本番で保存して読み直したときと同じ形（整数の鍵は文字列になる）
    canonical = json.dumps(as_saved, separators=(",", ":"), sort_keys=True).encode("utf-8")
    checks = AN.check_seed(as_saved, mode, seed, check_plan)
    return {"meta": raw["meta"], "blind": {"checks": {k: ("fail" if v else "ok") for k, v in checks.items()},
                                           "raw_sha256": G.sha256_bytes(canonical)}}


def conceal_times(out: Path) -> None:
    """盲検の実行の最後に、出力先のすべてのファイル・フォルダのアクセス・更新の時刻を CONCEALED_MTIME に揃える。"""
    for p in sorted(out.rglob("*"), reverse=True) + [out]:
        os.utime(p, (CONCEALED_MTIME, CONCEALED_MTIME), follow_symlinks=False)


def compute_and_write(seed: int, raw_path: str, meta: dict, runner: Callable[[int], dict] = measure,
                      blind: bool = False, check_plan=None) -> dict:
    """（別のプロセスで）1 つの seed を計算し、生の記録（盲検なら盲検の記録）を原子的に書く。
    返す値：seed と、書いたファイルの SHA-256・バイト数。"""
    result = runner(seed)
    if not isinstance(result, dict) or result.get("seed") != seed:
        raise G.GuardError(f"seed {seed} の結果の seed が違う（{result.get('seed') if isinstance(result, dict) else type(result)}）")
    record = {"meta": meta, "run": result}
    if blind:
        record = blinded(record, meta["mode"], seed, check_plan)
    payload = gzip.compress(json.dumps(record, separators=(",", ":")).encode("utf-8"), mtime=0)
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
            executor_factory: Callable[[int], object] = lambda n: ProcessPoolExecutor(max_workers=n),
            blind: bool | None = None, check_plan=None) -> dict:
    """seed を単位にした一度限りの実行の本体。runner・executor_factory は契約テストで差し替えるためにある
    （本番・smoke の main は既定のまま）。返す値：{completed: [...], failed: [...], not_started: [...]}。
    1 つでも失敗したら、記録を残してから GuardError を投げる。"""
    if mode not in MODES:
        raise G.GuardError(f"未知の mode（{mode}）")
    blind = (mode == "smoke") if blind is None else blind
    if mode == "smoke" and not blind:
        raise G.GuardError("smoke は盲検の記録だけを残す（protocol の smoke_seeds：現象の数値を保存しない）")
    if mode == "formal" and blind:
        raise G.GuardError("本番は生の記録をすべて残す（README §8）")
    if mode != "synthetic" and check_plan is not None:
        raise G.GuardError("本番・smoke の確認は protocol の Plan だけを使う")
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

    workers = 1 if blind else MAX_WORKERS

    def stamp() -> str:
        return BLINDED_TIME if blind else G.now_iso()

    def why(e: BaseException) -> str:
        # 盲検では、例外の文（Pulse の番号などを含みうる）を残さず、種類の名前だけを残す
        return type(e).__name__ if blind else repr(e)

    def fail(seed: int, reason: str) -> None:
        d = G.seed_dir(out, seed)
        if not (d / G.FINISH).exists():
            raw = d / G.RAW                                             # 書けていれば開示のために SHA-256 を残す
            G.finish_seed(out, seed, ek | {"seed": seed, "status": "failed", "finished_at": stamp(),
                                           "raw_file_sha256": G.sha256_file(raw) if raw.exists() else None,
                                           "raw_file_bytes": raw.stat().st_size if raw.exists() else None,
                                           "reason": reason, "seconds": None if blind else time.time() - started.get(seed, time.time())})
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
        G.finish_seed(out, seed, ek | {"seed": seed, "status": "completed", "finished_at": stamp(),
                                       "raw_file_sha256": res["raw_file_sha256"], "raw_file_bytes": res["raw_file_bytes"],
                                       "measurement_commit_end": commit, "seconds": None if blind else time.time() - started[seed]})
        done["completed"].append(seed)

    try:
        with G.session_lock(out):
            preflight(out, mode, seeds, commit, protocol_sha)
            queue = list(seeds)
            inflight: dict = {}
            try:
                with executor_factory(min(len(seeds), workers)) as pool:
                    while queue or inflight:
                        while queue and first_failure is None and len(inflight) < workers:
                            s = queue.pop(0)
                            try:
                                G.verify_clean_commit(repo, commit)          # seed に触れる前
                                G.begin_seed(out, s, ek | {"seed": s, "measurement_commit": commit,
                                                           "protocol_sha256": protocol_sha, "started_at": stamp(),
                                                           "max_workers": workers, "environment": G.environment()})
                            except BaseException as e:
                                first_failure = (s, e)
                                if (G.seed_dir(out, s) / G.START).exists():   # 開始の記録が残ったなら、その seed は使用済み
                                    started[s] = time.time()
                                else:
                                    queue.insert(0, s)
                                break
                            started[s] = time.time()
                            meta = ek | {"seed": s, "measurement_commit": commit, "protocol_sha256": protocol_sha,
                                         "protocol": PROTOCOL, "manifest": W.manifest_raw(), "blind": blind}
                            inflight[pool.submit(compute_and_write, s, str(G.seed_dir(out, s) / G.RAW), meta, runner,
                                                 blind, check_plan)] = s
                        if not inflight:
                            break
                        finished, _ = wait(list(inflight), return_when=FIRST_COMPLETED)
                        for fut in finished:
                            s = inflight.pop(fut)
                            try:
                                complete(s, fut.result())
                                if not blind:                            # 盲検では seed ごとの進み具合も表示しない
                                    print(f"seed {s} completed ({len(done['completed'])}/{len(seeds)}) / "
                                          f"{time.time() - started[s]:.0f}s", flush=True)
                            except BaseException as e:
                                fail(s, why(e))
                                first_failure = first_failure or (s, e)
            except BaseException as e:                                     # 中断・プールの破損
                first_failure = first_failure or (None, e)
                raise
            finally:
                for s in started:                                           # 始めたのに終了の記録がない seed
                    if s not in done["completed"] and s not in done["failed"]:
                        fail(s, why(first_failure[1]) if first_failure else "終了の記録がないまま実行が終わった")
                done["not_started"] = [s for s in seeds if s not in started]
                done["completed"].sort()
                done["failed"].sort()
        if first_failure is not None:
            s, e = first_failure
            raise G.GuardError(f"失敗（seed {s}：{why(e)}）。失敗・中断した seed は再実行しない。まだ始めていない seed "
                               f"{done['not_started']} も、この出力先では始めない") from e
        return done
    finally:
        if blind and out.exists():                                     # 盲検：ファイルの時刻からも seed ごとの時間を戻せないようにする
            conceal_times(out)


def record_contract_tests(repo: Path, out: Path, commit: str, run=subprocess.run) -> dict:
    """O1 の証拠：測定の commit のきれいな作業ツリーで、契約テストを実際に走らせ、その結果を出力先に一度だけ書く。
    既にあれば、同じ commit で通った記録であることだけを確かめて使う（走らせ直さない）。通らなければ実行しない。"""
    path = out / O1_FILE
    if path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        if rec.get("measurement_commit") != commit or rec.get("exit_code") != 0:
            raise G.GuardError(f"{O1_FILE} が別の commit のものか、契約テストが通っていない")
        return rec
    G.verify_clean_commit(repo, commit)
    cmd = [sys.executable, "-m", "pytest", "-q", *CONTRACT_TESTS]
    proc = run(cmd, cwd=repo, capture_output=True, text=True)
    lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    rec = {"measurement_commit": commit, "command": ["python", *cmd[1:]], "exit_code": proc.returncode,
           "summary": lines[-1] if lines else "", "test_files_sha256": {f: G.sha256_file(repo / f) for f in CONTRACT_TESTS},
           "at": G.now_iso()}
    out.mkdir(parents=True, exist_ok=True)
    G.write_once(path, json.dumps(rec, ensure_ascii=False, indent=1).encode("utf-8"))
    if proc.returncode != 0:
        raise G.GuardError(f"測定の commit で契約テストが通らない（{rec['summary']}）。実行しない")
    return rec


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
        commit = G.verify_clean_commit(REPO, args.measurement_commit)
        record_contract_tests(REPO, out, commit)                       # O1：seed に触れる前に
        result = execute(mode, seeds, out, REPO, args.measurement_commit)
    except G.GuardError as e:
        raise SystemExit(f"実行しない・失敗：{e}") from e
    print(f"completed: {result['completed']}")


if __name__ == "__main__":
    main()
