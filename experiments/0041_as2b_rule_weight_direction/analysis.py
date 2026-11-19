"""実験 0041（AS2b の候補 B の事前登録）の解析の部分：区間の算術、量の定義と札の入れ替えの性質、沈黙の十分条件（命題 S-1 の引き継ぎ）、
判定の閾値と検出力の見込み。

README §1.2・§3・§5・§7。seed・乱数・既存の raw（0038・0039・0040 の記録を含む）は使わない。値は次だけから計算する。
- C0 の設計図（experiments/0012_passive_world/neuroarchitecture.yaml）の力学・可塑性の値と、出生時のばらつきの幅
- 関門の宣言 v0.2（experiments/0038_as2b_forward_gate/gate_declaration.json）の予定・o・W・L・長さ
- この README で決める値（経験の区間の窓の数 25、個体数 200、誤りの水準）

二項の確率は分数で厳密に計算する。命題 S-1 の E_S と沈黙の割合は、実験 0039 の analysis.py と同じ式で求め直す
（0039 の確定したファイルは読み込まない・変えない）。
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

E_WINDOWS = 25                 # 経験の区間 E ＝ 窓 1〜25（README §1.2。実験 0039 の事前登録の E と同じ）
INDIVIDUALS = 200              # 本番の個体数（README §5.3）。判定の分母 m は、有効な実行では常にこの数（README §4.1）
ALPHA_PER_SIDE = Fraction(1, 40)   # 両側 0.05 を、向きごとに 0.025 に分ける（README §4.3）
BODIES_PER_INDIVIDUAL = 3      # B^{A1}・B^{A2}・B′^{A1}（README §2.2）
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")


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
    """窓 k の [a_k, b_k] と、経験の区間 E・境界 P_E。この実験の本体は P_E まで走らせて止める（README §2.1）。

    P_E は、E の最後の窓の次の手がかりの直前（c_(E+1) − 1）。E の最後の窓の決定から出た意図の結果の刺激（b_E ＋ L）は、
    P_E より前に成立する。したがって P_E では、どの本体にも未決の窓・出す予定の意図・結果の予約がない（SE-B7）。
    """
    cue = [g["first"] + g["spacing"] * k for k in range(g["count"])]
    windows = [(k + 1, c + g["o"], c + g["o"] + g["W"] - 1) for k, c in enumerate(cue)]
    assert windows[-1][2] + g["L"] == g["pulses"], "関門の本体の長さが b_K ＋ L と違う"
    p_e = cue[E_WINDOWS] - 1
    last_e_outcome = windows[E_WINDOWS - 1][2] + g["L"]
    assert last_e_outcome < p_e, "E の最後の結果が境界より後になる"
    boundaries = [cue[k] - 1 for k in range(1, E_WINDOWS + 1)]     # 窓 k の後、次の手がかりの直前（k ＝ 1〜25。最後が P_E）
    assert boundaries[-1] == p_e
    return {"cue_first_last_in_E": [cue[0], cue[E_WINDOWS - 1]], "E_windows": [1, E_WINDOWS], "E_pulses": [1, p_e],
            "P_E": p_e, "first_window": list(windows[0]), "last_E_window": list(windows[E_WINDOWS - 1]),
            "last_E_outcome_pulse": last_e_outcome, "next_cue_after_P_E": cue[E_WINDOWS],
            "window_boundaries": boundaries, "gate_body_pulses_not_run_here": g["pulses"],
            "pulses_per_individual": BODIES_PER_INDIVIDUAL * p_e}


def contrasts(w1: dict, w2: dict) -> dict:
    """README §3.2。w1・w2 は、規則 c ＝ A1・A2 の本体の P_E の 6 本の重み（役の名前の鍵）。分数で正確に計算する。"""
    f = {k: Fraction(w1[k]) for k in ROLES6}
    h = {k: Fraction(w2[k]) for k in ROLES6}
    q1 = f["C_to_source1"] - h["C_to_source1"]            # 源 1 について、規則が源 1 を指す本体 − 指さない本体
    q2 = h["C_to_source2"] - f["C_to_source2"]            # 源 2 について、規則が源 2 を指す本体 − 指さない本体
    back = (f["source1_to_C"] - h["source1_to_C"]) - (f["source2_to_C"] - h["source2_to_C"])
    eps = (f["source1_to_source2"] - h["source1_to_source2"]) - (f["source2_to_source1"] - h["source2_to_source1"])
    return {"delta": q1 + q2, "q1": q1, "q2": q2, "delta_back": back, "epsilon": eps}


def swap_labels(w: dict) -> dict:
    """源 1 と源 2（行動 ID の A1 と A2）の札を入れ替えた、同じ本体の重み。"""
    m = {"C_to_source1": "C_to_source2", "source1_to_C": "source2_to_C", "C_to_source2": "C_to_source1",
         "source2_to_C": "source1_to_C", "source1_to_source2": "source2_to_source1", "source2_to_source1": "source1_to_source2"}
    return {m[k]: v for k, v in w.items()}


def label_swap_check(p: dict) -> dict:
    """札の入れ替えの性質（README §3.2）を、手で置いた値で確かめる（seed も乱数も使わない）。

    札を入れ替えると、規則 c ＝ A1 の本体は、入れ替えた札では規則 c ＝ A2 の本体になる。δ・δ^←・ε は同じ値のまま、
    q_1 と q_2 は入れ替わる。
    """
    w_max, w0 = p["w_max"], p["w0"]
    cases = [
        ({"C_to_source1": 0.0053, "source1_to_C": w_max - 0.0053, "C_to_source2": 0.0049, "source2_to_C": w_max - 0.0049,
          "source1_to_source2": 0.00502, "source2_to_source1": w_max - 0.00502},
         {"C_to_source1": 0.0047, "source1_to_C": w_max - 0.0047, "C_to_source2": 0.0051, "source2_to_C": w_max - 0.0051,
          "source1_to_source2": 0.00497, "source2_to_source1": w_max - 0.00497}),
        (dict.fromkeys(ROLES6, w0), dict.fromkeys(ROLES6, w0)),                     # 構造的な 0（SE-B1）
        ({"C_to_source1": 0.0061, "source1_to_C": w_max - 0.0061, "C_to_source2": w0, "source2_to_C": w0,
          "source1_to_source2": w0, "source2_to_source1": w0},
         {"C_to_source1": 0.0058, "source1_to_C": w_max - 0.0058, "C_to_source2": w0, "source2_to_C": w0,
          "source1_to_source2": w0, "source2_to_source1": w0}),                     # 源 2 が構造的に沈黙（SE-B6）
    ]
    out = []
    for a1, a2 in cases:
        before = contrasts(a1, a2)
        after = contrasts(swap_labels(a2), swap_labels(a1))
        assert after["delta"] == before["delta"] and after["delta_back"] == before["delta_back"]
        assert after["epsilon"] == before["epsilon"]
        assert (after["q1"], after["q2"]) == (before["q2"], before["q1"])
        out.append({k: str(v) for k, v in before.items()})
    assert out[1] == {k: "0" for k in out[1]}
    assert out[2]["q2"] == "0" and out[2]["epsilon"] == "0" and out[2]["delta"] == out[2]["q1"]
    return {"cases": out, "delta_delta_back_epsilon_invariant": True, "q1_q2_exchanged": True}


def silence_bound(p: dict, g: dict) -> dict:
    """命題 S-1 の E_S と、その導出の途中の値（実験 0039 §7.2 と同じ式。結果を返す世界でそのまま成り立つ）。"""
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
    return {"d_min_between_firings_without_receptor_input": d_min, "phi_R": phi_r, "phi_N": phi_n, "E_S": e_s,
            "cue_unit_adaptation_upper_bound": h_bound, "cue_unit_fires_at_R_if_adaptation_below": r_drive_min - theta_max}


def silence_probability(p: dict, e_s: float) -> dict:
    """P(g ＜ −E_S)、g ＝ c/(1 − λ) − θ。θ と c は出生時の範囲で独立に一様。"""
    j, lam = p["jitter"], p["decay"]
    t0, t1 = p["threshold"] * (1 - j), p["threshold"] * (1 + j)
    a0, a1 = p["intrinsic_drive"] * (1 - j) / (1 - lam), p["intrinsic_drive"] * (1 + j) / (1 - lam)

    def p_gap_less(d: float) -> float:
        n = 200000
        total = 0.0
        for i in range(n):
            theta = t0 + (t1 - t0) * (i + 0.5) / n
            total += min(1.0, max(0.0, (theta - d - a0) / (a1 - a0)))
        return total / n

    per_source = p_gap_less(e_s)
    return {"per_source_structural": per_source,
            "individual_at_least_one_structural_source": 1 - (1 - per_source) ** 2,
            "individual_both_structural_sources": per_source ** 2}


def upper_tail(m: int, k: int, p: Fraction = Fraction(1, 2)) -> Fraction:
    return sum(comb(m, i) * p ** i * (1 - p) ** (m - i) for i in range(k, m + 1))


def k2(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと）。"""
    return next(k for k in range(m + 1) if upper_tail(m, k) <= ALPHA_PER_SIDE)


def power_table(m: int) -> dict:
    """真の P(δ ＞ 0) ＝ π のとき、＋の向きで成立する確率（−の向きでも同じ）。π は、構造的な 0 の割合 z と、
    E に決まった窓がある個体の中の＋の割合 π_d から π ＝ (1 − z) π_d。z・π_d は見込みの幅で、データから選んでいない。"""
    k = k2(m)
    out = {}
    for z in (Fraction(0), Fraction(5, 100), Fraction(10, 100)):
        out[str(z)] = {str(pd): round(float(upper_tail(m, k, (1 - z) * pd)), 3)
                       for pd in (Fraction(6, 10), Fraction(65, 100), Fraction(7, 10), Fraction(75, 100))}
    return out


def main() -> None:
    p = c0_values()
    g = gate_set()
    sb = silence_bound(p, g)
    m = INDIVIDUALS
    k = k2(m)
    out = {"c0": p, "gate_set": g, "intervals": intervals(g), "label_swap": label_swap_check(p),
           "silence_bound": sb, "silence_probability": silence_probability(p, sb["E_S"]),
           "m": m, "k2": k, "tail_at_k2": float(upper_tail(m, k)), "tail_at_k2_minus_1": float(upper_tail(m, k - 1)),
           "power_by_structural_zero_share_and_pi_d": power_table(m)}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
