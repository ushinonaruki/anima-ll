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
import platform
import subprocess
import sys
import traceback
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DECLARATION = HERE / "gate_declaration.json"
DECLARATION_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
ATTEMPTS_DIR = HERE / "attempts"
REPORT_KEYS = ("windows", "decided", "tie", "none", "A1_occurred", "A2_occurred")
OUTCOMES = ("A1", "A2", "tie", "none")


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


def _git_head() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def preflight(out_dir: Path, attempts_dir: Path, digest: str) -> None:
    """札を作る前の点検。出力先に前の報告・記録が残っている、またはこの宣言の札・結末がもうあるなら、札を使わずに止める。
    既存のファイルを消したり上書きしたりして回避しない。"""
    problems = []
    if (out_dir / "report.json").exists():
        problems.append(f"{out_dir / 'report.json'} がもうある")
    records = out_dir / "records"
    if records.exists() and any(records.iterdir()):
        problems.append(f"{records} に前の記録が残っている")
    if (attempts_dir / f"claim-{digest}.json").exists() or any(attempts_dir.glob(f"attempt-{digest}.*.json")):
        problems.append(f"この宣言の試行の札・結末が {attempts_dir} にもうある")
    if problems:
        raise AttemptRefused("走らせる前の点検で止めた（札は使っていない）：" + "; ".join(problems))


def claim_attempt(attempts_dir: Path, digest: str, out_dir: Path) -> Path:
    """最初の seed の前に、宣言のハッシュに結び付いた試行の札を排他に作る。あれば AttemptRefused。

    札が排他になるのは、同じ attempts の場所を共有する一つの作業木の中だけである。②b は一つの作業木・一つのホストで
    走らせ、札の原本と結果を記録の PR に入れる（README §4）。札には、ホスト・作業木・commit を書く。"""
    path = attempts_dir / f"claim-{digest}.json"
    try:
        _write_exclusive(path, {"declaration_sha256": digest, "status": "started", "started_at": _now(),
                                "out_dir": str(out_dir), "pid": os.getpid(), "host": platform.node(),
                                "checkout": str(ROOT), "git_head": _git_head()})
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


def declared_seeds(decl: dict) -> range:
    return range(decl["synthetic_seeds"]["first"], decl["synthetic_seeds"]["last"] + 1)


def declared_pairs(decl: dict) -> Counter:
    """宣言の (seed, 規則 c) の対の多重集合。各対はちょうど 1 つ。"""
    return Counter((seed, body["rule_c"]) for seed in declared_seeds(decl) for body in decl["bodies"]["per_individual"])


def declared_windows(decl: dict) -> list[tuple[int, int, int]]:
    """宣言の予定から窓 (k, a_k, b_k) を作る（TrialSchedule と同じ式：a ＝ c ＋ o、b ＝ c ＋ o ＋ W − 1）。"""
    s = decl["schedule"]
    cp = s["cue_pulses"]
    o, w = s["window_offset_o"], s["window_length_W"]
    return [(k + 1, cp["first"] + cp["spacing"] * k + o, cp["first"] + cp["spacing"] * k + o + w - 1)
            for k in range(cp["count"])]


def recount_from_layer_a(layer_a, windows, roles=None) -> tuple[dict, list[str]]:
    """層 A の窓ごとの記録から、報告の行の量を独立に計算し直す。記録の欄どうしの食い違いも挙げる。"""
    problems = []
    if not isinstance(layer_a, list):
        return {}, ["層 A の記録がない"]
    bounds = {k: (a, b) for k, a, b in windows}
    ids = [r.get("window") if isinstance(r, dict) else None for r in layer_a]
    if Counter(ids) != Counter(list(bounds)):
        problems.append("層 A の窓の番号が、宣言の窓と一致しない（重複・欠落・余分）")
    action_of = None
    if isinstance(roles, dict) and roles.get("source1") and roles.get("source2"):
        action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    outcomes = []
    for r in layer_a:
        if not isinstance(r, dict):
            problems.append("層 A に窓の記録でないものがある")
            continue
        k, o, d = r.get("window"), r.get("outcome"), r.get("decision_pulse")
        outcomes.append(o)
        if o not in OUTCOMES:
            problems.append(f"窓 {k}：予期しない結末 {o!r}")
            continue
        inside = k in bounds and d is not None and bounds[k][0] <= d <= bounds[k][1]
        if k in bounds and (r.get("open"), r.get("close")) != bounds[k]:
            problems.append(f"窓 {k}：区間が宣言と違う")
        if o in ("A1", "A2"):
            ok = (inside and r.get("action") == o and r.get("winner_unit") is not None
                  and r.get("emit_pulse") == d + 1 and r.get("emitted") is True
                  and (action_of is None or action_of.get(r["winner_unit"]) == o))
        elif o == "tie":
            ok = inside and r.get("winner_unit") is None and r.get("action") is None and r.get("emit_pulse") is None \
                and not r.get("emitted")
        else:
            ok = all(r.get(x) is None for x in ("winner_unit", "action", "decision_pulse", "emit_pulse")) \
                and not r.get("emitted")
        if not ok:
            problems.append(f"窓 {k}：結末 {o} と記録の欄が合わない")
    counts = {"windows": len(layer_a), "decided": outcomes.count("A1") + outcomes.count("A2"),
              "tie": outcomes.count("tie"), "none": outcomes.count("none"),
              "A1_occurred": "A1" in outcomes, "A2_occurred": "A2" in outcomes}
    return counts, problems


def evaluate(rows: list[dict], decl: dict) -> dict:
    """宣言の seed ごとに、規則 c の二つの本体（c ＝ A1・A2 を 1 つずつ）がそろい、どちらも本体の条件を満たす個体を数える。
    分母は宣言の個体数（synthetic_seeds.count）に固定する。"""
    q = Fraction(str(decl["evaluation"]["q"]))
    wanted = sorted(body["rule_c"] for body in decl["bodies"]["per_individual"])
    by_seed: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_seed[r["seed"]].append(r)
    feasible_individuals = sum(
        1 for seed in declared_seeds(decl)
        if sorted(r["rule_c"] for r in by_seed.get(seed, [])) == wanted and all(body_feasible(r, q) for r in by_seed[seed]))
    n = decl["synthetic_seeds"]["count"]
    return {"individuals": n, "bodies": len(rows), "feasible_bodies": sum(1 for r in rows if body_feasible(r, q)),
            "feasible_individuals": feasible_individuals, "pass": 2 * feasible_individuals > n}


def check_validity(rows: list[dict], audits: list[dict], decl: dict) -> dict:
    """どれかが合わなければ無効（宣言の validity。fail-closed）。

    - 対の完全性：報告の行と検査用の記録の (seed, 規則 c) が、宣言の対の集合とちょうど一致し（重複・欠落・範囲外なし）、
      行と記録が同じ順で対応する
    - 各本体：CT-E10 の監査、窓の到達、終わりの未発行の予定 0
    - 各本体：層 A の窓ごとの記録から計算し直した量が、報告の行と完全に一致する。層 A の記録の欄どうしが整合する
    """
    problems = []
    expected = declared_pairs(decl)
    row_keys = [(r.get("seed"), r.get("rule_c")) if isinstance(r, dict) else None for r in rows]
    audit_keys = [(a.get("seed"), a.get("rule_c")) if isinstance(a, dict) else None for a in audits]
    if Counter(row_keys) != expected:
        problems.append("報告の行の (seed, 規則 c) が、宣言の対の集合と一致しない（重複・欠落・範囲外）")
    if Counter(audit_keys) != expected:
        problems.append("検査用の記録の (seed, 規則 c) が、宣言の対の集合と一致しない（重複・欠落・範囲外）")
    if row_keys != audit_keys:
        problems.append("報告の行と検査用の記録の対応が食い違う")
    windows = declared_windows(decl)
    for r, a in zip(rows, audits):
        if not isinstance(r, dict) or not isinstance(a, dict):
            problems.append("行か記録が辞書でない")
            continue
        tag = f"{r.get('seed')}/{r.get('rule_c')}"
        if set(r) != {"seed", "rule_c", *REPORT_KEYS}:
            problems.append(f"{tag}：報告の行の欄が違う")
        audit = a.get("audit") if isinstance(a.get("audit"), dict) else {}
        if audit.get("ok") is not True:
            problems.append(f"{tag}：CT-E10 の監査が合わない")
        if audit.get("carried_over_windows"):
            problems.append(f"{tag}：終わりに未発行の予定が残る")
        if a.get("reached_windows") != len(windows):
            problems.append(f"{tag}：窓の到達が合わない")
        counts, sub = recount_from_layer_a(a.get("layer_a"), windows, a.get("roles"))
        problems += [f"{tag}：{p}" for p in sub]
        if {k: r.get(k) for k in REPORT_KEYS} != counts:
            problems.append(f"{tag}：報告の行が、層 A から計算し直した値と一致しない")
    return {"valid": not problems, "problems": problems}


def run_gate(decl: dict, digest: str, out_dir: Path, attempts_dir: Path = ATTEMPTS_DIR) -> dict:
    """順序：形の確かめ → 走らせる前の点検 → 試行の札（排他）→ 本体ごとに走らせて記録を書く → 有効性 → 報告 → 試行の記録。

    札は最初の seed の前に作り、消さない。途中の例外は失敗の記録を残して投げ直す。無効なら合否を出さない。
    この関数は、受け取った宣言と digest を検め直さない（契約テストの入口）。運用の入口は main で、固定した宣言の
    SHA-256 を検めてから呼ぶ。
    """
    _check_supported(decl)
    seeds = range(decl["synthetic_seeds"]["first"], decl["synthetic_seeds"]["last"] + 1)
    if len(seeds) != decl["synthetic_seeds"]["count"]:
        raise ValueError("seed の範囲と数が合わない")
    preflight(out_dir, attempts_dir, digest)
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
