"""実験 0039（AS2b の S3 の事前登録）の解析の部分：沈黙の十分条件（命題 S-1）、区間の算術、判定の閾値と検出力の見込み。

README §5・§7。seed・乱数・既存の raw（関門 0038 の記録を含む）は使わない。値は次だけから計算する。
- C0 の設計図（experiments/0012_passive_world/neuroarchitecture.yaml）の力学・可塑性の値と、出生時のばらつきの幅
- 関門の宣言 v0.2（experiments/0038_as2b_forward_gate/gate_declaration.json）の予定・o・W・L・長さ
- この README で決める値（経験の区間の窓の数 25、個体数 200、誤りの水準）

二項の確率は分数で厳密に計算する。
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

E_WINDOWS = 25                 # 経験の区間 E の窓の数（README §1.2）
INDIVIDUALS = 200              # 本番の個体数（README §5.3）
ALPHA_PER_SIDE = Fraction(1, 40)   # 両側 0.05 を、向きごとに 0.025 に分ける（README §4.3）
MIN_M = 10                     # 判定に必要な最小の m（0036・0037 と同じ）
MAX_M = INDIVIDUALS


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
            "w_max": w_max, "w0": weights.pop(), "receptor_weight": receptor.pop()}


def gate_set() -> dict:
    raw = GATE_DECLARATION.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == GATE_SHA256, "関門の宣言が v0.2 と違う"
    decl = json.loads(raw)
    cp = decl["schedule"]["cue_pulses"]
    return {"first": cp["first"], "spacing": cp["spacing"], "count": cp["count"],
            "o": decl["schedule"]["window_offset_o"], "W": decl["schedule"]["window_length_W"],
            "L": decl["world"]["delay_L"], "pulses": decl["bodies"]["pulses"]}


def intervals(g: dict) -> dict:
    """窓 k の [a_k, b_k]、E と U の境界。境界 P_E は、E の最後の窓の次の手がかりの直前（c_(E+1) − 1）。"""
    cue = [g["first"] + g["spacing"] * k for k in range(g["count"])]
    windows = [(k + 1, c + g["o"], c + g["o"] + g["W"] - 1) for k, c in enumerate(cue)]
    p_e = cue[E_WINDOWS] - 1
    last_e_outcome = windows[E_WINDOWS - 1][2] + g["L"]          # E の最後の窓の決定から出た意図の結果の刺激（b ＋ L）
    assert last_e_outcome < p_e, "E の最後の結果が境界より後になる"
    assert windows[-1][2] + g["L"] == g["pulses"], "本体の長さが b_K ＋ L と違う"
    return {"cue_first_last": [cue[0], cue[-1]], "E_windows": [1, E_WINDOWS], "U_windows": [E_WINDOWS + 1, g["count"]],
            "P_E": p_e, "E_pulses": [1, p_e], "U_pulses": [p_e + 1, g["pulses"]], "U_length": g["pulses"] - p_e,
            "last_E_outcome_pulse": last_e_outcome, "first_U_cue": cue[E_WINDOWS],
            "first_U_window": list(windows[E_WINDOWS]), "last_window": list(windows[-1])}


def silence_bound(p: dict, g: dict) -> dict:
    """命題 S-1 の E_S と、その導出の途中の値（README §7.2）。"""
    lam, w_max = p["decay"], p["w_max"]
    j = p["jitter"]
    theta_min, theta_max = p["threshold"] * (1 - j), p["threshold"] * (1 + j)
    c_min, c_max = p["intrinsic_drive"] * (1 - j), p["intrinsic_drive"] * (1 + j)
    # 補題 L2：受容器の入力のない Pulse だけで、0 から θ_min に届くまでの最小の Pulse 数（入力は毎 Pulse 2 w_max を上限とする）
    per_pulse = c_max + 2 * w_max
    d_min = next(n for n in range(1, 1000) if per_pulse * (1 - lam ** n) / (1 - lam) >= theta_min)
    ceiling = per_pulse / (1 - lam)                      # 受容器の入力がない Pulse だけで届きうる活動の上限
    # 受容器の入力のある Pulse（R）の間隔：手がかり → 結果 ≥ o ＋ L（＝ 4）、結果 → 次の手がかり ≥ 間隔 − (o ＋ W − 1 ＋ L)
    gap_cue_to_cons = g["o"] + g["L"]
    gap_cons_to_cue = g["spacing"] - (g["o"] + g["W"] - 1 + g["L"])
    pair = gap_cue_to_cons + gap_cons_to_cue
    phi_r = (1 + lam ** gap_cue_to_cons) / (1 - lam ** pair)
    phi_n = 1 / (1 - lam ** d_min)
    e_s = w_max * (phi_r + 2 * phi_n)
    # 補題 L1 の順応の上限：R でない発火の直前は h ＜ ceiling − θ_min、直後は ＋α。R の発火の寄与の上限を足す
    tau = p["adaptation_tau"]
    alpha = p["adaptation_increment"]
    q = math.exp(-1 / tau)
    h_cue = 1 / (1 - q ** g["spacing"])
    h_cons = 1 + q ** pair / (1 - q ** g["spacing"])
    h_bound = (ceiling - theta_min) + alpha + alpha * (h_cue + h_cons)
    r_drive_min = p["receptor_weight"] + c_min                     # R の Pulse の活動の下限（activity ≥ 0）
    assert h_bound < r_drive_min - theta_max, "R の Pulse で手がかりの Unit が必ず発火する、が示せない"
    return {"d_min_between_firings_without_receptor_input": d_min, "activity_ceiling_without_receptor_input": ceiling,
            "gap_cue_to_consequence_min": gap_cue_to_cons, "gap_consequence_to_next_cue_min": gap_cons_to_cue,
            "phi_R": phi_r, "phi_N": phi_n, "phi_other_source": phi_n, "E_S": e_s,
            "cue_unit_adaptation_upper_bound": h_bound, "cue_unit_fires_at_R_if_adaptation_below": r_drive_min - theta_max}


def silence_probability(p: dict, e_s: float) -> dict:
    """P(g ＜ −E_S)、g ＝ c/(1 − λ) − θ。θ と c は出生時の範囲で独立に一様（bootstrap の vary）。分数ではなく閉じた形の実数。"""
    j, lam = p["jitter"], p["decay"]
    t0, t1 = p["threshold"] * (1 - j), p["threshold"] * (1 + j)
    a0, a1 = p["intrinsic_drive"] * (1 - j) / (1 - lam), p["intrinsic_drive"] * (1 + j) / (1 - lam)

    def p_gap_less(d: float) -> float:
        """P(A − θ ＜ −d) を、θ について F_A(θ − d) を平均して求める（A ~ U[a0, a1]）。"""
        n = 200000
        total = 0.0
        for i in range(n):
            theta = t0 + (t1 - t0) * (i + 0.5) / n
            x = theta - d
            total += min(1.0, max(0.0, (x - a0) / (a1 - a0)))
        return total / n

    per_source = p_gap_less(e_s)
    zero = p_gap_less(0.0)
    return {"per_source_structural": per_source, "per_source_g_below_0": zero,
            "per_source_conditional_layer": zero - per_source,
            "individual_at_least_one_structural_source": 1 - (1 - per_source) ** 2}


def upper_tail(m: int, k: int, p: Fraction = Fraction(1, 2)) -> Fraction:
    return sum(comb(m, i) * p ** i * (1 - p) ** (m - i) for i in range(k, m + 1))


def k2(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと）。"""
    return next(k for k in range(m + 1) if upper_tail(m, k) <= ALPHA_PER_SIDE)


def power(m: int, p_dir: Fraction) -> float:
    return float(upper_tail(m, k2(m), p_dir))


def main() -> None:
    p = c0_values()
    g = gate_set()
    iv = intervals(g)
    sb = silence_bound(p, g)
    sp = silence_probability(p, sb["E_S"])
    table = {m: k2(m) for m in range(MIN_M, MAX_M + 1)}
    pw = {}
    for share in (Fraction(1, 2), Fraction(6, 10), Fraction(7, 10), Fraction(8, 10)):
        m = round(INDIVIDUALS * share)
        pw[str(share)] = {"m": m, "k2": table[m],
                          "power": {str(pd): round(power(m, pd), 3)
                                    for pd in (Fraction(6, 10), Fraction(65, 100), Fraction(7, 10), Fraction(75, 100))}}
    out = {"c0": p, "gate_set": g, "intervals": iv, "silence_bound": sb, "silence_probability": sp,
           "k2_of_m": table, "power": pw}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
