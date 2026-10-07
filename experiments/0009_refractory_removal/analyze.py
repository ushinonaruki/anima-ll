"""実験 0009 の判定（事前登録の一部。測定の前にコミットする）。

- K1：0004 の analyze_silent をそのまま当てはめる。基準の 4 条件すべてで「落ち着く」なら支持
- K2：0005 の analyze をそのまま当てはめる。基準の 4 条件すべてで α = 0 との差 0.3 以上なら支持
- K3：K1 と K2 がともに支持されたときだけ、0005 の choose_reference をそのまま当てはめる。どちらかが不支持なら N/A
- 参照値（α = 0.01・τ_a = 300）が不応期 0 の上でも根拠を保つ ＝ K1・K2 支持 かつ K3 が (0.01, 300)

記録（判定には使わない）：不応期 3（0008 の NEW、同じ新基盤）と不応期 0 の、発火・短い間隔の発火・計算・列・発話、
K2 の w* が「0.6 より上」だった個体の数

使い方:
  python experiments/0009_refractory_removal/analyze.py [data/experiments/0009]
"""

import gzip
import importlib.util
import json
import math
import sys
from pathlib import Path

DEFAULT_DIR = Path("data/experiments/0009")
BASELINE_0008 = Path("experiments/0008_baseline_new_runtime/results.json.gz")
RESULTS_0005 = Path("experiments/0005_response_threshold/results.json.gz")
EXPECTED_SEEDS = list(range(1, 21))
EXPECTED_CONDITIONS = [(0.0, 0)] + [(a, t) for a in (0.005, 0.01, 0.02) for t in (30, 300, 1200)]
REFERENCE = (0.01, 300)
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


def k1_problems(k1: dict) -> list[str]:
    meta = k1["meta"]
    problems = []
    if meta["refractory_pulses"] != 0:
        problems.append("不応期が 0 ではない")
    if meta["seeds"] != EXPECTED_SEEDS or meta["silent_pulses"] != 3600:
        problems.append("seed または Pulse 数が事前登録と違う")
    if [tuple(c) for c in meta["conditions"]] != EXPECTED_CONDITIONS:
        problems.append("条件が事前登録と違う")
    got = [(r["alpha"], r["tau"], r["seed"]) for r in k1["runs"]]
    expected = {(a, t, s) for a, t in EXPECTED_CONDITIONS for s in EXPECTED_SEEDS}
    if len(got) != len(set(got)) or set(got) != expected:
        problems.append(f"K1 の本数が足りない／重複がある（{len(set(got))}/{len(expected)}）")
    return problems


def short_intervals(runs: list[dict]) -> dict:
    """発火の間隔が 1〜3 Pulse だった回数（不応期 3 では起きえない）。条件ごとの合計。"""
    out: dict[str, int] = {}
    for r in runs:
        key = f"{r['alpha']}/{r['tau']}"
        n = 0
        for u in UNITS:
            p = r["fires"].get(u, [])
            n += sum(1 for a, b in zip(p, p[1:]) if b - a <= 3)
        out[key] = out.get(key, 0) + n
    return out


def above_grid(data: dict) -> dict:
    """w* が「0.6 より上」（0.6 でもすぐには発火しなかった）だった個体の数。条件・枝ごと。"""
    stars = A8.w_stars(data["runs"])
    out: dict[str, int] = {}
    for (a, t, _seed, branch), star in stars.items():
        key = f"{a}/{t} {branch}"
        out[key] = out.get(key, 0) + (star == math.inf)
    return out


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    k1, k2 = read(directory / "k1.json.gz"), read(directory / "k2.json.gz")
    problems = k1_problems(k1) + A5.completeness_problems(k2)
    if k2["meta"].get("refractory_pulses") != 0:
        problems.append("K2 の不応期が 0 ではない")
    valid = not problems

    h1_report = A4.analyze_silent(k1["runs"])
    h1_per_cond = {c: r["holds"] for c, r in h1_report.items()}
    k1_supported = all(h1_per_cond[c] for c in A4.H1_REFERENCE)
    h2_report = A5.analyze(k2)
    k2_supported = all(h2_report[c]["holds"] for c in A5.H2_REFERENCE)
    if k1_supported and k2_supported:
        chosen = A5.choose_reference(h1_per_cond, True, h2_report)
        k3 = {"applied": True, "chosen": list(chosen) if chosen else None,
              "same_as_reference": chosen == REFERENCE}
    else:
        k3 = {"applied": False, "chosen": None, "same_as_reference": None}

    baseline = read(BASELINE_0008)
    report = {
        "git_commit": k1["meta"]["git_commit"],
        "valid": valid,
        "problems": problems,
        "K1": {"supported": k1_supported if valid else None,
               "conditions": {f"{a}/{t}": {"calmed_seeds": h1_report[(a, t)]["calmed_seeds"],
                                           "holds": h1_report[(a, t)]["holds"]}
                              for a, t in EXPECTED_CONDITIONS}},
        "K2": {"supported": k2_supported if valid else None,
               "conditions": {f"{a}/{t}": {"difference_from_alpha0": round(h2_report[(a, t)]["difference_from_alpha0"], 3),
                                           "holds": h2_report[(a, t)]["holds"]}
                              for a, t in EXPECTED_CONDITIONS}},
        "K3": k3 if valid else None,
        "reference_values_keep_basis": (valid and k1_supported and k2_supported and bool(k3["same_as_reference"])),
        "records": {
            "refractory_3_new_runtime_0008": A8.records({"OLD": [], "NEW": baseline["NEW"]}),
            "refractory_0": A8.records({"OLD": [], "NEW": k1["runs"]}),
            "short_intervals_refractory_3": short_intervals(baseline["NEW"]),
            "short_intervals_refractory_0": short_intervals(k1["runs"]),
            "w_star_above_grid_refractory_3_0005": above_grid(read(RESULTS_0005)),
            "w_star_above_grid_refractory_0": above_grid(k2),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
