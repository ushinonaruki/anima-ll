"""実験 0010 の判定（事前登録の一部。測定の前にコミットする）。

判定の値の正本は protocol.yaml。0004 の analyze_silent・0005 の analyze からは生の集計
（条件ごとの「落ち着いた」個体数、α = 0 との差）だけを再利用し、成り立つかどうかは protocol.yaml の値で決める。
0005 の choose_reference は呼ばない（中で 0005 に書かれた 0.3 を使うため）。選び方の規則だけを当てはめる。

駆動の値ごとに：
- K1：α = 0 の終盤に発火した個体が min_active_seeds 未満なら「該当しない」。それ以外は、基準の条件すべてで
      落ち着いた個体が min_calmed_seeds 以上なら「成り立つ」
- K2：基準の条件すべてで α = 0 との差が min_difference_from_alpha0 以上なら「成り立つ」
- K3：K1・K2 がともに成り立つときだけ、両方を条件別に満たす条件（α = 0 を除く）のうち α × τ_a が最小、
      同じなら α が小さい方を選ぶ。それ以外は「該当しない」

確認：駆動 0.08 の結果が 0009 の K1・K2 と、発火の記録まで完全に一致すること

使い方:
  python experiments/0010_drive_regime/analyze.py [data/experiments/0010]
"""

import gzip
import importlib.util
import json
import sys
from pathlib import Path

import yaml

HERE = Path("experiments/0010_drive_regime")
PROTOCOL = yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0010")
RESULTS_0009 = Path("experiments/0009_refractory_removal")
UNITS = ("u0", "u1", "u2", "u3")


def load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def rho(drive: float, decay: float = 0.85, threshold: float = 0.5) -> float:
    return drive / ((1 - decay) * threshold)


def completeness(k1: dict, k2: dict, drive: float) -> list[str]:
    problems = []
    conds = pairs(PROTOCOL["adaptation_conditions"])
    if k1["meta"]["intrinsic_drive"] != drive or k2["meta"]["intrinsic_drive"] != drive:
        problems.append("駆動の値が違う")
    expected = {(a, t, s) for a, t in conds for s in expected_seeds()}
    got = [(r["alpha"], r["tau"], r["seed"]) for r in k1["runs"]]
    if len(got) != len(set(got)) or set(got) != expected:
        problems.append(f"K1 の本数（{len(set(got))}/{len(expected)}）")
    if k1["meta"]["silent_pulses"] != PROTOCOL["k1"]["silent_pulses"]:
        problems.append("K1 の Pulse 数が protocol と違う")
    problems += [f"K2：{p}" for p in A5.completeness_problems(k2)]
    return problems


def judge_k1(runs: list[dict]) -> dict:
    p = PROTOCOL["k1"]
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


def judge_k2(data: dict) -> dict:
    p = PROTOCOL["k2"]
    report = A5.analyze(data)
    per_cond = {c: c != (0.0, 0) and report[c]["difference_from_alpha0"] >= p["min_difference_from_alpha0"]
                for c in report}
    supported = all(per_cond[c] for c in pairs(p["reference_conditions"]))
    return {"result": "holds" if supported else "fails",
            "difference_from_alpha0": {f"{a}/{t}": round(report[(a, t)]["difference_from_alpha0"], 3)
                                       for a, t in report},
            "per_condition": per_cond}


def judge_k3(k1: dict, k2: dict) -> dict:
    if k1["result"] != "holds" or k2["result"] != "holds":
        return {"result": "N/A", "chosen": None}
    candidates = [c for c in k1["per_condition"]
                  if c != (0.0, 0) and k1["per_condition"][c] and k2["per_condition"].get(c)]
    if not candidates:
        return {"result": "no candidate", "chosen": None}
    chosen = min(candidates, key=lambda c: (c[0] * c[1], c[0]))
    same = list(chosen) == [float(PROTOCOL["k3"]["reference_value"][0]), PROTOCOL["k3"]["reference_value"][1]]
    return {"result": "same as reference" if same else "different", "chosen": list(chosen)}


def protocol_vs_old_constants() -> dict:
    """protocol の判定値と、0004・0005 の analyzer の定数の違い（記録。判定は protocol で行う）。"""
    return {
        "k1_min_calmed_seeds": [PROTOCOL["k1"]["min_calmed_seeds"], A4.H1_MIN_SEEDS],
        "k1_reference": [pairs(PROTOCOL["k1"]["reference_conditions"]) == pairs(A4.H1_REFERENCE)],
        "k2_min_difference": [PROTOCOL["k2"]["min_difference_from_alpha0"], A5.H2_MIN_DIFFERENCE],
        "k2_reference": [pairs(PROTOCOL["k2"]["reference_conditions"]) == pairs(A5.H2_REFERENCE)],
    }


def reproduces_0009(k1: dict, k2: dict) -> dict:
    old1, old2 = read(RESULTS_0009 / "k1.json.gz"), read(RESULTS_0009 / "k2.json.gz")
    f1 = {(r["alpha"], r["tau"], r["seed"]): r["fires"] for r in old1["runs"]}
    f2 = {(r["alpha"], r["tau"], r["seed"], r["branch"], r["weight"]): r["fires"] for r in old2["runs"]}
    m1 = sum(f1.get((r["alpha"], r["tau"], r["seed"])) != r["fires"] for r in k1["runs"])
    m2 = sum(f2.get((r["alpha"], r["tau"], r["seed"], r["branch"], r["weight"])) != r["fires"] for r in k2["runs"])
    return {"k1_mismatched_runs": m1, "k2_mismatched_runs": m2, "identical": m1 == 0 and m2 == 0}


def records(k1: dict) -> dict:
    runs = k1["runs"]
    rec = A8.records({"OLD": [], "NEW": runs})
    rhos = [x for r in runs if r["alpha"] == 0.0 for x in r["unit_rho"]]
    silent = {f"{a}/{t}": sum(not any(r["fires"].get(u) for u in UNITS) for r in runs if (r["alpha"], r["tau"]) == (a, t))
              for a, t in pairs(PROTOCOL["adaptation_conditions"])}
    periodic = {}
    for r in runs:
        if (r["alpha"], r["tau"]) != (0.01, 300):
            continue
        for u in UNITS:
            late = [p for p in r["fires"].get(u, []) if A4.LATE[0] <= p <= A4.LATE[1]]
            pat = A4.periodic_pattern(late)
            periodic[pat] = periodic.get(pat, 0) + 1
    return {
        "by_condition": {k.removeprefix("NEW "): v for k, v in rec.items()},
        "unit_rho_above_1_fraction": sum(x > 1 for x in rhos) / len(rhos) if rhos else None,
        "unit_rho_range": [min(rhos), max(rhos)] if rhos else None,
        "never_firing_seeds_by_condition": silent,
        "late_periodic_patterns_reference_condition": periodic,
    }


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    out: dict = {"protocol_vs_old_constants": protocol_vs_old_constants(), "drives": {}}
    all_problems = []
    for drive in [float(d) for d in PROTOCOL["intrinsic_drive_values"]]:
        k1 = read(directory / f"k1_drive{drive:.4f}.json.gz")
        k2 = read(directory / f"k2_drive{drive:.4f}.json.gz")
        problems = completeness(k1, k2, drive)
        all_problems += [f"drive {drive}: {p}" for p in problems]
        j1, j2 = judge_k1(k1["runs"]), judge_k2(k2)
        j3 = judge_k3(j1, j2)
        for j in (j1, j2):
            j["per_condition"] = {f"{a}/{t}": v for (a, t), v in j["per_condition"].items()}
        entry = {"rho": round(rho(drive), 4), "git_commit": k1["meta"]["git_commit"], "problems": problems,
                 "K1": j1, "K2": j2, "K3": j3, "records": records(k1)}
        if drive == float(PROTOCOL["current_intrinsic_drive"]):
            entry["reproduces_0009"] = reproduces_0009(k1, k2)
        out["drives"][f"{drive:.4f}"] = entry
    out["valid"] = not all_problems
    out["problems"] = all_problems
    out["summary"] = {d: {"rho": e["rho"], "K1": e["K1"]["result"], "K2": e["K2"]["result"],
                          "K3": e["K3"]["result"], "K3_chosen": e["K3"]["chosen"]}
                      for d, e in out["drives"].items()}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
