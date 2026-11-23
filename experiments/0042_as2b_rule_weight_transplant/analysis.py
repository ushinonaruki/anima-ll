"""実験 0042（AS2b の候補 1 の事前登録 v0.2）の解析の部分：区間の算術、量の定義と札の入れ替えの性質（s から計算する量と δ）、
算術の恒等・打ち消し、
沈黙の十分条件（命題 S-1 の引き継ぎ）、判定の閾値・判定の形の性質・検出力の見込み。

README §1.2・§2・§3・§4.5・§5・§7。seed・乱数・既存の raw（0038〜0041 の記録を含む）は使わない。値は次だけから計算する。
- C0 の設計図（experiments/0012_passive_world/neuroarchitecture.yaml）の力学・可塑性の値と、出生時のばらつきの幅
- 関門の宣言 v0.2（experiments/0038_as2b_forward_gate/gate_declaration.json）の予定・o・W・L・長さ
- この README で決める値（経験の区間の窓の数 25、個体数 200、誤りの水準、最小の m）

二項の確率と、試しの区間の割合 s とその差は、分数で厳密に計算する。命題 S-1 の E_S と沈黙の割合は、実験 0039・0041 の
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

E_WINDOWS = 25                 # 経験の区間 E ＝ 窓 1〜25（README §1.2。0039・0041 の事前登録の E と同じ）
INDIVIDUALS = 200              # 本番の個体数（README §5.3）
ALPHA_PER_SIDE = Fraction(1, 40)   # 両側 0.05 を、向きごとに 0.025 に分ける（README §4.3）
MIN_M = 10                     # 判定に必要な、T ≠ 0 の個体の最小の数（README §4.3。0036〜0040 の最小の m と同じ値）
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")

# README §2.2。c は背景の本体の規則、[·] は試しの区間の 6 本の重み。どの複製の系も P_E で B^c から作り、U で 6 本を FREEZE する
FULL_BODIES = ("B_A1", "B_A2", "B_A1_rerun")
U_SYSTEMS = ("G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr", "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr",
             "G_A1_X1", "G_A1_X2", "G_A2_X1", "G_A2_X2",
             "N_A1_WA1", "N_A1_WA2", "N_A2_WA2", "N_A2_WA1")


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
    """窓 k の [a_k, b_k]、経験の区間 E・境界 P_E・試しの区間 U（README §2.1）。

    P_E は、E の最後の窓の次の手がかりの直前（c_(E+1) − 1）。E の最後の窓の決定から出た意図の結果の刺激（b_E ＋ L）は
    P_E より前に成立する。そのため P_E では、どの本体にも未決の窓・出す予定の意図・結果の予約がない（SE-T1）。
    U の最初の窓の決定は早くとも a_26 で、そこから出た意図の結果の刺激は早くとも a_26 ＋ L（SE-T6 の根拠）。
    """
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
            "pulses_per_individual": len(FULL_BODIES) * g["pulses"] + len(U_SYSTEMS) * u_pulses}


def share(a1: int, a2: int):
    """s ＝ #A1／(#A1 ＋ #A2)。決まった窓がなければ定まらない（None）。分数で正確に。"""
    n = a1 + a2
    return None if n == 0 else Fraction(a1, n)


def _diff(x, y):
    return None if x is None or y is None else x - y


def _sum(x, y):
    return None if x is None or y is None else x + y


def quantities(s: dict) -> dict:
    """README §3.2。s は系の名前 → A1 の割合（分数、または定まらない None）。

    s_c（規則 c が指す行動の割合）は、c ＝ A1 なら s、c ＝ A2 なら 1 − s。
    """
    def s_c(name, c):
        v = s[name]
        return None if v is None else (v if c == "A1" else 1 - v)

    q = {}
    q["T_A1"] = _diff(s["G_A1_WA1"], s["G_A1_WA2"])
    q["T_A2"] = _diff(s["G_A2_WA1"], s["G_A2_WA2"])
    q["T"] = _sum(q["T_A1"], q["T_A2"])                                     # 主の量（J_T・E_T）
    # 少なくとも一方の背景で T^(c) ≠ 0 か（p_any の個体の事象。T が定まるときだけ定める）。T ＝ 0 でも真になりうる（打ち消し）
    q["T_any"] = None if q["T"] is None else (q["T_A1"] != 0 or q["T_A2"] != 0)
    q["BE_WA1"] = _diff(s["G_A1_WA1"], s["G_A2_WA1"])                       # 同じ重み W^{A1} で、背景だけ違う
    q["BE_WA2"] = _diff(s["G_A1_WA2"], s["G_A2_WA2"])
    q["BE"] = _sum(q["BE_WA1"], q["BE_WA2"])
    q["TE_F"] = _diff(s["G_A1_WA1"], s["G_A2_WA2"])                         # U で FREEZE した自然な組み合わせの差
    q["D"] = _diff(s["B_A1"], s["B_A2"])                                    # 自然な対（U も可塑性 ON）の差
    q["S_A1"] = _diff(s["G_A1_X1"], s["G_A1_X2"])                           # 人工の端の感度の対照
    q["S_A2"] = _diff(s["G_A2_X1"], s["G_A2_X2"])
    q["S"] = _sum(q["S_A1"], q["S_A2"])
    q["TN_A1"] = _diff(s["N_A1_WA1"], s["N_A1_WA2"])                        # 結果を返さない世界での入れ替え
    q["TN_A2"] = _diff(s["N_A2_WA1"], s["N_A2_WA2"])
    q["TN"] = _sum(q["TN_A1"], q["TN_A2"])
    q["K_A1"] = _diff(s_c("G_A1_WA1", "A1"), s_c("N_A1_WA1", "A1"))          # 結果の帰還の有無（同じ状態・同じ重み）
    q["K_A2"] = _diff(s_c("G_A2_WA2", "A2"), s_c("N_A2_WA2", "A2"))
    q["Z_A1"] = _diff(s_c("B_A1", "A1"), s_c("G_A1_WA1", "A1"))              # 試しの区間の可塑性 ON・OFF
    q["Z_A2"] = _diff(s_c("B_A2", "A2"), s_c("G_A2_WA2", "A2"))
    return q


# 札の入れ替え：源 1 と源 2（A1 と A2）の札を入れ替えると、規則 c ＝ A1 の本体は規則 c ＝ A2 の本体になり、W^{A1} は W^{A2}、
# 端 X1（C → 源 1 ＝ w_max）は X2 になり、A1 の割合 s は 1 − s になる。
SWAP = {"B_A1": "B_A2", "B_A2": "B_A1", "B_A1_rerun": "B_A2",
        "G_A1_WA1": "G_A2_WA2", "G_A2_WA2": "G_A1_WA1", "G_A1_WA2": "G_A2_WA1", "G_A2_WA1": "G_A1_WA2",
        "G_A1_WA1_tr": "G_A2_WA2_tr", "G_A2_WA2_tr": "G_A1_WA1_tr",
        "G_A1_X1": "G_A2_X2", "G_A2_X2": "G_A1_X1", "G_A1_X2": "G_A2_X1", "G_A2_X1": "G_A1_X2",
        "N_A1_WA1": "N_A2_WA2", "N_A2_WA2": "N_A1_WA1", "N_A1_WA2": "N_A2_WA1", "N_A2_WA1": "N_A1_WA2"}
INVARIANT = ("T", "T_any", "BE", "TE_F", "D", "S", "TN")
EXCHANGED = (("T_A1", "T_A2"), ("BE_WA1", "BE_WA2"), ("S_A1", "S_A2"), ("TN_A1", "TN_A2"), ("K_A1", "K_A2"), ("Z_A1", "Z_A2"))


def swapped(s: dict) -> dict:
    """札を入れ替えた札で見た、同じ物理の系の割合。新しい札の系 x の値は、元の札の系 SWAP[x] の 1 − s。"""
    out = {}
    for x in s:
        if x == "B_A1_rerun":
            continue
        v = s[SWAP[x]]
        out[x] = None if v is None else 1 - v
    return out


def label_swap_and_identity_check() -> dict:
    """札の入れ替えの性質と算術の恒等（README §3.2・SE-T4・SE-T7）を、手で置いた値で確かめる（seed も乱数も使わない）。

    - INVARIANT の量は正確に同じ値のまま。EXCHANGED の組は互いに入れ替わる
    - TE_F ＝ (T ＋ BE)／2（四つの s がすべて定まるとき）。本当の内訳とは呼ばない
    - W^{A1} ＝ W^{A2} の個体（構造上の恒等）では、G^c[W^d] ＝ G^c[W^c]・N^c[W^d] ＝ N^c[W^c] なので T ＝ TN ＝ 0
    - 打ち消し：T^{(A1)} ＝ −T^{(A2)} ≠ 0 なら、両方の背景で s が変わっていても T ＝ 0（T_any は真。README §3.2）
    - δ は s から計算しないので、ここでは扱わない（delta_label_swap_check）
    - この性質は、T の符号が＋・−で対称であることの根拠ではない（札の入れ替えは T を −T に移さない：README §4.6）
    """
    def f(a, b):
        return Fraction(a, b)
    base = {"B_A1": f(7, 12), "B_A2": f(5, 13), "B_A1_rerun": f(7, 12),
            "G_A1_WA1": f(9, 14), "G_A1_WA2": f(8, 14), "G_A1_WA1_tr": f(9, 14),
            "G_A2_WA2": f(4, 11), "G_A2_WA1": f(6, 11), "G_A2_WA2_tr": f(4, 11),
            "G_A1_X1": f(12, 13), "G_A1_X2": f(2, 13), "G_A2_X1": f(10, 12), "G_A2_X2": f(1, 12),
            "N_A1_WA1": f(3, 5), "N_A1_WA2": f(3, 5), "N_A2_WA2": f(2, 9), "N_A2_WA1": f(4, 9)}
    identical = dict(base, G_A1_WA2=base["G_A1_WA1"], G_A2_WA1=base["G_A2_WA2"],
                     N_A1_WA2=base["N_A1_WA1"], N_A2_WA1=base["N_A2_WA2"])         # 構造上の恒等（W^{A1} ＝ W^{A2}）
    undefined = dict(base, G_A2_WA1=None)                                          # 四つの系のどれかが定まらない
    single_action = {k: Fraction(1) for k in base}                                 # どの系も一方の行動だけ（A7 の凍結）
    cancel = dict(base, G_A1_WA1=f(3, 4), G_A1_WA2=f(1, 2), G_A2_WA1=f(1, 4), G_A2_WA2=f(1, 2))  # T^(A1) ＝ ＋1/4、T^(A2) ＝ −1/4
    out = []
    for case in (base, identical, undefined, single_action, cancel):
        q = quantities(case)
        r = quantities(swapped(case))
        for k in INVARIANT:
            assert r[k] == q[k], k
        for a, b in EXCHANGED:
            assert (r[a], r[b]) == (q[b], q[a]), (a, b)
        if None not in (q["T"], q["BE"], q["TE_F"]):
            assert q["TE_F"] == (q["T"] + q["BE"]) / 2
        out.append({k: (None if v is None else str(v)) for k, v in q.items()})
    assert out[1]["T"] == "0" and out[1]["TN"] == "0"
    assert out[2]["T"] is None and out[2]["T_A1"] is not None
    assert out[3]["T"] == "0" and out[3]["T_any"] == "False"
    assert out[1]["T_any"] == "False" and out[2]["T_any"] is None
    assert out[4]["T_A1"] == "1/4" and out[4]["T_A2"] == "-1/4" and out[4]["T"] == "0" and out[4]["T_any"] == "True"
    return {"cases": out, "invariant": list(INVARIANT), "exchanged": [list(p) for p in EXCHANGED],
            "TE_F_equals_half_T_plus_BE": True, "cancellation_gives_T_zero_with_T_any_true": True,
            "not_a_basis_for_sign_symmetry": True}


def delta(w_a1: dict, w_a2: dict):
    """0041 §3.2 の δ ＝ (a_1^{A1} − a_1^{A2}) − (a_2^{A1} − a_2^{A2})、a_j^c ＝ W^c(C → 源 j)。"""
    return (w_a1["C_to_source1"] - w_a2["C_to_source1"]) - (w_a1["C_to_source2"] - w_a2["C_to_source2"])


SOURCE_SWAP = {"C_to_source1": "C_to_source2", "C_to_source2": "C_to_source1",
               "source1_to_C": "source2_to_C", "source2_to_C": "source1_to_C",
               "source1_to_source2": "source2_to_source1", "source2_to_source1": "source1_to_source2"}


def delta_label_swap_check() -> dict:
    """δ の札の入れ替えの不変（README §3.2・SE-T11）を、手で置いた 6 本の重みの組で確かめる（seed も乱数も記録も使わない）。

    札を入れ替えると、規則 c ＝ A1 の本体は規則 c ＝ A2 の本体になり（W^{A1} と W^{A2} が入れ替わる）、各本体の中で
    源 1 と源 2 の接続の名前が入れ替わる。新しい札の W'^{A1}(x) ＝ 元の W^{A2}(SOURCE_SWAP[x])。
    δ' ＝ (a_2^{A2} − a_2^{A1}) − (a_1^{A2} − a_1^{A1}) ＝ δ（代数）。分数では正確に、浮動小数でも差の反対称
    fl(p − q) ＝ −fl(q − p) により正確に同じ値になることを確かめる。実際の記録での確かめは道具の契約テスト（CT-42-9）。
    """
    def swap(w_a1, w_a2):
        return ({x: w_a2[SOURCE_SWAP[x]] for x in ROLES6}, {x: w_a1[SOURCE_SWAP[x]] for x in ROLES6})

    def frac(d):
        return {k: Fraction(v) for k, v in d.items()}
    sets = [
        ({"C_to_source1": 0.0047, "source1_to_C": 0.0053, "C_to_source2": 0.0051, "source2_to_C": 0.0049,
          "source1_to_source2": 0.0044, "source2_to_source1": 0.0056},
         {"C_to_source1": 0.00512, "source1_to_C": 0.00488, "C_to_source2": 0.00497, "source2_to_C": 0.00503,
          "source1_to_source2": 0.0046, "source2_to_source1": 0.0054}),
        ({"C_to_source1": 0.004812345678, "source1_to_C": 0.005187654322, "C_to_source2": 0.005003, "source2_to_C": 0.004997,
          "source1_to_source2": 0.005, "source2_to_source1": 0.005},
         {"C_to_source1": 0.005231, "source1_to_C": 0.004769, "C_to_source2": 0.004801999, "source2_to_C": 0.005198001,
          "source1_to_source2": 0.005, "source2_to_source1": 0.005}),
    ]
    sets.append((dict(sets[0][0]), dict(sets[0][0])))                                # W^{A1} ＝ W^{A2}：δ ＝ 0
    out = []
    for w1, w2 in sets:
        f1, f2 = frac(w1), frac(w2)
        d_frac = delta(f1, f2)
        s1, s2 = swap(f1, f2)
        assert delta(s1, s2) == d_frac                                                # 分数で正確に同じ
        d_float = delta(w1, w2)
        t1, t2 = swap(w1, w2)
        assert delta(t1, t2) == d_float                                               # 浮動小数でも正確に同じ値
        assert (d_float > 0) == (d_frac > 0) and (d_float < 0) == (d_frac < 0)        # 手で置いた値では符号も一致
        out.append({"delta_fraction": str(d_frac), "delta_float": repr(d_float)})
    assert out[2]["delta_fraction"] == "0"
    return {"cases": out, "delta_invariant_under_label_swap": True, "scope": "algebra on hand-placed weights only"}


def extremes(p: dict) -> dict:
    """人工の端 X1・X2 の 6 本（0040 §2.3 と同じ値。w_min・w_max・w0 だけから決める）。F1 を確かめる。"""
    w_max, w0 = p["w_max"], p["w0"]
    x1 = {"C_to_source1": w_max, "source1_to_C": 0.0, "C_to_source2": 0.0, "source2_to_C": w_max,
          "source1_to_source2": w0, "source2_to_source1": w0}
    x2 = {"C_to_source1": 0.0, "source1_to_C": w_max, "C_to_source2": w_max, "source2_to_C": 0.0,
          "source1_to_source2": w0, "source2_to_source1": w0}
    for x in (x1, x2):
        assert x["C_to_source1"] + x["source1_to_C"] == w_max and x["C_to_source2"] + x["source2_to_C"] == w_max
        assert x["source1_to_source2"] + x["source2_to_source1"] == w_max
    delta_units = (Fraction(x1["C_to_source1"]) - Fraction(x2["C_to_source1"])) \
        - (Fraction(x1["C_to_source2"]) - Fraction(x2["C_to_source2"]))
    return {"X1": x1, "X2": x2, "contrast_in_delta_units": float(delta_units)}


def silence_bound(p: dict, g: dict) -> dict:
    """命題 S-1 の E_S と、その導出の途中の値（実験 0039 §7.2 と同じ式。移植・FREEZE・世界の応答の有無に依らない）。"""
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


def house_form_ceiling() -> dict:
    """0 を分母に残す個体の多数の形（0039〜0041 の形）で、T ＝ 0 の個体の割合 z が 1 − k₂(m)/m を超えると、
    T ≠ 0 の個体がすべて同じ向きでも成立しえない（README §4.5）。分布やデータを仮定しない算術。"""
    return {str(m): {"k2": k2(m), "zero_share_above_which_impossible": float(1 - Fraction(k2(m), m))}
            for m in (50, 100, 150, 180, 200)}


def power_sign_among_nonzero() -> dict:
    """J_T（README §4.3）の検出力の見込み：T ≠ 0 の個体の数 m≠ と、その中の＋の割合 π_dir ごとに、＋の向きで成立する確率
    （−の向きでも同じ）。m≠・π_dir の値は見込みの幅で、データから選んでいない。"""
    out = {}
    for m in (10, 15, 20, 30, 50, 80, 120):
        k = k2(m)
        out[str(m)] = {"k2": k, **{str(pd): round(float(upper_tail(m, k, pd)), 3)
                                    for pd in (Fraction(65, 100), Fraction(75, 100), Fraction(85, 100))}}
    return out


def power_house_form() -> dict:
    """比べのための、0 を分母に残す形の検出力：m ＝ 180、T ＝ 0 の割合 z、T ≠ 0 の中の＋の割合 π_dir。"""
    m = 180
    k = k2(m)
    out = {"m": m, "k2": k}
    for z in (Fraction(1, 10), Fraction(3, 10), Fraction(5, 10), Fraction(7, 10)):
        out[str(z)] = {str(pd): round(float(upper_tail(m, k, (1 - z) * pd)), 3)
                       for pd in (Fraction(75, 100), Fraction(85, 100), Fraction(1))}
    return out


def main() -> None:
    p = c0_values()
    g = gate_set()
    sb = silence_bound(p, g)
    out = {"c0": p, "gate_set": g, "intervals": intervals(g), "systems": {"full": list(FULL_BODIES), "U_only": list(U_SYSTEMS)},
           "extremes": extremes(p), "label_swap_and_identity": label_swap_and_identity_check(),
           "delta_label_swap": delta_label_swap_check(),
           "silence_bound": sb, "silence_probability": silence_probability(p, sb["E_S"]),
           "min_m": MIN_M, "k2_of_m": {m: k2(m) for m in range(MIN_M, INDIVIDUALS + 1)},
           "house_form_ceiling": house_form_ceiling(), "power_J_T": power_sign_among_nonzero(),
           "power_house_form_for_comparison": power_house_form()}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
