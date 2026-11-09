"""実験 0038（②b）の出力の独立の検め直し（標準ライブラリだけ。gate.py・as2b.py を読み込まない）。

関門を走らせた後に一度だけ使う。条件を変えず、関門を走らせ直さない。計算するのは、宣言で出してよい量
（本体ごとの窓・決まった窓・引き分け・発火なし・A1 が出たか・A2 が出たか）と、本体・個体の条件と合否、
CT-E10 の突合だけで、A1・A2 の別々の数、A1 の割合、時間の変化、規則 c の違う本体の差は計算しない。
"""

import hashlib
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTCOMES = {"A1", "A2", "tie", "none"}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    decl_path = HERE / "gate_declaration.json"
    decl = json.loads(decl_path.read_text(encoding="utf-8"))
    digest = sha(decl_path)
    results = HERE / "results"
    report = json.loads((results / "report.json").read_text(encoding="utf-8"))
    checks, problems = 0, []

    def check(cond: bool, msg: str) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            problems.append(msg)

    check(digest == "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb", "宣言のハッシュ")
    check(report["declaration_sha256"] == digest, "報告の宣言のハッシュ")
    claim = HERE / "attempts" / f"claim-{digest}.json"
    check(claim.exists(), "試行の札がない")
    finals = sorted(p.name for p in (HERE / "attempts").glob(f"attempt-{digest}.*.json"))
    check(len(finals) == 1, f"試行の結末の記録が一つでない：{finals}")

    cp = decl["schedule"]["cue_pulses"]
    o, w = decl["schedule"]["window_offset_o"], decl["schedule"]["window_length_W"]
    windows = {k + 1: (cp["first"] + cp["spacing"] * k + o, cp["first"] + cp["spacing"] * k + o + w - 1)
               for k in range(cp["count"])}
    seeds = range(decl["synthetic_seeds"]["first"], decl["synthetic_seeds"]["last"] + 1)
    rule_cs = [b["rule_c"] for b in decl["bodies"]["per_individual"]]
    expected = Counter((s, c) for s in seeds for c in rule_cs)
    rows = report["per_body"]
    check(Counter((r["seed"], r["rule_c"]) for r in rows) == expected, "報告の行の対")
    record_files = sorted((results / "records").glob("*.json"))
    check(len(record_files) == len(expected), "記録のファイルの数")

    recomputed = {}
    for path in record_files:
        rec = json.loads(path.read_text(encoding="utf-8"))
        key = (rec["seed"], rec["rule_c"])
        check(path.name == f"{key[0]}_{key[1]}.json", f"{path.name}：ファイル名と中身")
        la, lb = rec["layer_a"], rec["layer_b"]
        check(sorted(r["window"] for r in la) == sorted(windows), f"{key}：窓の番号")
        roles = rec["roles"]
        action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
        for r in la:
            k, out, d = r["window"], r["outcome"], r["decision_pulse"]
            check(out in OUTCOMES, f"{key} 窓 {k}：結末")
            check((r["open"], r["close"]) == windows.get(k), f"{key} 窓 {k}：区間")
            if out in ("A1", "A2"):
                check(action_of.get(r["winner_unit"]) == out == r["action"] and r["emitted"] is True
                      and windows[k][0] <= d <= windows[k][1] and r["emit_pulse"] == d + 1, f"{key} 窓 {k}：勝ちの欄")
            elif out == "tie":
                check(r["winner_unit"] is None and r["action"] is None and windows[k][0] <= d <= windows[k][1]
                      and not r["emitted"], f"{key} 窓 {k}：引き分けの欄")
            else:
                check(d is None and r["winner_unit"] is None and not r["emitted"], f"{key} 窓 {k}：発火なしの欄")
        # CT-E10 を独立に：層 A の「出した」記録と層 B の意図の記録の一対一
        a_side = Counter((r["emit_pulse"], r["winner_unit"], r["action"]) for r in la if r["emitted"])
        b_side = Counter((p, src, act) for p, _did, src, act in lb)
        check(a_side == b_side, f"{key}：層 A と層 B")
        check(len({did for _p, did, _s, _a in lb}) == len(lb), f"{key}：Delta の識別子の重複")
        check(not any(r["winner_unit"] is not None and not r["emitted"] for r in la), f"{key}：未発行の予定")
        check(rec["audit"]["ok"] is True, f"{key}：道具の監査")
        outs = [r["outcome"] for r in la]
        recomputed[key] = {"windows": len(la), "decided": outs.count("A1") + outs.count("A2"), "tie": outs.count("tie"),
                           "none": outs.count("none"), "A1_occurred": "A1" in outs, "A2_occurred": "A2" in outs}
    for r in rows:
        key = (r["seed"], r["rule_c"])
        check({k: r[k] for k in recomputed.get(key, {})} == recomputed.get(key), f"{key}：報告の行と計算し直した値")

    q = Fraction(str(decl["evaluation"]["q"]))

    def feasible(v: dict) -> bool:
        return Fraction(v["decided"], v["windows"]) >= q and v["A1_occurred"] and v["A2_occurred"]

    for r in rows:
        key = (r["seed"], r["rule_c"])
        if key in recomputed:
            check(r.get("feasible") == feasible(recomputed[key]), f"{key}：本体の条件")
    feasible_individuals = sum(1 for s in seeds
                               if all((s, c) in recomputed and feasible(recomputed[(s, c)]) for c in rule_cs))
    n = decl["synthetic_seeds"]["count"]
    mine = {"individuals": n, "bodies": len(recomputed), "feasible_bodies": sum(1 for v in recomputed.values() if feasible(v)),
            "feasible_individuals": feasible_individuals, "pass": 2 * feasible_individuals > n}
    check(report["status"] == "completed", f"報告の状態 {report['status']}")
    if report["status"] == "completed":
        check(report["evaluation"] == mine, "評価")

    files = sorted(p for p in list(results.rglob("*.json")) + list((HERE / "attempts").glob("*.json")))
    out = {"declaration_sha256": digest, "checks": checks, "mismatches": len(problems), "problems": problems,
           "recomputed_evaluation": mine,
           "sha256": {str(p.relative_to(HERE)): sha(p) for p in files}}
    target = HERE / "recheck" / "recheck_result.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"checks": checks, "mismatches": len(problems), "recomputed_evaluation": mine}, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
