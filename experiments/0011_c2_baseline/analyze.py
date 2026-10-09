"""実験 0011 の判定（事前登録の一部。測定の前にコミットする）。

判定の値の正本は protocol.yaml。0004 の analyze_silent・0005 の analyze・w_star からは生の集計だけを再利用し、
成り立つかどうかは protocol.yaml の値で決める（0010 と同じ方法）。

- B1：入力（silent・part_b）ごとに、seed ごとの 6 つの Kernel の条件の発火の記録（activity の出来事の列）が
      完全に一致する seed の数を数える。両方の入力で required_identical_seeds 以上なら「成り立つ」
- B2：0005 の手順で、u0 の w*（0005 の w_star）を (条件, seed, 枝) ごとに求め、0010 の駆動 0.0800 の
      保存済みデータから同じく求めた値と比べる。すべて一致すれば「成り立つ」
- B3：0010 の K1 と同じ判定（protocol の b3）。α = 0 の終盤に発火した個体が min_active_seeds 未満なら「該当しない」
- B4：0010 の K2 と同じ判定（protocol の b4）
- 参照値の選び方の規則（旧 K3）：B3・B4 がともに成り立つときだけ当てはめる。参照値は変えない

使い方:
  python experiments/0011_c2_baseline/analyze.py [data/experiments/0011]
  （同じ内容を <データのフォルダ>/report.json にも保存する）

B1 の操作の確認：Kernel の条件ごと・入力ごとに、指定した種類の結果（ok → 中身あり、empty → 空、failure → 失敗）が
1 件以上あり、ほかの種類が 0 件でなければ、B1 は fails ではなく invalid（problems）とする
"""

import gzip
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import yaml

HERE = Path("experiments/0011_c2_baseline")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0011")
UNITS = ("u0", "u1", "u2", "u3")


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0011", str(HERE / "alignment.py"))
A4 = load("analyze_0004", "experiments/0004_adaptation/analyze.py")
A5 = load("analyze_0005", "experiments/0005_response_threshold/analyze.py")
A8 = load("analyze_0008", "experiments/0008_baseline_new_runtime/analyze.py")


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def pairs(xs) -> list[tuple[float, float]]:
    return [(float(a), t) for a, t in xs]


def expected_seeds() -> list[int]:
    return list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))


# ---- 完全性 -----------------------------------------------------------------------

def completeness(b1: dict, b2: dict, b3: dict) -> list[str]:
    problems = []
    for name, data in (("B1", b1), ("B2B4", b2), ("B3", b3)):
        commit = data["meta"]["git_commit"]
        if commit != b1["meta"]["git_commit"]:
            problems.append(f"{name} の commit が B1 と違う")
    p = PROTOCOL["b1"]
    expected = {(k["id"], i, s) for k in p["kernel_conditions"] for i in p["inputs"] for s in expected_seeds()}
    got = [(r["kernel"], r["inputs"], r["seed"]) for r in b1["runs"]]
    if len(got) != len(set(got)) or set(got) != expected:
        problems.append(f"B1 の本数（{len(set(got))}/{len(expected)}）")
    if b1["meta"]["b1"] != p:
        problems.append("B1 の条件が protocol と違う")
    problems += [f"B2B4：{x}" for x in A5.completeness_problems(b2)]
    if b2["meta"]["neuroarchitecture"] != PROTOCOL["base_neuroarchitecture"]:
        problems.append("B2B4 の設計図が protocol と違う")
    conds = pairs(PROTOCOL["adaptation_conditions"])
    expected3 = {(a, t, s) for a, t in conds for s in expected_seeds()}
    got3 = [(r["alpha"], r["tau"], r["seed"]) for r in b3["runs"]]
    if len(got3) != len(set(got3)) or set(got3) != expected3:
        problems.append(f"B3 の本数（{len(set(got3))}/{len(expected3)}）")
    if b3["meta"]["silent_pulses"] != PROTOCOL["b3"]["silent_pulses"]:
        problems.append("B3 の Pulse 数が protocol と違う")
    if b3["meta"]["base_neuroarchitecture"] != PROTOCOL["base_neuroarchitecture"]:
        problems.append("B3 の設計図が protocol と違う")
    return problems


# ---- B1 ---------------------------------------------------------------------------

def judge_b1(b1: dict) -> dict:
    p = PROTOCOL["b1"]
    ids = [k["id"] for k in p["kernel_conditions"]]
    by: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in b1["runs"]:
        by[(r["inputs"], r["seed"])][r["kernel"]] = r
    per_input = {}
    for inputs in p["inputs"]:
        identical, mismatched = 0, []
        for seed in expected_seeds():
            runs = by.get((inputs, seed), {})
            records = [runs[k]["activity"] for k in ids if k in runs]
            if len(records) == len(ids) and all(rec == records[0] for rec in records[1:]):
                identical += 1
            else:
                mismatched.append(seed)
        present = [by[(inputs, s)] for s in expected_seeds() if (inputs, s) in by]

        def mean(key: str, k: str) -> float | None:
            xs = [runs[k][key] for runs in present if k in runs]
            return statistics.fmean(xs) if xs else None

        per_input[inputs] = {
            "identical_seeds": identical,
            "mismatched_seeds": mismatched,
            "kernel_outcomes_total": {k: {o: sum(runs[k]["kernel_outcomes"][o] for runs in present if k in runs)
                                          for o in OUTCOMES} for k in ids},
            "effects_mean": {k: mean("effects", k) for k in ids},
            "firings_mean": statistics.fmean(len(runs[ids[0]]["activity"]) for runs in present
                                             if ids[0] in runs) if present else None,
        }
    holds = all(v["identical_seeds"] >= p["required_identical_seeds"] for v in per_input.values())
    return {"result": "holds" if holds else "fails", "per_input": per_input}


OUTCOMES = ("ok_nonempty", "ok_empty", "error")
EXPECTED_OUTCOME = {"ok": "ok_nonempty", "empty": "ok_empty", "failure": "error"}


def manipulation_problems(b1: dict) -> list[str]:
    """B1 の操作が成立していたか（Kernel の条件が、指定した種類の結果だけを実際に返したか）。

    成立していなければ B1 の判定は意味を持たないので、fails ではなく invalid（problems）にする。
    入力ごとに、条件の指定した種類が 1 件以上あり、ほかの種類が 0 件であること。
    """
    problems = []
    for kernel in PROTOCOL["b1"]["kernel_conditions"]:
        expected = EXPECTED_OUTCOME[kernel["result"]]
        for inputs in PROTOCOL["b1"]["inputs"]:
            total = {o: sum(r["kernel_outcomes"][o] for r in b1["runs"]
                            if r["kernel"] == kernel["id"] and r["inputs"] == inputs) for o in OUTCOMES}
            if total[expected] == 0:
                problems.append(f"B1 操作不成立：{kernel['id']}／{inputs} で {expected} が 1 件もない")
            others = {o: n for o, n in total.items() if o != expected and n}
            if others:
                problems.append(f"B1 操作不成立：{kernel['id']}／{inputs} で指定外の結果 {others}")
    return problems


# ---- B2 ---------------------------------------------------------------------------

def w_stars(data: dict) -> dict[tuple, float]:
    grouped: dict[tuple, dict[float, dict]] = defaultdict(dict)
    for r in data["runs"]:
        grouped[(r["alpha"], r["tau"], r["seed"], r["branch"])][r["weight"]] = r
    return {key: A5.w_star(runs)[0] for key, runs in grouped.items()}


def judge_b2(b2: dict) -> dict:
    new = w_stars(b2)
    old = w_stars(read(Path(PROTOCOL["old_reference"]["k2_data"])))
    mismatched = sorted([list(k) + [A5.fmt_w(old.get(k, float("nan"))), A5.fmt_w(v)]
                         for k, v in new.items() if old.get(k) != v])
    missing = sorted(set(old) ^ set(new))
    holds = not mismatched and not missing
    return {"result": "holds" if holds else "fails", "compared": len(new),
            "mismatched": mismatched, "missing_keys": [list(k) for k in missing]}


# ---- B3・B4・参照値の規則（0010 の K1・K2・K3 と同じ） ---------------------------------------

def judge_b3(runs: list[dict]) -> dict:
    p = PROTOCOL["b3"]
    lo, hi = p["applicability"]["window"]
    baseline = [r for r in runs if r["alpha"] == 0.0]
    active = sum(any(lo <= x <= hi for u in UNITS for x in r["fires"].get(u, [])) for r in baseline)
    report = A4.analyze_silent(runs)
    per_cond = {c: report[c]["calmed_seeds"] >= p["min_calmed_seeds"] for c in report}
    applicable = active >= p["applicability"]["min_active_seeds"]
    supported = applicable and all(per_cond[c] for c in pairs(p["reference_conditions"]))
    return {"applicable": applicable, "baseline_active_seeds": active,
            "result": "N/A" if not applicable else ("holds" if supported else "fails"),
            "calmed_seeds": {f"{a}/{t}": report[(a, t)]["calmed_seeds"] for a, t in report},
            "per_condition": per_cond}


def judge_b4(data: dict) -> dict:
    p = PROTOCOL["b4"]
    report = A5.analyze(data)
    per_cond = {c: c != (0.0, 0) and report[c]["difference_from_alpha0"] >= p["min_difference_from_alpha0"]
                for c in report}
    supported = all(per_cond[c] for c in pairs(p["reference_conditions"]))
    return {"result": "holds" if supported else "fails",
            "difference_from_alpha0": {f"{a}/{t}": round(report[(a, t)]["difference_from_alpha0"], 3)
                                       for a, t in report},
            "per_condition": per_cond}


def judge_reference_rule(b3: dict, b4: dict) -> dict:
    if b3["result"] != "holds" or b4["result"] != "holds":
        return {"result": "N/A", "chosen": None}
    candidates = [c for c in b3["per_condition"]
                  if c != (0.0, 0) and b3["per_condition"][c] and b4["per_condition"].get(c)]
    if not candidates:
        return {"result": "no candidate", "chosen": None}
    chosen = min(candidates, key=lambda c: (c[0] * c[1], c[0]))
    ref = PROTOCOL["reference_value_rule"]["reference_value"]
    same = list(chosen) == [float(ref[0]), ref[1]]
    return {"result": "same as reference" if same else "different", "chosen": list(chosen)}


# ---- 記録（判定には使わない） ------------------------------------------------------------

def follow_fraction(runs: list[dict]) -> dict:
    """u0 が発火した次の Pulse に、u1・u2 が発火した割合。"""
    out = {}
    for target in ("u1", "u2"):
        hit = total = 0
        for r in runs:
            fired = set(r["fires"].get(target, []))
            for p in r["fires"].get("u0", []):
                total += 1
                hit += (p + 1) in fired
        out[target] = hit / total if total else None
    return out


def records(new_runs: list[dict], old_runs: list[dict]) -> dict:
    rec = A8.records({"OLD": [], "NEW": new_runs})
    rec_old = A8.records({"OLD": [], "NEW": old_runs})
    by_cond = {}
    for key, v in rec.items():
        cond = key.removeprefix("NEW ")
        by_cond[cond] = {"c2": v, "old_path_0010": rec_old.get(key)}
    follow = {}
    never = {}
    for a, t in pairs(PROTOCOL["adaptation_conditions"]):
        runs = [r for r in new_runs if (r["alpha"], r["tau"]) == (a, t)]
        follow[f"{a}/{t}"] = follow_fraction(runs)
        never[f"{a}/{t}"] = sum(not any(r["fires"].get(u) for u in UNITS) for r in runs)
    periodic: dict[str, int] = {}
    for r in new_runs:
        if (r["alpha"], r["tau"]) != (0.01, 300):
            continue
        for u in UNITS:
            late = [p for p in r["fires"].get(u, []) if A4.LATE[0] <= p <= A4.LATE[1]]
            pat = A4.periodic_pattern(late)
            periodic[pat] = periodic.get(pat, 0) + 1
    return {"by_condition": by_cond, "u0_followed_next_pulse": follow,
            "never_firing_seeds_by_condition": never,
            "late_periodic_patterns_reference_condition": periodic}


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    ALIGN.check(PROTOCOL)   # protocol と再利用する旧の実装がずれていたら止める
    b1, b2, b3 = (read(directory / name) for name in ("b1.json.gz", "b2b4.json.gz", "b3.json.gz"))
    manipulation = manipulation_problems(b1)
    problems = completeness(b1, b2, b3) + manipulation
    j1, j2 = judge_b1(b1), judge_b2(b2)
    if manipulation:
        # 操作が成立していなければ、B1 は fails ではなく invalid。生の比較（identical_seeds など）は残す
        j1["comparison_result"] = j1["result"]
        j1["result"] = "invalid"
        j1["manipulation_problems"] = manipulation
    j3, j4 = judge_b3(b3["runs"]), judge_b4(b2)
    jr = judge_reference_rule(j3, j4)
    for j in (j3, j4):
        j["per_condition"] = {f"{a}/{t}": v for (a, t), v in j["per_condition"].items()}
    old_k1 = read(Path(PROTOCOL["old_reference"]["k1_data"]))
    out = {
        "git_commit": b1["meta"]["git_commit"],
        "valid": not problems,
        "problems": problems,
        "B1": j1, "B2": j2, "B3": j3, "B4": j4, "reference_value_rule": jr,
        "records": records(b3["runs"], old_k1["runs"]),
    }
    out["summary"] = {"B1": j1["result"], "B2": j2["result"], "B3": j3["result"], "B4": j4["result"],
                      "reference_value_rule": jr["result"], "chosen": jr["chosen"]}
    text = json.dumps(out, ensure_ascii=False, indent=2, default=str)
    (directory / "report.json").write_text(text + "\n", encoding="utf-8")   # 測定の commit を含む判定の記録
    print(text)


if __name__ == "__main__":
    main()
