"""実験 0038：AS2b の前方の関門を走らせるコード（契約 §7。②b で一度だけ使う）。

- 読むのは `gate_declaration.json` だけ。値をこのコードに書き込まない（契約 §7.2 の固定の方法）
- 宣言の SHA-256 が `DECLARATION_SHA256` と違えば止まる。`--execute` がなければ走らない（②a では走らせない）
- 出すのは、本体ごとの実行可能性の量（窓・決まった窓・引き分け・発火なし・A1 が出たか・A2 が出たか）と、二つの条件の
  成否だけ。A1・A2 の別々の数、A1 の割合、時間の変化、c の違う本体の差は計算しない（宣言の forbidden_outputs）
- 検査用の記録として、本体ごとに層 A・層 B の記録と、CT-E10 の突合の結果を保存する（関門の報告には集計しない）
"""

import argparse
import hashlib
import importlib.util
import json
import sys
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DECLARATION = HERE / "gate_declaration.json"
DECLARATION_SHA256 = "909ab4f8ecd8bbefc688ccfe5a9296ab10dadecb6c6f5d4f189d19fe187fb3e4"
REPORT_KEYS = ("windows", "decided", "tie", "none", "A1_occurred", "A2_occurred")


def _load_as2b():
    spec = importlib.util.spec_from_file_location("as2b_for_gate", ROOT / "experiments" / "as2b_choice" / "as2b.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeclarationMismatch(RuntimeError):
    """宣言のハッシュが、②a で固定したものと違う。"""


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


def evaluate(rows: list[dict], decl: dict) -> dict:
    ev = decl["evaluation"]
    q = Fraction(str(ev["q"]))
    n = len(rows)
    c1 = sum(1 for r in rows if Fraction(r["decided"], r["windows"]) >= q)
    c2 = sum(1 for r in rows if r["A1_occurred"] and r["A2_occurred"])
    crit1, crit2 = 2 * c1 > n, 2 * c2 > n
    return {"bodies": n, "bodies_decided_at_least_q": c1, "bodies_with_both_actions": c2,
            "criterion_1": crit1, "criterion_2": crit2, "pass": crit1 and crit2}


def run_gate(decl: dict, digest: str, out_dir: Path | None = None) -> dict:
    _check_supported(decl)
    as2b = _load_as2b()
    seeds = range(decl["synthetic_seeds"]["first"], decl["synthetic_seeds"]["last"] + 1)
    if len(seeds) != decl["synthetic_seeds"]["count"]:
        raise ValueError("seed の範囲と数が合わない")
    rows, audits = [], []
    for seed in seeds:
        for body in decl["bodies"]["per_individual"]:
            row, record = run_body(as2b, decl, seed, body["rule_c"])
            rows.append({"seed": seed, "rule_c": body["rule_c"], **row})
            audits.append(record)
    report = {"declaration_sha256": digest, "per_body": rows, "evaluation": evaluate(rows, decl),
              "audit_all_ok": all(a["audit"]["ok"] for a in audits)}
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        rec_dir = out_dir / "records"
        rec_dir.mkdir(exist_ok=True)
        for a in audits:
            (rec_dir / f"{a['seed']}_{a['rule_c']}.json").write_text(
                json.dumps(a, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="②a の技術受理の後に、②b で一度だけ付ける")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    args = parser.parse_args(argv)
    decl, digest = load_declaration()
    if not args.execute:
        print(f"宣言を確かめた（SHA-256 {digest}）。--execute がないので走らせない")
        return 0
    if (args.out / "report.json").exists():
        print("結果がもうある。関門は一度だけ走らせる", file=sys.stderr)
        return 2
    report = run_gate(decl, digest, args.out)
    print(json.dumps(report["evaluation"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
