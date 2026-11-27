"""実験 0043（AS2b の候補 A の事前登録 v0.1）の解析の部分：区間の算術、重みの算術（自然な差の倍数・δ をそろえた対称な介入・
範囲・F1・札の入れ替え・入れ子）、量の定義と札の入れ替えの性質、主の段 k₀ を選ぶ算術、沈黙の十分条件（命題 S-1 の引き継ぎ）、
判定の閾値・検出力の見込み。

README §1.2・§2・§3・§4・§5・§7。seed・乱数・既存の raw（0038〜0042 の記録を含む）は使わない。値は次だけから計算する。
- C0 の設計図（experiments/0012_passive_world/neuroarchitecture.yaml）の力学・可塑性の値と、出生時のばらつきの幅
- 関門の宣言 v0.2（experiments/0038_as2b_forward_gate/gate_declaration.json）の予定・o・W・L・長さ
- 実験 0042 の README §15.6 の R4 の表に公表した、P_E の重みの五つの数（最小・四分位・最大）。主の段 k₀ と段の組の上限を
  決める範囲の算術にだけ使う（README §4.6）。0042 の選択の結果（T・S・δ と T の表など）は使わない
- この README で決める値（段の組、主の段、個体数、誤りの水準、最小の m）

重みの算術は、P_E の浮動小数の値を有理数として正確に扱い、端の重みごとに最後に一度だけ最近接の浮動小数に丸める（README §2.2）。
二項の確率と、試しの区間の割合 s とその差は、分数で厳密に計算する。命題 S-1 の E_S と沈黙の割合は、実験 0039・0041・0042 の
analysis.py と同じ式で求め直す（確定したそれらのファイルは読み込まない・変えない）。
"""

import hashlib
import json
import math
from fractions import Fraction
from math import comb
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
C0_MANIFEST = ROOT / "experiments" / "0012_passive_world" / "neuroarchitecture.yaml"
GATE_DECLARATION = ROOT / "experiments" / "0038_as2b_forward_gate" / "gate_declaration.json"
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"

E_WINDOWS = 25                 # 経験の区間 E ＝ 窓 1〜25（0039・0041・0042 の事前登録の E と同じ）
INDIVIDUALS = 200              # 本番の個体数（README §5.3）
ALPHA_PER_SIDE = Fraction(1, 40)   # 両側 0.05 を、向きごとに 0.025 に分ける（README §4.4）
MIN_M = 10                     # 判定に必要な、C_{k₀} ≠ 0 の個体の最小の数（0036〜0042 の最小の m と同じ値）
LEVELS = (1, 2, 4, 8)          # 段の組（README §4.6）
K0 = 2                         # 主の段（README §4.6。range_guide が同じ値を導くことを確かめる）
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")
PAIRS = (("C_to_source1", "source1_to_C"), ("C_to_source2", "source2_to_C"), ("source1_to_source2", "source2_to_source1"))
SOURCE_SWAP = {"C_to_source1": "C_to_source2", "C_to_source2": "C_to_source1",
               "source1_to_C": "source2_to_C", "source2_to_C": "source1_to_C",
               "source1_to_source2": "source2_to_source1", "source2_to_source1": "source1_to_source2"}
# 対称な介入の向き u：0040 の X1 − X2 を w_max で割った向き（README §2.2）。δ(u) ＝ 2、F1 を保つ
U_DIRECTION = {"C_to_source1": 1, "source1_to_C": -1, "C_to_source2": -1, "source2_to_C": 1,
               "source1_to_source2": 0, "source2_to_source1": 0}
F1_TOLERANCE = 1e-12           # 0041 の O6・0042 の O11 と同じ幅


def clone_names(c: str) -> tuple:
    """背景 c の複製の系（README §2.3）。base ＝ G^c[W^c]、P_k／M_k ＝ G^c[W^c ± k e]、UP_k／UM_k ＝ G^c[W^c ± m_k u]。"""
    names = [f"G_{c}_base"]
    for k in LEVELS:
        names += [f"G_{c}_P{k}", f"G_{c}_M{k}"]
    for k in LEVELS:
        names += [f"G_{c}_UP{k}", f"G_{c}_UM{k}"]
    names += [f"G_{c}_X1", f"G_{c}_X2", f"G_{c}_tr"]
    return tuple(names)


FULL_BODIES = ("B_A1", "B_A2", "B_A1_rerun")
U_SYSTEMS = clone_names("A1") + clone_names("A2")


def c0_values() -> dict:
    raw = yaml.safe_load(C0_MANIFEST.read_text(encoding="utf-8"))
    d = raw["defaults"]["dynamics"]
    weights = {p["weight"] for p in raw["projections"] if p.get("plastic")}
    receptor = {p["weight"] for p in raw["projections"] if p["from"].startswith("receptor.")}
    assert len(weights) == 1 and len(receptor) == 1
    w_max_key = raw["plasticity"]["w_max"]
    w_max = float(d[w_max_key]) if isinstance(w_max_key, str) else float(w_max_key)
    return {"decay": float(d["decay"]), "threshold": float(d["threshold"]), "intrinsic_drive": float(d["intrinsic_drive"]),
            "jitter": float(d["jitter"]), "refractory_pulses": int(d["refractory_pulses"]),
            "initial_activity_max_ratio": float(d["initial_activity_max_ratio"]),
            "adaptation_increment": float(d["adaptation_increment"]), "adaptation_tau": float(d["adaptation_tau"]),
            "w_min": float(raw["plasticity"]["w_min"]), "w_max": w_max, "w0": weights.pop(),
            "receptor_weight": receptor.pop()}


def gate_set() -> dict:
    raw = GATE_DECLARATION.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == GATE_SHA256, "関門の宣言が v0.2 と違う"
    decl = json.loads(raw)
    cp = decl["schedule"]["cue_pulses"]
    return {"first": cp["first"], "spacing": cp["spacing"], "count": cp["count"],
            "o": decl["schedule"]["window_offset_o"], "W": decl["schedule"]["window_length_W"],
            "L": decl["world"]["delay_L"], "pulses": decl["bodies"]["pulses"]}


def intervals(g: dict) -> dict:
    """窓 k の [a_k, b_k]、経験の区間 E・境界 P_E・試しの区間 U（README §2.1。0042 と同じ）。"""
    cue = [g["first"] + g["spacing"] * k for k in range(g["count"])]
    windows = [(k + 1, c + g["o"], c + g["o"] + g["W"] - 1) for k, c in enumerate(cue)]
    assert windows[-1][2] + g["L"] == g["pulses"], "関門の本体の長さが b_K ＋ L と違う"
    p_e = cue[E_WINDOWS] - 1
    last_e_outcome = windows[E_WINDOWS - 1][2] + g["L"]
    assert last_e_outcome < p_e, "E の最後の結果が境界より後になる"
    first_u = windows[E_WINDOWS]
    u_pulses = g["pulses"] - p_e
    return {"E_windows": [1, E_WINDOWS], "E_pulses": [1, p_e], "P_E": p_e,
            "last_E_window": list(windows[E_WINDOWS - 1]), "last_E_outcome_pulse": last_e_outcome,
            "U_windows": [E_WINDOWS + 1, g["count"]], "U_pulses": [p_e + 1, g["pulses"]], "U_length": u_pulses,
            "first_U_cue": cue[E_WINDOWS], "first_U_window": list(first_u),
            "earliest_U_intent_pulse": first_u[1] + 1, "earliest_U_consequence_pulse": first_u[1] + g["L"],
            "body_pulses": g["pulses"],
            "clones_per_individual_max": len(U_SYSTEMS),
            "pulses_per_individual_max": len(FULL_BODIES) * g["pulses"] + len(U_SYSTEMS) * u_pulses,
            "pulses_0042_for_comparison": len(FULL_BODIES) * g["pulses"] + 14 * u_pulses}


# ---------------------------------------------------------------- 重みの算術（README §2.2）

def exact(w: dict) -> dict:
    return {x: Fraction(w[x]) for x in ROLES6}


def delta_of(d: dict) -> Fraction:
    """δ(Δ) ＝ Δ(C → 源 1) − Δ(C → 源 2)（0041 §3.2 の δ を、6 本の変化 Δ に当てたもの）。"""
    return d["C_to_source1"] - d["C_to_source2"]


def natural_difference(w_a1: dict, w_a2: dict) -> dict:
    """e ＝ W^{A1} − W^{A2}（有理数で正確に）。"""
    a, b = exact(w_a1), exact(w_a2)
    return {x: a[x] - b[x] for x in ROLES6}


def m_of(e: dict, k: int) -> Fraction:
    """m_k ＝ k |δ(e)|／2。|δ(2 m_k u)| ＝ 4 m_k ＝ |δ(2k e)|（README §2.2）。"""
    return Fraction(k) * abs(delta_of(e)) / 2


def in_range(v: dict, w_max: float) -> bool:
    top = Fraction(w_max)
    return all(0 <= v[x] <= top for x in ROLES6)


def rounded(v: dict) -> dict:
    """有理数の値を、重みごとに一度だけ最近接の浮動小数に丸める（float(Fraction) は正しく丸める）。"""
    return {x: float(v[x]) for x in ROLES6}


def endpoints(w_a1: dict, w_a2: dict, c: str, k: int, w_max: float, kind: str) -> dict:
    """背景 c・段 k の二つの端。kind ＝ "natural"（W^c ± k e）か "symmetric"（W^c ± m_k u）。

    返す値：{"plus": {...}, "minus": {...}}。各端は {"exact": 有理数の 6 本, "in_range": 真偽, "weights": 浮動小数の 6 本か None}。
    範囲の外の端は丸めず、系を作らない（README §2.2・§2.3）。
    """
    e = natural_difference(w_a1, w_a2)
    base = exact(w_a1 if c == "A1" else w_a2)
    if kind == "natural":
        step = {x: Fraction(k) * e[x] for x in ROLES6}
    elif kind == "symmetric":
        m = m_of(e, k)
        step = {x: m * U_DIRECTION[x] for x in ROLES6}
    else:
        raise ValueError(kind)
    out = {}
    for name, sign in (("plus", 1), ("minus", -1)):
        v = {x: base[x] + sign * step[x] for x in ROLES6}
        ok = in_range(v, w_max)
        out[name] = {"exact": v, "in_range": ok, "weights": rounded(v) if ok else None}
    return out


def pair_sum_deviation(w: dict, w_max: float) -> float:
    return max(abs(float(Fraction(w[a]) + Fraction(w[b]) - Fraction(w_max))) for a, b in PAIRS)


def _f1_pair(a: float, w_max: float) -> tuple:
    return a, w_max - a                     # 浮動小数の引き算一回。組の和は w_max から高々丸めの分だけずれる


def _hand_weights(c1s1, c1s2, s12, c2s1, c2s2, s12b, w_max):
    """手で置いた 6 本（F1 を浮動小数の丸めの幅で満たす形）。"""
    a = dict(zip(("C_to_source1", "source1_to_C"), _f1_pair(c1s1, w_max)))
    a.update(zip(("C_to_source2", "source2_to_C"), _f1_pair(c1s2, w_max)))
    a.update(zip(("source1_to_source2", "source2_to_source1"), _f1_pair(s12, w_max)))
    b = dict(zip(("C_to_source1", "source1_to_C"), _f1_pair(c2s1, w_max)))
    b.update(zip(("C_to_source2", "source2_to_C"), _f1_pair(c2s2, w_max)))
    b.update(zip(("source1_to_source2", "source2_to_source1"), _f1_pair(s12b, w_max)))
    return a, b


def weight_arithmetic_check(p: dict) -> dict:
    """README §2.2・SE-C6〜SE-C11 を、手で置いた 6 本の重みの組で確かめる（seed も乱数も記録も使わない）。

    - k ＝ 1 の自然な側の端：V^{A1}_{−1} ＝ W^{A2}、V^{A2}_{+1} ＝ W^{A1}（ビット単位。SE-C8）
    - 端の 6 本の組の和と w_max のずれが F1 の許容の内（SE-C9）。対称な介入は、丸めの前の有理数で組の和を正確に保つ
    - |δ(Y_+ − Y_−)| ＝ |δ(V_+ − V_−)|（有理数で正確に）、δ(u) ＝ 2
    - 札の入れ替え（e′ ＝ −P e、P u ＝ −u）で、端の 6 本が、元の背景の逆の端の札の付け替えにビット単位で一致する（SE-C14）
    - e ＝ 0 なら、どの段の端も W^c（SE-C6）。δ(e) ＝ 0 で e ≠ 0 なら、対称な介入の端だけが W^c（SE-C7）
    - e ＝ −b u なら、V^c_{±k} ＝ Y^c_{∓k}（有理数で正確に。SE-C11）
    - 二つの背景の両方の端が範囲の中 ⟺ W^{A1} ＋ k e と W^{A2} − k e が範囲の中。範囲の中は段について入れ子（SE-C10）
    """
    w_max = p["w_max"]
    cases = {
        "generic": _hand_weights(0.0047, 0.0051, 0.0044, 0.00512, 0.00497, 0.0046, w_max),
        "large_e": _hand_weights(0.0062, 0.0049, 0.0050, 0.0049, 0.0052, 0.0050, w_max),
        "fine": _hand_weights(0.004812345678, 0.005003, 0.005, 0.005231, 0.004801999, 0.005000123, w_max),
    }
    a0, _ = cases["generic"]
    cases["e_zero"] = (dict(a0), dict(a0))
    # δ(e) ＝ 0 で e ≠ 0：C → 源 1 と C → 源 2 に同じ差、源どうしにも差
    za, zb = _hand_weights(0.0050, 0.0050, 0.0050, 0.0047, 0.0047, 0.0049, w_max)
    cases["delta_zero"] = (za, zb)
    # e ＝ −b u：W^{A1} ＝ W^{A2} − b u（b ＝ 0.0002）。δ(e) ＝ −2b
    ua = {"C_to_source1": 0.0049, "source1_to_C": 0.0051, "C_to_source2": 0.0051, "source2_to_C": 0.0049,
          "source1_to_source2": 0.005, "source2_to_source1": 0.005}
    ub = {"C_to_source1": 0.0051, "source1_to_C": 0.0049, "C_to_source2": 0.0049, "source2_to_C": 0.0051,
          "source1_to_source2": 0.005, "source2_to_source1": 0.005}
    cases["anti_u"] = (ua, ub)
    report = {}
    for name, (w1, w2) in cases.items():
        e = natural_difference(w1, w2)
        r = {"delta_e": str(delta_of(e)), "levels": {}}
        nat_ok = {}
        for k in LEVELS:
            lv = {}
            for c in ("A1", "A2"):
                nat = endpoints(w1, w2, c, k, w_max, "natural")
                sym = endpoints(w1, w2, c, k, w_max, "symmetric")
                nat_ok[(c, k)] = nat["plus"]["in_range"] and nat["minus"]["in_range"]
                # δ をそろえた量の一致（有理数）
                dv = delta_of({x: nat["plus"]["exact"][x] - nat["minus"]["exact"][x] for x in ROLES6})
                dy = delta_of({x: sym["plus"]["exact"][x] - sym["minus"]["exact"][x] for x in ROLES6})
                assert abs(dv) == abs(dy) == 2 * k * abs(delta_of(e))
                # 対称な介入は丸めの前に組の和を正確に保つ
                base = exact(w1 if c == "A1" else w2)
                for end in ("plus", "minus"):
                    for a, b in PAIRS:
                        assert sym[end]["exact"][a] + sym[end]["exact"][b] == base[a] + base[b]
                # F1：範囲の中の端の組の和
                for kind in (nat, sym):
                    for end in ("plus", "minus"):
                        if kind[end]["in_range"]:
                            assert pair_sum_deviation(kind[end]["weights"], w_max) <= F1_TOLERANCE
                lv[c] = {"natural_in_range": [nat["plus"]["in_range"], nat["minus"]["in_range"]],
                         "symmetric_in_range": [sym["plus"]["in_range"], sym["minus"]["in_range"]]}
                # SE-C6・SE-C7
                if all(v == 0 for v in e.values()):
                    assert nat["plus"]["weights"] == nat["minus"]["weights"] == {x: (w1 if c == "A1" else w2)[x] for x in ROLES6}
                if delta_of(e) == 0:
                    assert sym["plus"]["weights"] == sym["minus"]["weights"] == {x: (w1 if c == "A1" else w2)[x] for x in ROLES6}
                    if any(v != 0 for v in e.values()) and nat["plus"]["in_range"] and nat["minus"]["in_range"]:
                        assert nat["plus"]["weights"] != nat["minus"]["weights"]
                # SE-C11：e ＝ −b u
                if name == "anti_u":
                    assert nat["plus"]["exact"] == sym["minus"]["exact"] and nat["minus"]["exact"] == sym["plus"]["exact"]
                # SE-C14：札の入れ替え。新しい札の W'^{A1}(x) ＝ W^{A2}(P x)、W'^{A2}(x) ＝ W^{A1}(P x)
                n1 = {x: w2[SOURCE_SWAP[x]] for x in ROLES6}
                n2 = {x: w1[SOURCE_SWAP[x]] for x in ROLES6}
                d = "A2" if c == "A1" else "A1"
                for kind in ("natural", "symmetric"):
                    new = endpoints(n1, n2, c, k, w_max, kind)
                    old = endpoints(w1, w2, d, k, w_max, kind)
                    for end, opp in (("plus", "minus"), ("minus", "plus")):
                        assert new[end]["in_range"] == old[opp]["in_range"]
                        if new[end]["in_range"]:
                            assert new[end]["weights"] == {x: old[opp]["weights"][SOURCE_SWAP[x]] for x in ROLES6}
            # SE-C10：二つの背景の両方 ⟺ 外側の二点
            outer_plus = {x: exact(w1)[x] + k * e[x] for x in ROLES6}
            outer_minus = {x: exact(w2)[x] - k * e[x] for x in ROLES6}
            both = nat_ok[("A1", k)] and nat_ok[("A2", k)]
            assert both == (in_range(outer_plus, w_max) and in_range(outer_minus, w_max))
            r["levels"][str(k)] = lv
        # SE-C8：k ＝ 1 の自然な側の端
        m1 = endpoints(w1, w2, "A1", 1, w_max, "natural")["minus"]
        p2 = endpoints(w1, w2, "A2", 1, w_max, "natural")["plus"]
        assert m1["in_range"] and p2["in_range"]
        assert m1["weights"] == {x: w2[x] for x in ROLES6} and p2["weights"] == {x: w1[x] for x in ROLES6}
        # SE-C10：入れ子（背景ごと）
        for c in ("A1", "A2"):
            seq = [nat_ok[(c, k)] for k in LEVELS]
            assert all(seq[i] or not seq[i + 1] for i in range(len(seq) - 1))
        report[name] = r
    assert report["large_e"]["levels"]["4"]["A1"]["natural_in_range"] == [False, True]
    assert report["large_e"]["levels"]["2"]["A1"]["natural_in_range"] == [True, True]
    assert report["e_zero"]["delta_e"] == "0" and report["delta_zero"]["delta_e"] == "0"
    u = U_DIRECTION
    assert delta_of({x: Fraction(u[x]) for x in ROLES6}) == 2
    assert all(u[a] + u[b] == 0 for a, b in PAIRS)
    return {"cases": report, "k1_natural_side_equals_other_body_bitwise": True,
            "symmetric_pair_sums_exact_before_rounding": True, "delta_magnitudes_match": True,
            "label_swap_maps_to_opposite_endpoint_of_other_background_bitwise": True,
            "e_zero_gives_identical_endpoints": True, "delta_zero_gives_identical_symmetric_endpoints": True,
            "anti_u_gives_coinciding_endpoint_pairs": True, "outer_points_and_nesting": True,
            "scope": "algebra on hand-placed weights only"}


# ---------------------------------------------------------------- 主の段と段の組の範囲の算術（README §4.6）

# 実験 0042 §15.6 R4 に公表した P_E の 6 本の五つの数（最小 / 第 1 四分位 / 中央 / 第 3 四分位 / 最大）。
# 0042 の 200 個体の値で、0043 の個体群の値ではない。範囲の算術にだけ使う
R4_PUBLISHED_0042 = {
    "C_to_source1": ((0.004171, 0.004932, 0.005, 0.005149, 0.005646), (0.004345, 0.005002, 0.005219, 0.005421, 0.005983),
                     (0, 5.128e-05, 0.0002513, 0.0004393, 0.001246)),
    "source1_to_C": ((0.004354, 0.004851, 0.005, 0.005068, 0.005829), (0.004017, 0.004579, 0.004781, 0.004998, 0.005655),
                     (0, 5.128e-05, 0.0002513, 0.0004393, 0.001246)),
    "C_to_source2": ((0.004466, 0.005, 0.005214, 0.005426, 0.005859), (0.004329, 0.004944, 0.005002, 0.005196, 0.005756),
                     (0, 3.239e-05, 0.0001947, 0.0004312, 0.001321)),
    "source2_to_C": ((0.004141, 0.004574, 0.004786, 0.005, 0.005534), (0.004244, 0.004804, 0.004998, 0.005056, 0.005671),
                     (0, 3.239e-05, 0.0001947, 0.0004312, 0.001321)),
    "source1_to_source2": ((0.003249, 0.004773, 0.005, 0.00525, 0.006229), (0.003249, 0.004733, 0.005, 0.005235, 0.006244),
                           (0, 0, 2.015e-05, 6.403e-05, 0.0004577)),
    "source2_to_source1": ((0.003771, 0.00475, 0.005, 0.005227, 0.006751), (0.003756, 0.004765, 0.005, 0.005267, 0.006751),
                           (0, 0, 2.015e-05, 6.403e-05, 0.0004577)),
}


def range_guide(p: dict) -> dict:
    """README §4.6 の算術。0042 の公表値の周辺の値だけを使い、個体ごとの値の組は使わない。

    - 保守的な目安 k_cons(x) ＝ min(最小, w_max − 最大)／|差| の最大（W^{A1}・W^{A2} の両方の最小・最大）。k ≤ min_x k_cons なら、
      0042 のどの値の組み合わせでも、W^c ± k e は範囲の中（十分条件）
    - 両端の幅：k ＝ 4 では 2k × |差| の最大 ＝ 8 × 0.001321 ＞ w_max なので、その個体は中心に依らず範囲に収まらない
    - 粗い目安 k_rough(x) ＝ min(中央, w_max − 中央)／|差| の第 3 四分位（周辺の値の組み合わせ。個体の結合の分布ではない）
    - 主の段：段の組の中で、(i) k ＞ 1、(ii) k ≤ min_x k_cons、を満たす最大の段
    - 段の組の上限：倍の段（1, 2, 4, …）のうち、min_x k_rough を超えない最大の段
    """
    w_max = p["w_max"]
    cons, rough, widths = {}, {}, {}
    for x, (a1, a2, d) in R4_PUBLISHED_0042.items():
        lo, hi = min(a1[0], a2[0]), max(a1[4], a2[4])
        cons[x] = min(lo, w_max - hi) / d[4]
        mlo, mhi = min(a1[2], a2[2]), max(a1[2], a2[2])
        rough[x] = min(mlo, w_max - mhi) / d[3]
        widths[x] = {str(k): 2 * k * d[4] for k in LEVELS}
    k_cons = min(cons.values())
    k_rough = min(rough.values())
    k0 = max(k for k in LEVELS if k > 1 and k <= k_cons)
    doubling = [2 ** i for i in range(0, 8)]
    top = max(k for k in doubling if k <= k_rough)
    margin_k0 = k_cons / k0
    assert k0 == K0 and top == LEVELS[-1] and tuple(k for k in doubling if k <= top) == LEVELS
    assert widths["C_to_source2"]["4"] > w_max and widths["C_to_source2"]["2"] < w_max
    return {"k_conservative_per_connection": cons, "k_conservative": k_cons,
            "k_rough_per_connection": rough, "k_rough": k_rough,
            "two_end_width_by_level": widths, "k0": k0, "k0_margin_against_conservative": margin_k0,
            "largest_doubling_level_not_above_rough": top, "levels": list(LEVELS),
            "scope": "marginal published five-number summaries of 0042 R4 only; not the 0043 population; not a forecast of out-of-range counts"}


# ---------------------------------------------------------------- 量（README §3.2）

def share(a1: int, a2: int):
    """s ＝ #A1／(#A1 ＋ #A2)。決まった窓がなければ定まらない（None）。分数で正確に。"""
    n = a1 + a2
    return None if n == 0 else Fraction(a1, n)


def _diff(x, y):
    return None if x is None or y is None else x - y


def _sum(x, y):
    return None if x is None or y is None else x + y


def quantities(s: dict) -> dict:
    """README §3.2。s は系の名前 → A1 の割合（分数、または定まらない・作らない系の None）。"""
    def s_c(name, c):
        v = s[name]
        return None if v is None else (v if c == "A1" else 1 - v)

    q = {}
    for k in LEVELS:
        for c in ("A1", "A2"):
            q[f"C{k}_{c}"] = _diff(s[f"G_{c}_P{k}"], s[f"G_{c}_M{k}"])
            q[f"up{k}_{c}"] = _diff(s[f"G_{c}_P{k}"], s[f"G_{c}_base"])
            q[f"dn{k}_{c}"] = _diff(s[f"G_{c}_base"], s[f"G_{c}_M{k}"])
            q[f"Du{k}_{c}"] = _diff(s[f"G_{c}_UP{k}"], s[f"G_{c}_UM{k}"])
        q[f"C{k}"] = _sum(q[f"C{k}_A1"], q[f"C{k}_A2"])
        q[f"C{k}_any"] = None if q[f"C{k}"] is None else (q[f"C{k}_A1"] != 0 or q[f"C{k}_A2"] != 0)
        q[f"Du{k}"] = _sum(q[f"Du{k}_A1"], q[f"Du{k}_A2"])
    q["T_A1"] = _diff(s["G_A1_base"], s["G_A1_M1"])       # V^{A1}_{−1} ＝ W^{A2}
    q["T_A2"] = _diff(s["G_A2_P1"], s["G_A2_base"])       # V^{A2}_{+1} ＝ W^{A1}
    q["T"] = _sum(q["T_A1"], q["T_A2"])
    q["S_A1"] = _diff(s["G_A1_X1"], s["G_A1_X2"])
    q["S_A2"] = _diff(s["G_A2_X1"], s["G_A2_X2"])
    q["S"] = _sum(q["S_A1"], q["S_A2"])
    q["D"] = _diff(s["B_A1"], s["B_A2"])
    q["Z_A1"] = _diff(s_c("B_A1", "A1"), s_c("G_A1_base", "A1"))
    q["Z_A2"] = _diff(s_c("B_A2", "A2"), s_c("G_A2_base", "A2"))
    return q


def swap_map() -> dict:
    """札の入れ替えで、新しい札の系 x が、元の札のどの系に当たるか（README §3.3。e′ ＝ −P e、P u ＝ −u）。"""
    m = {"B_A1": "B_A2", "B_A2": "B_A1", "B_A1_rerun": "B_A2"}
    for c, d in (("A1", "A2"), ("A2", "A1")):
        m[f"G_{c}_base"] = f"G_{d}_base"
        m[f"G_{c}_tr"] = f"G_{d}_tr"
        m[f"G_{c}_X1"] = f"G_{d}_X2"
        m[f"G_{c}_X2"] = f"G_{d}_X1"
        for k in LEVELS:
            m[f"G_{c}_P{k}"] = f"G_{d}_M{k}"
            m[f"G_{c}_M{k}"] = f"G_{d}_P{k}"
            m[f"G_{c}_UP{k}"] = f"G_{d}_UM{k}"
            m[f"G_{c}_UM{k}"] = f"G_{d}_UP{k}"
    return m


def invariant_and_exchanged() -> tuple:
    inv = ["T", "S", "D"] + [f"C{k}" for k in LEVELS] + [f"C{k}_any" for k in LEVELS] + [f"Du{k}" for k in LEVELS]
    exc = [("T_A1", "T_A2"), ("S_A1", "S_A2"), ("Z_A1", "Z_A2")]
    for k in LEVELS:
        exc += [(f"C{k}_A1", f"C{k}_A2"), (f"Du{k}_A1", f"Du{k}_A2"), (f"up{k}_A1", f"dn{k}_A2"), (f"dn{k}_A1", f"up{k}_A2")]
    return tuple(inv), tuple(exc)


def swapped(s: dict) -> dict:
    m = swap_map()
    return {x: (None if s[m[x]] is None else 1 - s[m[x]]) for x in s if x != "B_A1_rerun"}


def _hand_shares() -> dict:
    """手で置いた割合（乱数を使わない決まった式）。"""
    names = list(FULL_BODIES) + list(U_SYSTEMS)
    return {x: Fraction((7 * i + 3) % 13 + 1, 15) for i, x in enumerate(names)}


def label_swap_and_identity_check() -> dict:
    """札の入れ替えの性質と、構造上の 0・打ち消し・e ＝ −b u の算術を、手で置いた割合で確かめる（README §3.3・SE-C6・SE-C7・SE-C11）。

    この性質は、C_k の符号が＋・−で対称であることの根拠ではない（札の入れ替えは C_k を −C_k に移さない：README §4.8）。
    """
    inv, exc = invariant_and_exchanged()
    base = _hand_shares()
    e_zero = dict(base)                                    # e ＝ 0：自然な差の端も対称な介入の端も基の系と同じ
    for c in ("A1", "A2"):
        for k in LEVELS:
            for x in (f"G_{c}_P{k}", f"G_{c}_M{k}", f"G_{c}_UP{k}", f"G_{c}_UM{k}"):
                e_zero[x] = base[f"G_{c}_base"]
    delta_zero = dict(base)                                # δ(e) ＝ 0、e ≠ 0：対称な介入の端だけが基の系と同じ
    for c in ("A1", "A2"):
        for k in LEVELS:
            delta_zero[f"G_{c}_UP{k}"] = delta_zero[f"G_{c}_UM{k}"] = base[f"G_{c}_base"]
    anti_u = dict(base)                                    # e ＝ −b u：V_{±k} ＝ Y_{∓k}
    for c in ("A1", "A2"):
        for k in LEVELS:
            anti_u[f"G_{c}_UM{k}"] = base[f"G_{c}_P{k}"]
            anti_u[f"G_{c}_UP{k}"] = base[f"G_{c}_M{k}"]
    out_of_range = dict(base, G_A1_P8=None)                # 範囲の外の系は作らない（割合なし）
    cancel = dict(base)
    cancel.update({"G_A1_P2": Fraction(3, 4), "G_A1_M2": Fraction(1, 2), "G_A2_P2": Fraction(1, 4), "G_A2_M2": Fraction(1, 2)})
    out = {}
    for name, case in (("base", base), ("e_zero", e_zero), ("delta_zero", delta_zero), ("anti_u", anti_u),
                       ("out_of_range", out_of_range), ("cancel", cancel)):
        q = quantities(case)
        r = quantities(swapped(case))
        for x in inv:
            assert r[x] == q[x], x
        for a, b in exc:
            assert (r[a], r[b]) == (q[b], q[a]), (a, b)
        for k in LEVELS:
            for c in ("A1", "A2"):
                if q[f"C{k}_{c}"] is not None:
                    assert q[f"C{k}_{c}"] == q[f"up{k}_{c}"] + q[f"dn{k}_{c}"]
        out[name] = {x: (None if v is None else str(v)) for x, v in q.items()}
    assert all(out["e_zero"][f"C{k}"] == "0" and out["e_zero"][f"Du{k}"] == "0" for k in LEVELS)
    assert all(out["e_zero"][f"C{k}_any"] == "False" for k in LEVELS)
    assert all(out["delta_zero"][f"Du{k}"] == "0" for k in LEVELS)
    assert all(Fraction(out["anti_u"][f"C{k}"]) == -Fraction(out["anti_u"][f"Du{k}"]) for k in LEVELS)
    assert out["out_of_range"]["C8"] is None and out["out_of_range"]["C8_A2"] is not None and out["out_of_range"]["C4"] is not None
    assert out["cancel"]["C2_A1"] == "1/4" and out["cancel"]["C2_A2"] == "-1/4" and out["cancel"]["C2"] == "0"
    assert out["cancel"]["C2_any"] == "True"
    return {"cases": out, "invariant": list(inv), "exchanged": [list(x) for x in exc],
            "C_equals_up_plus_down": True, "anti_u_gives_C_equal_minus_Du": True,
            "not_a_basis_for_sign_symmetry": True}


def extremes(p: dict) -> dict:
    """人工の端 X1・X2 の 6 本（0040 §2.3・0042 と同じ値）。u ＝ (X1 − X2)／w_max も確かめる。"""
    w_max, w0 = p["w_max"], p["w0"]
    x1 = {"C_to_source1": w_max, "source1_to_C": 0.0, "C_to_source2": 0.0, "source2_to_C": w_max,
          "source1_to_source2": w0, "source2_to_source1": w0}
    x2 = {"C_to_source1": 0.0, "source1_to_C": w_max, "C_to_source2": w_max, "source2_to_C": 0.0,
          "source1_to_source2": w0, "source2_to_source1": w0}
    for x in (x1, x2):
        assert x["C_to_source1"] + x["source1_to_C"] == w_max and x["C_to_source2"] + x["source2_to_C"] == w_max
        assert x["source1_to_source2"] + x["source2_to_source1"] == w_max
    assert all((Fraction(x1[r]) - Fraction(x2[r])) / Fraction(w_max) == U_DIRECTION[r] for r in ROLES6)
    delta_units = (Fraction(x1["C_to_source1"]) - Fraction(x2["C_to_source1"])) \
        - (Fraction(x1["C_to_source2"]) - Fraction(x2["C_to_source2"]))
    return {"X1": x1, "X2": x2, "contrast_in_delta_units": float(delta_units), "u": U_DIRECTION,
            "midpoint_all_w0": all((x1[r] + x2[r]) / 2 == w0 for r in ROLES6)}


def silence_bound(p: dict, g: dict) -> dict:
    """命題 S-1 の E_S（実験 0039 §7.2 と同じ式。移植・FREEZE に依らない。範囲の中の重みだけを使う）。"""
    lam, w_max = p["decay"], p["w_max"]
    j = p["jitter"]
    theta_min, theta_max = p["threshold"] * (1 - j), p["threshold"] * (1 + j)
    c_min, c_max = p["intrinsic_drive"] * (1 - j), p["intrinsic_drive"] * (1 + j)
    per_pulse = c_max + 2 * w_max
    d_min = next(n for n in range(1, 1000) if per_pulse * (1 - lam ** n) / (1 - lam) >= theta_min)
    ceiling = per_pulse / (1 - lam)
    gap_cue_to_cons = g["o"] + g["L"]
    gap_cons_to_cue = g["spacing"] - (g["o"] + g["W"] - 1 + g["L"])
    pair = gap_cue_to_cons + gap_cons_to_cue
    phi_r = (1 + lam ** gap_cue_to_cons) / (1 - lam ** pair)
    phi_n = 1 / (1 - lam ** d_min)
    e_s = w_max * (phi_r + 2 * phi_n)
    tau, alpha = p["adaptation_tau"], p["adaptation_increment"]
    q = math.exp(-1 / tau)
    h_bound = (ceiling - theta_min) + alpha + alpha * (1 / (1 - q ** g["spacing"]) + 1 + q ** pair / (1 - q ** g["spacing"]))
    r_drive_min = p["receptor_weight"] + c_min
    assert h_bound < r_drive_min - theta_max, "R の Pulse で手がかりの Unit が必ず発火する、が示せない"
    return {"d_min_between_firings_without_receptor_input": d_min, "phi_R": phi_r, "phi_N": phi_n, "E_S": e_s}


def silence_probability(p: dict, e_s: float) -> dict:
    """P(g ＜ −E_S)、g ＝ c/(1 − λ) − θ。θ と c は出生時の範囲で独立に一様。"""
    j, lam = p["jitter"], p["decay"]
    t0, t1 = p["threshold"] * (1 - j), p["threshold"] * (1 + j)
    a0, a1 = p["intrinsic_drive"] * (1 - j) / (1 - lam), p["intrinsic_drive"] * (1 + j) / (1 - lam)
    n = 200000
    total = 0.0
    for i in range(n):
        theta = t0 + (t1 - t0) * (i + 0.5) / n
        total += min(1.0, max(0.0, (theta - e_s - a0) / (a1 - a0)))
    per_source = total / n
    return {"per_source_structural": per_source,
            "individual_at_least_one_structural_source": 1 - (1 - per_source) ** 2}


def upper_tail(m: int, k: int, p: Fraction = Fraction(1, 2)) -> Fraction:
    return sum(comb(m, i) * p ** i * (1 - p) ** (m - i) for i in range(k, m + 1))


def k2(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと）。"""
    return next(k for k in range(m + 1) if upper_tail(m, k) <= ALPHA_PER_SIDE)


def power_sign_among_nonzero() -> dict:
    """J_C（README §4.4）の検出力の見込み：C_{k₀} ≠ 0 の個体の数 m≠ と、その中の＋の割合 π_dir ごとに、＋の向きで成立する確率
    （−の向きでも同じ）。m≠・π_dir の値は見込みの幅で、データから選んでいない。0042 の J_T の表と同じ値。"""
    out = {}
    for m in (10, 15, 20, 30, 50, 80, 120):
        k = k2(m)
        out[str(m)] = {"k2": k, **{str(pd): round(float(upper_tail(m, k, pd)), 3)
                                    for pd in (Fraction(65, 100), Fraction(75, 100), Fraction(85, 100))}}
    return out


def main() -> None:
    p = c0_values()
    g = gate_set()
    sb = silence_bound(p, g)
    out = {"c0": p, "gate_set": g, "intervals": intervals(g),
           "systems": {"full": list(FULL_BODIES), "U_only": list(U_SYSTEMS)},
           "levels": list(LEVELS), "k0": K0,
           "extremes": extremes(p), "weight_arithmetic": weight_arithmetic_check(p), "range_guide": range_guide(p),
           "label_swap_and_identity": label_swap_and_identity_check(),
           "silence_bound": sb, "silence_probability": silence_probability(p, sb["E_S"]),
           "min_m": MIN_M, "k2_of_m": {m: k2(m) for m in range(MIN_M, INDIVIDUALS + 1)},
           "power_J_C": power_sign_among_nonzero()}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
