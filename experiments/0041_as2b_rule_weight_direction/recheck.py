"""実験 0041 の独立の検算（README §9.1。標準のライブラリだけ）。

この実験の解析・測定の道具も、anima_ll も、AS2b の道具も、protocol.yaml を読む道具も読み込まない。保存した生の記録
（seeds/<seed>/raw.json.gz）だけから、定義（README §3〜§6）を書き起こし直して report の欄をすべて組み立て直し、report.json と
欄ごとに照合する。判定の閾値などの事前登録の値は、README・protocol.yaml（v0.1。#189 merge `5fba79f`）から書き起こした
PREREGISTERED から取る。生の記録の meta に保存された protocol の写し（meta.protocol・meta.protocol_sha256）は、次のことを確かめる
だけに使う（0040 の道具 v0.3 と同じ形）
- 全個体にあり、全個体で同じであること
- 写しの中身全体を JSON に正規化したもののハッシュが、事前登録 v0.1 の protocol の固定のハッシュ（PROTOCOL_JSON_SHA256）と同じであること
  （PREREGISTERED で個別に照らさない欄の改変も見つける）
- SHA-256 が、リポジトリの確定済みの protocol.yaml のバイト列の SHA-256（PROTOCOL_FILE_SHA256）と同じであること
- 写しの中の判定に関わる値が、PREREGISTERED と同じであること。k₂(200) は、二項から求め直した値と同じであること
どれかが欠けたり違ったりすれば、食い違いとして数える。

report との照合（recheck）
- 生の記録から、report と同じ形の期待値を作る：mode・valid・O1・関門の宣言の SHA-256、判定 J_B、推定 E_B、§6.1 の必ず報告する記述
  （k* がある個体での δ、δ^←、ε、(sign q_1, sign q_2) の表、0 の個体の表）、個体ごとの量（窓の数・k*・札・δ・q_1・q_2・δ^←・ε・
  重み・差・組の和のずれ・窓の境界の重みと δ の符号・結果の刺激・最初に分かれた Pulse と窓・発火の数）、補助の記録 R1〜R8
- 期待値と report を、欄の組・列の長さ・葉の値まで、すべての欄で比べる（compare）。葉の値は、型（真偽・文字列・null・数）も比べる。
  数はちょうど同じであることを求める。許す違いは、計算の書き方が解析と違う二つだけ：Clopper–Pearson の端点（二分法の書き方）と
  命題 S-1 の E_S（設計図から書き起こした式）で、絶対値 1e-9 まで
- 操作の確認の主なもの（O3〜O10）を、別の書き方で

測定の来歴と全件性（recheck_directory。guard・解析の道具の確かめに頼らず、ファイルを直接読む）
- seeds/ の下は、seed の名前（先頭に 0 のない 10 進）のフォルダだけで、各フォルダは開始の記録・終了の記録・raw の 3 つだけを持つ
- 終了の記録が completed で、raw のファイルの SHA-256・バイト数が終了の記録と同じ
- フォルダの名前・開始の記録・終了の記録・raw の meta・raw の run の seed が同じ。experiment・kind・mode が開始・終了・meta で同じ
- 測定の commit：開始の記録 ＝ 終了の記録の measurement_commit_end ＝ raw の meta（40 桁）で、全 seed で一つ。report の
  measurement_commit と O1 の記録の commit も、それと同じ
- protocol の SHA-256：開始の記録 ＝ raw の meta ＝ 確定済みの protocol.yaml（PROTOCOL_FILE_SHA256）
- 関門の宣言：raw の meta の SHA-256 ＝ 固定の値（GATE_SHA256）＝ リポジトリの宣言のファイル。meta の宣言の中身 ＝ そのファイル
- seed の組：本番は 34001〜34200 の 200 個体がちょうど（欠け・余り・範囲の外がない）。合成は合成の範囲の中。
  smoke の盲検の記録は、この検算の対象ではない（食い違いとして数える）
- O1 の記録：欄の組、commit、終了コード 0、すべて通った結果の行、走らせた契約テストの組、テストのファイルの SHA-256
  （この検算が置かれたリポジトリのファイルと照らす。測定の commit で走らせる）

使い方（結果を保存したフォルダを渡す。測定の commit で、計算の後で一度だけ）:
  python experiments/0041_as2b_rule_weight_direction/recheck.py <フォルダ> [--write <結果の JSON>]
"""

import argparse
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

BODIES = ["B_A1", "B_A2", "B_A1_rerun"]
OBSERVED = BODIES[:2]
RERUN = "B_A1_rerun"
RULE_OF = {"B_A1": "A1", "B_A2": "A2", "B_A1_rerun": "A1"}
ROLES3 = ("cue", "source1", "source2")
SOURCES = ("source1", "source2")
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")
NAMES = ("delta", "q_1", "q_2", "delta_back", "epsilon")
ACTIONS = ("A1", "A2")
SIGNS = ("+", "-", "0")
ZEROS = ("Z-1", "Z-2")
# report の決まった文（README §4.4・§6.2。解析の道具と同じ文を、ここに書き起こす）
NOTES = {"estimate": "estimate only; no threshold; not a judgment (README section 4.4)",
         "R4": "per individual: individuals.<seed>.boundaries (six weights of B_A1 and B_A2 at each window boundary); "
               "descriptive only, never used to choose another time point",
         "R8": "Clopper-Pearson 95% intervals are in judgment.J_B, estimate and descriptive_controls"}
HEX = set("0123456789abcdef")
DIGITS = set("0123456789")
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROTOCOL_FILE = HERE / "protocol.yaml"
# 事前登録 v0.1 の protocol.yaml（#189 merge `5fba79f`）を、raw の meta と同じ形（YAML を読み、JSON を通した形）にして正規化した
# JSON の SHA-256。正規化：json.dumps(写し, sort_keys=True, ensure_ascii=False, separators=(",", ":")) の UTF-8。
# 値は契約テストで、正本から計算し直して照らす
PROTOCOL_JSON_SHA256 = "dd377cd1700d24f7c4b9f850d1c78907e07b0b712e2e34fc6901cbe697d59fc5"
PROTOCOL_FILE_SHA256 = "cdb09a2b9b90318ceea254c6ebbdcbd1a5404a3736c82d326ac3a9a7d10446c4"   # 同じ正本のファイルのバイト列
# 引き継ぐ関門の宣言 v0.2（protocol の inherited_gate_set）のファイルと、そのバイト列の SHA-256
GATE_FILE = "experiments/0038_as2b_forward_gate/gate_declaration.json"
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
# 事前登録 v0.1 から書き起こした値：README §1.2・§2・§4.3・§5.1・§8・§9.2、protocol.yaml の judgment・timeline・brain・world・seeds。
# 判定はこの値で計算し、meta の protocol の写しは、これと照らすだけに使う
PREREGISTERED = {
    "experiment": "0041", "kind": "preregistered_test",
    "alpha_per_direction": Fraction(1, 40), "alpha_two_sided": Fraction(1, 20),
    "m": 200, "k2_200": 115,
    "experience_windows": [1, 25], "experience_pulses": [1, 1065], "boundary_P_E": 1065, "runs_to": 1065,
    "w_min": 0.0, "w_max": 0.01, "w0": 0.005, "f1_tolerance": 1e-12,
    "respond": True, "rule_c": {"B_A1": "A1", "B_A2": "A2", "B_A1_rerun": "A1"}, "per_individual": BODIES,
    "seeds": {"first": 34001, "last": 34200}, "smoke_seeds": {"first": 34201, "last": 34206},
    "synthetic_seeds": {"first": 34301, "last": 34399},
    "formal_plan": {"first": 41, "spacing": 41, "count": 50, "offset": 2, "length": 19, "delay": 2, "e_windows": 25},
}
W_MIN, W_MAX, W0 = PREREGISTERED["w_min"], PREREGISTERED["w_max"], PREREGISTERED["w0"]
# 出力先のファイル（README §9.4。guard.py・analyze.py と同じ名前を、ここに書き起こす）
START, FINISH, RAW, SEEDS_DIR = "run_started.json", "run_finished.json", "raw.json.gz", "seeds"
REPORT, O1_FILE = "report.json", "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py",
                  "tests/integration/test_as2b_rule_weight_direction_0041.py")
RECHECKED_MODES = {"formal": "seeds", "synthetic": "synthetic_seeds"}          # smoke（盲検の記録）は対象ではない
LOOSE = 1e-9                                                                   # 計算の書き方が違う欄だけに許す違い


def geometry(plan: dict) -> dict:
    cues = [plan["first"] + plan["spacing"] * k for k in range(plan["count"])]
    windows = [(k + 1, c + plan["offset"], c + plan["offset"] + plan["length"] - 1) for k, c in enumerate(cues)]
    e = plan["e_windows"]
    return {"cues": cues, "windows": windows, "e": e, "p_e": cues[e] - 1, "boundaries": [cues[k] - 1 for k in range(1, e + 1)]}


def sign_of(x: Fraction) -> str:
    return "+" if x > 0 else "-" if x < 0 else "0"


def bound_e_s(manifest: dict, plan: dict) -> float:
    """命題 S-1 の E_S ＝ w_max [(1 ＋ λ^g1)／(1 − λ^(g1 ＋ g2)) ＋ 2／(1 − λ^d)]（README §7.2 を書き起こしたもの）。"""
    d = manifest["defaults"]["dynamics"]
    lam, j = float(d["decay"]), float(d["jitter"])
    key = manifest["plasticity"]["w_max"]
    w_max = float(d[key]) if isinstance(key, str) else float(key)
    theta_min, c_max = float(d["threshold"]) * (1 - j), float(d["intrinsic_drive"]) * (1 + j)
    gain, n = c_max + 2 * w_max, 1
    while gain * (1 - lam ** n) / (1 - lam) < theta_min:
        n += 1
    g1 = plan["offset"] + plan["delay"]
    g2 = plan["spacing"] - (plan["offset"] + plan["length"] - 1 + plan["delay"])
    return w_max * ((1 + lam ** g1) / (1 - lam ** (g1 + g2)) + 2 / (1 - lam ** n))


def five(values: list) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def frac(x: Fraction | None) -> dict | None:
    return None if x is None else {"num": x.numerator, "den": x.denominator, "value": float(x)}


# ---- 個体ごとの量（README §3・§4.1・§6） ---------------------------------------------------------------

def role_cids(roles: dict) -> dict:
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


def contrast(x: dict, y: dict) -> dict:
    """README §3.2 の定義を、規則 c ＝ A1 の本体の重み x と A2 の本体の重み y（役の名前の鍵）から、そのまま書き起こす。"""
    f = {k: Fraction(v) for k, v in x.items()}
    h = {k: Fraction(v) for k, v in y.items()}
    return {"delta": (f["C_to_source1"] - h["C_to_source1"]) - (f["C_to_source2"] - h["C_to_source2"]),
            "q_1": f["C_to_source1"] - h["C_to_source1"],
            "q_2": h["C_to_source2"] - f["C_to_source2"],
            "delta_back": (f["source1_to_C"] - h["source1_to_C"]) - (f["source2_to_C"] - h["source2_to_C"]),
            "epsilon": (f["source1_to_source2"] - h["source1_to_source2"]) - (f["source2_to_source1"] - h["source2_to_source1"])}


def firing_at(activity: list, end: int) -> dict:
    """Pulse 1〜end の、Pulse ごとの発火した Unit の数え上げ（同じ Unit の重なりも数える）。"""
    out: dict[int, Counter] = {}
    for p, u in activity:
        if 1 <= p <= end:
            out.setdefault(p, Counter())[u] += 1
    return out


def first_split(act_a: list, act_b: list, end: int) -> int | None:
    a, b = firing_at(act_a, end), firing_at(act_b, end)
    return min((p for p in set(a) | set(b) if a.get(p, Counter()) != b.get(p, Counter())), default=None)


def window_count(layer_a: list, lo: int, hi: int) -> dict:
    outs = Counter(r["outcome"] for r in layer_a if lo <= r["window"] <= hi)
    return {"windows": sum(outs.values()), "decided": outs["A1"] + outs["A2"], "A1": outs["A1"], "A2": outs["A2"],
            "tie": outs["tie"], "none": outs["none"]}


def max_pair_gap(weights: dict) -> Fraction:
    """組（二つの Unit のあいだの 2 本）ごとの正確な和と w_max の差の絶対値の最大。"""
    by_pair: dict[tuple, list] = {}
    for cid, w in weights.items():
        by_pair.setdefault(tuple(sorted(cid.split(".main->"))), []).append(Fraction(w))
    return max(abs(sum(ws, Fraction(0)) - Fraction(W_MAX)) for ws in by_pair.values())


def individual(data: dict) -> dict:
    """1 個体の量を、report の individuals の欄と同じ形で書き起こす。"""
    run, plan = data["run"], data["run"]["plan"]
    geo = geometry(plan)
    e, p_e = geo["e"], geo["p_e"]
    roles, rec = run["roles"], run["bodies"]
    name_of = {roles[r]: r for r in ROLES3}
    counts = {n: window_count(rec[n]["layer_a"], 1, e) for n in BODIES}
    decided = [r["window"] for r in rec["B_A1"]["layer_a"] if r["window"] <= e and r["outcome"] in ACTIONS]
    ks = decided[0] if decided else None
    zero = None if ks is not None else ("Z-1" if counts["B_A1"]["none"] == counts["B_A1"]["windows"] else "Z-2")
    cid_of = role_cids(roles)
    w = {n: {role: rec[n]["sigma_p_e"]["connections"][cid_of[role]]["weight"] for role in ROLES6} for n in BODIES}
    q = contrast(w["B_A1"], w["B_A2"])
    e_s = bound_e_s(data["meta"]["manifest"], plan)
    units = run["birth_units"]
    margin = {}
    for u, role in name_of.items():
        d = units[u]["dynamics"]
        margin[role] = d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]
    silent = {role: margin[role] < -e_s for role in SOURCES}
    fired = {u for n in BODIES for _p, u in rec[n]["activity"]}
    position = {cid: i for i, cid in enumerate(run["connection_order"])}
    rows = {n: {p: row for p, row in rec[n]["pulse_weights"]} for n in OBSERVED}
    at = {n: [{role: rows[n][p][position[cid_of[role]]] for role in ROLES6} for p in geo["boundaries"]] for n in OBSERVED}
    boundaries = {"pulses": geo["boundaries"]}
    for n in OBSERVED:
        boundaries[n] = {role: [x[role] for x in at[n]] for role in ROLES6}
    boundaries["delta_signs"] = [sign_of(contrast(x, y)["delta"]) for x, y in zip(at["B_A1"], at["B_A2"])]
    consequences = {}
    for n in BODIES:
        world = rec[n]["world_end"]
        realized = {rid for _p, _r, rids, _cnt in world["realized"] for rid in rids}
        stimuli = sum(1 for r in world["reserved"] if r[1] == "consequence" and r[3] <= p_e and r[0] in realized)
        consequences[n] = {"stimuli": stimuli, "decided_of_rule_c": counts[n][RULE_OF[n]]}
    b1, b2 = rec["B_A1"], rec["B_A2"]
    outcome_split = next((x["window"] for x, y in zip(b1["layer_a"], b2["layer_a"]) if x["outcome"] != y["outcome"]), None)
    weight_split = next((p for (p, x), (_p, y) in zip(b1["pulse_weights"], b2["pulse_weights"]) if x != y), None)
    split = {"firing": first_split(b1["activity"], b2["activity"], p_e), "window": outcome_split, "weights": weight_split}
    firing = {}
    for n in BODIES:
        firing[n] = dict.fromkeys(ROLES3, 0)
        for p, u in rec[n]["activity"]:
            if u in name_of and p <= p_e:
                firing[n][name_of[u]] += 1
    return {
        "roles": {k: roles[k] for k in ROLES3},
        "birth": {role: {"threshold": units[roles[role]]["dynamics"]["threshold"],
                         "intrinsic_drive": units[roles[role]]["dynamics"]["intrinsic_drive_per_second"],
                         "margin_g": margin[role]} for role in ROLES3},
        "S1": {"silent_source": silent, "violations": sorted(r for r in SOURCES if silent[r] and roles[r] in fired)},
        "k_star": ks,
        "structural_zero": zero,
        "other_zero": ks is not None and q["delta"] == 0,
        "counts_E": counts,
        "quantities": {k: frac(q[k]) | {"sign": sign_of(q[k])} for k in NAMES},
        "delta_plus_delta_back": frac(q["delta"] + q["delta_back"]),
        "weights_P_E": w,
        "weight_differences": {role: frac(Fraction(w["B_A1"][role]) - Fraction(w["B_A2"][role])) for role in ROLES6},
        "pair_sum_max_deviation": {n: float(max_pair_gap({cid: v["weight"] for cid, v in rec[n]["sigma_p_e"]["connections"].items()}))
                                   for n in BODIES},
        "boundaries": boundaries,
        "consequences": consequences,
        "first_divergence": split,
        "never_diverged": all(v is None for v in split.values()),
        "firing_E": firing,
    }


# ---- 判定・推定・記述の対照・補助の記録（README §4〜§6） ------------------------------------------------------

def upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, i) for i in range(k, m + 1)), 2 ** m)


def k2(m: int, alpha: Fraction) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ α の最小の k（m ＋ 1 なら、どの数でも成立しない）。"""
    k = 0
    while k <= m and upper_tail(m, k) > alpha:
        k += 1
    return k


def exact_interval(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """Clopper–Pearson（二項の裾の確率の二分法）。下の端は P(X ≥ x) ＝ α/2、上の端は P(X ≤ x) ＝ α/2 の解。"""
    half = (1 - level) / 2

    def at_least(p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x, n + 1))

    def at_most(p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(x + 1))

    def root(f, rising: bool) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if (f(mid) >= half) == rising:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if x == 0 else root(at_least, True)
    upper = 1.0 if x == n else root(at_most, False)
    return lower, upper


def interval_of(x: int, n: int) -> dict:
    if n < 1:
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "m = 0"}
    return {"computed": True, "interval": list(exact_interval(x, n)), "numerator": x, "denominator": n}


def count_signs(people: list[dict], name: str) -> dict:
    c = Counter(p["quantities"][name]["sign"] for p in people)
    return {s: c[s] for s in SIGNS}


def judgment(people: list[dict]) -> dict:
    m = len(people)
    counts = count_signs(people, "delta")
    k = k2(m, PREREGISTERED["alpha_per_direction"])
    direction = "+" if counts["+"] >= k else "-" if counts["-"] >= k else None
    return {"J_B": {"m": m, "counts": counts, "proportion": {s: (counts[s] / m if m else None) for s in ("+", "-")},
                    "interval": {s: interval_of(counts[s], m) for s in ("+", "-")}, "k2": k,
                    "tail_probability": float(upper_tail(m, k)),
                    "status": "established" if direction else "not_established", "direction": direction},
            "outcome": {"+": "plus", "-": "minus", None: "not_established"}[direction]}


def estimate(people: list[dict]) -> dict:
    m = len(people)
    counts = count_signs(people, "delta")
    sizes = [abs(p["quantities"]["delta"]["value"]) for p in people]

    def part(x: int) -> dict:
        return {"count": x, "proportion": x / m if m else None, "interval": interval_of(x, m)}
    return {"m": m, "p_change": part(counts["+"] + counts["-"]), "p_plus": part(counts["+"]), "p_minus": part(counts["-"]),
            "abs_delta": {"all": five(sizes), "changed": five([x for x in sizes if x != 0])}, "note": NOTES["estimate"]}


def controls(people: dict) -> dict:
    group = list(people.values())
    sub = [p for p in group if p["k_star"] is not None]
    n, m = len(sub), len(group)
    dc, ec = count_signs(sub, "delta"), count_signs(group, "epsilon")
    flip = {"+": "-", "-": "+", "0": "0"}
    cells = {a + b: 0 for a in SIGNS for b in SIGNS}
    for p in group:
        cells[p["quantities"]["q_1"]["sign"] + p["quantities"]["q_2"]["sign"]] += 1
    withdrawn = any(p["S1"]["violations"] for p in group)
    sizes = [abs(p["delta_plus_delta_back"]["value"]) for p in group]
    return {
        "diverged": {"count": n, "counts": dc, "proportion": {s: (dc[s] / n if n else None) for s in ("+", "-")},
                     "interval": {s: interval_of(dc[s], n) for s in ("+", "-")},
                     "delta": five([p["quantities"]["delta"]["value"] for p in sub])},
        "delta_back": {"counts": count_signs(group, "delta_back"),
                       "sign_not_opposite_to_delta": sum(1 for p in group if p["quantities"]["delta_back"]["sign"]
                                                         != flip[p["quantities"]["delta"]["sign"]]),
                       "max_abs_delta_plus_delta_back": max(sizes) if sizes else None},
        "epsilon": {"counts": ec, "proportion": {s: (ec[s] / m if m else None) for s in ("+", "-")},
                    "interval": {s: interval_of(ec[s], m) for s in ("+", "-")},
                    "distribution": five([p["quantities"]["epsilon"]["value"] for p in group])},
        "cross_table_q": {"order": ["q_1", "q_2"], "cells": cells},
        "zero_table": {"structural": {z: sorted(k for k, p in people.items() if p["structural_zero"] == z) for z in ZEROS},
                       "other_zero": sorted(k for k, p in people.items() if p["other_zero"]),
                       "silent_source": None if withdrawn else {r: sorted(k for k, p in people.items() if p["S1"]["silent_source"][r])
                                                                for r in SOURCES},
                       "S1_labels_withdrawn": withdrawn},
    }


def auxiliary(people: dict, e_s: float | None) -> dict:
    vals = list(people.values())
    violations = sum(len(p["S1"]["violations"]) for p in vals)
    ks = [p["k_star"] for p in vals if p["k_star"] is not None]
    out: dict = {"R1": {
        "individuals": len(vals),
        "k_star": {"none": len(vals) - len(ks), "windows": five(ks)},
        "structural_zero": {z: sum(1 for p in vals if p["structural_zero"] == z) for z in ZEROS},
        "other_zero": sum(1 for p in vals if p["other_zero"]),
        "S1": {"E_S": e_s, "violations": violations, "labels_withdrawn": violations > 0,
               "individuals_with_silent_source": None if violations else sum(1 for p in vals if any(p["S1"]["silent_source"].values())),
               "per_source": None if violations else {r: sum(1 for p in vals if p["S1"]["silent_source"][r]) for r in SOURCES}}}}
    out["R2"] = {n: {k: five([p["counts_E"][n][k] for p in vals]) for k in ("decided", "A1", "A2", "tie", "none")} for n in BODIES}
    out["R3"] = {k: five([p["quantities"][k]["value"] for p in vals]) for k in NAMES}
    out["R3"]["abs_delta"] = five([abs(p["quantities"]["delta"]["value"]) for p in vals])
    gaps = [x for p in vals for x in p["pair_sum_max_deviation"].values()]
    pulses = vals[0]["boundaries"]["pulses"] if vals else []
    boundary = []
    for i, pulse in enumerate(pulses):
        c = Counter(p["boundaries"]["delta_signs"][i] for p in vals)
        boundary.append({"pulse": pulse, "+": c["+"], "-": c["-"], "0": c["0"]})
    out["R4"] = {"P_E_weights": {n: {role: five([p["weights_P_E"][n][role] for p in vals]) for role in ROLES6} for n in BODIES},
                 "differences_B_A1_minus_B_A2": {role: five([p["weight_differences"][role]["value"] for p in vals]) for role in ROLES6},
                 "pair_sum_max_deviation": max(gaps) if gaps else None,
                 "boundary_delta_signs": boundary, "boundary_weights": NOTES["R4"]}
    out["R5"] = {n: {"stimuli": five([p["consequences"][n]["stimuli"] for p in vals]),
                     "equals_decided_of_rule_c": all(p["consequences"][n]["stimuli"] == p["consequences"][n]["decided_of_rule_c"]
                                                     for p in vals)} for n in BODIES}
    out["R6"] = {}
    for key in ("firing", "window", "weights"):
        xs = [p["first_divergence"][key] for p in vals if p["first_divergence"][key] is not None]
        out["R6"][key] = {"none": len(vals) - len(xs), "values": five(xs)}
    out["R6"]["never_diverged"] = sum(1 for p in vals if p["never_diverged"])
    out["R7"] = {n: {role: five([p["firing_E"][n][role] for p in vals]) for role in ROLES3} for n in BODIES}
    out["R8"] = NOTES["R8"]
    return out


def expected_report(runs: dict, measurement_commit: str | None = None) -> dict:
    """保存した生の記録だけから、有効な report の全体（mode・valid・O1・関門の SHA-256・判定・推定・記述の対照・個体・補助の記録）を
    組み立て直す。measurement_commit を渡したときは、その欄も期待値に入れる（解析の main が書き足す欄）。"""
    seeds = sorted(runs)
    people = {str(s): individual(runs[s]) for s in seeds}
    ordered = list(people.values())
    modes = {runs[s]["meta"]["mode"] for s in seeds}
    e_s = bound_e_s(runs[seeds[0]]["meta"]["manifest"], runs[seeds[0]]["run"]["plan"]) if seeds else None
    out = {"mode": modes.pop() if len(modes) == 1 else None, "valid": True, "O1": {"status": "ok", "problems": []},
           "gate_declaration_sha256": GATE_SHA256,
           "judgment": judgment(ordered), "estimate": estimate(ordered), "descriptive_controls": controls(people),
           "individuals": people, "auxiliary": auxiliary(people, e_s)}
    if measurement_commit is not None:
        out["measurement_commit"] = measurement_commit
    return out


# ---- 期待値と report の照合（すべての欄） ---------------------------------------------------------------------

def _loose(where: str) -> bool:
    """計算の書き方が解析と違う欄（Clopper–Pearson の端点、E_S）。ほかの数は、ちょうど同じであることを求める。"""
    return where.endswith((".interval[0]", ".interval[1]")) or where == "report.auxiliary.R1.S1.E_S"


def compare(mine, theirs, where: str = "report") -> tuple[int, list[str]]:
    """期待値 mine と report の theirs を、欄の組・列の長さ・葉の型と値まで比べる。(比べた葉の数, 食い違った場所) を返す。
    食い違いの文には場所だけを書き、値は書かない。"""
    checks, found = 0, []
    stack = [(mine, theirs, where)]
    while stack:
        a, b, at = stack.pop()
        if isinstance(a, dict):
            if not isinstance(b, dict):
                checks, found = checks + 1, found + [f"{at}: 欄の形"]
                continue
            if set(a) != set(b):
                checks, found = checks + 1, found + [f"{at}: 欄の組"]
            stack += [(a[k], b[k], f"{at}.{k}") for k in sorted(set(a) & set(b), reverse=True)]
        elif isinstance(a, (list, tuple)):
            if not isinstance(b, list) or len(a) != len(b):
                checks, found = checks + 1, found + [f"{at}: 列の形・長さ"]
                continue
            stack += [(x, y, f"{at}[{i}]") for i, (x, y) in reversed(list(enumerate(zip(a, b))))]
        else:
            checks += 1
            if a is None or isinstance(a, (bool, str)):
                ok = type(a) is type(b) and a == b
            elif isinstance(a, (int, float)):
                ok = isinstance(b, (int, float)) and not isinstance(b, bool) and (
                    abs(a - b) <= LOOSE if _loose(at) else a == b)
            else:
                ok = False
            if not ok:
                found.append(at)
    return checks, found


# ---- 操作の確認の主なもの（別の書き方で） -----------------------------------------------------------------

def _without(sigma: dict, paths: list[tuple]) -> str:
    """Σ から、違ってよい欄（paths）を取り除いた正規化した JSON の文字列。"""
    s = json.loads(json.dumps(sigma))
    for path in paths:
        node = s
        for key in path[:-1]:
            node = node[key]
        node.pop(path[-1], None)
    return json.dumps(s, sort_keys=True, separators=(",", ":"))


def _sha(sigma: dict) -> str:
    return hashlib.sha256(json.dumps(sigma, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def operation_problems(data: dict) -> list[str]:
    run = data["run"]
    plan, roles = run["plan"], run["roles"]
    geo = geometry(plan)
    e, p_e, windows = geo["e"], geo["p_e"], geo["windows"][:geo["e"]]
    order, cue_r = run["connection_order"], roles["cue_receptor"]
    action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    rec = run["bodies"]
    partner = {}
    for i, cid in enumerate(order):
        src, tgt = cid.split(".main->")
        partner[i] = order.index(f"{tgt}.main->{src}")
    problems = []

    def weights_ok(row: list) -> bool:
        return all(0.0 <= x <= W_MAX for x in row) and all(abs(row[i] + row[j] - W_MAX) <= PREREGISTERED["f1_tolerance"]
                                                          for i, j in partner.items())
    for n in BODIES:
        r = rec[n]
        la, lb = r["layer_a"], r["layer_b"]
        # O10 の一部：層 A の欄の整合（窓 1〜E）
        if [x["window"] for x in la] != [k for k, _a, _b in windows]:
            problems.append(f"O10 {n}: 窓の番号")
        for x, (k, a, b) in zip(la, windows):
            d = x["decision_pulse"]
            if x["outcome"] in ACTIONS:
                ok = (a <= d <= b and x["action"] == x["outcome"] == action_of.get(x["winner_unit"])
                      and x["emit_pulse"] == d + 1 and x["emitted"] is True)
            elif x["outcome"] == "tie":
                ok = a <= d <= b and x["winner_unit"] is None and x["action"] is None and not x["emitted"]
            else:
                ok = x["outcome"] == "none" and d is None and x["winner_unit"] is None and not x["emitted"]
            if not ok or (x["open"], x["close"]) != (a, b):
                problems.append(f"O10 {n}: 窓 {k}")
        # O3：層 A と層 B の一対一、識別子の重複、未発行の予定
        if Counter((x["emit_pulse"], x["winner_unit"], x["action"]) for x in la if x["emitted"]) \
                != Counter((p, src, act) for p, _did, src, act in lb):
            problems.append(f"O3 {n}: 層 A と層 B")
        if len({did for _p, did, _s, _a in lb}) != len(lb):
            problems.append(f"O3 {n}: 識別子の重複")
        if any(x["winner_unit"] is not None and not x["emitted"] for x in la):
            problems.append(f"O3 {n}: 未発行の予定")
        # O5：結果は規則 c の意図にだけ、意図の Pulse ＋ L − 1。感覚の出来事は手がかりの Receptor だけ
        world = r["world_end"]
        cons = sorted((row[3], row[4]) for row in world["reserved"] if row[1] == "consequence")
        if cons != sorted((p + plan["delay"] - 1, did) for p, did, _s, act in lb if act == RULE_OF[n]):
            problems.append(f"O5 {n}: 結果の予約")
        if len(cons) != sum(1 for x in la if x["outcome"] == RULE_OF[n]):
            problems.append(f"O5 {n}: 結果の刺激の数")
        if any(receptor != cue_r for _p, receptor in r["sensory"]) or any(row[1] not in ("cue", "consequence")
                                                                          for row in world["reserved"]):
            problems.append(f"O5 {n}: 感覚の出来事・予約の種類")
        # O6：範囲と F1、介入なし
        here = {cid: v["weight"] for cid, v in r["sigma_p_e"]["connections"].items()}
        if not weights_ok([here[cid] for cid in order]) or r["history"] != [] \
                or r["sigma_p_e"]["interventions"] != {"active": [], "frozen": {}}:
            problems.append(f"O6 {n}")
        # O7：P_E で止まり、未決の窓・意図・結果の予約がない。残る予約は P_E より後の手がかりだけ
        ex = r["sigma_p_e"]["exit"]
        if r["pulse_end"] != p_e or r["sigma_p_e"]["pulse"] != p_e or ex["cursor"] != e or ex["pending"] is not None:
            problems.append(f"O7 {n}: P_E")
        if sorted((row[1], row[3]) for row in world["pending"]) != [("cue", c) for c in geo["cues"] if c > p_e]:
            problems.append(f"O7 {n}: 残る予約")
    for n in OBSERVED:
        r = rec[n]
        # O6・O9：Pulse ごとの重み（1〜P_E）、範囲と F1、P_E の値と Σ、Σ_0 は w0
        rows = r["pulse_weights"]
        here = {cid: v["weight"] for cid, v in r["sigma_p_e"]["connections"].items()}
        if [p for p, _w in rows] != list(range(1, p_e + 1)) or rows[-1][1] != [here[cid] for cid in order]:
            problems.append(f"O9 {n}")
        if not all(weights_ok(w) for _p, w in rows):
            problems.append(f"O6 {n}: Pulse ごと")
        if any(v["weight"] != W0 for v in r["sigma_0"]["connections"].values()) or r["sigma_0"]["pulse"] != 0:
            problems.append(f"O9 {n}: Σ_0")
    # O8：B′^{A1} と B^{A1} の完全な一致（値が主、SHA-256 は補助）
    ra, rb = rec["B_A1"], rec[RERUN]
    if any(ra[k] != rb[k] for k in ("activity", "sensory", "layer_a", "layer_b", "history")) or ra["sigma_p_e"] != rb["sigma_p_e"]:
        problems.append("O8")
    for n in BODIES:
        if _sha(rec[n]["sigma_p_e"]) != rec[n]["sigma_p_e_sha256"]:
            problems.append(f"O8 {n}: SHA-256")
    # O4：R-7 の対。Pulse 0 は規則 c だけが違う。k* がなければ P_E まで規則 c だけ。あれば k* の意図の Pulse の後の脳の側が同じ
    a1, a2 = rec["B_A1"], rec["B_A2"]
    rule = [("world", "rule", "rule_c")]
    if _without(a1["sigma_0"], rule) != _without(a2["sigma_0"], rule) or a1["sigma_0"]["world"]["rule"]["rule_c"] == \
            a2["sigma_0"]["world"]["rule"]["rule_c"]:
        problems.append("O4: Pulse 0")
    decided = [x for x in a1["layer_a"] if x["outcome"] in ACTIONS]
    if not decided:
        if any(a1[k] != a2[k] for k in ("activity", "sensory", "layer_a", "layer_b", "pulse_weights")) \
                or _without(a1["sigma_p_e"], rule) != _without(a2["sigma_p_e"], rule) \
                or a1["first_intent"] is not None or a2["first_intent"] is not None:
            problems.append("O4: 構造的な 0")
    else:
        k, t = decided[0]["window"], decided[0]["decision_pulse"] + 1
        fa, fb = a1["first_intent"], a2["first_intent"]
        brain = rule + [("world", "pending"), ("world", "reserved"), ("world", "next_rid")]
        if a1["layer_a"][:k] != a2["layer_a"][:k] or fa is None or fb is None or fa["pulse"] != t or fb["pulse"] != t \
                or _without(fa["sigma"], brain) != _without(fb["sigma"], brain):
            problems.append("O4: k* の意図の Pulse")
    # O10 の一部：P_E の Σ と、Pulse P_E の重みの記録から求めた量が同じ。k* がなければちょうど 0
    cid_of = role_cids(roles)
    position = {cid: i for i, cid in enumerate(order)}
    by_sigma = [{role: rec[n]["sigma_p_e"]["connections"][cid_of[role]]["weight"] for role in ROLES6} for n in OBSERVED]
    by_rows = [{role: rec[n]["pulse_weights"][-1][1][position[cid_of[role]]] for role in ROLES6} for n in OBSERVED]
    q = contrast(*by_sigma)
    if q != contrast(*by_rows):
        problems.append("O10: 量")
    if not decided and any(v != 0 for v in q.values()):
        problems.append("O10: 構造的な 0 の量")
    return problems


# ---- protocol の写しと、確定済みの事前登録の結び付き ------------------------------------------------

def _number(x) -> Fraction | None:
    try:
        return Fraction(str(x))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _sha256_hex(x) -> bool:
    return isinstance(x, str) and len(x) == 64 and set(x) <= HEX


def _commit_hex(x) -> bool:
    return isinstance(x, str) and len(x) == 40 and set(x) <= HEX


def canonical_protocol_sha256(proto: dict) -> str:
    """写しの中身全体の、正規化した JSON の SHA-256（PROTOCOL_JSON_SHA256 と同じ正規化）。"""
    text = json.dumps(proto, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def protocol_problems(runs: dict, protocol_file: Path = PROTOCOL_FILE) -> list[str]:
    """全個体の meta の protocol の写しが、そろってあり、確定済みの protocol.yaml と PREREGISTERED に結び付くこと。"""
    problems = []
    file_sha = hashlib.sha256(protocol_file.read_bytes()).hexdigest()
    if file_sha != PROTOCOL_FILE_SHA256:
        problems.append("照らす protocol.yaml が、事前登録 v0.1 の protocol.yaml と違う")
    copies, shas = set(), set()
    for s in sorted(runs):
        meta = runs[s].get("meta", {})
        proto, sha = meta.get("protocol"), meta.get("protocol_sha256")
        if not isinstance(proto, dict) or not _sha256_hex(sha):
            problems.append(f"seed {s}: meta に protocol の写し・SHA-256 がない")
            continue
        copies.add(json.dumps(proto, sort_keys=True, ensure_ascii=False))
        shas.add(sha)
        if canonical_protocol_sha256(proto) != PROTOCOL_JSON_SHA256:
            problems.append(f"seed {s}: meta の protocol の写しの中身が、事前登録 v0.1 の protocol と違う")
        if sha != file_sha:
            problems.append(f"seed {s}: meta の protocol の SHA-256 が、確定済みの protocol.yaml と違う")
        if meta.get("mode") == "formal" and runs[s].get("run", {}).get("plan") != PREREGISTERED["formal_plan"]:
            problems.append(f"seed {s}: 本番の Plan が事前登録の値と違う")
    if len(copies) > 1 or len(shas) > 1:
        problems.append("個体によって meta の protocol の写しが違う")
    if len(copies) == 1:
        problems += [f"protocol の写し：{p}" for p in _preregistered_values(json.loads(next(iter(copies))))]
    return problems


def _preregistered_values(proto: dict) -> list[str]:
    """写しの中の、判定に関わる値と PREREGISTERED の照合。k₂(200) は、二項から求め直した値と照らす。"""
    out = []
    try:
        jb, tl, pr, br = proto["judgment"]["J_B"], proto["timeline"], PREREGISTERED, proto["brain"]
        if (proto["experiment"], proto["kind"]) != (pr["experiment"], pr["kind"]):
            out.append("experiment・kind")
        if jb["m"] != pr["m"] or jb["k2_200"] != pr["k2_200"] or k2(pr["m"], pr["alpha_per_direction"]) != pr["k2_200"]:
            out.append("J_B.m・k2_200")
        if _number(jb["alpha"]["per_direction"]) != pr["alpha_per_direction"] \
                or _number(jb["alpha"]["two_sided"]) != pr["alpha_two_sided"]:
            out.append("J_B.alpha")
        if (tl["experience_E"]["windows"], tl["experience_E"]["pulses"], tl["boundary_P_E"], tl["runs_to"]) != \
                (pr["experience_windows"], pr["experience_pulses"], pr["boundary_P_E"], pr["runs_to"]):
            out.append("timeline")
        if (_number(br["w_min"]), _number(br["w_max"]), _number(br["initial_weight_w0"])) != \
                (_number(pr["w_min"]), _number(pr["w_max"]), _number(pr["w0"])):
            out.append("brain.weights")
        if proto["world"]["respond"] is not pr["respond"] or proto["world"]["rule_c"] != pr["rule_c"]:
            out.append("world.respond・rule_c")
        if proto["bodies"]["per_individual"] != pr["per_individual"]:
            out.append("bodies.per_individual")
        for key in ("seeds", "smoke_seeds", "synthetic_seeds"):
            if proto[key] != pr[key]:
                out.append(key)
        if (proto["inherited_gate_set"]["declaration"], proto["inherited_gate_set"]["sha256"]) != (GATE_FILE, GATE_SHA256):
            out.append("inherited_gate_set")
    except (KeyError, TypeError, AttributeError, ValueError):
        out.append("判定に関わる欄が読めない")
    return out


def gate_problems(runs: dict, repo: Path = REPO_ROOT) -> list[str]:
    """raw の meta の関門の宣言が、固定の SHA-256 と、リポジトリの宣言のファイル（バイト列と中身）に結び付くこと。"""
    problems = []
    path = repo / GATE_FILE
    raw = path.read_bytes() if path.is_file() else b""
    if hashlib.sha256(raw).hexdigest() != GATE_SHA256:
        problems.append("リポジトリの関門の宣言のファイルが、固定の SHA-256 と違う")
        declaration = None
    else:
        declaration = json.loads(raw.decode("utf-8"))
    for s in sorted(runs):
        gate = runs[s].get("meta", {}).get("gate")
        if not isinstance(gate, dict) or set(gate) != {"sha256", "declaration"} or gate["sha256"] != GATE_SHA256 \
                or (declaration is not None and gate["declaration"] != declaration):
            problems.append(f"seed {s}: meta の関門の宣言・SHA-256 が、確定済みの宣言と違う")
    return problems


# ---- report との照合 ------------------------------------------------------------------------------------

def recheck(runs: dict, report: dict, measurement_commit: str | None = None) -> dict:
    """runs：seed → 生の記録（meta に protocol の写しを含む）。report：解析の report。
    report の全体を生の記録から組み立て直して、すべての欄を照合する。照合の数と、食い違いの一覧を返す。"""
    checks, mismatches = 0, []
    seeds = sorted(runs)
    binding = protocol_problems(runs) + gate_problems(runs)          # 写しが欠けても、違っても、食い違いとして数える
    checks, mismatches = checks + 2, mismatches + binding
    manifests = {json.dumps(runs[s].get("meta", {}).get("manifest"), sort_keys=True) for s in seeds}
    checks += 1
    if len(manifests) > 1:
        mismatches.append("個体によって meta の設計図が違う")
    for s in seeds:
        checks += 1
        try:
            mismatches += [f"seed {s}: {p}" for p in operation_problems(runs[s])]
        except (KeyError, TypeError, ValueError, IndexError) as e:
            mismatches.append(f"seed {s}: 操作の確認の記録を読めない（{type(e).__name__}）")
    checks += 1
    if not isinstance(report, dict) or report.get("valid") is not True:
        return {"checks": checks, "mismatches": mismatches + ["report.valid"], "recomputed": None}
    try:
        mine = expected_report(runs, measurement_commit)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as e:
        return {"checks": checks, "mismatches": mismatches + [f"生の記録から report を組み立て直せない（{type(e).__name__}）"],
                "recomputed": None}
    if mine["mode"] is None:
        mismatches.append("個体によって meta の mode が違う")
    n, found = compare(mine, report)
    j, est = mine["judgment"], mine["estimate"]
    return {"checks": checks + n, "mismatches": mismatches + found,
            "recomputed": {"outcome": j["outcome"],
                           "J_B": {k: j["J_B"][k] for k in ("m", "counts", "status", "direction", "k2")},
                           "E_B": {"m": est["m"], "p_change_count": est["p_change"]["count"]}}}


# ---- 測定の来歴と全件性（出力先のファイルを直接読む） ------------------------------------------------------

def _seed_name(name: str) -> bool:
    return bool(name) and set(name) <= DIGITS and str(int(name)) == name


def seed_set_problems(mode: str | None, seeds: list[int]) -> list[str]:
    """seed の組の全件性：本番は事前登録の 200 個体がちょうど。合成は合成の範囲の中。欠け・余り・範囲の外・重複を数える。"""
    if mode not in RECHECKED_MODES:
        return [f"mode が {mode!r}（独立の検算は本番・合成の生の記録だけを対象にする。smoke は盲検の記録）"]
    rng = PREREGISTERED[RECHECKED_MODES[mode]]
    allowed = set(range(rng["first"], rng["last"] + 1))
    problems = []
    if len(set(seeds)) != len(seeds):
        problems.append("seed が重複している")
    outside = sorted(set(seeds) - allowed)
    if outside:
        problems.append(f"{mode} の範囲の外の seed（{len(outside)} 個）")
    if mode == "formal":
        missing = sorted(allowed - set(seeds))
        if missing:
            problems.append(f"本番の seed の欠け（{len(missing)} 個：{missing[:5]}{' ほか' if len(missing) > 5 else ''}）")
        if len(seeds) != PREREGISTERED["m"]:
            problems.append(f"本番の個体の数が {PREREGISTERED['m']} ではない")
    elif not seeds:
        problems.append("seed がない")
    return problems


def read_directory(out: Path) -> tuple[dict, dict, list[str]]:
    """出力先の seeds/ を、guard・解析の道具に頼らずに読む。(runs, 記録, 食い違い) を返す。
    seed ごとに：フォルダの名前と中身、終了の記録の status と raw の SHA-256・バイト数、四つの seed の一致、
    experiment・kind・mode と測定の commit・protocol の SHA-256 の、開始・終了の記録と raw の meta の結び付き。"""
    runs, records, problems = {}, {}, []
    root = out / SEEDS_DIR
    if not root.is_dir():
        return runs, records, ["seeds/ がない"]
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not _seed_name(d.name):
            problems.append(f"seeds/ の下に、seed のフォルダでないもの（{d.name}）")
            continue
        seed = int(d.name)
        names = sorted(p.name for p in d.iterdir())
        if names != sorted((START, FINISH, RAW)):
            problems.append(f"seed {seed}: フォルダの中身が、開始の記録・終了の記録・raw の 3 つではない")
        try:
            start = json.loads((d / START).read_text(encoding="utf-8"))
            finish = json.loads((d / FINISH).read_text(encoding="utf-8"))
            raw = (d / RAW).read_bytes()
            data = json.loads(gzip.decompress(raw).decode("utf-8"))
        except (OSError, ValueError, EOFError) as e:
            problems.append(f"seed {seed}: 開始・終了の記録か raw を読めない（{type(e).__name__}）")
            continue
        if not all(isinstance(x, dict) for x in (start, finish, data)) or not isinstance(data.get("meta"), dict):
            problems.append(f"seed {seed}: 開始・終了の記録か raw の形が違う")
            continue
        meta, run = data["meta"], data.get("run")
        if finish.get("status") != "completed":
            problems.append(f"seed {seed}: 終了の記録が completed ではない")
        if hashlib.sha256(raw).hexdigest() != finish.get("raw_file_sha256") or len(raw) != finish.get("raw_file_bytes"):
            problems.append(f"seed {seed}: raw の SHA-256・バイト数が、終了の記録と違う")
        if not (start.get("seed") == finish.get("seed") == meta.get("seed") == seed) \
                or not isinstance(run, dict) or run.get("seed") != seed:
            problems.append(f"seed {seed}: フォルダの名前・開始の記録・終了の記録・raw の meta と run の seed が一致しない")
        ekm = [tuple(x.get(k) for k in ("experiment", "kind", "mode")) for x in (start, finish, meta)]
        if len(set(ekm)) != 1 or ekm[0][:2] != (PREREGISTERED["experiment"], PREREGISTERED["kind"]):
            problems.append(f"seed {seed}: 開始・終了の記録と raw の meta の experiment・kind・mode が一致しない")
        commit = start.get("measurement_commit")
        if not _commit_hex(commit) or finish.get("measurement_commit_end") != commit or meta.get("measurement_commit") != commit:
            problems.append(f"seed {seed}: 測定の commit が、開始の記録・終了の記録・raw の meta で一つにならない")
        if not (start.get("protocol_sha256") == meta.get("protocol_sha256") == PROTOCOL_FILE_SHA256):
            problems.append(f"seed {seed}: protocol の SHA-256 が、開始の記録・raw の meta・確定済みの protocol.yaml で一致しない")
        runs[seed], records[seed] = data, {"start": start, "finish": finish}
    return runs, records, problems


def o1_problems(out: Path, commit: str | None, repo: Path = REPO_ROOT) -> list[str]:
    """O1 の記録（測定の commit で契約テストを走らせた記録）。テストのファイルの SHA-256 は、この検算のリポジトリのものと照らす。"""
    path = out / O1_FILE
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [f"{O1_FILE} がないか、読めない"]
    if not isinstance(rec, dict) or set(rec) != O1_KEYS:
        return [f"{O1_FILE} の欄の組が違う"]
    problems = []
    if rec["measurement_commit"] != commit:
        problems.append("O1：契約テストを走らせた commit が、測定の commit と違う")
    if type(rec["exit_code"]) is not int or rec["exit_code"] != 0:
        problems.append("O1：契約テストの終了コードが 0 ではない")
    summary = str(rec["summary"])
    if " passed" not in summary or " failed" in summary or " error" in summary:
        problems.append("O1：結果の行が、すべて通ったことを示していない")
    if not isinstance(rec["command"], list) or tuple(rec["command"][-len(CONTRACT_TESTS):]) != CONTRACT_TESTS:
        problems.append("O1：走らせた契約テストの組が違う")
    files = rec["test_files_sha256"]
    if not isinstance(files, dict) or set(files) != set(CONTRACT_TESTS):
        problems.append("O1：テストのファイルの SHA-256 の組が違う")
    else:
        for f in CONTRACT_TESTS:
            p = repo / f
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != files[f]:
                problems.append(f"O1：{f} の SHA-256 が、このリポジトリのものと違う")
    return problems


def recheck_directory(out: Path, repo: Path = REPO_ROOT) -> dict:
    """出力先から、測定の来歴・全件性を確かめ、report の全体を照合する。"""
    runs, records, problems = read_directory(out)
    seeds = sorted(runs)
    commits = {records[s]["start"].get("measurement_commit") for s in seeds}
    modes = {runs[s]["meta"].get("mode") for s in seeds}
    commit = next(iter(commits)) if len(commits) == 1 else None
    mode = next(iter(modes)) if len(modes) == 1 else None
    if len(commits) > 1:
        problems.append("seed によって測定の commit が違う")
    if len(modes) > 1:
        problems.append("seed によって mode が違う")
    names = sorted(p.name for p in (out / SEEDS_DIR).iterdir() if _seed_name(p.name)) if (out / SEEDS_DIR).is_dir() else []
    problems += seed_set_problems(mode, [int(x) for x in names])
    problems += o1_problems(out, commit, repo)
    files = {f"{SEEDS_DIR}/{s}/{RAW}": records[s]["finish"].get("raw_file_sha256") for s in seeds}
    report_path = out / REPORT
    try:
        report_bytes = report_path.read_bytes()
        report = json.loads(report_bytes.decode("utf-8"))
        files[REPORT] = hashlib.sha256(report_bytes).hexdigest()
    except (OSError, ValueError):
        report = None
        problems.append("report.json がないか、読めない")
    if mode in RECHECKED_MODES and runs:
        result = recheck(runs, report, commit if commit is not None else "（測定の commit が一つに定まらない）")
    else:
        result = {"checks": 0, "mismatches": [], "recomputed": None}
    return result | {"checks": result["checks"] + len(seeds) + 3, "mismatches": problems + result["mismatches"],
                     "individuals": len(runs), "sha256": files,
                     "provenance": {"mode": mode, "measurement_commit": commit, "seeds": len(seeds)}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", type=Path)
    parser.add_argument("--write", type=Path, default=None)
    args = parser.parse_args()
    result = recheck_directory(args.out)
    if args.write is not None:
        args.write.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"individuals": result["individuals"], "checks": result["checks"],
                      "mismatches": len(result["mismatches"])}, ensure_ascii=False))
    return 0 if not result["mismatches"] else 1


if __name__ == "__main__":
    sys.exit(main())
