"""実験 0040（AS2b の候補 A の事前登録）の解析の部分：介入の値、沈黙の十分条件（命題 S-1 の引き継ぎ）、判定の閾値と検出力の見込み。

README §2.3・§5・§7。seed・乱数・既存の raw（0038・0039 の記録を含む）は使わない。値は次だけから計算する。
- C0 の設計図（experiments/0012_passive_world/neuroarchitecture.yaml）の力学・可塑性の値と、出生時のばらつきの幅
- 関門の宣言 v0.2（experiments/0038_as2b_forward_gate/gate_declaration.json）の予定・o・W・L・長さ
- この README で決める値（試しの区間の窓、個体数 200、誤りの水準、介入の値の作り方）

二項の確率は分数で厳密に計算する。命題 S-1 の E_S と沈黙の割合は、実験 0039 の analysis.py と同じ式で求め直す
（0039 の確定したファイルは読み込まない・変えない）。
"""

import hashlib
import json
from fractions import Fraction
from math import comb
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
C0_MANIFEST = ROOT / "experiments" / "0012_passive_world" / "neuroarchitecture.yaml"
GATE_DECLARATION = ROOT / "experiments" / "0038_as2b_forward_gate" / "gate_declaration.json"
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"

FIRST_U_WINDOW = 26            # 試しの区間 U ＝ 窓 26〜50（README §1.2。実験 0039 の事前登録の U と同じ）
INDIVIDUALS = 200              # 本番の個体数（README §5.3）
ALPHA_PER_SIDE = Fraction(1, 40)   # 両側 0.05 を、向きごとに 0.025 に分ける（README §4.3）
MIN_M = 10                     # 判定に必要な最小の m（0036・0037・0039 と同じ）
MAX_M = INDIVIDUALS


def c0_values() -> dict:
    raw = yaml.safe_load(C0_MANIFEST.read_text(encoding="utf-8"))
    d = raw["defaults"]["dynamics"]
    weights = {p["weight"] for p in raw["projections"] if p.get("plastic")}
    receptor = {p["weight"] for p in raw["projections"] if p["from"].startswith("receptor.")}
    assert len(weights) == 1 and len(receptor) == 1
    w_max_key = raw["plasticity"]["w_max"]
    w_max = float(d[w_max_key]) if isinstance(w_max_key, str) else float(w_max_key)
    w_min = float(raw["plasticity"]["w_min"])
    return {"decay": float(d["decay"]), "threshold": float(d["threshold"]), "intrinsic_drive": float(d["intrinsic_drive"]),
            "jitter": float(d["jitter"]), "refractory_pulses": int(d["refractory_pulses"]),
            "initial_activity_max_ratio": float(d["initial_activity_max_ratio"]),
            "adaptation_increment": float(d["adaptation_increment"]), "adaptation_tau": float(d["adaptation_tau"]),
            "w_min": w_min, "w_max": w_max, "w0": weights.pop(), "receptor_weight": receptor.pop()}


def gate_set() -> dict:
    raw = GATE_DECLARATION.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == GATE_SHA256, "関門の宣言が v0.2 と違う"
    decl = json.loads(raw)
    cp = decl["schedule"]["cue_pulses"]
    return {"first": cp["first"], "spacing": cp["spacing"], "count": cp["count"],
            "o": decl["schedule"]["window_offset_o"], "W": decl["schedule"]["window_length_W"],
            "L": decl["world"]["delay_L"], "pulses": decl["bodies"]["pulses"]}


def intervals(g: dict) -> dict:
    """窓 k の [a_k, b_k] と、E（記述）・U（判定）の窓の範囲。境界の操作はしないので、区間は窓の番号だけで分ける。"""
    cue = [g["first"] + g["spacing"] * k for k in range(g["count"])]
    windows = [(k + 1, c + g["o"], c + g["o"] + g["W"] - 1) for k, c in enumerate(cue)]
    assert windows[-1][2] + g["L"] == g["pulses"], "本体の長さが b_K ＋ L と違う"
    u0 = FIRST_U_WINDOW - 1
    return {"cue_first_last": [cue[0], cue[-1]], "E_windows": [1, u0], "U_windows": [FIRST_U_WINDOW, g["count"]],
            "E_pulses": [1, cue[u0] - 1], "U_pulses": [cue[u0], g["pulses"]],
            "first_window": list(windows[0]), "first_U_window": list(windows[u0]), "last_window": list(windows[-1])}


def intervention_values(p: dict) -> dict:
    """README §2.3：C ↔ 源 1・C ↔ 源 2 の 2 組の値（組の和は w_max：F1）。源 1 ↔ 源 2 の組は w0 のまま。

    端は [w_min, w_max] の両端、中間は w0 と端の中点（3 w_max/4 と w_max/4）。どれも w_max と w_min だけから決め、データから選ばない。
    """
    w_min, w_max, w0 = p["w_min"], p["w_max"], p["w0"]
    assert w_min == 0.0 and w0 == w_max / 2, "C0 の w_min ＝ 0、w0 ＝ w_max/2 を前提にしている"
    hi, lo = w_max * 3 / 4, w_max / 4

    def system(c_s1: float, s1_c: float, c_s2: float, s2_c: float) -> dict:
        # 組の和の保存（F1）。相手の値は差 w_max − x で作らず、定数（w_max・w_min・w0・3w_max/4・w_max/4）のまま置き、
        # 鏡の系どうしで値がビット単位で入れ替わるようにする。和が二進の浮動小数で w_max にちょうど一致することを確かめる
        out = {"C->source1": c_s1, "source1->C": s1_c, "C->source2": c_s2, "source2->C": s2_c,
               "source1->source2": w0, "source2->source1": w0}
        for a, b in (("C->source1", "source1->C"), ("C->source2", "source2->C"), ("source1->source2", "source2->source1")):
            assert out[a] + out[b] == w_max, (a, b, out[a] + out[b])
            assert w_min <= out[a] <= w_max and w_min <= out[b] <= w_max
        return out

    return {"X1": system(w_max, w_min, w_min, w_max), "X2": system(w_min, w_max, w_max, w_min),
            "M1": system(hi, lo, lo, hi), "M2": system(lo, hi, hi, lo), "X0": system(w0, w0, w0, w0)}


def silence_bound(p: dict, g: dict) -> dict:
    """命題 S-1 の E_S（実験 0039 §7.2 と同じ式）。結果の刺激のない世界で成り立つことは README §7.2 の系 S-1′。"""
    lam, w_max = p["decay"], p["w_max"]
    j = p["jitter"]
    theta_min = p["threshold"] * (1 - j)
    c_max = p["intrinsic_drive"] * (1 + j)
    per_pulse = c_max + 2 * w_max
    d_min = next(n for n in range(1, 1000) if per_pulse * (1 - lam ** n) / (1 - lam) >= theta_min)
    gap_cue_to_cons = g["o"] + g["L"]
    gap_cons_to_cue = g["spacing"] - (g["o"] + g["W"] - 1 + g["L"])
    pair = gap_cue_to_cons + gap_cons_to_cue
    phi_r = (1 + lam ** gap_cue_to_cons) / (1 - lam ** pair)
    phi_r_cues_only = 1 / (1 - lam ** g["spacing"])          # 結果の刺激がないとき、R の Pulse は手がかりだけ（間隔 41）
    assert phi_r_cues_only <= phi_r
    phi_n = 1 / (1 - lam ** d_min)
    return {"d_min_between_firings_without_receptor_input": d_min, "phi_R": phi_r,
            "phi_R_cues_only": phi_r_cues_only, "phi_N": phi_n, "E_S": w_max * (phi_r + 2 * phi_n)}


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


def power(m: int, p_dir: Fraction) -> float:
    return float(upper_tail(m, k2(m), p_dir))


def main() -> None:
    p = c0_values()
    g = gate_set()
    sb = silence_bound(p, g)
    table = {m: k2(m) for m in range(MIN_M, MAX_M + 1)}
    pw = {}
    for share in (Fraction(1, 2), Fraction(6, 10), Fraction(7, 10), Fraction(8, 10)):
        m = round(INDIVIDUALS * share)
        pw[str(share)] = {"m": m, "k2": table[m],
                          "power": {str(pd): round(power(m, pd), 3)
                                    for pd in (Fraction(6, 10), Fraction(65, 100), Fraction(7, 10), Fraction(75, 100))}}
    out = {"c0": p, "gate_set": g, "intervals": intervals(g), "intervention_values": intervention_values(p),
           "silence_bound": sb, "silence_probability": silence_probability(p, sb["E_S"]),
           "k2_of_m": table, "power": pw}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
