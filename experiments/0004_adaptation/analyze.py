"""実験 0004 の集計（事前登録の一部。実行前にコミットする）。

使い方:
  python experiments/0004_adaptation/analyze.py data/experiments/0004/results.json.gz

標準ライブラリだけで動く。判定の基準はすべてこのファイルの定数として固定する。
"""

import argparse
import gzip
import json
import statistics
import sys
from collections import defaultdict

UNITS = ("u0", "u1", "u2", "u3")

# ---- H1：入力なしで落ち着くか ----------------------------------------------------
EARLY = (1, 600)             # 序盤 10 分
LATE = (1801, 3600)          # 終盤 30 分
H1_MIN_SEEDS = 16            # 20 個体中 16 個体以上で成り立てば、その条件で「落ち着く」
H1_REFERENCE = [(0.01, 300), (0.01, 1200), (0.02, 300), (0.02, 1200)]  # 単一 Unit の予備計算から効くと予測した条件

# ---- H2：同じ probe に対する反応が、直前の発火履歴で変わるか ------------------------
PROBE_VISIBLE = 651          # probe は 650 Pulse に入り、651 Pulse から u0 に見える
RESPONSE_WINDOW = (651, 653)  # u0 がこの間に発火したら「反応した」
COUNT_WINDOW = (651, 670)    # この間の u0・u1・u2 の発火回数
H2_WEIGHT = 0.6              # 判定に使う probe の強さ（閾値付近）。1.0 は記録のみ
H2_MIN_DIFFERENCE = 0.3      # 「conditioning 側が弱く反応した個体の割合」が α = 0 より 0.3 以上高い
H2_REFERENCE = H1_REFERENCE


def in_window(pulses: list[int], window: tuple[int, int]) -> int:
    lo, hi = window
    return sum(lo <= p <= hi for p in pulses)


def total_fires(run: dict, window: tuple[int, int], units=UNITS) -> int:
    return sum(in_window(run["fires"].get(u, []), window) for u in units)


def periodic_pattern(pulses: list[int]) -> str:
    """間隔の並びが k 個ごとに繰り返すか（±1 Pulse、9 割以上）。k = 1〜4。見つからなければ 'none'。"""
    iv = [b - a for a, b in zip(pulses, pulses[1:])]
    if len(iv) < 8:
        return "few"
    for k in range(1, 5):
        pairs = [(iv[i], iv[i + k]) for i in range(len(iv) - k)]
        if sum(abs(a - b) <= 1 for a, b in pairs) >= 0.9 * len(pairs):
            return f"period-{k}"
    return "none"


def cv(pulses: list[int]) -> float | None:
    iv = [b - a for a, b in zip(pulses, pulses[1:])]
    if len(iv) < 2:
        return None
    m = statistics.fmean(iv)
    return statistics.pstdev(iv) / m if m else None


def key(r: dict) -> tuple[float, float]:
    return (r["alpha"], r["tau"])


# ---- パート A ---------------------------------------------------------------------

def analyze_silent(silent: list[dict]) -> dict:
    by_cond: dict[tuple, dict[int, dict]] = defaultdict(dict)
    for r in silent:
        by_cond[key(r)][r["seed"]] = r
    baseline = by_cond[(0.0, 0)]
    report = {}
    for cond, runs in sorted(by_cond.items()):
        rows = []
        for seed, r in sorted(runs.items()):
            early = total_fires(r, EARLY) / (EARLY[1] - EARLY[0] + 1) * 600
            late = total_fires(r, LATE) / (LATE[1] - LATE[0] + 1) * 600
            base_late = total_fires(baseline[seed], LATE) / (LATE[1] - LATE[0] + 1) * 600
            late_window = {u: [p for p in r["fires"].get(u, []) if LATE[0] <= p <= LATE[1]] for u in UNITS}
            last_adapt = {u: (r["adaptation"].get(u) or [[0, 0.0]])[-1][1] for u in UNITS}
            rows.append({
                "seed": seed,
                "early_per_10min": early,
                "late_per_10min": late,
                "baseline_late_per_10min": base_late,
                "calmed": late < early and late < base_late,
                "patterns": {u: periodic_pattern(late_window[u]) for u in UNITS},
                "cv": {u: cv(late_window[u]) for u in UNITS},
                "adaptation_end": last_adapt,
                "utterances": len(r["effects"]),
                "u2_accepted": r["accepted"].get("u2", 0),
            })
        calmed = sum(row["calmed"] for row in rows)
        report[cond] = {
            "rows": rows,
            "calmed_seeds": calmed,
            "holds": calmed >= H1_MIN_SEEDS,
            "mean_early": statistics.fmean(r["early_per_10min"] for r in rows),
            "mean_late": statistics.fmean(r["late_per_10min"] for r in rows),
            "mean_utterances": statistics.fmean(r["utterances"] for r in rows),
            "u2_accepted_seeds": sum(r["u2_accepted"] > 0 for r in rows),
        }
    return report


# ---- パート B ---------------------------------------------------------------------

def response(run: dict) -> tuple[int, int]:
    reacted = int(in_window(run["fires"].get("u0", []), RESPONSE_WINDOW) > 0)
    count = total_fires(run, COUNT_WINDOW, units=("u0", "u1", "u2"))
    return reacted, count


def compare(adapted: dict, rested: dict) -> str:
    ra, ca = response(adapted)
    rr, cr = response(rested)
    if (ra, ca) == (rr, cr):
        return "same"
    if ra < rr or (ra == rr and ca < cr):
        return "weaker"
    return "stronger"


def analyze_probe(probe: list[dict]) -> dict:
    report: dict = {}
    for weight in sorted({r["weight"] for r in probe}):
        rows_by_cond: dict[tuple, list[str]] = defaultdict(list)
        for r in probe:
            if r["weight"] == weight:
                rows_by_cond[key(r)].append(compare(r["adapted"], r["rested"]))
        base = rows_by_cond[(0.0, 0)]
        base_weaker = base.count("weaker") / len(base)
        per_cond = {}
        for cond, outcomes in sorted(rows_by_cond.items()):
            n = len(outcomes)
            weaker = outcomes.count("weaker") / n
            per_cond[cond] = {
                "weaker": weaker,
                "stronger": outcomes.count("stronger") / n,
                "same": outcomes.count("same") / n,
                "difference_from_alpha0": weaker - base_weaker,
                "holds": cond != (0.0, 0) and weaker - base_weaker >= H2_MIN_DIFFERENCE,
            }
        report[weight] = per_cond
    return report


# ---- 出力 ----------------------------------------------------------------------

def fmt_cond(cond: tuple) -> str:
    a, t = cond
    return "α=0（順応なし）" if a == 0 else f"α={a} τ={t}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    args = parser.parse_args()
    with gzip.open(args.results, "rt", encoding="utf-8") as f:
        data = json.load(f)
    meta = data["meta"]
    if meta.get("quick"):
        print("quick（動作確認用）の結果なので判定しません")
        return 2
    print(f"commit={meta['git_commit']}  seeds={len(meta['seeds'])}")

    silent = analyze_silent(data["silent"])
    print("\n## パート A：入力なし 3600 Pulse（発火回数は全 Unit の合計、10 分あたり）")
    print("条件 | 序盤 | 終盤 | 落ち着いた個体 | 発話回数（平均） | u2 が実行権を得た個体 | 終盤の周期パターン（u1）")
    for cond, r in silent.items():
        patterns = defaultdict(int)
        for row in r["rows"]:
            patterns[row["patterns"]["u1"]] += 1
        print(f"{fmt_cond(cond)} | {r['mean_early']:.1f} | {r['mean_late']:.1f} | "
              f"{r['calmed_seeds']}/{len(r['rows'])}{' ✓' if r['holds'] else ''} | "
              f"{r['mean_utterances']:.0f} | {r['u2_accepted_seeds']} | {dict(patterns)}")
    h1 = all(silent[c]["holds"] for c in H1_REFERENCE)

    probe = analyze_probe(data["probe"])
    print("\n## パート B：同じ seed から分岐（conditioning あり／なし）→ 同じ probe")
    for weight, per_cond in probe.items():
        label = "判定" if weight == H2_WEIGHT else "記録のみ"
        print(f"\n### probe の重み {weight}（{label}）")
        print("条件 | 弱く反応 | 強く反応 | 同じ | α=0 との差")
        for cond, r in per_cond.items():
            print(f"{fmt_cond(cond)} | {r['weaker']:.2f} | {r['stronger']:.2f} | {r['same']:.2f} | "
                  f"{r['difference_from_alpha0']:+.2f}{' ✓' if r['holds'] else ''}")
    h2 = all(probe[H2_WEIGHT][c]["holds"] for c in H2_REFERENCE)

    print(f"\n判定：H1（落ち着く）{'支持' if h1 else '不支持'} / H2（履歴依存）{'支持' if h2 else '不支持'}")
    print("（判定に使う条件：" + ", ".join(fmt_cond(c) for c in H1_REFERENCE) + "）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
