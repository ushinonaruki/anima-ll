"""実験 0005 の集計（事前登録の一部。実行前にコミットする）。

使い方:
  python experiments/0005_response_threshold/analyze.py data/experiments/0005/results.json.gz \
      --with-0004 experiments/0004_adaptation/results.json.gz

--with-0004 を渡すと、事前に決めた規則で標準の α・τ_a を選ぶ（§ 参照値の選び方）。
標準ライブラリだけで動く。判定の基準はすべてこのファイルの定数として固定する。
"""

import argparse
import gzip
import importlib.util
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

# ---- 事前登録した実行条件 ----------------------------------------------------------
EXPECTED_SEEDS = list(range(1, 21))
EXPECTED_CONDITIONS = [(0.0, 0)] + [(a, t) for a in (0.005, 0.01, 0.02) for t in (30, 300, 1200)]
EXPECTED_PROTOCOL = {"conditioning": [600, 605, 610, 615, 620], "probe": 650, "pulses": 700,
                     "probe_weights": [0.0, 0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, 0.40, 0.60],
                     "conditioning_weight": 1.0}
BRANCHES = ("rested", "adapted")

# ---- 判定 ---------------------------------------------------------------------------
IMMEDIATE = 651              # probe が u0 に見える Pulse。ここで発火したら「すぐに発火した」
H2_REFERENCE = [(0.01, 300), (0.01, 1200), (0.02, 300), (0.02, 1200)]
H2_MIN_DIFFERENCE = 0.3      # 「adapted の w* が rested より高い個体の割合」が α = 0 より 0.3 以上高い
LATENCY_WINDOW = 20          # 記録：probe の後この Pulse 数までの最初の発火を潜時とする
ABOVE_GRID = math.inf        # 0.6 でもすぐには発火しなかった（不応期など）


def completeness_problems(data: dict) -> list[str]:
    meta = data["meta"]
    problems = []
    if list(meta.get("seeds", [])) != EXPECTED_SEEDS:
        problems.append(f"seed が 1〜20 ではない: {meta.get('seeds')}")
    if json.loads(json.dumps(meta.get("protocol"))) != EXPECTED_PROTOCOL:
        problems.append(f"手順が事前登録と違う: {meta.get('protocol')}")
    if [tuple(c) for c in meta.get("conditions", [])] != EXPECTED_CONDITIONS:
        problems.append(f"条件が事前登録と違う: {meta.get('conditions')}")
    expected = {(a, t, s, b, w) for a, t in EXPECTED_CONDITIONS for s in EXPECTED_SEEDS
                for b in BRANCHES for w in EXPECTED_PROTOCOL["probe_weights"]}
    got = [(r["alpha"], r["tau"], r["seed"], r["branch"], r["weight"]) for r in data["runs"]]
    if len(got) != len(set(got)):
        problems.append("重複がある")
    if set(got) != expected:
        problems.append(f"本数が足りない／余分がある（{len(set(got))}/{len(expected)}）")
    return problems


def w_star(runs_by_weight: dict[float, dict]) -> tuple[float, bool]:
    """すぐに発火した最小の強さと、強さについて単調だったか（強くすれば必ず発火したか）。"""
    fired = {w: IMMEDIATE in r["fires"].get("u0", []) for w, r in runs_by_weight.items()}
    weights = sorted(fired)
    star = next((w for w in weights if fired[w]), ABOVE_GRID)
    monotonic = all(fired[w] for w in weights if w >= star) if star != ABOVE_GRID else True
    return star, monotonic


def margin(state: dict) -> float | None:
    """651 Pulse に u0 がすぐ発火するために、あと必要だった入力の量（モデル式から計算。記録用）。"""
    if not state:
        return None
    dyn = state["dynamics"]
    if state["refractory_remaining"] > 0:
        return ABOVE_GRID
    tau = dyn["adaptation_tau_seconds"]
    adaptation = state["adaptation"] * (math.exp(-1 / tau) if tau > 0 else 1.0)
    activity = state["activity"] * dyn["decay_per_second"] + dyn["intrinsic_drive_per_second"]
    return dyn["threshold"] + adaptation - activity


def latency(run: dict) -> int | None:
    after = [p - IMMEDIATE for p in run["fires"].get("u0", []) if IMMEDIATE <= p < IMMEDIATE + LATENCY_WINDOW]
    return after[0] if after else None


def fmt_w(w: float) -> str:
    return ">0.6" if w == ABOVE_GRID else f"{w:g}"


def fmt_cond(cond: tuple) -> str:
    a, t = cond
    return "α=0（順応なし）" if a == 0 else f"α={a} τ={t}"


def analyze(data: dict) -> dict:
    grouped: dict[tuple, dict[float, dict]] = defaultdict(dict)
    for r in data["runs"]:
        grouped[(r["alpha"], r["tau"], r["seed"], r["branch"])][r["weight"]] = r

    per_cond: dict[tuple, dict] = defaultdict(lambda: {"pairs": [], "nonmonotonic": 0})
    for (a, t, seed, branch), runs in grouped.items():
        if branch != "rested":
            continue
        rested_star, rm = w_star(runs)
        adapted_runs = grouped[(a, t, seed, "adapted")]
        adapted_star, am = w_star(adapted_runs)
        ref_w = EXPECTED_PROTOCOL["probe_weights"][-1]
        per_cond[(a, t)]["pairs"].append({
            "seed": seed,
            "rested": rested_star,
            "adapted": adapted_star,
            "rested_margin": margin(runs[0.0]["u0_state_650"]),
            "adapted_margin": margin(adapted_runs[0.0]["u0_state_650"]),
            "rested_adaptation": runs[0.0]["u0_state_650"].get("adaptation"),
            "adapted_adaptation": adapted_runs[0.0]["u0_state_650"].get("adaptation"),
            "latency": {b: {w: latency(grouped[(a, t, seed, b)][w]) for w in (0.05, 0.10, 0.20)} for b in BRANCHES},
            "max_weight_latency": {b: latency(grouped[(a, t, seed, b)][ref_w]) for b in BRANCHES},
        })
        per_cond[(a, t)]["nonmonotonic"] += (not rm) + (not am)

    report = {}
    for cond, r in sorted(per_cond.items()):
        pairs = sorted(r["pairs"], key=lambda p: p["seed"])
        n = len(pairs)
        higher = sum(p["adapted"] > p["rested"] for p in pairs) / n
        lower = sum(p["adapted"] < p["rested"] for p in pairs) / n
        report[cond] = {"pairs": pairs, "higher": higher, "lower": lower, "same": 1 - higher - lower,
                        "nonmonotonic": r["nonmonotonic"]}
    base = report[(0.0, 0)]["higher"]
    for cond, r in report.items():
        r["difference_from_alpha0"] = r["higher"] - base
        r["holds"] = cond != (0.0, 0) and r["higher"] - base >= H2_MIN_DIFFERENCE
    return report


# ---- 参照値の選び方（事前登録した規則） ----------------------------------------------

def load_0004_h1(path: Path) -> tuple[dict[tuple, bool], bool]:
    """0004 の条件ごとの H1 と、H1 の正式判定（判定用 4 条件すべてで成り立つか）。"""
    spec = importlib.util.spec_from_file_location("analyze_0004",
                                                  Path(__file__).parent.parent / "0004_adaptation" / "analyze.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    problems = module.completeness_problems(data)
    if problems:
        raise SystemExit("0004 の結果が事前登録とそろっていない: " + "; ".join(problems))
    per_cond = {cond: r["holds"] for cond, r in module.analyze_silent(data["silent"]).items()}
    return per_cond, all(per_cond[c] for c in module.H1_REFERENCE)


def choose_reference(h1: dict[tuple, bool], h1_supported: bool, h2: dict[tuple, dict]) -> tuple | None:
    """参照値を選ぶ。0004 の H1 と 0005 の H2' の正式判定が両方とも支持された場合に限る。

    そのときだけ、全 10 条件から「H1 を条件別に満たす」かつ「H2' を条件別に満たす」ものを候補にし、
    最も弱い順応を選ぶ。弱さ = α × τ_a（1 回の発火で生じる順応 a(t) = α·exp(−t/τ_a) の時間積分。
    1 回の発火が後の時間に残す順応の総量）。同じなら α が小さい方。
    """
    h2_supported = all(h2[c]["holds"] for c in H2_REFERENCE)
    if not (h1_supported and h2_supported):
        return None
    candidates = [c for c in h2 if c != (0.0, 0) and h1.get(c) and h2[c]["holds"]]
    if not candidates:
        return None
    return min(candidates, key=lambda c: (c[0] * c[1], c[0]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("--with-0004", type=Path, default=None)
    args = parser.parse_args()
    with gzip.open(args.results, "rt", encoding="utf-8") as f:
        data = json.load(f)
    problems = completeness_problems(data)
    if problems:
        print("事前登録した実行条件とそろっていないので判定しません（判定不能）:\n  " + "\n  ".join(problems))
        return 2
    print(f"commit={data['meta']['git_commit']}  seeds={len(data['meta']['seeds'])}")

    report = analyze(data)
    print("\n## u0 をすぐに発火させる最小の強さ w*（同じ個体の adapted と rested の比較）")
    print("条件 | adapted が高い | 低い | 同じ | α=0 との差 | w* の中央値（rested → adapted） | 必要な入力の量の中央値（rested → adapted、記録） | 単調でない")
    for cond, r in report.items():
        pairs = r["pairs"]
        med = lambda xs: statistics.median(xs)  # noqa: E731
        rm = med([p["rested"] for p in pairs])
        am = med([p["adapted"] for p in pairs])
        finite = lambda xs: [x for x in xs if x is not None and x != math.inf]  # noqa: E731
        mr = finite([p["rested_margin"] for p in pairs])
        ma = finite([p["adapted_margin"] for p in pairs])
        print(f"{fmt_cond(cond)} | {r['higher']:.2f} | {r['lower']:.2f} | {r['same']:.2f} | "
              f"{r['difference_from_alpha0']:+.2f}{' ✓' if r['holds'] else ''} | {fmt_w(rm)} → {fmt_w(am)} | "
              f"{(statistics.median(mr) if mr else float('nan')):.3f} → {(statistics.median(ma) if ma else float('nan')):.3f} | "
              f"{r['nonmonotonic']}")

    print("\n## 記録：probe（0.05 / 0.10 / 0.20）の後、u0 が最初に発火するまでの潜時の中央値（Pulse）")
    for cond, r in report.items():
        cells = []
        for b in BRANCHES:
            parts = []
            for w in (0.05, 0.10, 0.20):
                vals = [p["latency"][b][w] for p in r["pairs"] if p["latency"][b][w] is not None]
                parts.append(f"{statistics.median(vals):g}" if vals else "-")
            cells.append(f"{b} {'/'.join(parts)}")
        print(f"{fmt_cond(cond)} | " + " | ".join(cells))

    h2 = all(report[c]["holds"] for c in H2_REFERENCE)
    print(f"\n判定：H2（発火履歴で、発火に必要な最小の入力が上がる）{'支持' if h2 else '不支持'}")
    print("（判定に使う条件：" + ", ".join(fmt_cond(c) for c in H2_REFERENCE) + "）")

    if args.with_0004:
        h1, h1_supported = load_0004_h1(args.with_0004)
        chosen = choose_reference(h1, h1_supported, report)
        print("\n## 参照値（H1・H2' の正式判定が両方支持された場合に限り、条件別に両方を満たす中で最も弱い順応）")
        print(f"0004 H1：{'支持' if h1_supported else '不支持'} / 0005 H2'：{'支持' if h2 else '不支持'}")
        print(f"→ {fmt_cond(chosen)}" if chosen else "→ 該当なし（参照値は決めない）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
