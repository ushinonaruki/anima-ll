"""実験 0041 の記録の解析（確定した事前登録 v0.1 に従う。正本は README・protocol.yaml。#189 merge `5fba79f`）。

0040 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、protocol の結び付き、raw の meta と開始・終了の記録の照合、結果の写しの照合）を
引き継ぐ（ほかの実験の analyze.py は読み込まない。0040 の道具 v0.3、#185 merge `06ec685` と同じ形）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid。
   raw の中身の meta（測定の commit・protocol の SHA-256・seed・experiment・kind・mode）も、開始・終了の記録と直接照らす
   （provenance_problems）。違えば invalid
2. 操作の確認 O2〜O11（README §8）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   判定と推定の量を計算・表示しない。O1 は、run.py が seed に触れる前に測定の commit で走らせた契約テストの記録を確かめる（o1_check）
3. 判定と推定（README §3〜§6）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 個体ごと：P_E の 6 本の重みから δ・q_1・q_2・δ^←・ε（保存した倍精度の値を有理数として正確に）と符号、k*、構造的な 0 の札
     （Z-1・Z-2）、ほかの 0 の札、命題 S-1 の札、R1〜R7 の記録
   - J_B：生まれた全個体を分母にする（m ＝ 個体の数。本番は 200）。向きごとの個体の数 ≥ k₂(m) で、その向きで成立
   - E_B（判定ではない）：p_change・p_＋・p_− と Clopper–Pearson の 95%、|δ| の分布。有効なら成否に依らず必ず計算する
   - §6.1 の必ず報告する記述（k* がある個体での δ、δ^←、ε、(sign q_1, sign q_2) の 9 つの組の表、0 の個体の表）と、
     §6.2 の R1〜R8（判定に使わない）
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0041_as2b_rule_weight_direction/analyze.py                    # 本番（data/experiments/0041）
  python experiments/0041_as2b_rule_weight_direction/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
  python experiments/0041_as2b_rule_weight_direction/analyze.py --verify-copy <写し>   # 本番の出力先と写しの照合
"""

import argparse
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import math
import re
import statistics
from collections import Counter
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
# 事前登録の正本（v0.1）。生の記録の meta に保存した protocol の写しと SHA-256 を、これと照らす
PROTOCOL_SHA256 = hashlib.sha256((REPO / PROTOCOL_PATH).read_bytes()).hexdigest()
PROTOCOL_AS_STORED = json.loads(json.dumps(PROTOCOL))      # raw は JSON なので、写しは JSON を通した形で照らす
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0041")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure",) + tuple(f"O{i}" for i in range(2, 12))
REPORT, LOG = "report.json", "analysis_log.jsonl"
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py",
                  "tests/integration/test_as2b_rule_weight_direction_0041.py")
O1_FILE = "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
BLIND_KEYS = {"checks", "raw_sha256"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


G = load(f"guard_{EXPERIMENT}_analyze", REPO / HERE / "guard.py")
M = load(f"measure_{EXPERIMENT}_analyze", REPO / HERE / "measure.py")
ALIGN = load(f"alignment_{EXPERIMENT}_analyze", REPO / HERE / "alignment.py")
AX = load(f"analysis_{EXPERIMENT}_analyze", REPO / HERE / "analysis.py")     # 事前登録の解析（量の定義・命題 S-1 の E_S）
A, AS1 = M.A, M.AS1
W_MIN, W_MAX = float(PROTOCOL["brain"]["w_min"]), float(PROTOCOL["brain"]["w_max"])
W0 = float(PROTOCOL["brain"]["initial_weight_w0"])
F1_TOLERANCE = 1e-12                                                         # README §8 の O6（組の和と w_max の差の絶対値の上限）
GATE_DECLARATION, GATE_SHA256 = M.gate_declaration(PROTOCOL)
E_S = AX.silence_bound(AX.c0_values(), AX.gate_set())["E_S"]                # 命題 S-1（README §7.2）。札だけに使う
OUTCOMES = (*A.ACTION_IDS, A.TIE, A.NONE)
SIGNS = ("+", "-", "0")
ROLES3 = ("cue", "source1", "source2")
SOURCES = ("source1", "source2")
ROLES6 = AX.ROLES6
# README §3.2 の量：report の名前 → analysis.contrasts の名前
QUANTITIES = {"delta": "delta", "q_1": "q1", "q_2": "q2", "delta_back": "delta_back", "epsilon": "epsilon"}
NOTES = {"estimate": "estimate only; no threshold; not a judgment (README section 4.4)",
         "R4": "per individual: individuals.<seed>.boundaries (six weights of B_A1 and B_A2 at each window boundary); "
               "descriptive only, never used to choose another time point",
         "R8": "Clopper-Pearson 95% intervals are in judgment.J_B, estimate and descriptive_controls"}


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


# ---- 量（README §3） -------------------------------------------------------------------------------

def sign(x) -> str:
    return "+" if x > 0 else ("-" if x < 0 else "0")


def window_counts(layer_a: list, lo: int, hi: int) -> dict:
    """窓 lo〜hi の結末の数（README §3.3。記述だけ）。"""
    outs = [r["outcome"] for r in layer_a if lo <= r["window"] <= hi]
    c = Counter(outs)
    return {"windows": len(outs), "decided": c["A1"] + c["A2"], "A1": c["A1"], "A2": c["A2"],
            "tie": c[A.TIE], "none": c[A.NONE]}


def k_star(layer_a: list, e: int) -> int | None:
    """k*：窓 1〜e の中で、結末が A1 か A2 の最初の窓（README §3.3。共通の部分で二つの本体に同じことは O4・O10 で確かめる）。"""
    return next((r["window"] for r in layer_a if r["window"] <= e and r["outcome"] in A.ACTION_IDS), None)


def zero_label(layer_a: list, e: int) -> str | None:
    """構造的な 0 の札（README §4.1）：k* がなく、E のすべての窓が発火なしなら Z-1、引き分けがあれば Z-2。k* があれば None。"""
    if k_star(layer_a, e) is not None:
        return None
    return "Z-1" if all(r["outcome"] == A.NONE for r in layer_a if r["window"] <= e) else "Z-2"


def _by_pulse(activity: list, lo: int, hi: int) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {p: [] for p in range(lo, hi + 1)}
    for p, u in activity:
        if lo <= p <= hi:
            out[p].append(u)
    return {p: sorted(us) for p, us in out.items()}


def first_divergence(act_a: list, act_b: list, lo: int, hi: int) -> int | None:
    """区間 [lo, hi] で、全 Unit の発火の集まりが最初に違った Pulse（違わなければ None）。"""
    a, b = _by_pulse(act_a, lo, hi), _by_pulse(act_b, lo, hi)
    return next((p for p in range(lo, hi + 1) if a[p] != b[p]), None)


def first_window_divergence(la: list, lb: list) -> int | None:
    """窓の結末が最初に違った窓の番号（違わなければ None）。"""
    return next((x["window"] for x, y in zip(la, lb) if x["outcome"] != y["outcome"]), None)


def first_weight_divergence(rows_a: list, rows_b: list) -> int | None:
    """6 本の重みが最初に違った Pulse（違わなければ None）。"""
    return next((p for (p, wa), (_q, wb) in zip(rows_a, rows_b) if wa != wb), None)


def _ends(cid: str) -> tuple[str, str]:
    src, tgt = cid.split(".main->")
    return src, tgt


def pair_deviation(weights: Mapping[str, float]) -> Fraction:
    """各組の 2 本の和（正確な有理数）と w_max の差の絶対値の最大（F1。README §3.1・O6）。"""
    sums: dict[frozenset, Fraction] = {}
    for cid, w in weights.items():
        key = frozenset(_ends(cid))
        sums[key] = sums.get(key, Fraction(0)) + Fraction(w)
    return max(abs(s - Fraction(W_MAX)) for s in sums.values())


def _role_names(roles: Mapping) -> dict[str, str]:
    return {roles["cue"]: "cue", roles["source1"]: "source1", roles["source2"]: "source2"}


def role_cids(roles: Mapping) -> dict[str, str]:
    """役の名前（analysis.ROLES6）→ 接続の識別子。"""
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


def margin(unit_state: Mapping) -> float:
    """余裕 g ＝ c／(1 − λ) − θ（出生時の Unit の値から。README §7.2）。"""
    d = unit_state["dynamics"]
    return d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]


def _frac(x: Fraction | None) -> dict | None:
    return None if x is None else {"num": x.numerator, "den": x.denominator, "value": float(x)}


def _weights_of(sigma: Mapping) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in sorted(sigma["connections"].items())}


def _by_role(run: Mapping, weights: Mapping[str, float]) -> dict[str, float]:
    cids = role_cids(run["roles"])
    return {role: weights[cids[role]] for role in ROLES6}


def _row_by_role(run: Mapping, row: list[float]) -> dict[str, float]:
    return _by_role(run, dict(zip(run["connection_order"], row, strict=True)))


def quantities(w1: Mapping[str, float], w2: Mapping[str, float]) -> dict[str, Fraction]:
    """README §3.2 の量（analysis.contrasts の事前登録の定義。保存した倍精度の値を有理数として正確に）。"""
    c = AX.contrasts(w1, w2)
    return {name: c[key] for name, key in QUANTITIES.items()}


def individual(run: Mapping) -> dict:
    """1 個体の量（README §3・§4.1・§6）。生の記録だけから計算する。"""
    plan = M.Plan(**run["plan"])
    e, p_e = plan.e_windows, plan.p_e
    roles = run["roles"]
    names = _role_names(roles)
    bodies = run["bodies"]
    counts = {n: window_counts(bodies[n]["layer_a"], 1, e) for n in M.SYSTEMS}
    la1 = bodies["B_A1"]["layer_a"]
    ks = k_star(la1, e)
    w_pe = {n: _by_role(run, _weights_of(bodies[n]["sigma_p_e"])) for n in M.SYSTEMS}
    q = quantities(w_pe["B_A1"], w_pe["B_A2"])
    # 命題 S-1 の札（出生時の値から）と、それに反する発火の有無（どの本体でも）
    units = run["birth_units"]
    g = {names[u]: margin(units[u]) for u in names}
    silent = {role: g[role] < -E_S for role in SOURCES}
    fired = {u for n in M.SYSTEMS for _, u in bodies[n]["activity"]}
    violations = sorted(role for role in SOURCES if silent[role] and roles[role] in fired)
    # R4：窓の境界ごとの 6 本の重み（観測する本体の Pulse ごとの重みから）と、そこで計算した δ の符号
    rows = {n: {p: w for p, w in bodies[n]["pulse_weights"]} for n in M.BODIES}
    at = {n: [_row_by_role(run, rows[n][p]) for p in plan.boundaries] for n in M.BODIES}
    boundaries = {"pulses": plan.boundaries} | {n: {role: [w[role] for w in at[n]] for role in ROLES6} for n in M.BODIES} \
        | {"delta_signs": [sign(quantities(x, y)["delta"]) for x, y in zip(at["B_A1"], at["B_A2"], strict=True)]}
    # R5：E で受けた結果の刺激の数（成立した結果の予約）と、行動 ID が規則 c の決まった窓の数（SE-B2）
    consequences = {}
    for n in M.SYSTEMS:
        w = bodies[n]["world_end"]
        cons = {r[0] for r in w["reserved"] if r[1] == A.CONSEQUENCE}
        stimuli = sum(cnt for pulse, _r, rids, cnt in w["realized"] if pulse <= p_e and set(rids) <= cons and rids)
        consequences[n] = {"stimuli": stimuli, "decided_of_rule_c": counts[n][M.RULE_OF[n]]}
    # R6：B^{A1} と B^{A2} が最初に分かれた Pulse・窓
    b1, b2 = bodies["B_A1"], bodies["B_A2"]
    divergence = {"firing": first_divergence(b1["activity"], b2["activity"], 1, p_e),
                  "window": first_window_divergence(b1["layer_a"], b2["layer_a"]),
                  "weights": first_weight_divergence(b1["pulse_weights"], b2["pulse_weights"])}
    # R7：E の発火の数（役ごと）
    firing = {n: {names[u]: sum(1 for p, x in bodies[n]["activity"] if x == u and p <= p_e) for u in names} for n in M.SYSTEMS}
    return {
        "roles": {k: roles[k] for k in ROLES3},
        "birth": {names[u]: {"threshold": units[u]["dynamics"]["threshold"],
                             "intrinsic_drive": units[u]["dynamics"]["intrinsic_drive_per_second"], "margin_g": g[names[u]]}
                  for u in names},
        "S1": {"silent_source": silent, "violations": violations},
        "k_star": ks,
        "structural_zero": zero_label(la1, e),
        "other_zero": ks is not None and q["delta"] == 0,
        "counts_E": counts,
        "quantities": {name: _frac(v) | {"sign": sign(v)} for name, v in q.items()},
        "delta_plus_delta_back": _frac(q["delta"] + q["delta_back"]),
        "weights_P_E": w_pe,
        "weight_differences": {role: _frac(Fraction(w_pe["B_A1"][role]) - Fraction(w_pe["B_A2"][role])) for role in ROLES6},
        "pair_sum_max_deviation": {n: float(pair_deviation(_weights_of(bodies[n]["sigma_p_e"]))) for n in M.SYSTEMS},
        "boundaries": boundaries,
        "consequences": consequences,
        "first_divergence": divergence,
        "never_diverged": all(v is None for v in divergence.values()),
        "firing_E": firing,
    }


# ---- 判定と推定（README §4・§5） -----------------------------------------------------------------------------

def binom_upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, j) for j in range(k, m + 1)), 2 ** m)


def k2_of_m(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと。分数で厳密に。どの k でも満たさなければ m ＋ 1）。
    m ＝ 200 のときは protocol の k2_200 と同じであることを確かめる。"""
    jb = PROTOCOL["judgment"]["J_B"]
    alpha = Fraction(str(jb["alpha"]["per_direction"]))
    k = next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)
    if m == jb["m"] and k != jb["k2_200"]:
        raise ValueError(f"protocol の k₂({m}) ＝ {jb['k2_200']} が二項の計算 {k} と違う")
    return k


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """二項の和の二分法（0036〜0040 と同じ）。"""
    a = 1 - level

    def cdf(k: int, p: float) -> float:
        return sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k + 1))

    def solve(f, lo=0.0, hi=1.0) -> float:
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if x == 0 else solve(lambda p: 1 - cdf(x - 1, p) >= a / 2)
    upper = 1.0 if x == n else solve(lambda p: cdf(x, p) <= a / 2)
    return lower, upper


def interval(x: int, n: int) -> dict:
    """§5.2：分母が 1 以上なら必ず計算する（判定に使わない）。0 なら計算できない。"""
    if n < 1:
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "m = 0"}
    return {"computed": True, "interval": list(clopper_pearson(x, n)), "numerator": x, "denominator": n}


def _signs(group: list[Mapping], name: str) -> dict[str, int]:
    c = Counter(v["quantities"][name]["sign"] for v in group)
    return {s: c[s] for s in SIGNS}


def _part(x: int, m: int) -> dict:
    return {"count": x, "proportion": x / m if m else None, "interval": interval(x, m)}


def judge(individuals: Mapping[str, Mapping]) -> dict:
    """J_B（README §4.3）：生まれた全個体を分母にし、向きごとの個体の数 ≥ k₂(m) で、その向きで成立。判定不能の区分はない。
    数と区間は、判定の成否に依らず必ず出す。"""
    group = list(individuals.values())
    m = len(group)
    counts = _signs(group, "delta")
    k = k2_of_m(m)
    direction = "+" if counts["+"] >= k else ("-" if counts["-"] >= k else None)
    table = {"m": m, "counts": counts, "proportion": {s: (counts[s] / m if m else None) for s in ("+", "-")},
             "interval": {s: interval(counts[s], m) for s in ("+", "-")},
             "k2": k, "tail_probability": float(binom_upper_tail(m, k)),
             "status": "established" if direction else "not_established", "direction": direction}
    return {"J_B": table, "outcome": {"+": "plus", "-": "minus", None: "not_established"}[direction]}


def five_numbers(values: list) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null。0036〜0040 と同じ）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def estimate(individuals: Mapping[str, Mapping]) -> dict:
    """主の推定 E_B（README §4.4。判定ではない。閾値を置かない）。分母は J_B と同じ m（生まれた全個体）。"""
    group = list(individuals.values())
    m = len(group)
    counts = _signs(group, "delta")
    absolute = [abs(v["quantities"]["delta"]["value"]) for v in group]
    return {"m": m, "p_change": _part(counts["+"] + counts["-"], m), "p_plus": _part(counts["+"], m),
            "p_minus": _part(counts["-"], m),
            "abs_delta": {"all": five_numbers(absolute), "changed": five_numbers([x for x in absolute if x != 0])},
            "note": NOTES["estimate"]}


def _opposite(s: str) -> str:
    return {"+": "-", "-": "+", "0": "0"}[s]


def descriptive_controls(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.1：必ず報告する記述の対照（検定しない。主の判定に替えない）。"""
    group = list(individuals.values())
    diverged = [v for v in group if v["k_star"] is not None]
    n = len(diverged)
    dc = _signs(diverged, "delta")
    cells = {a + b: 0 for a in SIGNS for b in SIGNS}
    for v in group:
        cells[v["quantities"]["q_1"]["sign"] + v["quantities"]["q_2"]["sign"]] += 1
    ec = _signs(group, "epsilon")
    m = len(group)
    withdrawn = sum(len(v["S1"]["violations"]) for v in group) > 0
    return {
        "diverged": {"count": n, "counts": dc, "proportion": {s: (dc[s] / n if n else None) for s in ("+", "-")},
                     "interval": {s: interval(dc[s], n) for s in ("+", "-")},
                     "delta": five_numbers([v["quantities"]["delta"]["value"] for v in diverged])},
        "delta_back": {"counts": _signs(group, "delta_back"),
                       "sign_not_opposite_to_delta": sum(1 for v in group if v["quantities"]["delta_back"]["sign"]
                                                         != _opposite(v["quantities"]["delta"]["sign"])),
                       "max_abs_delta_plus_delta_back": max((abs(v["delta_plus_delta_back"]["value"]) for v in group),
                                                            default=None)},
        "epsilon": {"counts": ec, "proportion": {s: (ec[s] / m if m else None) for s in ("+", "-")},
                    "interval": {s: interval(ec[s], m) for s in ("+", "-")},
                    "distribution": five_numbers([v["quantities"]["epsilon"]["value"] for v in group])},
        "cross_table_q": {"order": ["q_1", "q_2"], "cells": cells},
        "zero_table": {
            "structural": {z: sorted(s for s, v in individuals.items() if v["structural_zero"] == z) for z in ("Z-1", "Z-2")},
            "other_zero": sorted(s for s, v in individuals.items() if v["other_zero"]),
            "silent_source": None if withdrawn else {r: sorted(s for s, v in individuals.items() if v["S1"]["silent_source"][r])
                                                     for r in SOURCES},
            "S1_labels_withdrawn": withdrawn},
    }


def auxiliary(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.2 の R1〜R8 の全体の数（判定に使わない）。"""
    vals = list(individuals.values())
    violations = sum(len(v["S1"]["violations"]) for v in vals)
    out: dict = {"R1": {
        "individuals": len(vals),
        "k_star": {"none": sum(1 for v in vals if v["k_star"] is None),
                   "windows": five_numbers([v["k_star"] for v in vals if v["k_star"] is not None])},
        "structural_zero": {z: sum(1 for v in vals if v["structural_zero"] == z) for z in ("Z-1", "Z-2")},
        "other_zero": sum(1 for v in vals if v["other_zero"]),
        # 命題 S-1：反する発火があれば、その件数を開示し、札の報告を取り下げる（README §7.2。判定は S-1 に依らない）
        "S1": {"E_S": E_S, "violations": violations, "labels_withdrawn": violations > 0,
               "individuals_with_silent_source": None if violations else sum(1 for v in vals
                                                                             if any(v["S1"]["silent_source"].values())),
               "per_source": None if violations else {r: sum(1 for v in vals if v["S1"]["silent_source"][r]) for r in SOURCES}},
    }}
    out["R2"] = {n: {k: five_numbers([v["counts_E"][n][k] for v in vals]) for k in ("decided", "A1", "A2", "tie", "none")}
                 for n in M.SYSTEMS}
    out["R3"] = {name: five_numbers([v["quantities"][name]["value"] for v in vals]) for name in QUANTITIES} \
        | {"abs_delta": five_numbers([abs(v["quantities"]["delta"]["value"]) for v in vals])}
    pulses = vals[0]["boundaries"]["pulses"] if vals else []
    out["R4"] = {"P_E_weights": {n: {role: five_numbers([v["weights_P_E"][n][role] for v in vals]) for role in ROLES6}
                                 for n in M.SYSTEMS},
                 "differences_B_A1_minus_B_A2": {role: five_numbers([v["weight_differences"][role]["value"] for v in vals])
                                                 for role in ROLES6},
                 "pair_sum_max_deviation": max((x for v in vals for x in v["pair_sum_max_deviation"].values()), default=None),
                 "boundary_delta_signs": [{"pulse": p} | {s: sum(1 for v in vals if v["boundaries"]["delta_signs"][i] == s)
                                                         for s in SIGNS} for i, p in enumerate(pulses)],
                 "boundary_weights": NOTES["R4"]}
    out["R5"] = {n: {"stimuli": five_numbers([v["consequences"][n]["stimuli"] for v in vals]),
                     "equals_decided_of_rule_c": all(v["consequences"][n]["stimuli"] == v["consequences"][n]["decided_of_rule_c"]
                                                     for v in vals)} for n in M.SYSTEMS}
    out["R6"] = {key: {"none": sum(1 for v in vals if v["first_divergence"][key] is None),
                       "values": five_numbers([v["first_divergence"][key] for v in vals if v["first_divergence"][key] is not None])}
                 for key in ("firing", "window", "weights")} | {"never_diverged": sum(1 for v in vals if v["never_diverged"])}
    out["R7"] = {n: {role: five_numbers([v["firing_E"][n][role] for v in vals]) for role in ROLES3} for n in M.SYSTEMS}
    out["R8"] = NOTES["R8"]
    return out


# ---- 操作の確認（README §8） -----------------------------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "birth_units", "connection_order", "W_0", "steps", "bodies"}
END_KEYS = {"activity", "sensory", "delta_log", "layer_a", "layer_b", "audit", "world_end", "sigma_p_e", "sigma_p_e_sha256",
            "history", "pulse_end"}
# 観測する本体は Σ_0・Pulse ごとの重み・k* の意図の Σ を実測して持つ。B′^{A1} は P_E の記録だけ（README §2.2 の観測の区分）
BODY_KEYS = {n: END_KEYS | {"sigma_0", "pulse_weights", "first_intent"} for n in M.BODIES} | {M.RERUN: END_KEYS}
AUDIT_KEYS = {"ok", "matched", "only_in_layer_a", "only_in_layer_b", "win_windows", "issued",
              "identity_issued_plus_carried_equals_wins", "duplicate_delta_ids", "carried_over_windows", "log_matches_world"}
EMPTY_INTERVENTIONS = {"active": [], "frozen": {}}
RULE_C_PATH = ("world", "rule", "rule_c")


def _prefix_allowed(path) -> bool:
    """k* の意図の Pulse の後に、規則 c だけが違う二つの本体で違ってよい欄：世界の規則 c と、結果の予約（予約の列と、次の予約の番号）。"""
    p = tuple(path)
    return p in (RULE_C_PATH, ("world", "next_rid")) or p[:2] in (("world", "pending"), ("world", "reserved"))


def _plan(run) -> "M.Plan":
    return M.Plan(**run["plan"])


def _as_row(run, weights: Mapping[str, float]) -> list[float]:
    return [weights[cid] for cid in run["connection_order"]]


def _windows(plan) -> list[list[int]]:
    return [list(w) for w in plan.schedule().windows]


def _expand_realized(world: Mapping) -> list:
    """世界の成立の記録を、感覚の出来事の列 [Pulse, Receptor]（個数の分だけ並べる）にする。"""
    return [[pulse, receptor] for pulse, receptor, _rids, n in world["realized"] for _ in range(n)]


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, out["structure"])
        if not out["structure"]:
            for name, f in (("O3", _o3), ("O4", _o4), ("O5", _o5), ("O6", _o6), ("O7", _o7), ("O8", _o8), ("O9", _o9),
                            ("O10", _o10)):
                try:
                    f(run, out[name])
                except Exception as e:                       # noqa: BLE001  記録の形が壊れていても止めずに、その確認を不成立にする
                    out[name].append(f"記録を読めない：{e!r}")
            try:
                _o2(data, mode, out["O2"])
            except Exception as e:                           # noqa: BLE001
                out["O2"].append(f"記録を読めない：{e!r}")
        _o11(seed, mode, out["O11"])
    except Exception as e:                                   # noqa: BLE001
        out["structure"].append(f"記録を読めない：{e!r}")
    return out


def _structure(data, mode, seed, plan, out) -> None:
    run = data.get("run", {})
    if set(data) != {"meta", "run"}:
        out.append(f"raw の最上位の欄が {sorted(data)}")
    if set(run) != RUN_KEYS:
        out.append(f"run の欄が {sorted(run)}（判定の量の欄を raw に入れない）")
        return
    if set(run["bodies"]) != set(BODY_KEYS) or any(set(run["bodies"][n]) != keys for n, keys in BODY_KEYS.items()):
        out.append("bodies の本体の組・欄が違う")
        return
    for n in M.SYSTEMS:
        if set(run["bodies"][n]["audit"]) != AUDIT_KEYS:
            out.append(f"{n}：道具の突合の記録の欄が違う")
    if run["seed"] != seed:
        out.append(f"seed が {run['seed']}")
    want = plan or M.formal_plan(PROTOCOL)
    if mode in ("formal", "smoke") and plan is not None and plan != M.formal_plan(PROTOCOL):
        out.append("本番・smoke では protocol の Plan だけを使う")
    if run["plan"] != json.loads(json.dumps(dataclasses.asdict(want))):
        out.append("raw の plan が使う Plan と違う")
    if run["roles"] != A.assign_roles(seed).as_dict():
        out.append("役の割り当てが assign_roles と違う")
    if len(run["W_0"]) != 6 or set(run["W_0"].values()) != {W0} or run["connection_order"] != sorted(run["W_0"]) \
            or set(run["W_0"]) != set(role_cids(run["roles"]).values()):
        out.append("W_0 が出生時の値（6 本とも w0）ではないか、接続の組・順が違う")
    if set(run["birth_units"]) != set(A.UNITS):
        out.append("出生時の Unit の記録が 3 Unit ではない")
    meta = data.get("meta", {})
    for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode), ("seed", seed)):
        if meta.get(k) != v:
            out.append(f"meta の {k} が {meta.get(k)}")
    if meta.get("manifest") != M.manifest_raw():
        out.append("meta の設計図が AS2b の設計図と違う")
    _protocol_binding(meta, out)
    want_blind = {"smoke": True, "formal": False}.get(mode)
    if not isinstance(meta.get("blind"), bool) or (want_blind is not None and meta["blind"] is not want_blind):
        out.append(f"meta の blind が {meta.get('blind')}（smoke は盲検、本番は盲検でない）")


def _protocol_binding(meta: Mapping, out: list[str]) -> None:
    """meta の protocol の写しが存在し、確定済みの protocol.yaml（正本）と一致すること。独立の検算は、この写しを正本と照らし直す。"""
    if "protocol" not in meta or "protocol_sha256" not in meta:
        out.append("meta に protocol の写し・SHA-256 がない（独立の検算が確定済みの条件で再検証できない）")
        return
    if meta["protocol_sha256"] != PROTOCOL_SHA256:
        out.append("meta の protocol の SHA-256 が、確定済みの protocol.yaml と違う")
    if meta["protocol"] != PROTOCOL_AS_STORED:
        out.append("meta の protocol の写しが、確定済みの protocol.yaml と違う")


def expected_steps(run) -> list:
    """README §2.4 の T0〜T2：観測する本体は 1 Pulse ずつ、B′^{A1} は一度に、P_E まで。"""
    p_e = _plan(run).p_e
    steps = []
    for n in M.BODIES:
        steps += [["T0", n, 0, "build", {"rule_c": M.RULE_OF[n], "respond": True}],
                  ["T1", n, p_e, "advance_each_pulse", {"from": 0}], ["T2", n, p_e, "end_records", None]]
    steps += [["T0", M.RERUN, 0, "build", {"rule_c": M.RULE_OF[M.RERUN], "respond": True}],
              ["T1", M.RERUN, p_e, "advance_to", {"from": 0}], ["T2", M.RERUN, p_e, "end_records", None]]
    return steps


def _o2(data, mode, out) -> None:
    """関門の組（README §1.1）：宣言の SHA-256 と、すべての本体の予定・o・W・L・世界・役・規則 c の組・出口・世界が応じること。
    どの本体も P_E で止まっている（手順の記録）。"""
    run, gate = data["run"], data["meta"].get("gate")
    if not isinstance(gate, Mapping) or gate.get("sha256") != GATE_SHA256 or gate.get("declaration") != GATE_DECLARATION:
        out.append("meta の関門の宣言・SHA-256 が、v0.2（protocol の値・リポジトリのファイル）と違う")
        return
    plan = _plan(run)
    if mode in ("formal", "smoke"):
        e_windows = int(PROTOCOL["timeline"]["experience_E"]["windows"][1])
        if plan != M.plan_from_declaration(gate["declaration"], e_windows):
            out.append("区間・予定が、関門の宣言から取った値と違う")
    windows = _windows(plan)
    cues = [[A.CUE, run["roles"]["cue_receptor"], c] for c in plan.schedule().cues]
    action_of = {run["roles"]["source1"]: "A1", run["roles"]["source2"]: "A2"}
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        rule = {"cue_receptor": run["roles"]["cue_receptor"], "delay": plan.delay, "rule_c": M.RULE_OF[n],
                "respond": True, "multiplicity": AS1.PER_RESERVATION}
        if rec["world_end"]["rule"] != rule:
            out.append(f"{n}：世界の規則（L・規則 c・手がかりの Receptor・応じる・多重度）が違う")
        if [[r["window"], r["open"], r["close"]] for r in rec["layer_a"]] != windows[:plan.e_windows]:
            out.append(f"{n}：窓（番号・区間）が、宣言の予定・o・W から作った窓 1〜{plan.e_windows} と違う")
        if [[r[1], r[2], r[3]] for r in rec["world_end"]["reserved"] if r[1] == A.CUE] != cues:
            out.append(f"{n}：手がかりの予約が、宣言の予定と違う")
        if rec["pulse_end"] != plan.p_e:
            out.append(f"{n}：止まった Pulse が {rec['pulse_end']}（P_E は {plan.p_e}）")
        sigmas = [rec["sigma_p_e"]] + ([rec["sigma_0"]] if n in M.BODIES else [])
        if any(s["exit"] is None or s["exit"]["windows"] != windows or s["exit"]["action_of"] != action_of for s in sigmas):
            out.append(f"{n}：出口の窓の写し・行動 ID の対応が違う（出口がない）")
        if n in M.BODIES and rec["sigma_0"]["world"]["rule"] != rule:
            out.append(f"{n}：Pulse 0 の世界の規則が違う")
    if run["steps"] != expected_steps(run):
        out.append("T0〜T2 の手順の記録が、決めた順序・Pulse・操作と違う（どの本体も P_E で止める）")


def _o3(run, out) -> None:
    """CT-E10 の突合を、保存した層 A・層 B・来歴のログから計算し直す。窓 1〜25 への到達、P_E に未発行の予定がないこと。"""
    plan = _plan(run)
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        la, lb = rec["layer_a"], rec["layer_b"]
        emitted = Counter((r["emit_pulse"], r["winner_unit"], r["action"]) for r in la if r["emitted"])
        received = Counter((p, src, act) for p, _did, src, act in lb)
        wins = sum(1 for r in la if r["winner_unit"] is not None)
        carried = [r["window"] for r in la if r["winner_unit"] is not None and not r["emitted"]]
        ids = [did for _p, did, _src, _act in lb]
        if emitted != received:
            out.append(f"{n}：層 A の「出した」記録と層 B の意図の記録が一対一でない")
        if len(lb) + len(carried) != wins or carried:
            out.append(f"{n}：発行済み ＋ 未発行の予定 ≠ 勝ちの窓、または P_E に未発行の予定がある")
        if len(ids) != len(set(ids)):
            out.append(f"{n}：Delta の識別子が重複している")
        if [r["window"] for r in la] != list(range(1, plan.e_windows + 1)):
            out.append(f"{n}：窓 1〜{plan.e_windows} に到達していない（窓の番号の重複・欠落・余分）")
        if sorted(rec["delta_log"]) != sorted(lb):
            out.append(f"{n}：来歴のログの意図が、世界の受けた意図の記録と違う")
        au = rec["audit"]
        ok = (au["ok"] is True and au["log_matches_world"] is True and au["only_in_layer_a"] == []
              and au["only_in_layer_b"] == [] and au["duplicate_delta_ids"] == 0
              and au["identity_issued_plus_carried_equals_wins"] is True and au["carried_over_windows"] == []
              and au["win_windows"] == wins and au["issued"] == len(lb) and au["matched"] == len(lb))
        if not ok:
            out.append(f"{n}：道具の突合の記録が ok でないか、計算し直した値と違う")


def _o4(run, out) -> None:
    """R-7 の対（SE-B1）：Pulse 0 の Σ の違いは規則 c だけ。窓 1〜k* の記録が同じ。k* の意図の Pulse の処理の後の脳の側の Σ が
    同じで、結果の予約は規則 c が k* の行動 ID を指す本体にだけある。k* がない個体では、P_E まで規則 c のほかが同じ。"""
    e = _plan(run).e_windows
    ra, rb = run["bodies"]["B_A1"], run["bodies"]["B_A2"]
    if sorted(tuple(p) for p in AS1.sigma_diff(ra["sigma_0"], rb["sigma_0"])) != [RULE_C_PATH]:
        out.append("B_A1 と B_A2 の Pulse 0 の Σ の違いが、規則 c だけではない")
    ka, kb = k_star(ra["layer_a"], e), k_star(rb["layer_a"], e)
    if (ka is None) != (kb is None):
        out.append("B_A1 と B_A2 で、k* の有無が違う")
        return
    if ka is None:
        if ra["first_intent"] is not None or rb["first_intent"] is not None:
            out.append("k* がないのに、k* の意図の Σ がある")
        if any(ra[k] != rb[k] for k in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "pulse_weights")):
            out.append("k* がないのに、発火・感覚・層 A・層 B・意図・重みが違う")
        if sorted(tuple(p) for p in AS1.sigma_diff(ra["sigma_p_e"], rb["sigma_p_e"])) != [RULE_C_PATH]:
            out.append("k* がないのに、P_E の Σ の違いが規則 c だけではない")
        return
    if ra["layer_a"][:ka] != rb["layer_a"][:ka]:
        out.append("B_A1 と B_A2 の窓 1〜k* の記録が違う")
        return
    first = ra["layer_a"][ka - 1]
    t = first["decision_pulse"] + 1
    ia, ib = ra["first_intent"], rb["first_intent"]
    if ia is None or ib is None or ia["pulse"] != t or ib["pulse"] != t \
            or ia["sigma"]["pulse"] != t or ib["sigma"]["pulse"] != t:
        out.append("k* の意図の Pulse（決定の翌 Pulse）の処理の後の Σ がない")
        return
    if not all(_prefix_allowed(p) for p in AS1.sigma_diff(ia["sigma"], ib["sigma"])):
        out.append("k* の意図の Pulse の後の脳の側の Σ（世界の規則 c と予約のほか）が違う")
    for x, y in ((ia, "B_A1"), (ib, "B_A2")):
        cons = [[r[3], r[4]] for r in x["sigma"]["world"]["reserved"] if r[1] == A.CONSEQUENCE]
        delay = x["sigma"]["world"]["rule"]["delay"]
        want = [[t + delay - 1, x["sigma"]["world"]["intents"][-1][1]]] if M.RULE_OF[y] == first["outcome"] else []
        if cons != want:
            out.append(f"{y}：k* の意図の Pulse の後の結果の予約が、規則 c が k* の行動 ID を指す本体にだけ 1 つ、になっていない")
    if [x for x in ra["activity"] if x[0] <= t] != [x for x in rb["activity"] if x[0] <= t]:
        out.append("B_A1 と B_A2 の、k* の意図の Pulse までの発火が違う")
    if ra["pulse_weights"][:t] != rb["pulse_weights"][:t]:
        out.append("B_A1 と B_A2 の、k* の意図の Pulse までの重みが違う")


def _o5(run, out) -> None:
    """世界の規則（CT-W1・W3、SE-B2）：源の Receptor の出来事が 0。結果は、行動 ID が規則 c の意図にだけ、意図の Pulse ＋ L − 1。
    その数が、行動 ID が c の決まった窓の数に等しい。"""
    plan = _plan(run)
    cue_r = run["roles"]["cue_receptor"]
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        w = rec["world_end"]
        if any(r != cue_r for _, r in rec["sensory"]) or any(row[1] != cue_r for row in w["realized"]):
            out.append(f"{n}：手がかりの Receptor のほかに感覚の出来事がある（K1）")
        want = sorted([cue_r, p + plan.delay - 1, did] for p, did, _src, act in rec["layer_b"] if act == M.RULE_OF[n])
        got = sorted([r[2], r[3], r[4]] for r in w["reserved"] if r[1] == A.CONSEQUENCE)
        if got != want:
            out.append(f"{n}：結果の予約が、行動 ID が規則 c の意図ごとに意図の Pulse ＋ L − 1 へ 1 つ、だけになっていない")
        if len(got) != sum(1 for r in rec["layer_a"] if r["outcome"] == M.RULE_OF[n]):
            out.append(f"{n}：結果の刺激の数が、行動 ID が規則 c の決まった窓の数と違う（SE-B2）")
        if any(r[1] not in (A.CUE, A.CONSEQUENCE) for r in w["reserved"]) or w["cancelled"]:
            out.append(f"{n}：手がかり・結果のほかの予約か、取り消しがある")
        if any(len(rids) != 1 or cnt != 1 for _p, _r, rids, cnt in w["realized"]):
            out.append(f"{n}：予約が同じ Pulse に重なった")
        if sorted(_expand_realized(w)) != sorted([r[3], r[2]] for r in w["reserved"] if r[3] <= plan.p_e):
            out.append(f"{n}：成立した感覚の出来事が、P_E までの手がかりと結果の予約と違う")
        if rec["sensory"] != _expand_realized(w):
            out.append(f"{n}：来歴のログの感覚の出来事が、世界の成立の記録と違う")


def _pairs(order: list[str]) -> list[tuple[int, int]]:
    """接続の順の中で、同じ二つの Unit の 2 本（組）の位置の対。"""
    index = {cid: i for i, cid in enumerate(order)}
    out = []
    for cid, i in index.items():
        src, tgt = _ends(cid)
        j = index[f"{tgt}.main->{src}"]
        if i < j:
            out.append((i, j))
    return out


def _row_ok(row: list[float], pairs: list[tuple[int, int]]) -> bool:
    return all(W_MIN <= w <= W_MAX for w in row) and all(abs(row[i] + row[j] - W_MAX) <= F1_TOLERANCE for i, j in pairs)


def _o6(run, out) -> None:
    """重みの範囲と F1（SE-B5）：観測する本体の Pulse ごとの重みと、3 本体の P_E の重みが [0, w_max] にあり、各組の 2 本の和と
    w_max の差の絶対値が 10⁻¹² 以下。どの本体の介入の履歴・介入の状態も空。"""
    order = run["connection_order"]
    pairs = _pairs(order)
    if len(pairs) != 3:
        out.append("接続の組が 3 組ではない")
        return
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        if not _row_ok(_as_row(run, _weights_of(rec["sigma_p_e"])), pairs):
            out.append(f"{n}：P_E の重みが範囲の外か、組の和が w_max から 10⁻¹² より離れている")
        if n in M.BODIES and not all(_row_ok(w, pairs) for _p, w in rec["pulse_weights"]):
            out.append(f"{n}：ある Pulse の重みが範囲の外か、組の和が w_max から 10⁻¹² より離れている")
        if rec["history"] != []:
            out.append(f"{n}：介入の履歴が空ではない（介入をしない）")
        sigmas = [rec["sigma_p_e"]] + ([rec["sigma_0"]] if n in M.BODIES else []) \
            + ([rec["first_intent"]["sigma"]] if n in M.BODIES and rec["first_intent"] is not None else [])
        if any(s["interventions"] != EMPTY_INTERVENTIONS for s in sigmas):
            out.append(f"{n}：介入の状態が空ではない")


def _o7(run, out) -> None:
    """境界 P_E（SE-B7）：どの本体も Pulse の番号が P_E で、未決の窓・出す予定の意図・結果の予約がない。残る予約は、P_E より後の
    手がかり（窓 E ＋ 1〜K。関門の予定のまま、組み立てのときに置いたもの）だけ。"""
    plan = _plan(run)
    p_e, e = plan.p_e, plan.e_windows
    cue_r = run["roles"]["cue_receptor"]
    later = [[A.CUE, cue_r, c] for c in plan.schedule().cues if c > p_e]
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        s = rec["sigma_p_e"]
        if rec["pulse_end"] != p_e or s["pulse"] != p_e:
            out.append(f"{n}：Pulse の番号が P_E ではない")
        ex = s["exit"]
        if ex["cursor"] != e or ex["pending"] is not None or ex["reports_pulse"] is not None or ex["reports"] != {}:
            out.append(f"{n}：P_E に未決の窓・出す予定の意図・そろっていない報告がある")
        if ex["records"] != rec["layer_a"] or any(r["close"] > p_e for r in rec["layer_a"]):
            out.append(f"{n}：P_E の出口の記録が層 A と違うか、P_E より後に閉じる窓がある")
        w = rec["world_end"]
        if w != s["world"]:
            out.append(f"{n}：世界の記録が P_E の Σ の世界と違う")
        if sorted([r[1], r[2], r[3]] for r in w["pending"]) != later:
            out.append(f"{n}：P_E に残る予約が、P_E より後の手がかりだけではない（結果の予約が残っている）")
        if any(r[1] == A.CONSEQUENCE and r[3] > p_e for r in w["reserved"]):
            out.append(f"{n}：P_E より後の結果の予約がある")


def _o8(run, out) -> None:
    """記録の非干渉と決定論（SE-B4）：B′^{A1} の全 Unit の発火・層 A・層 B・感覚の出来事・意図・介入の履歴と、P_E の Σ の値の全体
    （主）が B^{A1} と同じ。SHA-256 は補助：保存した Σ から計算し直した値が、記録した値と、相手の値に一致する。"""
    ra, rb = run["bodies"]["B_A1"], run["bodies"][M.RERUN]
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "history"):
        if ra[key] != rb[key]:
            out.append(f"B′^{{A1}} と B^{{A1}}：{key} が違う")
    diff = AS1.sigma_diff(ra["sigma_p_e"], rb["sigma_p_e"])
    if diff:
        out.append(f"B′^{{A1}} と B^{{A1}}：P_E の Σ の値が違う（{[list(x) for x in diff[:3]]}）")
    for n, r in (("B_A1", ra), (M.RERUN, rb)):
        if M.sigma_sha256(r["sigma_p_e"]) != r["sigma_p_e_sha256"]:
            out.append(f"{n}：P_E の Σ の SHA-256 が、保存した Σ から計算し直した値と違う")
    if ra["sigma_p_e_sha256"] != rb["sigma_p_e_sha256"]:
        out.append("B′^{A1} と B^{A1}：P_E の Σ の SHA-256 が違う")
    if M.sigma_sha256(run["bodies"]["B_A2"]["sigma_p_e"]) != run["bodies"]["B_A2"]["sigma_p_e_sha256"]:
        out.append("B_A2：P_E の Σ の SHA-256 が、保存した Σ から計算し直した値と違う")


def _o9(run, out) -> None:
    """重みの記録の整合：観測する本体の Pulse ごとの重みが Pulse 1〜P_E のすべてにあり、P_E の値が P_E の Σ の重みと同じ。Σ_0 の重みが
    6 本とも w0。k* の意図の Σ の重みが、その Pulse の重みの記録と同じ。"""
    p_e = _plan(run).p_e
    for n in M.BODIES:
        rec = run["bodies"][n]
        rows = rec["pulse_weights"]
        if [p for p, _ in rows] != list(range(1, p_e + 1)):
            out.append(f"{n}：Pulse ごとの重みの記録が 1〜P_E にそろっていない")
            continue
        if rows[-1][1] != _as_row(run, _weights_of(rec["sigma_p_e"])):
            out.append(f"{n}：Pulse P_E の重みの記録が、P_E の Σ の重みと違う")
        if rec["sigma_0"]["pulse"] != 0 or _weights_of(rec["sigma_0"]) != run["W_0"]:
            out.append(f"{n}：Σ_0 が Pulse 0 ではないか、重みが出生時の値（w0）ではない")
        fi = rec["first_intent"]
        if fi is not None and not (1 <= fi["pulse"] <= p_e and rows[fi["pulse"] - 1][1] == _as_row(run, _weights_of(fi["sigma"]))):
            out.append(f"{n}：k* の意図の Σ の重みが、その Pulse の重みの記録と違う")


def layer_a_problems(layer_a: list, windows: list, roles: Mapping) -> list[str]:
    """層 A の窓ごとの記録の欄どうしの整合（番号・区間・結末・勝った源と行動 ID・決定と出した Pulse）。"""
    problems = []
    action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    if [r["window"] for r in layer_a] != [k for k, _a, _b in windows]:
        return ["窓の番号が予定と違う"]
    for r, (k, a, b) in zip(layer_a, windows):
        o, d = r["outcome"], r["decision_pulse"]
        if (r["open"], r["close"]) != (a, b) or o not in OUTCOMES:
            problems.append(f"窓 {k}：区間か結末が違う")
            continue
        inside = d is not None and a <= d <= b
        if o in A.ACTION_IDS:
            ok = (inside and r["action"] == o and action_of.get(r["winner_unit"]) == o
                  and r["emit_pulse"] == d + 1 and r["emitted"] is True)
        elif o == A.TIE:
            ok = inside and r["winner_unit"] is None and r["action"] is None and r["emit_pulse"] is None \
                and r["emitted"] is False
        else:
            ok = d is None and r["winner_unit"] is None and r["action"] is None and r["emit_pulse"] is None \
                and r["emitted"] is False
        if not ok:
            problems.append(f"窓 {k}：結末と記録の欄が合わない")
    return problems


def _o10(run, out) -> None:
    """量の計算：層 A から数え直した窓の結末が層 B の意図の記録と一致し、k* と構造的な 0 の札が二つの本体で同じ。P_E の Σ から
    計算した δ・q_1・q_2・δ^←・ε が、Pulse P_E の重みの記録から計算した値と一致し、k* がなければどれもちょうど 0。"""
    plan = _plan(run)
    e = plan.e_windows
    windows = [tuple(w) for w in plan.schedule().windows][:e]
    bodies = run["bodies"]
    for n in M.SYSTEMS:
        rec = bodies[n]
        problems = layer_a_problems(rec["layer_a"], windows, run["roles"])
        if problems:
            out.append(f"{n}：層 A の記録が整合しない（{problems[0]}）")
            continue
        c = window_counts(rec["layer_a"], 1, e)
        if c["decided"] + c["tie"] + c["none"] != e or c["windows"] != e:
            out.append(f"{n}：窓の結末の数の和が E の窓の数と違う")
        from_b: dict[int, str] = {}
        for p, _did, _src, act in rec["layer_b"]:
            k = next((k for k, a, b in windows if a <= p - 1 <= b), None)
            if k is None or k in from_b:
                out.append(f"{n}：層 B に、窓の決定に対応しない意図か、同じ窓の二つ目の意図がある")
                break
            from_b[k] = act
        else:
            if from_b != {r["window"]: r["outcome"] for r in rec["layer_a"] if r["outcome"] in A.ACTION_IDS}:
                out.append(f"{n}：層 A から数えた窓ごとの行動 ID が、層 B の意図の記録と違う")
    la1, la2 = bodies["B_A1"]["layer_a"], bodies["B_A2"]["layer_a"]
    if k_star(la1, e) != k_star(la2, e) or zero_label(la1, e) != zero_label(la2, e):
        out.append("k* か構造的な 0 の札が、二つの本体で違う")
    from_sigma = quantities(*(_by_role(run, _weights_of(bodies[n]["sigma_p_e"])) for n in M.BODIES))
    from_rows = quantities(*(_row_by_role(run, bodies[n]["pulse_weights"][-1][1]) for n in M.BODIES))
    if from_sigma != from_rows:
        out.append("P_E の Σ から計算した量が、Pulse P_E の重みの記録から計算した量と違う")
    if k_star(la1, e) is None and any(v != 0 for v in from_sigma.values()):
        out.append("k* がないのに、δ・q・δ^←・ε のどれかが 0 ではない（SE-B1）")


def _o11(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed {seed} は {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5。関門の 31001〜31040、0039 の 32001〜32399、"
                   "0040 の 33001〜33399 を含む）")


# ---- 記録の確認・前提・report（0040 と同じ） ----------------------------------------------------------

def verify_records(out: Path, mode: str, seeds: list[int]) -> dict:
    found = G.scan(out)
    problems = list(found["anomalies"])
    statuses = {s: st for s, (st, _) in found["seeds"].items()}
    for s, (st, why) in found["seeds"].items():
        if s not in seeds:
            problems.append(f"範囲の外・余分な seed {s}（{st}）がある")
        if st in ("failed", "started", "broken"):
            problems.append(f"seed {s} が {st}" + (f"（{'; '.join(why)}）" if why else ""))
    missing = [s for s in seeds if statuses.get(s, "absent") == "absent"]
    commits, shas = set(), set()
    for s in sorted(statuses):
        try:
            st = G.read_seed(out, s)["start"]
        except (OSError, ValueError):
            st = None
        if isinstance(st, dict):
            commits.add(st.get("measurement_commit"))
            shas.add(st.get("protocol_sha256"))
    for s in seeds:
        if statuses.get(s) != "completed":
            continue
        r = G.read_seed(out, s)
        st, fin = r["start"], r["finish"]
        if any(x.get(k) != v for x in (st, fin) for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode))):
            problems.append(f"seed {s} の開始・終了の記録の experiment・kind・mode が {EXPERIMENT}・{KIND}・{mode} ではない")
        if not G.SHA_RE.match(str(st.get("measurement_commit"))) or fin.get("measurement_commit_end") != st.get("measurement_commit"):
            problems.append(f"seed {s} の測定の commit が 40 桁でないか、開始と終了で違う")
    if len(commits) > 1:
        problems.append(f"seed によって測定の commit が違う（{sorted(map(str, commits))}）")
    if shas and shas != {G.sha256_file(REPO / PROTOCOL_PATH)}:
        problems.append("開始の記録の protocol.yaml の SHA-256 が今のものと違う")
    state = "failed" if problems else ("incomplete" if missing else "complete")
    commit = next(iter(commits)) if len(commits) == 1 else None
    return {"state": state, "problems": problems, "missing": missing,
            "measurement_commit": commit if G.SHA_RE.match(str(commit)) else None}


def provenance_problems(out: Path, runs: Mapping[int, dict], mode: str) -> list[str]:
    """raw の中身の meta と、開始・終了の記録の結び付き（0040 の道具 v0.3 と同じ）。測定の commit：raw の meta ＝ 開始の記録 ＝
    終了の記録の measurement_commit_end。protocol の SHA-256：raw の meta ＝ 開始の記録。seed：raw の meta ＝ 開始・終了の記録 ＝
    フォルダ。experiment・kind・mode も同じ。raw のファイルの SHA-256・バイト数も、終了の記録と照らし直す。"""
    problems = []
    for s, data in sorted(runs.items()):
        rec = G.read_seed(out, s)
        st, fin = rec["start"] or {}, rec["finish"] or {}
        meta = data.get("meta") if isinstance(data, Mapping) else None
        meta = meta if isinstance(meta, Mapping) else {}
        commit = meta.get("measurement_commit")
        if not G.SHA_RE.match(str(commit)) or commit != st.get("measurement_commit") or commit != fin.get("measurement_commit_end"):
            problems.append(f"seed {s} の raw の meta の測定の commit が、開始・終了の記録と違う")
        if meta.get("protocol_sha256") != st.get("protocol_sha256"):
            problems.append(f"seed {s} の raw の meta の protocol の SHA-256 が、開始の記録と違う")
        if not (meta.get("seed") == st.get("seed") == fin.get("seed") == s):
            problems.append(f"seed {s} の raw の meta・開始・終了の記録の seed が一致しない")
        if any(x.get(k) != v for x in (meta, st, fin) for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode))):
            problems.append(f"seed {s} の raw の meta・開始・終了の記録の experiment・kind・mode が {EXPERIMENT}・{KIND}・{mode} ではない")
        if rec["raw_sha256"] != fin.get("raw_file_sha256") or rec["raw_bytes"] != fin.get("raw_file_bytes"):
            problems.append(f"seed {s} の raw の SHA-256・バイト数が、終了の記録と違う")
    return problems


def check_blinded(data: Mapping, seed: int, mode: str = "smoke") -> dict[str, str]:
    """smoke の盲検の記録の確かめ（0040 と同じ）。O11（seed の範囲）は記録に頼らずここで確かめ直す。"""
    status = {k: "fail" for k in CHECK_NAMES}
    try:
        meta, blind = data["meta"], data["blind"]
        ok_shape = (set(data) == {"meta", "blind"} and set(blind) == BLIND_KEYS
                    and set(blind["checks"]) == set(CHECK_NAMES)
                    and all(v in ("ok", "fail") for v in blind["checks"].values())
                    and bool(SHA256_RE.match(str(blind["raw_sha256"])))
                    and all(meta.get(k) == v for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode),
                                                          ("seed", seed)))
                    and meta.get("blind") is True
                    and meta.get("manifest") == M.manifest_raw()
                    and meta.get("gate") == {"sha256": GATE_SHA256, "declaration": GATE_DECLARATION})
        binding: list[str] = []
        _protocol_binding(meta, binding)                             # 盲検の記録でも、protocol の写しを正本と照らす
        ok_shape = ok_shape and not binding
    except (KeyError, TypeError, AttributeError):
        ok_shape = False
    if not ok_shape:
        return status
    status = dict(blind["checks"])
    o11: list[str] = []
    _o11(seed, mode, o11)
    if o11:
        status["O11"] = "fail"
    return status


def o1_check(out: Path, commit: str | None, repo: Path | None = None) -> list[str]:
    """O1 の証拠（0040 と同じ）。テストのファイルの SHA-256 は repo（省略したときは呼んだ時点の REPO）のものと比べる。"""
    repo = REPO if repo is None else repo
    path = out / O1_FILE
    if not path.exists():
        return [f"{O1_FILE} がない（測定の commit で契約テストを走らせた記録がない）"]
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"{O1_FILE} を読めない（{e!r}）"]
    problems = []
    if not isinstance(rec, dict) or set(rec) != O1_KEYS:
        return [f"{O1_FILE} の欄が違う"]
    if rec["measurement_commit"] != commit:
        problems.append("契約テストを走らせた commit が測定の commit と違う")
    if rec["exit_code"] != 0:
        problems.append(f"契約テストの終了コードが {rec['exit_code']}")
    summary = str(rec["summary"])
    if " passed" not in summary or any(w in summary for w in (" failed", " error")):
        problems.append(f"契約テストの結果の行が、すべて通ったことを示していない（{summary}）")
    if list(rec["command"])[-len(CONTRACT_TESTS):] != list(CONTRACT_TESTS):
        problems.append("走らせた契約テストの組が違う")
    files = rec["test_files_sha256"]
    if not isinstance(files, dict) or set(files) != set(CONTRACT_TESTS):
        problems.append("テストのファイルの SHA-256 の組が違う")
    else:
        for f, sha in files.items():
            if sha != G.sha256_file(repo / f):
                problems.append(f"{f} の SHA-256 が、測定の commit のものと違う")
    return problems


def analyze_runs(runs: Mapping[int, dict], mode: str, plan: "M.Plan | None" = None, *, o1: list[str]) -> dict:
    """記録（seed → 本番・合成なら生の記録、smoke なら盲検の記録）と O1 の確かめの結果から、report の中身を作る。"""
    o1_status = "fail" if o1 else "ok"
    if mode == "smoke":
        checks = {str(s): check_blinded(data, s) for s, data in sorted(runs.items())}
        return {"mode": "smoke", "O1": o1_status, "checks": checks,
                "valid": not o1 and all(v == "ok" for c in checks.values() for v in c.values())}
    checks = {s: check_seed(data, mode, s, plan) for s, data in sorted(runs.items())}
    failed = {s: {k: v for k, v in c.items() if v} for s, c in checks.items() if any(c.values())}
    if failed or o1:
        return {"mode": mode, "valid": False, "O1": {"status": o1_status, "problems": o1},
                "failed_checks": {str(s): v for s, v in failed.items()}, "judgment": None, "estimate": None}
    individuals = {str(s): individual(data["run"]) for s, data in sorted(runs.items())}
    return {"mode": mode, "valid": True, "O1": {"status": o1_status, "problems": o1},
            "gate_declaration_sha256": GATE_SHA256,
            "judgment": judge(individuals),
            "estimate": estimate(individuals),
            "descriptive_controls": descriptive_controls(individuals),
            "individuals": individuals, "auxiliary": auxiliary(individuals)}


def verify_results_copy(src: Path, dst: Path) -> list[str]:
    """出力先 src と写し dst の照合（0040 と同じ）。鍵のファイル（run.lock）は写さない。"""
    def files(root: Path) -> dict[str, str]:
        return {str(p.relative_to(root)): G.sha256_file(p) for p in sorted(root.rglob("*"))
                if p.is_file() and p.name != G.LOCK}
    problems = []
    a, b = files(src), files(dst)
    if set(a) != set(b):
        problems.append(f"ファイルの組が違う（元だけ：{sorted(set(a) - set(b))}、写しだけ：{sorted(set(b) - set(a))}）")
    problems += [f"{f} の SHA-256 が元と違う" for f in sorted(set(a) & set(b)) if a[f] != b[f]]
    found = G.scan(dst)
    problems += found["anomalies"]
    commits = set()
    for s, (st, _) in sorted(found["seeds"].items()):
        rec = G.read_seed(dst, s)
        if st != "completed":
            problems.append(f"写しの seed {s} が {st}")
            continue
        commits.add(rec["start"].get("measurement_commit"))
        if G.sha256_file(G.seed_dir(dst, s) / G.RAW) != rec["finish"].get("raw_file_sha256"):
            problems.append(f"写しの seed {s} の raw が終了の記録の SHA-256 と違う")
    if (dst / REPORT).exists():
        rep = json.loads((dst / REPORT).read_text(encoding="utf-8"))
        if commits != {rep.get("measurement_commit")}:
            problems.append("report の測定の commit が、記録の測定の commit と違う")
    else:
        problems.append("写しに report がない")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", type=Path, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--verify-copy", type=Path, default=None, help="本番の出力先とその写し（results/）を照合するだけ")
    args = parser.parse_args()
    if args.verify_copy is not None:
        problems = verify_results_copy(REPO / OUT_DIR, args.verify_copy)
        if problems:
            raise SystemExit("写しが元と違う：\n- " + "\n- ".join(problems))
        print(f"写しは元と同じ：{args.verify_copy}")
        return
    ALIGN.check(PROTOCOL)
    mode = "smoke" if args.smoke else "formal"
    out = (args.out if args.smoke else REPO / OUT_DIR)
    if args.smoke and args.out is None:
        raise SystemExit("--smoke のときは作業用のフォルダを指定する")
    if not args.smoke and args.out is not None:
        raise SystemExit(f"本番の出力先は {OUT_DIR} に固定")
    seeds = expected_seeds(mode)
    records = verify_records(out, mode, seeds)
    if records["state"] == "incomplete":
        raise SystemExit(f"未完了（まだ始めていない seed：{records['missing']}）。集計しない")
    if records["measurement_commit"] is None:
        raise SystemExit("測定の commit が 1 つに定まらない。解析しない")
    G.verify_clean_commit(REPO, records["measurement_commit"])
    if (out / REPORT).exists():
        raise SystemExit("report は既にある（上書きしない）")
    shas = {}
    runs = {}
    if records["state"] == "complete":
        for s in seeds:
            raw = G.seed_dir(out, s) / G.RAW
            shas[str(s)] = G.sha256_file(raw)
            runs[s] = read_raw(raw)
        provenance = provenance_problems(out, runs, mode)                # raw の meta と開始・終了の記録の結び付き
        if provenance:
            records["state"], records["problems"] = "failed", records["problems"] + provenance
    with open(out / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "start", "at": G.now_iso(), "inputs": shas}) + "\n")
    o1 = o1_check(out, records["measurement_commit"])
    if records["state"] == "failed":
        report = {"mode": mode, "valid": False, "record_problems": records["problems"],
                  "O1": ("fail" if o1 else "ok") if mode == "smoke" else {"status": "fail" if o1 else "ok", "problems": o1},
                  "judgment": None, "estimate": None}
    else:
        report = analyze_runs(runs, mode, o1=o1)
    G.verify_clean_commit(REPO, records["measurement_commit"])
    report["measurement_commit"] = records["measurement_commit"]
    G.write_once(out / REPORT, json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    with open(out / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "complete", "at": G.now_iso(), "inputs": shas}) + "\n")
    print(f"report: {out / REPORT}")


if __name__ == "__main__":
    main()
