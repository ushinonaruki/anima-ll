"""実験 0038：AS2b の前方の関門を走らせるコード（契約 §7。②b で一度だけ使う）。

- 読むのは `gate_declaration.json` だけ。値をこのコードに書き込まない（契約 §7.2 の固定の方法）
- 宣言の SHA-256 が `DECLARATION_SHA256` と違えば止まる。`--execute` がなければ走らない（②a では走らせない）
- **一度だけ**（宣言の one_time_execution）：最初の seed の前に、宣言のハッシュに結び付いた試行の札
  `attempts/claim-<sha256>.json` を排他に作る（O_CREAT | O_EXCL）。札があれば、--out が何であっても走らない。
  途中で失敗しても札は残り、失敗の記録を残す。このコードに札を消す口はない
- **無効は合格にしない**（宣言の validity）：監査（CT-E10）・窓の到達・持ち越し・行の数のどれかが合わなければ、試行は
  無効で、合否を出さない。有効な試行で条件を満たさないのは、正当な陰性の結果で、無効とは区別する
- 合否（宣言の evaluation）：同じ本体で「決まった窓が q 以上」かつ「A1 と A2 の両方が出た」を満たす本体を数え、
  同じ seed の二つの本体（c ＝ A1・A2）がどちらも満たす個体を数える。40 個体の過半で成立
- 出すのは、本体ごとの実行可能性の量（窓・決まった窓・引き分け・発火なし・A1 が出たか・A2 が出たか）と、本体・個体の
  条件の成否だけ。A1・A2 の別々の数、A1 の割合、時間の変化、c の違う本体の差は計算しない（宣言の forbidden_outputs）
- 検査用の記録として、本体ごとに層 A・層 B の記録と、CT-E10 の突合の結果を、本体が終わるたびに保存する（関門の報告には
  集計しない）
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import sys
import traceback
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DECLARATION = HERE / "gate_declaration.json"
DECLARATION_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
ATTEMPTS_DIR = HERE / "attempts"
REPORT_KEYS = ("windows", "decided", "tie", "none", "A1_occurred", "A2_occurred")


def _load_as2b():
    spec = importlib.util.spec_from_file_location("as2b_for_gate", ROOT / "experiments" / "as2b_choice" / "as2b.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeclarationMismatch(RuntimeError):
    """宣言のハッシュが、②a で固定したものと違う。"""


class AttemptRefused(RuntimeError):
    """この宣言の試行の札がもうある（一度だけ）。"""


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _write_exclusive(path: Path, data: dict) -> None:
    """排他に作って書く（あれば FileExistsError）。上書きしない。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
        f.flush()
        os.fsync(f.fileno())


def claim_attempt(attempts_dir: Path, digest: str, out_dir: Path) -> Path:
    """最初の seed の前に、宣言のハッシュに結び付いた試行の札を排他に作る。あれば AttemptRefused。"""
    path = attempts_dir / f"claim-{digest}.json"
    try:
        _write_exclusive(path, {"declaration_sha256": digest, "status": "started", "started_at": _now(),
                                "out_dir": str(out_dir), "pid": os.getpid()})
    except FileExistsError as exc:
        raise AttemptRefused(f"この宣言の試行の札 {path} がもうある。関門は一度だけ走らせる（--out を変えても走らない）") from exc
    return path


def record_attempt(attempts_dir: Path, digest: str, status: str, detail: dict) -> Path:
    path = attempts_dir / f"attempt-{digest}.{status}.json"
    _write_exclusive(path, {"declaration_sha256": digest, "status": status, "recorded_at": _now(), **detail})
    return path


def load_declaration(path: Path = DECLARATION, expected_sha256: str | None = DECLARATION_SHA256) -> tuple[dict, str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise DeclarationMismatch(f"宣言のハッシュ {digest} が、固定した {expected_sha256} と違う")
    return json.loads(raw.decode("utf-8")), digest


def schedule_of(decl: dict, as2b):
    s = decl["schedule"]
    cp = s["cue_pulses"]
    return as2b.TrialSchedule.periodic(first=cp["first"], spacing=cp["spacing"], count=cp["count"],
                                       offset=s["window_offset_o"], length=s["window_length_W"])


def _check_supported(decl: dict) -> None:
    """宣言の中で、この道具が実現する形だけを受ける（それ以外は止める。読み替えない）。"""
    w, b = decl["world"], decl["bodies"]
    problems = []
    if decl["exit"]["tie_rule"] != "close_window_without_intent":
        problems.append("tie_rule")
    if w["consequence_receptor"] != "cue_receptor" or w["multiplicity"] != "per_reservation" or w["lc3"] is not None:
        problems.append("world")
    if w["rule_c_assignment"] != "both_values_as_separate_bodies":
        problems.append("rule_c_assignment")
    if not {"q", "body_feasible", "individual_feasible", "pass"} <= set(decl["evaluation"]) or "validity" not in decl:
        problems.append("evaluation")
    if (b["plasticity"], b["outlet"], b["respond"], b["interventions"]) != ("on", True, True, "none"):
        problems.append("bodies")
    if problems:
        raise ValueError(f"この道具が実現しない宣言の欄: {problems}")


def run_body(as2b, decl: dict, seed: int, rule_c: str) -> tuple[dict, dict]:
    """一つの本体を走らせ、(報告の行, 検査用の記録) を返す。報告の行には REPORT_KEYS だけを入れる。"""
    schedule = schedule_of(decl, as2b)
    system = as2b.build(seed, schedule=schedule, delay=decl["world"]["delay_L"], rule_c=rule_c, respond=True)
    as2b.advance_to(system.app, decl["bodies"]["pulses"])
    records = system.decider.records
    outcomes = [r["outcome"] for r in records]
    decided = sum(1 for o in outcomes if o in as2b.ACTION_IDS)
    row = {"windows": len(schedule.windows), "decided": decided, "tie": outcomes.count(as2b.TIE),
           "none": outcomes.count(as2b.NONE), "A1_occurred": "A1" in outcomes, "A2_occurred": "A2" in outcomes}
    audit_record = {"seed": seed, "rule_c": rule_c, "layer_a": records, "layer_b": system.world.export_state()["intents"],
                    "audit": as2b.audit(system), "roles": system.roles.as_dict(), "reached_windows": len(records)}
    return row, audit_record


def body_feasible(row: dict, q: Fraction) -> bool:
    """同じ本体で「決まった窓が q 以上」かつ「A1 と A2 の両方が出た」（宣言の body_feasible）。"""
    return Fraction(row["decided"], row["windows"]) >= q and row["A1_occurred"] and row["A2_occurred"]


def evaluate(rows: list[dict], decl: dict) -> dict:
    """個体（seed）ごとに、対の二つの本体がどちらも本体の条件を満たすかを数え、個体の過半で成立とする。"""
    q = Fraction(str(decl["evaluation"]["q"]))
    per_body = len(decl["bodies"]["per_individual"])
    by_seed: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_seed[r["seed"]].append(r)
    feasible_individuals = sum(1 for rs in by_seed.values() if len(rs) == per_body and all(body_feasible(r, q) for r in rs))
    n = len(by_seed)
    return {"individuals": n, "bodies": len(rows), "feasible_bodies": sum(1 for r in rows if body_feasible(r, q)),
            "feasible_individuals": feasible_individuals, "pass": 2 * feasible_individuals > n}


def check_validity(rows: list[dict], audits: list[dict], decl: dict) -> dict:
    """監査・窓の到達・持ち越し・行の数を確かめる。どれかが合わなければ無効（宣言の validity）。"""
    problems = []
    expected = decl["synthetic_seeds"]["count"] * len(decl["bodies"]["per_individual"])
    if len(rows) != expected or len(audits) != expected:
        problems.append(f"行の数 {len(rows)}・記録の数 {len(audits)} が {expected} でない")
    windows = decl["schedule"]["cue_pulses"]["count"]
    for r, a in zip(rows, audits):
        tag = f"{r['seed']}/{r['rule_c']}"
        if not a["audit"]["ok"]:
            problems.append(f"{tag}：CT-E10 の監査が合わない")
        if r["windows"] != windows or a["reached_windows"] != windows or r["decided"] + r["tie"] + r["none"] != windows:
            problems.append(f"{tag}：窓の到達・数が合わない")
        if a["audit"].get("carried_over_windows"):
            problems.append(f"{tag}：終わりに未発行の予定が残る")
    return {"valid": not problems, "problems": problems}


def run_gate(decl: dict, digest: str, out_dir: Path, attempts_dir: Path = ATTEMPTS_DIR) -> dict:
    """順序：形の確かめ → 試行の札（排他）→ 本体ごとに走らせて記録を書く → 有効性 → 報告 → 試行の記録。

    札は最初の seed の前に作り、消さない。途中の例外は失敗の記録を残して投げ直す。無効なら合否を出さない。
    """
    _check_supported(decl)
    seeds = range(decl["synthetic_seeds"]["first"], decl["synthetic_seeds"]["last"] + 1)
    if len(seeds) != decl["synthetic_seeds"]["count"]:
        raise ValueError("seed の範囲と数が合わない")
    if (out_dir / "report.json").exists():
        raise AttemptRefused(f"{out_dir / 'report.json'} がもうある")
    claim_attempt(attempts_dir, digest, out_dir)                       # ここから先は、この宣言では二度と走らない
    rows, audits = [], []
    try:
        as2b = _load_as2b()
        for seed in seeds:
            for body in decl["bodies"]["per_individual"]:
                row, record = run_body(as2b, decl, seed, body["rule_c"])
                _write_exclusive(out_dir / "records" / f"{seed}_{body['rule_c']}.json", record)
                rows.append({"seed": seed, "rule_c": body["rule_c"], **row})
                audits.append(record)
        validity = check_validity(rows, audits, decl)
        q = Fraction(str(decl["evaluation"]["q"]))
        for r in rows:
            r["feasible"] = body_feasible(r, q)
        evaluation = evaluate(rows, decl) if validity["valid"] else {"pass": None}
        status = "completed" if validity["valid"] else "invalid"
        report = {"declaration_sha256": digest, "status": status, "validity": validity, "per_body": rows,
                  "evaluation": evaluation}
        _write_exclusive(out_dir / "report.json", report)
    except Exception as exc:
        record_attempt(attempts_dir, digest, "failed", {"finished_bodies": len(rows), "error": repr(exc),
                                                        "traceback": traceback.format_exc(limit=5)})
        raise
    record_attempt(attempts_dir, digest, status, {"finished_bodies": len(rows), "valid": validity["valid"],
                                                  "pass": evaluation["pass"]})
    return report


EXIT_DONE, EXIT_REFUSED, EXIT_INVALID, EXIT_FAILED = 0, 2, 3, 4


def main(argv: list[str] | None = None, *, declaration: Path = DECLARATION,
         expected_sha256: str | None = DECLARATION_SHA256, attempts_dir: Path = ATTEMPTS_DIR) -> int:
    """終了の値：0 ＝ 有効に完走（合否は報告の evaluation.pass。陰性も 0）、2 ＝ 走らせない（札・結果がある）、
    3 ＝ 無効（合否を出さない）、4 ＝ 途中で失敗（札は残る）。キーワードの引数は契約テストのためだけ。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="②a の技術受理の後に、②b で一度だけ付ける")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args(argv)
    decl, digest = load_declaration(declaration, expected_sha256)
    if not args.execute:
        print(f"宣言を確かめた（SHA-256 {digest}）。--execute がないので走らせない")
        return EXIT_DONE
    try:
        report = run_gate(decl, digest, args.out, attempts_dir)
    except AttemptRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_REFUSED
    except Exception:  # noqa: BLE001 — どの例外でも「途中で失敗」として終了の値 4 を返す（札は run_gate が残す）
        traceback.print_exc()
        print("途中で失敗した。試行の札は残る。再開は、部分の記録の中身を読まない独立の審査の後に限る", file=sys.stderr)
        return EXIT_FAILED
    if report["status"] != "completed":
        print("無効な試行：合否を出さない。" + "; ".join(report["validity"]["problems"][:5]), file=sys.stderr)
        return EXIT_INVALID
    print(json.dumps(report["evaluation"], ensure_ascii=False))
    return EXIT_DONE


if __name__ == "__main__":
    raise SystemExit(main())
