"""実験 0006 の集計（事前登録の一部。実行前にコミットする）。

使い方:
  python experiments/0006_pending_compute/analyze.py data/experiments/0006/results.json.gz

標準ライブラリだけで動く。判定の基準はすべてこのファイルの定数として固定する。
"""

import argparse
import gzip
import json
import statistics
import sys
from collections import defaultdict

# ---- 事前登録した実行条件 ----------------------------------------------------------
EXPECTED = {"pending_taus": [0, 2, 5, 10], "pending_floor": 0.1, "kernel_delays": [1, 3],
            "seeds": list(range(1, 21)), "pulses": 3600}

# ---- 判定 ---------------------------------------------------------------------------
JUDGED_TAUS = (5, 10)            # 判定に使う τ_p
INFORMATIVE_BASELINE = 3         # τ_p = 0 で取り残しのある個体がこれ以上いる遅延だけを H1 の判定に使う
H1_MAX_STARVED = 1               # 判定に使う τ_p で、取り残しのある個体が 20 中これ以下
H2_MIN_RECOVERY = 0.5            # 負けた要求のエピソードのうち、後で計算が始まった割合がこれ以上
STARTED, REJECTED, BUSY = "started", "rejected_capacity", "dropped_busy"
CONTINUING = ("pending", "merged")  # 前のエピソードを引き継ぐ要求の由来。"firing" は新しいエピソード


def completeness_problems(data: dict) -> list[str]:
    meta = data["meta"]
    problems = [f"{k} が事前登録と違う: {meta.get(k)}"
                for k, v in EXPECTED.items() if json.loads(json.dumps(meta.get(k))) != v]
    expected = {(d, t, s) for d in EXPECTED["kernel_delays"] for t in EXPECTED["pending_taus"]
                for s in EXPECTED["seeds"]}
    got = [(r["delay"], r["pending_tau"], r["seed"]) for r in data["runs"]]
    if len(got) != len(set(got)):
        problems.append("重複がある")
    if set(got) != expected:
        problems.append(f"本数が足りない／余分がある（{len(set(got))}/{len(expected)}）")
    return problems


def starved_units(run: dict) -> list[str]:
    """claim を出したのに、一度も計算が始まらなかった Unit。"""
    claimed = {c[1] for c in run["claims"]}
    got = {c[1] for c in run["claims"] if c[4] == STARTED}
    return sorted(claimed - got)


def episodes(run: dict) -> list[dict]:
    """同じ Unit の、連続する Pulse の要求の並びを 1 つのエピソードにまとめる。

    エピソードは、要求が「容量の取り合いに負けた」で終わらない限り終わる（始まった／busy で捨てた）。
    負けたあと次の Pulse の要求が持ち越しの再提示（pending）か統合（merged）なら同じエピソードを続ける。
    次の Pulse に要求がない、または持ち越しを諦めた直後の新しい発火（firing）なら、前のエピソードは
    「諦めた」で終わり、新しいエピソードが始まる。
    """
    by_unit: dict[str, list] = defaultdict(list)
    for pulse, unit, origin, strength, outcome in run["claims"]:
        by_unit[unit].append((pulse, origin, outcome))
    result = []
    for unit, claims in by_unit.items():
        current: list = []
        for claim in claims:
            continues = (claim[0] == current[-1][0] + 1 and current[-1][2] == REJECTED
                         and claim[1] in CONTINUING) if current else False
            if current and not continues:
                result.append(_close(unit, current))
                current = []
            current.append(claim)
        if current:
            result.append(_close(unit, current))
    return result


def _close(unit: str, claims: list) -> dict:
    last = claims[-1][2]
    end = {STARTED: "started", BUSY: "busy"}.get(last, "gave_up")
    rejected = any(c[2] == REJECTED for c in claims)
    return {"unit": unit, "start": claims[0][0], "length": len(claims), "end": end,
            "rejected": rejected, "wait": claims[-1][0] - claims[0][0] if end == "started" else None,
            "retries": sum(c[1] in CONTINUING for c in claims)}


def analyze(data: dict) -> dict:
    runs = {(r["delay"], r["pending_tau"], r["seed"]): r for r in data["runs"]}
    report: dict = {}
    for delay in EXPECTED["kernel_delays"]:
        for tau in EXPECTED["pending_taus"]:
            rows = []
            for seed in EXPECTED["seeds"]:
                r = runs[(delay, tau, seed)]
                eps = episodes(r)
                rej = [e for e in eps if e["rejected"]]
                rows.append({
                    "seed": seed,
                    "starved": starved_units(r),
                    "rejected_episodes": len(rej),
                    "recovered": sum(e["end"] == "started" for e in rej),
                    "waits": [e["wait"] for e in rej if e["end"] == "started"],
                    "tasks": len(r["started"]),
                    "claims": len(r["claims"]),
                    "retries": sum(c[2] in CONTINUING for c in r["claims"]),
                    "without_evidence": sum(s[2] for s in r["started"]),
                    "effects": r["effects"],
                    "fires": sum(v[-1][1] for v in r["fire_counts"].values()),
                })
            rej_total = sum(x["rejected_episodes"] for x in rows)
            waits = [w for x in rows for w in x["waits"]]
            tasks = sum(x["tasks"] for x in rows)
            report[(delay, tau)] = {
                "rows": rows,
                "starved_seeds": sum(bool(x["starved"]) for x in rows),
                "starved_units": sorted({u for x in rows for u in x["starved"]}),
                "recovery": (sum(x["recovered"] for x in rows) / rej_total) if rej_total else None,
                "rejected_episodes": rej_total,
                "median_wait": statistics.median(waits) if waits else None,
                "tasks": tasks,
                "claims": sum(x["claims"] for x in rows),
                "retries": sum(x["retries"] for x in rows),
                "without_evidence_ratio": (sum(x["without_evidence"] for x in rows) / tasks) if tasks else None,
                "effects": sum(x["effects"] for x in rows),
                "fires": sum(x["fires"] for x in rows),
            }
    return report


def cell_holds(report: dict, delay: int, tau: int, informative: bool) -> dict:
    r = report[(delay, tau)]
    h1 = (r["starved_seeds"] <= H1_MAX_STARVED) if informative else None
    h2 = r["recovery"] is not None and r["recovery"] >= H2_MIN_RECOVERY
    return {"h1": h1, "h2": h2}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    args = parser.parse_args()
    with gzip.open(args.results, "rt", encoding="utf-8") as f:
        data = json.load(f)
    problems = completeness_problems(data)
    if problems:
        print("事前登録した実行条件とそろっていないので判定しません（判定不能）:\n  " + "\n  ".join(problems))
        return 2
    print(f"commit={data['meta']['git_commit']}")
    report = analyze(data)
    informative = {d: report[(d, 0)]["starved_seeds"] >= INFORMATIVE_BASELINE for d in EXPECTED["kernel_delays"]}

    for delay in EXPECTED["kernel_delays"]:
        print(f"\n## Kernel の推論時間 {delay} 秒"
              f"（τ_p=0 の取り残し {report[(delay, 0)]['starved_seeds']} 個体 → H1 の判定に{'使う' if informative[delay] else '使わない'}）")
        print("τ_p | 取り残しのある個体 | 取り残された Unit | 負けたエピソード | 回収率 | 待ちの中央値 | 計算の総数 | claim 総数（うち再提示） | 根拠なしの割合 | 発話 | 発火の総数")
        base = report[(delay, 0)]
        for tau in EXPECTED["pending_taus"]:
            r = report[(delay, tau)]
            c = cell_holds(report, delay, tau, informative[delay])
            marks = ""
            if tau in JUDGED_TAUS:
                marks = f"  [H1 {'-' if c['h1'] is None else ('✓' if c['h1'] else '✗')} / H2 {'✓' if c['h2'] else '✗'}]"
            rec = "-" if r["recovery"] is None else f"{r['recovery']:.2f}"
            wait = "-" if r["median_wait"] is None else f"{r['median_wait']:g}"
            wer = "-" if r["without_evidence_ratio"] is None else f"{r['without_evidence_ratio']:.2f}"
            print(f"{tau} | {r['starved_seeds']}/20 | {','.join(r['starved_units']) or '-'} | {r['rejected_episodes']} | {rec} | "
                  f"{wait} | {r['tasks']}（×{r['tasks'] / base['tasks']:.2f}） | {r['claims']}（{r['retries']}） | {wer} | "
                  f"{r['effects']} | {r['fires']}（×{r['fires'] / base['fires']:.2f}）{marks}")

        sentinel = []
        for row0 in base["rows"]:
            for unit in row0["starved"]:
                after = {tau: unit not in next(x for x in report[(delay, tau)]["rows"] if x["seed"] == row0["seed"])["starved"]
                         for tau in JUDGED_TAUS}
                sentinel.append(f"seed {row0['seed']} {unit}: " + " ".join(f"τ_p={t} {'解消' if v else '残る'}" for t, v in after.items()))
        if sentinel:
            print("記録（τ_p=0 で取り残された Unit のその後）：\n  " + "\n  ".join(sentinel))

    judged_delays = [d for d in EXPECTED["kernel_delays"] if informative[d]]
    h1 = bool(judged_delays) and all(cell_holds(report, d, t, True)["h1"] for d in judged_delays for t in JUDGED_TAUS)
    h2 = all(cell_holds(report, d, t, informative[d])["h2"] for d in EXPECTED["kernel_delays"] for t in JUDGED_TAUS)
    print(f"\n判定：H1（観測期間内の取り残しがほぼなくなる）{'判定不能（基準の取り残しが少ない）' if not judged_delays else ('支持' if h1 else '不支持')}"
          f" / H2（負けた要求が後で計算される）{'支持' if h2 else '不支持'}")

    print("\n## 参照値（H1・H2 の正式判定がともに支持された場合に限る）")
    if not (h1 and h2):
        print("→ 該当なし（参照値は決めない）")
        return 0
    candidates = [t for t in EXPECTED["pending_taus"] if t > 0 and all(
        (cell_holds(report, d, t, True)["h1"] if informative[d] else True) and cell_holds(report, d, t, informative[d])["h2"]
        for d in EXPECTED["kernel_delays"])]
    print(f"→ τ_p = {min(candidates)} 秒（p_min = {EXPECTED['pending_floor']} に固定した条件で）" if candidates else "→ 該当なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
