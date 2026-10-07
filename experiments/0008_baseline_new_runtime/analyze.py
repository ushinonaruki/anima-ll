"""実験 0008 の判定（事前登録の一部。測定の前にコミットする）。

1. 前提：OLD の発火が 0004 の results.json.gz（パート A）と、全 200 本で Unit ごとに完全一致する
2. H1-new：0004 の analyze_silent（同じ基準）を NEW に当てはめ、
   α ∈ {0.01, 0.02} × τ_a ∈ {300, 1200} の 4 条件すべてで「落ち着く」（20 個体中 16 以上）なら支持
3. 0005 の再現：0005 の手順を NEW で回した結果の w*（0005 の w_star と同じ定義）が、
   0005 の results.json.gz と全組（10 条件 × 20 個体 × 2 枝）で完全一致する
4. 参照値（α = 0.01・τ_a = 300）が新しい基盤の上でも根拠を保つ ＝ 2 と 3 の両方

記録（判定には使わない）：条件ごとの発火・計算・列・待ち時間・発話・旧基盤が捨てていた割合

使い方:
  python experiments/0008_baseline_new_runtime/analyze.py [data/experiments/0008]
"""

import gzip
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_DIR = Path("data/experiments/0008")
RESULTS_0004 = Path("experiments/0004_adaptation/results.json.gz")
RESULTS_0005 = Path("experiments/0005_response_threshold/results.json.gz")
UNITS = ("u0", "u1", "u2", "u3")
EXPECTED_SEEDS = list(range(1, 21))
EXPECTED_CONDITIONS = [(0.0, 0)] + [(a, t) for a in (0.005, 0.01, 0.02) for t in (30, 300, 1200)]
REFERENCE = (0.01, 300)


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A4 = load_module("analyze_0004", "experiments/0004_adaptation/analyze.py")
A5 = load_module("analyze_0005", "experiments/0005_response_threshold/analyze.py")


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def completeness(data: dict) -> list[str]:
    problems = []
    meta = data["meta"]
    if meta["seeds"] != EXPECTED_SEEDS:
        problems.append(f"seed が 1〜20 ではない: {meta['seeds']}")
    if [tuple(c) for c in meta["conditions"]] != EXPECTED_CONDITIONS:
        problems.append("条件が事前登録と違う")
    if meta["silent_pulses"] != 3600:
        problems.append("Pulse 数が 3600 ではない")
    expected = {(a, t, s) for a, t in EXPECTED_CONDITIONS for s in EXPECTED_SEEDS}
    for impl in ("OLD", "NEW"):
        got = [(r["alpha"], r["tau"], r["seed"]) for r in data[impl]]
        if len(got) != len(set(got)) or set(got) != expected:
            problems.append(f"{impl} の本数が足りない／重複がある（{len(set(got))}/{len(expected)}）")
    return problems


def old_reproduces_0004(data: dict) -> tuple[bool, list]:
    ref = {(r["alpha"], r["tau"], r["seed"]): r["fires"] for r in read(RESULTS_0004)["silent"]}
    mismatched = [(r["alpha"], r["tau"], r["seed"]) for r in data["OLD"]
                  if ref.get((r["alpha"], r["tau"], r["seed"])) != r["fires"]]
    return not mismatched, mismatched


def h1_new(data: dict) -> tuple[bool | None, dict]:
    report = A4.analyze_silent(data["NEW"])
    per_cond = {f"{a}/{t}": {"calmed_seeds": report[(a, t)]["calmed_seeds"], "holds": report[(a, t)]["holds"]}
                for a, t in EXPECTED_CONDITIONS}
    supported = all(report[c]["holds"] for c in A4.H1_REFERENCE)
    # どちらの比較（序盤との比較／α = 0 との比較）が崩れたかを分けて記録する
    for a, t in EXPECTED_CONDITIONS:
        rows = report[(a, t)]["rows"]
        per_cond[f"{a}/{t}"]["late_lt_early"] = sum(r["late_per_10min"] < r["early_per_10min"] for r in rows)
        per_cond[f"{a}/{t}"]["late_lt_alpha0"] = sum(
            r["late_per_10min"] < r["baseline_late_per_10min"] for r in rows)
    return supported, per_cond


def w_stars(runs: list[dict]) -> dict:
    grouped: dict[tuple, dict[float, dict]] = defaultdict(dict)
    for r in runs:
        grouped[(r["alpha"], r["tau"], r["seed"], r["branch"])][r["weight"]] = r
    return {k: A5.w_star(v)[0] for k, v in grouped.items()}


def reproduces_0005(path: Path) -> tuple[bool | None, int, list]:
    if not path.exists():
        return None, 0, []
    new = read(path)
    problems = A5.completeness_problems(new)
    if problems:
        return False, 0, problems
    ref, got = w_stars(read(RESULTS_0005)["runs"]), w_stars(new["runs"])
    mismatched = [k for k in ref if ref[k] != got.get(k)]
    return not mismatched and set(ref) == set(got), len(ref), mismatched


# ---- 記録 --------------------------------------------------------------------------

def per_10min(pulses: list[int], window: tuple[int, int]) -> float:
    return A4.in_window(pulses, window) / (window[1] - window[0] + 1) * 600


def slope(values: list[int]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = range(n)
    mx, my = (n - 1) / 2, statistics.fmean(values)
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / sum((x - mx) ** 2 for x in xs)


def quantile(values: list[int], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def records(data: dict) -> dict:
    out = {}
    for impl in ("OLD", "NEW"):
        by_cond: dict[tuple, list[dict]] = defaultdict(list)
        for r in data[impl]:
            by_cond[(r["alpha"], r["tau"])].append(r)
        for (a, t), runs in sorted(by_cond.items()):
            row: dict = {
                "early_fires_per_10min": statistics.fmean(
                    sum(per_10min(r["fires"].get(u, []), A4.EARLY) for u in UNITS) for r in runs),
                "late_fires_per_10min": statistics.fmean(
                    sum(per_10min(r["fires"].get(u, []), A4.LATE) for u in UNITS) for r in runs),
                "late_fires_per_10min_by_unit": {
                    u: statistics.fmean(per_10min(r["fires"].get(u, []), A4.LATE) for r in runs) for u in UNITS},
                "utterances": statistics.fmean(len(r["effects"]) for r in runs),
                "computed_by_unit": {u: statistics.fmean(r["accepted"].get(u, 0) for r in runs)
                                     for u in ("u1", "u2", "u3")},
                "seeds_where_u2_computed": sum(r["accepted"].get("u2", 0) > 0 for r in runs),
            }
            if impl == "OLD":
                claims = sum(sum(r["old"]["claims"].values()) for r in runs if r["old"])
                dropped = sum(sum(r["old"]["rejected"].values()) + sum(r["old"]["busy_dropped"].values())
                              for r in runs if r["old"])
                row["requests"] = claims / len(runs)
                row["dropped_ratio"] = dropped / claims if claims else None
                row["dropped_ratio_by_unit"] = {
                    u: (lambda c, d: d / c if c else None)(
                        sum(r["old"]["claims"].get(u, 0) for r in runs if r["old"]),
                        sum(r["old"]["rejected"].get(u, 0) + r["old"]["busy_dropped"].get(u, 0)
                            for r in runs if r["old"]))
                    for u in ("u1", "u2", "u3")}
            else:
                news = [r["new"] for r in runs if r["new"]]
                waits = [w for n in news for w in n["waits"]]
                row["intents"] = statistics.fmean(sum(n["created"].values()) for n in news) if news else 0
                row["completed"] = statistics.fmean(sum(n["completed"].values()) for n in news) if news else 0
                row["queue_max"] = max((max(n["waiting"]) for n in news), default=0)
                row["queue_mean"] = statistics.fmean(statistics.fmean(n["waiting"]) for n in news) if news else 0
                row["queue_end_mean"] = statistics.fmean(n["waiting"][-1] for n in news) if news else 0
                row["queue_late_slope_mean"] = statistics.fmean(
                    slope(n["waiting"][A4.LATE[0] - 1:A4.LATE[1]]) for n in news) if news else 0
                row["seeds_with_growing_queue"] = sum(
                    slope(n["waiting"][A4.LATE[0] - 1:A4.LATE[1]]) > 0.001 for n in news)
                row["wait_median"] = quantile(waits, 0.5)
                row["wait_p90"] = quantile(waits, 0.9)
                row["wait_max"] = max(waits, default=None)
                row["overflow"] = sum(n["overflow"] for n in news)
            out[f"{impl} {a}/{t}"] = row
    return out


def main() -> None:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    data = read(directory / "results.json.gz")
    problems = completeness(data)
    repro_ok, repro_mismatch = old_reproduces_0004(data)
    supported, h1_detail = h1_new(data)
    r5, r5_compared, r5_mismatch = reproduces_0005(directory / "0005_new.json.gz")
    valid = not problems and repro_ok
    report = {
        "git_commit": data["meta"]["git_commit"],
        "complete": not problems,
        "problems": problems,
        "precondition_old_reproduces_0004": repro_ok,
        "precondition_mismatches": repro_mismatch[:20],
        "valid": valid,
        "H1_new": {"supported": supported if valid else None, "conditions": h1_detail},
        "reproduces_0005": {"reproduced": r5, "compared": r5_compared, "mismatches": r5_mismatch[:20]},
        "reference_values_keep_basis": (valid and bool(supported) and bool(r5)) if valid and r5 is not None else None,
        "records": records(data),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
