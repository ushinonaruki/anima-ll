"""実験 0043 の独立の検算（README §9.1。標準のライブラリだけ）。

この実験の解析・測定の道具も、事前登録の analysis.py も、anima_ll も、AS2b の道具も、protocol.yaml を読む道具も読み込まない。
保存した生の記録（seeds/<seed>/raw.json.gz）だけから、定義（README §2.2・§3〜§6）を書き起こし直して report の欄をすべて組み立て直し、
report.json と欄ごとに照合する。判定の閾値などの事前登録の値は、README・protocol.yaml（v0.2。#200 merge `8fee59e`）から
書き起こした PREREGISTERED から取る。生の記録の meta に保存された protocol の写しは、0042 と同じく、次を確かめるだけに使う
- 全個体にあり、全個体で同じであること
- 写しの中身全体を JSON に正規化したもののハッシュが、事前登録 v0.2 の protocol の固定のハッシュ（PROTOCOL_JSON_SHA256）と同じであること
- SHA-256 が、リポジトリの確定済みの protocol.yaml のバイト列の SHA-256（PROTOCOL_FILE_SHA256）と同じであること
- 写しの中の判定に関わる値が、PREREGISTERED と同じであること。k₂(m)（m ＝ 10〜200）は、二項から求め直した値と同じであること

report との照合（recheck）
- 生の記録から、report と同じ形の期待値を作る：mode・valid・outcome・O1・関門の宣言の SHA-256、判定 J_C、推定 E_C、§6 の必ず報告する記述、
  個体ごとの量（作った系の窓の数と s、段ごとの中心の差と値の区分・合算・比べへの適格、§3.2 のほかの量、k*、札、δ(e)、重み、
  作らない系、結果の刺激、最初に分かれた Pulse と窓、発火の数）、補助の記録 R1〜R9
- s と量は、層 A の窓の結末から数え直した分数で、定義をここに書き下して計算する
- 重みの算術（e・δ(e)・m_k・端の正確な値・範囲・丸め）は、保存した P_E の Σ の浮動小数の値を有理数として、ここで書き直して確かめる（O10）
- 期待値と report を、欄の組・列の長さ・葉の値まで、すべての欄で比べる（compare）。葉の値は型も比べる。数はちょうど同じであることを
  求める。許す違いは、Clopper–Pearson の端点と命題 S-1 の E_S だけで、絶対値 1e-9 まで
- 操作の確認の主なもの（O3〜O14）を、別の書き方で

測定の来歴と全件性（recheck_directory）：0042 と同じ（seed の組は、本番は 36001〜36200 の 200 個体がちょうど。合成は合成の範囲の中。
smoke の盲検の記録は対象ではない）

使い方（結果を保存したフォルダを渡す。測定の commit で、計算の後で一度だけ）:
  python experiments/0043_as2b_natural_difference_scaling/recheck.py <フォルダ> [--write <結果の JSON>]
"""

import argparse
import copy
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

ACTIONS = ("A1", "A2")
SIGNS = ("+", "-", "0")
ROLES3 = ("cue", "source1", "source2")
SOURCES = ("source1", "source2")
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")
U_SIGN = {"C_to_source1": 1, "source1_to_C": -1, "C_to_source2": -1, "source2_to_C": 1,
          "source1_to_source2": 0, "source2_to_source1": 0}                          # u ＝ (X1 − X2)／w_max
BODIES = ["B_A1", "B_A2"]
RERUN = "B_A1_rerun"
CLASS_ORDER = ("out_of_range", "s_undefined", "structural_zero", "measured_zero", "nonzero")
DEFINED = ("structural_zero", "measured_zero", "nonzero")
PEOPLE_CLASSES = ("plus", "minus", "structural_zero", "both_zero", "cancellation", "undefined")
C_LABELS = ("Z-1", "Z-2", "identity", "rounding_coincidence")
DU_LABELS = ("delta_zero", "rounding_coincidence")
REASONS = ("C_out_of_range", "Du_out_of_range", "s_undefined", "C_structural_zero", "Du_structural_zero")
OTHERS = ("T_A1", "T_A2", "T", "S_A1", "S_A2", "S", "D", "Z_A1", "Z_A2")
# report の決まった文（README §4・§6。解析の道具と同じ文を、ここに書き起こす）
NOTES = {"estimate": "estimate only; no threshold; not a judgment (README section 4.5)",
         "p_nz": "share of individuals whose summed C_2 is nonzero; not the share whose choice changed (cancellations are C_2 = 0)",
         "p_any": "share of individuals in which at least one background has C_2_c != 0; descriptive",
         "prominence": "report m_nonzero / m_def, p_nz and p_any with their intervals with the same prominence as the J_C direction",
         "artificial": "k >= 2 weights are artificial (the natural difference stretched); never a statement about natural weights (README section 0.4)",
         "levels": "levels other than k0 = 2 are descriptive; differences between levels include the change of the surviving individuals (README section 6.1)",
         "comparison": "C_k (rule meaning) and D^u_k (weight-direction meaning) have different sign meanings; only tables split by the sign of delta(e) are shown; only the magnitude of delta is matched (README section 6.2)",
         "R8": "Clopper-Pearson 95% intervals are in judgment.J_C, estimate and descriptive",
         "R4": "the six weights of every built clone after S3 are its endpoint, X1, X2 or W_c (O6 (a), O10, O11)",
         "R9": "within-body before/after; not a counterfactual contrast",
         "T": "0042-type natural swap in this population; never a re-test of 0042 J_T, never merged",
         "S": "midpoint w0 (not W_c); a positive response is not guaranteed; material for reading a negative only",
         "not_made": "no cross tables of sign delta(e), sign S or sign T against sign C_k (other than the comparison table); no correlation test"}
HEX = set("0123456789abcdef")
DIGITS = set("0123456789")
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROTOCOL_FILE = HERE / "protocol.yaml"
# 事前登録 v0.2 の protocol.yaml（#200 merge `8fee59e`）を、raw の meta と同じ形（YAML を読み、JSON を通した形）にして正規化した
# JSON の SHA-256。正規化：json.dumps(写し, sort_keys=True, ensure_ascii=False, separators=(",", ":")) の UTF-8。
# 値は契約テストで、正本から計算し直して照らす
PROTOCOL_JSON_SHA256 = "ccb945bf6535eceec1de09dffe81022260898dbb4826fbccc0fb3de8c4205e0d"
PROTOCOL_FILE_SHA256 = "aad8053fd56e7b69e3cb6fef2c325514800ea4dccc1033125259aaff826cfcad"   # 同じ正本のファイルのバイト列
GATE_FILE = "experiments/0038_as2b_forward_gate/gate_declaration.json"
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
# 事前登録 v0.2 から書き起こした値：README §1.2・§2・§4・§5.1・§8・§9.2、protocol.yaml の judgment・timeline・brain・world・weights・
# systems・extremes・seeds。判定はこの値で計算し、meta の protocol の写しは、これと照らすだけに使う
PREREGISTERED = {
    "experiment": "0043", "kind": "preregistered_test",
    "alpha_per_direction": Fraction(1, 40), "alpha_two_sided": Fraction(1, 20), "min_population": 10, "individuals": 200,
    "k2_200": 115, "outcomes": ["invalid", "inconclusive", "not_established", "plus", "minus"],
    "experience_windows": [1, 25], "experience_pulses": [1, 1065], "boundary_P_E": 1065,
    "test_windows": [26, 50], "test_pulses": [1066, 2072], "body_pulses": 2072,
    "w_min": 0.0, "w_max": 0.01, "w0": 0.005, "f1_tolerance": 1e-12,
    "levels": [1, 2, 4, 8], "k0": 2, "scheme": "multiple",
    "rule_c": {"B_A1": "A1", "B_A2": "A2", "B_A1_rerun": "A1"},
    "extremes": {"X1": {"C_to_source1": 0.01, "source1_to_C": 0.0, "C_to_source2": 0.0, "source2_to_C": 0.01,
                        "source1_to_source2": 0.005, "source2_to_source1": 0.005},
                 "X2": {"C_to_source1": 0.0, "source1_to_C": 0.01, "C_to_source2": 0.01, "source2_to_C": 0.0,
                        "source1_to_source2": 0.005, "source2_to_source1": 0.005}},
    "seeds": {"first": 36001, "last": 36200}, "smoke_seeds": {"first": 36201, "last": 36206},
    "synthetic_seeds": {"first": 36301, "last": 36399},
    "formal_plan": {"first": 41, "spacing": 41, "count": 50, "offset": 2, "length": 19, "delay": 2, "e_windows": 25},
}
W_MIN, W_MAX, W0 = PREREGISTERED["w_min"], PREREGISTERED["w_max"], PREREGISTERED["w0"]
K0 = PREREGISTERED["k0"]
START, FINISH, RAW, SEEDS_DIR = "run_started.json", "run_finished.json", "raw.json.gz", "seeds"
REPORT, O1_FILE = "report.json", "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py",
                  "tests/integration/test_as2b_rule_weight_direction_0041.py",
                  "tests/integration/test_as2b_rule_weight_transplant_0042.py",
                  "tests/integration/test_as2b_natural_difference_scaling_0043.py")
RECHECKED_MODES = {"formal": "seeds", "synthetic": "synthetic_seeds"}          # smoke（盲検の記録）は対象ではない
LOOSE = 1e-9


def geometry(plan: dict) -> dict:
    cues = [plan["first"] + plan["spacing"] * k for k in range(plan["count"])]
    windows = [(k + 1, c + plan["offset"], c + plan["offset"] + plan["length"] - 1) for k, c in enumerate(cues)]
    e = plan["e_windows"]
    return {"cues": cues, "windows": windows, "e": e, "p_e": cues[e] - 1, "end": windows[-1][2] + plan["delay"]}


def sign_of(x: Fraction) -> str:
    return "+" if x > 0 else "-" if x < 0 else "0"


def bound_e_s(manifest: dict, plan: dict) -> float:
    """命題 S-1 の E_S（README §7.2 を書き起こしたもの。0042 と同じ式）。"""
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
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def frac(x: Fraction | None) -> dict | None:
    return None if x is None else {"num": x.numerator, "den": x.denominator, "value": float(x)}


def valued(x: Fraction | None) -> dict:
    return {"value": frac(x), "sign": None if x is None else sign_of(x)}


def fstr(x: Fraction) -> str:
    return f"{x.numerator}/{x.denominator}"


# ---- 系の名前（README §2.3 の表から書き起こす） ------------------------------------------------------------

def clone_list(levels: list) -> list[str]:
    out = []
    for c in ACTIONS:
        out.append(f"G_{c}_base")
        out += [f"G_{c}_{s}{k}" for k in levels for s in ("P", "M")]
        out += [f"G_{c}_{s}{k}" for k in levels for s in ("UP", "UM")]
        out += [f"G_{c}_X1", f"G_{c}_X2", f"G_{c}_tr"]
    return out


def split_name(name: str) -> tuple:
    """複製の系の名前 → (背景, 種類, 段, 側)。種類は base・tr・X1・X2・natural・symmetric。"""
    c, part = name[2:4], name[5:]
    if part in ("base", "tr", "X1", "X2"):
        return c, part, None, None
    for head, kind, side in (("UP", "symmetric", 1), ("UM", "symmetric", -1), ("P", "natural", 1), ("M", "natural", -1)):
        if part.startswith(head) and part[len(head):].isdigit():
            return c, kind, int(part[len(head):]), side
    raise ValueError(name)


def endpoint_list(levels: list) -> list[str]:
    return [n for n in clone_list(levels) if split_name(n)[1] in ("natural", "symmetric")]


def role_cids(roles: dict) -> dict:
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


def records_of(run: dict) -> dict:
    return {**run["bodies"], **run["clones"]}


def built_list(run: dict) -> list[str]:
    return [n for n in clone_list(run["levels"]) if n in run["clones"]]


def window_count(layer_a: list, lo: int, hi: int) -> dict:
    outs = Counter(r["outcome"] for r in layer_a if lo <= r["window"] <= hi)
    return {"windows": sum(outs.values()), "decided": outs["A1"] + outs["A2"], "A1": outs["A1"], "A2": outs["A2"],
            "tie": outs["tie"], "none": outs["none"]}


def a1_share(counts: dict) -> Fraction | None:
    return None if counts["decided"] == 0 else Fraction(counts["A1"], counts["decided"])


def conn_weights(sigma: dict) -> dict:
    return {cid: v["weight"] for cid, v in sigma["connections"].items()}


def max_pair_gap(weights: dict) -> Fraction:
    by_pair: dict[tuple, list] = {}
    for cid, w in weights.items():
        by_pair.setdefault(tuple(sorted(cid.split(".main->"))), []).append(Fraction(w))
    return max(abs(sum(ws, Fraction(0)) - Fraction(W_MAX)) for ws in by_pair.values())


# ---- 重みの算術（README §2.2 を書き直したもの） --------------------------------------------------------------

def rational_endpoints(roles: dict, w_a1: dict, w_a2: dict, levels: list) -> dict:
    """端ごとに (正確な値（役 → 分数）, 範囲の中か, 範囲の外の [役, 側] の列, 丸めた値（接続の ID → 浮動小数）か None)。"""
    cid = role_cids(roles)
    top = Fraction(W_MAX)
    exact = {"A1": {r: Fraction(w_a1[cid[r]]) for r in ROLES6}, "A2": {r: Fraction(w_a2[cid[r]]) for r in ROLES6}}
    diff = {r: exact["A1"][r] - exact["A2"][r] for r in ROLES6}
    d_e = diff["C_to_source1"] - diff["C_to_source2"]
    out = {}
    for name in endpoint_list(levels):
        c, kind, k, side = split_name(name)
        if kind == "natural":
            step = {r: diff[r] * k for r in ROLES6}
        else:
            step = {r: abs(d_e) * k / 2 * U_SIGN[r] for r in ROLES6}
        v = {r: exact[c][r] + side * step[r] for r in ROLES6}
        outside = [[r, "below" if v[r] < 0 else "above"] for r in ROLES6 if v[r] < 0 or v[r] > top]
        out[name] = (v, not outside, outside, None if outside else {cid[r]: float(v[r]) for r in ROLES6})
    return {"e": diff, "delta_e": d_e, "m": {k: abs(d_e) * k / 2 for k in levels}, "endpoints": out}


# ---- 個体ごとの量（README §3・§4・§6） ---------------------------------------------------------------

def definitions(levels: list, s: dict) -> dict:
    """README §3.2 を書き起こしたもの（分数。使う s が一つでも定まらなければ、その量は定まらない）。"""
    def minus(a, b):
        return None if s.get(a) is None or s.get(b) is None else s[a] - s[b]

    def plus(a, b):
        return None if a is None or b is None else a + b

    def of_c(name, c):
        v = s.get(name)
        return None if v is None else (v if c == "A1" else 1 - v)
    q = {}
    for k in levels:
        for c in ACTIONS:
            q[f"C{k}_{c}"] = minus(f"G_{c}_P{k}", f"G_{c}_M{k}")
            q[f"up{k}_{c}"] = minus(f"G_{c}_P{k}", f"G_{c}_base")
            q[f"dn{k}_{c}"] = minus(f"G_{c}_base", f"G_{c}_M{k}")
            q[f"Du{k}_{c}"] = minus(f"G_{c}_UP{k}", f"G_{c}_UM{k}")
        q[f"C{k}"] = plus(q[f"C{k}_A1"], q[f"C{k}_A2"])
        q[f"C{k}_any"] = None if q[f"C{k}"] is None else (q[f"C{k}_A1"] != 0 or q[f"C{k}_A2"] != 0)
        q[f"Du{k}"] = plus(q[f"Du{k}_A1"], q[f"Du{k}_A2"])
    has1 = 1 in levels
    q["T_A1"] = minus("G_A1_base", "G_A1_M1") if has1 else None
    q["T_A2"] = minus("G_A2_P1", "G_A2_base") if has1 else None
    q["T"] = plus(q["T_A1"], q["T_A2"])
    q["S_A1"], q["S_A2"] = minus("G_A1_X1", "G_A1_X2"), minus("G_A2_X1", "G_A2_X2")
    q["S"] = plus(q["S_A1"], q["S_A2"])
    q["D"] = minus("B_A1", "B_A2")
    za = None if of_c("B_A1", "A1") is None or of_c("G_A1_base", "A1") is None else of_c("B_A1", "A1") - of_c("G_A1_base", "A1")
    zb = None if of_c("B_A2", "A2") is None or of_c("G_A2_base", "A2") is None else of_c("B_A2", "A2") - of_c("G_A2_base", "A2")
    q["Z_A1"], q["Z_A2"] = za, zb
    return q


def value_class(run: dict, s: dict, plus: str, minus: str) -> tuple:
    """§4.1 の順：範囲 → s の定義 → 両端の一致 → 測った値。"""
    ep, em = run["endpoints"][plus], run["endpoints"][minus]
    if not ep["in_range"] or not em["in_range"]:
        return "out_of_range", None
    sp, sm = s.get(plus), s.get(minus)
    if sp is None or sm is None:
        return "s_undefined", None
    if ep["weights"] == em["weights"]:
        return "structural_zero", Fraction(0)
    d = sp - sm
    return ("nonzero" if d != 0 else "measured_zero"), d


def firing_at(activity: list, lo: int, hi: int) -> dict:
    out: dict[int, Counter] = {}
    for p, u in activity:
        if lo <= p <= hi:
            out.setdefault(p, Counter())[u] += 1
    return out


def first_split(act_a: list, act_b: list, lo: int, hi: int) -> int | None:
    a, b = firing_at(act_a, lo, hi), firing_at(act_b, lo, hi)
    return min((p for p in set(a) | set(b) if a.get(p, Counter()) != b.get(p, Counter())), default=None)


def first_outcome_split(la: list, lb: list) -> int | None:
    return next((x["window"] for x, y in zip(la, lb) if x["outcome"] != y["outcome"]), None)


def r6_keys(run: dict) -> list[tuple]:
    built = built_list(run)
    out = []
    for c in ACTIONS:
        out += [(f"G_{c}_base", n) for n in built if n[2:4] == c and n != f"G_{c}_base"]
        for k in run["levels"]:
            for a, b in ((f"G_{c}_P{k}", f"G_{c}_M{k}"), (f"G_{c}_UP{k}", f"G_{c}_UM{k}")):
                if a in run["clones"] and b in run["clones"]:
                    out.append((a, b))
        out.append((f"G_{c}_X1", f"G_{c}_X2"))
    return out


def individual(data: dict) -> dict:
    """1 個体の量を、report の individuals の欄と同じ形で書き起こす。"""
    run, plan = data["run"], data["run"]["plan"]
    levels = list(run["levels"])
    geo = geometry(plan)
    e, k_all, p_e, end = geo["e"], plan["count"], geo["p_e"], geo["end"]
    roles, rec = run["roles"], records_of(run)
    systems = BODIES + [RERUN] + built_list(run)
    built = built_list(run)
    name_of = {roles[r]: r for r in ROLES3}
    counts_e = {n: window_count(rec[n]["layer_a"], 1, e) for n in systems}
    counts_u = {n: window_count(rec[n]["layer_a"], e + 1, k_all) for n in systems}
    s = {n: a1_share(counts_u[n]) for n in systems}
    q = definitions(levels, s)
    decided = [r["window"] for r in rec["B_A1"]["layer_a"] if r["window"] <= e and r["outcome"] in ACTIONS]
    ks = decided[0] if decided else None
    zero = None if ks is not None else ("Z-1" if counts_e["B_A1"]["none"] == counts_e["B_A1"]["windows"] else "Z-2")
    w = run["boundary"]["W"]
    same = w["A1"] == w["A2"]
    cid_of = role_cids(roles)
    wa1 = {r: Fraction(w["A1"][cid_of[r]]) for r in ROLES6}
    wa2 = {r: Fraction(w["A2"][cid_of[r]]) for r in ROLES6}
    delta = (wa1["C_to_source1"] - wa2["C_to_source1"]) - (wa1["C_to_source2"] - wa2["C_to_source2"])
    per = {}
    for k in levels:
        cc = {c: value_class(run, s, f"G_{c}_P{k}", f"G_{c}_M{k}") for c in ACTIONS}
        dd = {c: value_class(run, s, f"G_{c}_UP{k}", f"G_{c}_UM{k}") for c in ACTIONS}
        cval = cc["A1"][1] + cc["A2"][1] if cc["A1"][0] in DEFINED and cc["A2"][0] in DEFINED else None
        dval = dd["A1"][1] + dd["A2"][1] if dd["A1"][0] in DEFINED and dd["A2"][0] in DEFINED else None
        if cval is None:
            cls = "undefined"
        elif cval != 0:
            cls = "plus" if cval > 0 else "minus"
        elif cc["A1"][0] == cc["A2"][0] == "structural_zero":
            cls = "structural_zero"
        elif cc["A1"][1] == 0 == cc["A2"][1]:
            cls = "both_zero"
        else:
            cls = "cancellation"

        def lab_c(x):
            if x != "structural_zero":
                return None
            if ks is None:
                return zero
            return "identity" if same else "rounding_coincidence"

        def lab_d(x):
            return None if x != "structural_zero" else ("delta_zero" if delta == 0 else "rounding_coincidence")
        good = {c: cc[c][0] in ("measured_zero", "nonzero") and dd[c][0] in ("measured_zero", "nonzero") for c in ACTIONS}
        why = {}
        for c in ACTIONS:
            flags = {"C_out_of_range": cc[c][0] == "out_of_range", "Du_out_of_range": dd[c][0] == "out_of_range",
                     "s_undefined": "s_undefined" in (cc[c][0], dd[c][0]),
                     "C_structural_zero": cc[c][0] == "structural_zero", "Du_structural_zero": dd[c][0] == "structural_zero"}
            why[c] = [r for r in REASONS if flags[r]]
        per[str(k)] = {
            "C": {"value": valued(cval), "class": cls, "any": q[f"C{k}_any"],
                  **{c: {"class": cc[c][0], "value": valued(cc[c][1]), "label": lab_c(cc[c][0])} for c in ACTIONS}},
            "Du": {"value": valued(dval), "structural": "structural_zero" in (dd["A1"][0], dd["A2"][0]),
                   **{c: {"class": dd[c][0], "value": valued(dd[c][1]), "label": lab_d(dd[c][0])} for c in ACTIONS}},
            "eligible": {"A1": good["A1"], "A2": good["A2"], "individual": good["A1"] and good["A2"]},
            "ineligible_reasons": why,
            "up": {c: valued(q[f"up{k}_{c}"]) for c in ACTIONS},
            "dn": {c: valued(q[f"dn{k}_{c}"]) for c in ACTIONS},
        }
    e_s = bound_e_s(data["meta"]["manifest"], plan)
    units = run["birth_units"]
    margin = {}
    for u, role in name_of.items():
        dyn = units[u]["dynamics"]
        margin[role] = dyn["intrinsic_drive_per_second"] / (1 - dyn["decay_per_second"]) - dyn["threshold"]
    silent = {role: margin[role] < -e_s for role in SOURCES}
    fired = {u for n in systems for _p, u in rec[n]["activity"]}
    rule = {"B_A1": "A1", "B_A2": "A2"} | {n: n[2:4] for n in built}
    consequences = {}
    for n in BODIES + built:
        pulses = [row[3] for row in rec[n]["world_end"]["reserved"] if row[1] == "consequence"]
        consequences[n] = {"E": sum(1 for p in pulses if p <= p_e), "U": sum(1 for p in pulses if p > p_e),
                           "decided_windows_of_c": {"E": counts_e[n][rule[n]], "U": counts_u[n][rule[n]]}}
    split = {"B_A1|B_A2": {"firing": first_split(rec["B_A1"]["activity"], rec["B_A2"]["activity"], 1, end),
                           "window": first_outcome_split(rec["B_A1"]["layer_a"], rec["B_A2"]["layer_a"])}}
    for a, b in r6_keys(run):
        split[f"{a}|{b}"] = {"firing": first_split(rec[a]["activity"], rec[b]["activity"], p_e + 1, end),
                             "window": first_outcome_split(rec[a]["layer_a"], rec[b]["layer_a"])}
    firing = {}
    for n in systems:
        by_part = {"U": dict.fromkeys(ROLES3, 0)}
        if n in BODIES or n == RERUN:
            by_part["E"] = dict.fromkeys(ROLES3, 0)
        for p, u in rec[n]["activity"]:
            part = "U" if p > p_e else "E"
            if part in by_part and u in name_of:
                by_part[part][name_of[u]] += 1
        firing[n] = by_part

    def base_kind(x):
        return "undefined" if x is None else ("0" if x == 0 else "1" if x == 1 else "between")
    main = per.get(str(K0), {"C": {"class": "undefined"}})["C"]
    return {
        "roles": {k: roles[k] for k in ROLES3},
        "birth": {role: {"threshold": units[roles[role]]["dynamics"]["threshold"],
                         "intrinsic_drive": units[roles[role]]["dynamics"]["intrinsic_drive_per_second"],
                         "margin_g": margin[role]} for role in ROLES3},
        "S1": {"silent_source": silent, "violations": sorted(r for r in SOURCES if silent[r] and roles[r] in fired)},
        "k_star": ks,
        "zero_label": zero,
        "e_zero": same,
        "delta_e": valued(delta),
        "class": main["class"],
        "levels": per,
        "quantities": {k: valued(q[k]) for k in OTHERS},
        "base_class": {c: base_kind(s.get(f"G_{c}_base")) for c in ACTIONS},
        "built": built,
        "not_built": {n: run["endpoints"][n]["out_of_range"] for n in endpoint_list(levels) if n not in run["clones"]},
        "counts_E": counts_e,
        "counts_U": counts_u,
        "s_U": {n: frac(s[n]) for n in systems},
        "s_E": {n: frac(a1_share(counts_e[n])) for n in BODIES},
        "W": {"A1": {r: w["A1"][cid_of[r]] for r in ROLES6}, "A2": {r: w["A2"][cid_of[r]] for r in ROLES6}},
        "W_abs_diff": {r: float(abs(wa1[r] - wa2[r])) for r in ROLES6},
        "pair_deviation": {c: float(max_pair_gap(w[c])) for c in ACTIONS},
        "clone_pair_deviation": float(max(max_pair_gap(conn_weights(run["boundary"]["sigma_a"][n])) for n in built)),
        "consequences": consequences,
        "first_divergence": split,
        "firing": firing,
    }


# ---- 判定・推定・記述・補助の記録（README §4〜§6） ------------------------------------------------------

def upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, i) for i in range(k, m + 1)), 2 ** m)


def k2(m: int, alpha: Fraction) -> int:
    k = 0
    while k <= m and upper_tail(m, k) > alpha:
        k += 1
    return k


def exact_interval(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
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
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "denominator = 0"}
    return {"computed": True, "interval": list(exact_interval(x, n)), "numerator": x, "denominator": n}


def share_of(x: int, n: int) -> dict:
    return {"count": x, "denominator": n, "proportion": x / n if n else None, "interval": interval_of(x, n)}


def at(p: dict, k) -> dict:
    return p["levels"][str(k)]


def spread(cs: list[dict]) -> dict:
    c = Counter(x["class"] for x in cs)
    n = len(cs) - c["undefined"]
    nz = c["plus"] + c["minus"]
    return {"m_def": n, "m_nonzero": nz, "p_nz": share_of(nz, n),
            "p_any": share_of(sum(1 for x in cs if x["class"] != "undefined" and x["any"] is True), n),
            "p_plus": share_of(c["plus"], n), "p_minus": share_of(c["minus"], n), "p_dir": share_of(c["plus"], nz),
            "cancellations": c["cancellation"], "classes": {k: c[k] for k in PEOPLE_CLASSES}}


def judgment(people: list[dict]) -> dict:
    by_class = Counter(at(p, K0)["C"]["class"] for p in people)
    plus, minus = by_class["plus"], by_class["minus"]
    m = plus + minus
    m_def = len(people) - by_class["undefined"]
    j = {"level": K0, "m_nonzero": m, "m_def": m_def,
         "counts": {"+": plus, "-": minus, "0": m_def - m, "undefined": by_class["undefined"]}}
    if m < PREREGISTERED["min_population"]:
        j |= {"status": "inconclusive", "direction": None, "k2": None, "tail_probability": None}
        outcome = "inconclusive"
    else:
        k = k2(m, PREREGISTERED["alpha_per_direction"])
        direction = "+" if plus >= k else "-" if minus >= k else None
        j |= {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
              "tail_probability": float(upper_tail(m, k))}
        outcome = {"+": "plus", "-": "minus", None: "not_established"}[direction]
    return {"J_C": j, "outcome": outcome, "prominence": NOTES["prominence"], "artificial": NOTES["artificial"]}


def estimate(people: list[dict]) -> dict:
    cs = [at(p, K0)["C"] for p in people]
    out = spread(cs)
    sizes = [abs(x["value"]["value"]["value"]) for x in cs if x["class"] != "undefined"]
    und = [p for p in people if at(p, K0)["C"]["class"] == "undefined"]
    reasons = Counter()
    for p in und:
        for c in ACTIONS:
            cl = at(p, K0)["C"][c]["class"]
            if cl not in DEFINED:
                reasons[f"{c}:{cl}"] += 1
    out |= {"level": K0, "abs_C2": {"defined": five(sizes), "nonzero": five([x for x in sizes if x != 0])},
            "undefined": {"count": len(und),
                          "by_reason_and_background": {f"{c}:{r}": reasons[f"{c}:{r}"] for c in ACTIONS
                                                       for r in ("out_of_range", "s_undefined")}},
            "notes": {k: NOTES[k] for k in ("estimate", "p_nz", "p_any", "prominence", "artificial")}}
    return out


def table_of(vs: list[dict]) -> dict:
    defined = [x for x in vs if x["sign"] is not None]
    n = len(defined)
    c = Counter(x["sign"] for x in defined)
    counts = {s: c[s] for s in SIGNS}
    values = [x["value"]["value"] for x in defined]
    return {"defined": n, "undefined": len(vs) - n, "counts": counts,
            "proportion": {s: share_of(counts[s], n) for s in ("+", "-")},
            "plus_among_nonzero": share_of(counts["+"], counts["+"] + counts["-"]),
            "distribution": five(values), "abs_distribution": five([abs(v) for v in values])}


def nine(pairs: list[tuple]) -> dict:
    cells = {a + b: 0 for a in SIGNS for b in SIGNS}
    for a, b in pairs:
        cells[a + b] += 1
    return cells


def nested(built: set, levels: list) -> bool:
    for c in ACTIONS:
        for head in ("P", "M", "UP", "UM"):
            have = [f"G_{c}_{head}{k}" in built for k in levels]
            for i in range(1, len(have)):
                if have[i] and not have[i - 1]:
                    return False
    return True


def describe(people: dict) -> dict:
    group = list(people.values())
    levels = sorted(int(k) for k in group[0]["levels"]) if group else []
    out: dict = {"notes": {k: NOTES[k] for k in ("levels", "comparison", "artificial")}}
    out["levels"] = {str(k): spread([at(p, k)["C"] for p in group]) | {"C": table_of([at(p, k)["C"]["value"] for p in group])}
                     for k in levels}
    common = sorted(s for s, p in people.items() if all(at(p, k)["C"]["class"] != "undefined" for k in levels))
    out["common_all_levels"] = {"seeds": common, "count": len(common),
                                "by_level": {str(k): spread([at(people[s], k)["C"] for s in common]) for k in levels}}
    systems = {}
    for k in levels:
        for c in ACTIONS:
            for kind, heads in (("natural", ("P", "M")), ("symmetric", ("UP", "UM"))):
                for side, head in zip(("plus", "minus"), heads):
                    systems[f"{k}|{c}|{kind}|{side}"] = sum(1 for p in group if f"G_{c}_{head}{k}" in p["not_built"])
    names = Counter()
    for p in group:
        for n, rows in p["not_built"].items():
            _c, kind, _k, sd = split_name(n)
            for r, where in rows:
                names[f"{kind}|{'plus' if sd == 1 else 'minus'}|{r}|{where}"] += 1
    out["out_of_range"] = {"systems": systems, "by_weight_name": {k: names[k] for k in sorted(names)},
                           "nesting_holds": all(nested(set(p["built"]), levels) for p in group)}
    out["per_background"] = {}
    for k in levels:
        row = {c: table_of([at(p, k)["C"][c]["value"] for p in group]) for c in ACTIONS}
        sg = [(at(p, k)["C"]["A1"]["value"]["sign"], at(p, k)["C"]["A2"]["value"]["sign"]) for p in group]
        full = [(a, b) for a, b in sg if a is not None and b is not None]
        row["cells_A1_A2"] = nine(full)
        row["in_both"] = len(full)
        row["only_one_background"] = {
            "A1": table_of([at(p, k)["C"]["A1"]["value"] for p, (a, b) in zip(group, sg) if a is not None and b is None]),
            "A2": table_of([at(p, k)["C"]["A2"]["value"] for p, (a, b) in zip(group, sg) if b is not None and a is None])}
        out["per_background"][str(k)] = row
    out["one_sided"] = {}
    for k in levels:
        out["one_sided"][str(k)] = {}
        for c in ACTIONS:
            rows = [(at(p, k)["up"][c]["sign"], at(p, k)["dn"][c]["sign"]) for p in group]
            rows = [(a, b) for a, b in rows if a is not None and b is not None]
            out["one_sided"][str(k)][c] = {"in_both": len(rows), "cells_up_dn": nine(rows)}
    if K0 in levels:
        strata = {}
        for c in ACTIONS:
            strata[c] = {}
            for bc in ("0", "1", "between", "undefined"):
                inside = [p for p in group if p["base_class"][c] == bc]
                cnt = Counter(at(p, K0)["C"][c]["value"]["sign"] for p in inside)
                strata[c][bc] = {"+": cnt["+"], "-": cnt["-"], "0": cnt["0"], "C_undefined": cnt[None]}
        out["base_strata"] = strata
    sym = {}
    for k in levels:
        dus = [at(p, k)["Du"] for p in group]
        ok = [(s, p) for s, p in people.items() if at(p, k)["eligible"]["individual"]]

        def cmp_cells(rows_people, which=None):
            res = {}
            for nm, want in (("delta_plus", "+"), ("delta_minus", "-")):
                chosen = [p for p in rows_people if p["delta_e"]["sign"] == want]
                if which is None:
                    pairs = [(at(p, k)["C"]["value"]["sign"], at(p, k)["Du"]["value"]["sign"]) for p in chosen]
                else:
                    pairs = [(at(p, k)["C"][which]["value"]["sign"], at(p, k)["Du"][which]["value"]["sign"]) for p in chosen]
                res[nm] = {"count": len(chosen), "cells_C_Du": nine(pairs)}
            return res
        inel = {}
        for c in ACTIONS:
            inel[c] = {r: sum(1 for p in group if r in at(p, k)["ineligible_reasons"][c]) for r in REASONS}
            inel[c]["ineligible"] = sum(1 for p in group if not at(p, k)["eligible"][c])
        split = {"undefined": 0, "neither_structural": 0, "one_structural": {c: dict.fromkeys(DU_LABELS, 0) for c in ACTIONS},
                 "both_structural": dict.fromkeys(DU_LABELS, 0)}
        for d in dus:
            zero_in = [c for c in ACTIONS if d[c]["class"] == "structural_zero"]
            if d["value"]["sign"] is None:
                split["undefined"] += 1
            elif len(zero_in) == 2:
                split["both_structural"][d["A2"]["label"]] += 1
            elif len(zero_in) == 1:
                split["one_structural"][zero_in[0]][d[zero_in[0]]["label"]] += 1
            else:
                split["neither_structural"] += 1
        sym[str(k)] = {
            "Du": table_of([d["value"] for d in dus if d["value"]["sign"] is not None and not d["structural"]]),
            "Du_defined_with_structural_zero": sum(1 for d in dus if d["value"]["sign"] is not None and d["structural"]),
            "Du_partition": split,
            "Du_structural_labels": {lab: sum(1 for d in dus for c in ACTIONS if d[c]["label"] == lab) for lab in DU_LABELS},
            "eligible_individuals": len(ok),
            "comparison": cmp_cells([p for _s, p in ok]),
            "comparison_per_background": {c: cmp_cells([p for p in group if at(p, k)["eligible"][c]], c) for c in ACTIONS},
            "ineligible": inel}
    every = sorted(s for s, p in people.items() if all(at(p, k)["eligible"]["individual"] for k in levels))
    sym["all_levels_eligible"] = {
        "seeds": every, "count": len(every),
        "by_level": {str(k): {nm: nine([(at(people[s], k)["C"]["value"]["sign"], at(people[s], k)["Du"]["value"]["sign"])
                                        for s in every if people[s]["delta_e"]["sign"] == want])
                              for nm, want in (("delta_plus", "+"), ("delta_minus", "-"))} for k in levels}}
    out["symmetric_control"] = sym
    tq = {k: table_of([p["quantities"][k] for p in group]) for k in OTHERS}
    tt = [(p["quantities"]["T_A1"]["sign"], p["quantities"]["T_A2"]["sign"]) for p in group]
    out["T"] = {"T": tq["T"], "T_A1": tq["T_A1"], "T_A2": tq["T_A2"],
                "cells_A1_A2": nine([(a, b) for a, b in tt if a is not None and b is not None]), "note": NOTES["T"]}
    out["sensitivity"] = {"S": tq["S"], "S_A1": tq["S_A1"], "S_A2": tq["S_A2"], "note": NOTES["S"]}
    out["natural_pair"] = {"D": tq["D"]}
    out["plasticity_contrast"] = {"Z_A1": tq["Z_A1"], "Z_A2": tq["Z_A2"]}
    out["delta_e"] = table_of([p["delta_e"] for p in group]) | {
        "delta_zero_with_e_nonzero": sum(1 for p in group if p["delta_e"]["sign"] == "0" and not p["e_zero"])}
    withdrawn = any(p["S1"]["violations"] for p in group)
    main = {s: at(p, K0)["C"] for s, p in people.items()} if K0 in levels else {}
    out["zero_table"] = {
        "structural_zero": {lab: sorted(s for s, c in main.items() if c["class"] == "structural_zero" and c["A1"]["label"] == lab)
                            for lab in C_LABELS},
        "both_zero": sorted(s for s, c in main.items() if c["class"] == "both_zero"),
        "cancellation": sorted(s for s, c in main.items() if c["class"] == "cancellation"),
        "undefined": {s: {**{bg: c[bg]["class"] for bg in ACTIONS if c[bg]["class"] not in DEFINED},
                          "not_built": sorted(n for n in people[s]["not_built"]
                                              if split_name(n)[1] == "natural" and split_name(n)[2] == K0)}
                      for s, c in sorted(main.items()) if c["class"] == "undefined"},
        "structurally_silent_source": None if withdrawn else
        sorted(s for s, p in people.items() if any(p["S1"]["silent_source"].values())),
    }
    out["not_made"] = NOTES["not_made"]
    return out


def auxiliary(people: dict, e_s: float | None) -> dict:
    vals = list(people.values())
    levels = sorted(int(k) for k in vals[0]["levels"]) if vals else []
    violations = sum(len(p["S1"]["violations"]) for p in vals)
    cls = Counter(p["class"] for p in vals)
    every = sorted({n for p in vals for n in p["s_U"]}, key=lambda n: (n not in BODIES + [RERUN], n))
    out: dict = {"R1": {
        "individuals": len(vals),
        "classes_at_k0": {c: cls[c] for c in PEOPLE_CLASSES},
        "zero_labels": {z: sum(1 for p in vals if p["zero_label"] == z) for z in ("Z-1", "Z-2")},
        "k_star": five([p["k_star"] for p in vals if p["k_star"] is not None]),
        "e_zero": sum(1 for p in vals if p["e_zero"]),
        "S1": {"E_S": e_s, "violations": violations, "labels_withdrawn": violations > 0,
               "individuals_with_silent_source": None if violations else
               sum(1 for p in vals if any(p["S1"]["silent_source"].values()))}}}
    out["R2"] = {}
    for n in every:
        having = [p for p in vals if n in p["s_U"]]
        out["R2"][n] = {part: {k: five([p[f"counts_{part}"][n][k] for p in having]) for k in ("decided", "A1", "A2", "tie", "none")}
                        for part in ("E", "U")}
        out["R2"][n]["s_U"] = five([p["s_U"][n]["value"] for p in having if p["s_U"][n] is not None])
        out["R2"][n]["built"] = len(having)
    out["R3"] = {}
    for k in levels:
        for kind in ("C", "Du"):
            xs = [at(p, k)[kind]["value"]["value"]["value"] for p in vals if at(p, k)[kind]["value"]["value"] is not None]
            out["R3"][f"{kind}{k}"] = {"value": five(xs), "abs_value": five([abs(x) for x in xs])}
    for k in OTHERS:
        xs = [p["quantities"][k]["value"]["value"] for p in vals if p["quantities"][k]["value"] is not None]
        out["R3"][k] = {"value": five(xs), "abs_value": five([abs(x) for x in xs])}
    xs = [p["delta_e"]["value"]["value"] for p in vals]
    out["R3"]["delta_e"] = {"value": five(xs), "abs_value": five([abs(x) for x in xs])}
    out["R4"] = {"W_A1": {r: five([p["W"]["A1"][r] for p in vals]) for r in ROLES6},
                 "W_A2": {r: five([p["W"]["A2"][r] for p in vals]) for r in ROLES6},
                 "abs_W_diff": {r: five([p["W_abs_diff"][r] for p in vals]) for r in ROLES6},
                 "pair_sum_max_abs_deviation": max([x for p in vals for x in p["pair_deviation"].values()], default=None),
                 "clones_after_transplant": {"weights": NOTES["R4"],
                                             "pair_sum_max_abs_deviation": max([p["clone_pair_deviation"] for p in vals],
                                                                               default=None)},
                 "not_built": {"systems": sum(len(p["not_built"]) for p in vals),
                               "individuals_with_any": sum(1 for p in vals if p["not_built"])}}
    out["R5"] = {}
    for n in sorted({n for p in vals for n in p["consequences"]}):
        rows = [p["consequences"][n] for p in vals if n in p["consequences"]]
        out["R5"][n] = {"E": five([r["E"] for r in rows]), "U": five([r["U"] for r in rows]),
                        "as_expected": all(r["E"] == r["decided_windows_of_c"]["E"] and r["U"] == r["decided_windows_of_c"]["U"]
                                           for r in rows)}
    out["R6"] = {}
    for key in sorted({k for p in vals for k in p["first_divergence"]}):
        rows = [p["first_divergence"][key] for p in vals if key in p["first_divergence"]]
        f = [r["firing"] for r in rows]
        w = [r["window"] for r in rows]
        out["R6"][key] = {"pairs": len(rows),
                          "firing": {"none": f.count(None), "pulses": five([x for x in f if x is not None])},
                          "window": {"none": w.count(None), "windows": five([x for x in w if x is not None])}}
    out["R7"] = {n: {part: {r: five([p["firing"][n][part][r] for p in vals if n in p["firing"]]) for r in ROLES3}
                     for part in (("E", "U") if n in BODIES + [RERUN] else ("U",))} for n in every}
    out["R8"] = NOTES["R8"]
    out["R9"] = {n: {"s_E": five([p["s_E"][n]["value"] for p in vals if p["s_E"][n] is not None]),
                     "s_U": five([p["s_U"][n]["value"] for p in vals if p["s_U"][n] is not None]),
                     "note": NOTES["R9"]} for n in BODIES}
    return out


def expected_report(runs: dict, measurement_commit: str | None = None) -> dict:
    """保存した生の記録だけから、有効な report の全体を組み立て直す。"""
    seeds = sorted(runs)
    people = {str(s): individual(runs[s]) for s in seeds}
    ordered = list(people.values())
    modes = {runs[s]["meta"]["mode"] for s in seeds}
    e_s = bound_e_s(runs[seeds[0]]["meta"]["manifest"], runs[seeds[0]]["run"]["plan"]) if seeds else None
    j = judgment(ordered)
    out = {"mode": modes.pop() if len(modes) == 1 else None, "valid": True, "outcome": j["outcome"],
           "O1": {"status": "ok", "problems": []}, "gate_declaration_sha256": GATE_SHA256,
           "judgment": j, "estimate": estimate(ordered), "descriptive": describe(people),
           "individuals": people, "auxiliary": auxiliary(people, e_s)}
    if measurement_commit is not None:
        out["measurement_commit"] = measurement_commit
    return out


# ---- 期待値と report の照合（すべての欄。0042 と同じ） ---------------------------------------------------------

def _loose(where: str) -> bool:
    return where.endswith((".interval[0]", ".interval[1]")) or where == "report.auxiliary.R1.S1.E_S"


def compare(mine, theirs, where: str = "report") -> tuple[int, list[str]]:
    """期待値 mine と report の theirs を、欄の組・列の長さ・葉の型と値まで比べる。食い違いの文には場所だけを書き、値は書かない。"""
    checks, found = 0, []
    stack = [(mine, theirs, where)]
    while stack:
        a, b, at_ = stack.pop()
        if isinstance(a, dict):
            if not isinstance(b, dict):
                checks, found = checks + 1, found + [f"{at_}: 欄の形"]
                continue
            if set(a) != set(b):
                checks, found = checks + 1, found + [f"{at_}: 欄の組"]
            stack += [(a[k], b[k], f"{at_}.{k}") for k in sorted(set(a) & set(b), reverse=True)]
        elif isinstance(a, (list, tuple)):
            if not isinstance(b, list) or len(a) != len(b):
                checks, found = checks + 1, found + [f"{at_}: 列の形・長さ"]
                continue
            stack += [(x, y, f"{at_}[{i}]") for i, (x, y) in reversed(list(enumerate(zip(a, b))))]
        else:
            checks += 1
            if a is None or isinstance(a, (bool, str)):
                ok = type(a) is type(b) and a == b
            elif isinstance(a, (int, float)):
                ok = isinstance(b, (int, float)) and not isinstance(b, bool) and (
                    abs(a - b) <= LOOSE if _loose(at_) else a == b)
            else:
                ok = False
            if not ok:
                found.append(at_)
    return checks, found


# ---- 操作の確認の主なもの（O3〜O14。別の書き方で） -----------------------------------------------------------

def _without(sigma: dict, paths: list[tuple]) -> str:
    s = json.loads(json.dumps(sigma))
    for path in paths:
        node = s
        for key in path[:-1]:
            node = node[key]
        node.pop(path[-1], None)
    return json.dumps(s, sort_keys=True, separators=(",", ":"))


def _sha(sigma: dict) -> str:
    return hashlib.sha256(json.dumps(sigma, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _with_weights(sigma: dict, weights: dict) -> str:
    s = copy.deepcopy(sigma)
    for cid, w in weights.items():
        s["connections"][cid]["weight"] = w
    return json.dumps(s, sort_keys=True, separators=(",", ":"))


def operation_problems(data: dict) -> list[str]:
    run = data["run"]
    plan, roles = run["plan"], run["roles"]
    levels = list(run["levels"])
    geo = geometry(plan)
    e, p_e, end, windows, L = geo["e"], geo["p_e"], geo["end"], geo["windows"], plan["delay"]
    order, cue_r = run["connection_order"], roles["cue_receptor"]
    action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    rec, b = records_of(run), run["boundary"]
    w = b["W"]
    built = built_list(run)
    systems = BODIES + [RERUN] + built
    rule = {"B_A1": "A1", "B_A2": "A2", RERUN: "A1"} | {n: n[2:4] for n in built}
    problems = []

    def target(n: str) -> dict:
        c, kind, _k, _s = split_name(n)
        if kind in ("natural", "symmetric"):
            return run["endpoints"][n]["weights"]
        if kind in ("X1", "X2"):
            return run["X"][kind]
        return w[c]

    def f1_ok(ws: dict) -> bool:
        return sorted(ws) == sorted(order) and all(W_MIN <= x <= W_MAX for x in ws.values()) \
            and max_pair_gap(ws) <= Fraction(PREREGISTERED["f1_tolerance"])
    for n in systems:
        r = rec[n]
        la, lb = r["layer_a"], r["layer_b"]
        if [x["window"] for x in la] != [k for k, _a, _b in windows]:
            problems.append(f"O3 {n}: 窓の番号")
        for x, (k, a, bb) in zip(la, windows):
            d = x["decision_pulse"]
            if x["outcome"] in ACTIONS:
                ok = (a <= d <= bb and x["action"] == x["outcome"] == action_of.get(x["winner_unit"])
                      and x["emit_pulse"] == d + 1 and x["emitted"] is True)
            elif x["outcome"] == "tie":
                ok = a <= d <= bb and x["winner_unit"] is None and x["action"] is None and x["emit_pulse"] is None \
                    and x["emitted"] is False
            else:
                ok = x["outcome"] == "none" and d is None and x["winner_unit"] is None and x["action"] is None \
                    and x["emit_pulse"] is None and x["emitted"] is False
            if not ok or (x["open"], x["close"]) != (a, bb):
                problems.append(f"O14 {n}: 窓 {k}")
        by_window = {x["window"]: x["outcome"] for x in la if x["outcome"] in ACTIONS}
        from_b = {}
        for p, _did, _src, act in lb:
            k = next((k for k, a, bb in windows if a <= p - 1 <= bb), None)
            from_b[k] = from_b.get(k, []) + [act]
        if {k: [v] for k, v in by_window.items()} != from_b:
            problems.append(f"O14 {n}: 層 A と層 B の行動 ID")
        if Counter((x["emit_pulse"], x["winner_unit"], x["action"]) for x in la if x["emitted"]) \
                != Counter((p, src, act) for p, _did, src, act in lb):
            problems.append(f"O3 {n}: 層 A と層 B")
        if len({did for _p, did, _s, _a in lb}) != len(lb):
            problems.append(f"O3 {n}: 識別子の重複")
        if any(x["winner_unit"] is not None and not x["emitted"] for x in la):
            problems.append(f"O3 {n}: 未発行の予定")
        if sorted(r["delta_log"]) != sorted(x for x in lb if n not in run["clones"] or x[0] > p_e):
            problems.append(f"O3 {n}: 来歴のログ")
        world = r["world_end"]
        live = [x for x in lb if x[3] == rule[n]]
        cons = sorted((row[3], row[4]) for row in world["reserved"] if row[1] == "consequence")
        if cons != sorted((p + L - 1, did) for p, did, _s, _a in live):
            problems.append(f"O5 {n}: 結果の予約")
        if len(cons) != sum(1 for x in la if x["outcome"] == rule[n]):
            problems.append(f"O5 {n}: 結果の刺激の数")
        if any(rc != cue_r for _p, rc in r["sensory"]) or any(row[1] not in ("cue", "consequence") or row[2] != cue_r
                                                              for row in world["reserved"]) or world["pending"]:
            problems.append(f"O5 {n}: 感覚の出来事・予約")
        if world["rule"]["rule_c"] != rule[n] or world["rule"]["respond"] is not True or world["rule"]["delay"] != L:
            problems.append(f"O5 {n}: 世界の規則")
        if r["world_switches"] != []:
            problems.append(f"O5 {n}: 世界の切り替え")
        if _sha(r["sigma_end"]) != r["sigma_end_sha256"] or r["pulse_end"] != end:
            problems.append(f"O14 {n}: 終わりの Σ")
    # O4：R-7 の対（0042 と同じ）
    a1, a2 = rec["B_A1"], rec["B_A2"]
    rc = [("world", "rule", "rule_c")]
    if _without(a1["sigma_0"], rc) != _without(a2["sigma_0"], rc):
        problems.append("O4: Pulse 0")
    decided = [x for x in a1["layer_a"] if x["window"] <= e and x["outcome"] in ACTIONS]
    if not decided:
        if any([x for x in a1[k] if x[0] <= p_e] != [x for x in a2[k] if x[0] <= p_e] for k in ("activity", "sensory")) \
                or _without(b["sigma_p_e"]["B_A1"], rc) != _without(b["sigma_p_e"]["B_A2"], rc) \
                or w["A1"] != w["A2"] or a1["first_intent"] is not None or a2["first_intent"] is not None:
            problems.append("O4: k* がない個体")
    else:
        k, t = decided[0]["window"], decided[0]["decision_pulse"] + 1
        fa, fb = a1["first_intent"], a2["first_intent"]
        brain = rc + [("world", "pending"), ("world", "reserved"), ("world", "next_rid")]
        if a1["layer_a"][:k] != a2["layer_a"][:k] or fa is None or fb is None or fa["pulse"] != t or fb["pulse"] != t \
                or _without(fa["sigma"], brain) != _without(fb["sigma"], brain):
            problems.append("O4: k* の意図の Pulse")
    # O12：P_E の Σ と、残る予約の全件
    for n in BODIES:
        sp = b["sigma_p_e"][n]
        ex = sp["exit"]
        if sp["pulse"] != p_e or ex["pending"] is not None or ex["cursor"] != e or ex["reports"] \
                or any(row[1] != "cue" for row in sp["world"]["pending"]):
            problems.append(f"O12 {n}")
        if conn_weights(sp) != w[rule[n]] or b["sigma_p_e_sha256"][n] != _sha(sp) \
                or sp["interventions"] != {"active": [], "frozen": {}} or rec[n]["history"] != []:
            problems.append(f"O12 {n}: W・Σ")
        future = sorted(json.dumps(["cue", cue_r, c, None]) for c in geo["cues"] if c > p_e)
        left = sorted(json.dumps(row[1:]) for row in sp["world"]["pending"])
        ids = [row[0] for row in sp["world"]["pending"]]
        all_cues = sorted(json.dumps(row[1:]) for row in sp["world"]["reserved"] if row[1] == "cue")
        if left != future or len(set(ids)) != len(ids) or any(row not in sp["world"]["reserved"] for row in sp["world"]["pending"]) \
                or all_cues != sorted(json.dumps(["cue", cue_r, c, None]) for c in geo["cues"]):
            problems.append(f"O12 {n}: 残る予約")
    # O10：重みの算術を、P_E の Σ から有理数で書き直して照らす
    sp1, sp2 = conn_weights(b["sigma_p_e"]["B_A1"]), conn_weights(b["sigma_p_e"]["B_A2"])
    arith = rational_endpoints(roles, sp1, sp2, levels)
    if run["difference"] != {"e": {r: fstr(arith["e"][r]) for r in ROLES6}, "delta_e": fstr(arith["delta_e"]),
                             "m": {str(k): fstr(arith["m"][k]) for k in levels}}:
        problems.append("O10: e・δ(e)・m_k")
    for n, (_v, inside, outside, rounded) in arith["endpoints"].items():
        got = run["endpoints"][n]
        if got != {"in_range": inside, "out_of_range": outside, "weights": rounded}:
            problems.append(f"O10 {n}: 端の記録")
        if inside != (n in run["clones"]):
            problems.append(f"O10 {n}: 作った系の組")
        elif inside and conn_weights(b["sigma_a"][n]) != rounded:
            problems.append(f"O10 {n}: 移植の値")
    if 1 in levels and (run["endpoints"]["G_A1_M1"]["weights"] != w["A2"] or run["endpoints"]["G_A2_P1"]["weights"] != w["A1"]):
        problems.append("O10: k = 1 の自然な側")
    # O6：境界の順序と差の目録
    six = sorted(order)
    want = [["S0", n, p_e, "advance_to", {"from": 0}] for n in BODIES]
    want += [["S1", n, p_e, "read_weights_and_sigma", None] for n in BODIES]
    want += [["S2", n, p_e, "clone", {"from": "B_" + n[2:4]}] for n in built]
    for n in built:
        c, kind, _k, _s = split_name(n)
        if kind == "base":
            continue
        to = "W_" + c if kind == "tr" else kind if kind in ("X1", "X2") else n
        want.append(["S3", n, p_e, "transplant", {"to": to, "intervention_state_at_transplant": {"active": [], "frozen": {}}}])
    want += [["S4", n, p_e, "declare", {"FREEZE": six, "trace_policy": "advance"}] for n in built]
    want += [["S5", n, end, "advance_to", {"from": p_e}] for n in BODIES + built]
    if b["steps"] != want:
        problems.append("O6: S0〜S5")
    freeze = [["FREEZE", six, "advance"]]
    for n in built:
        sa, sb = b["sigma_a"][n], b["sigma_b"][n]
        home = b["sigma_a"]["G_" + n[2:4] + "_base"]
        if sa["pulse"] != p_e or sb["pulse"] != p_e or sa["interventions"] != {"active": [], "frozen": {}}:
            problems.append(f"O6 {n}: (a) の Pulse・介入")
        if conn_weights(sa) != target(n):
            problems.append(f"O6 {n}: (a) の重み")
        if _with_weights(sa, conn_weights(home)) != _with_weights(home, conn_weights(home)):
            problems.append(f"O6 {n}: (a) の差の目録")
        if _with_weights(home, {}) != _with_weights(b["sigma_p_e"]["B_" + n[2:4]], {}):
            problems.append(f"O6 {n}: (a) の複製の元")
        frozen = {cid: {"weight": v["weight"], "pre_trace": v["pre_trace"], "post_trace": v["post_trace"], "policy": "advance"}
                  for cid, v in sb["connections"].items()}
        if sb["interventions"] != {"active": freeze, "frozen": frozen} \
                or _without(sa, [("interventions",)]) != _without(sb, [("interventions",)]):
            problems.append(f"O6 {n}: (b)")
        if rec[n]["history"] != [[p_e, "S4", freeze]]:
            problems.append(f"O6 {n}: 介入の履歴")
        tw = [target(n)[cid] for cid in order]
        rows = rec[n]["pulse_weights"]
        if [p for p, _x in rows] != list(range(p_e + 1, end + 1)) or any(x != tw for _p, x in rows):
            problems.append(f"O7 {n}")
        src = rec["B_" + n[2:4]]
        if rec[n]["layer_a"][:e] != src["layer_a"][:e] or [x for x in rec[n]["layer_b"] if x[0] <= p_e] \
                != [x for x in src["layer_b"] if x[0] <= p_e]:
            problems.append(f"O5 {n}: E")
    # O8：同じ背景で重みがビット単位で同じ系は U で同じ
    keys = ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end")
    groups: dict[str, list] = {}
    for n in built:
        groups.setdefault(n[2:4] + json.dumps([target(n)[cid] for cid in order]), []).append(n)
    for g in groups.values():
        for y in g[1:]:
            if any(rec[g[0]][k] != rec[y][k] for k in keys):
                problems.append(f"O8: {g[0]}・{y}")
    for c in ACTIONS:
        if not any(f"G_{c}_base" in g and f"G_{c}_tr" in g for g in groups.values()):
            problems.append(f"O8: G_{c}_tr")
    # O9：Pulse P_E ＋ 1 の一致（同じ背景の基の系と各複製の系）
    for y in built:
        x = "G_" + y[2:4] + "_base"
        if y == x:
            continue
        fx, fy = rec[x]["sigma_after_first"], rec[y]["sigma_after_first"]
        same_first = Counter(u for p, u in rec[x]["activity"] if p == p_e + 1) == \
            Counter(u for p, u in rec[y]["activity"] if p == p_e + 1)
        split = first_split(rec[x]["activity"], rec[y]["activity"], p_e + 1, end)
        if fx["pulse"] != p_e + 1 or fy["pulse"] != p_e + 1 or fx["units"] != fy["units"] or fx["exit"] != fy["exit"] \
                or not same_first or (split is not None and split < p_e + 2) \
                or [d[:2] + d[3:] for d in fx["drives"]] != [d[:2] + d[3:] for d in fy["drives"]]:
            problems.append(f"O9: {x}・{y}")
    # O11：範囲と F1（W と、作った複製の系）。端の値。入れ子
    cid_of = role_cids(roles)
    if run["X"] != {k: {cid_of[r]: v for r, v in PREREGISTERED["extremes"][k].items()} for k in ("X1", "X2")}:
        problems.append("O11: X1・X2")
    if not all(f1_ok(w[c]) for c in ACTIONS) or not all(f1_ok(conn_weights(b["sigma_a"][n])) for n in built):
        problems.append("O11: 範囲・F1")
    if not nested(set(run["clones"]), levels):
        problems.append("O11: 入れ子")
    # O13：B′^{A1} と B^{A1} の完全な一致
    ra, rr = rec["B_A1"], rec[RERUN]
    if any(ra[k] != rr[k] for k in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "history")) \
            or rr["sigma_p_e"] != b["sigma_p_e"]["B_A1"] or rr["sigma_end"] != ra["sigma_end"] \
            or _sha(rr["sigma_p_e"]) != rr["sigma_p_e_sha256"]:
        problems.append("O13")
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
    text = json.dumps(proto, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def protocol_problems(runs: dict, protocol_file: Path = PROTOCOL_FILE) -> list[str]:
    problems = []
    file_sha = hashlib.sha256(protocol_file.read_bytes()).hexdigest()
    if file_sha != PROTOCOL_FILE_SHA256:
        problems.append("照らす protocol.yaml が、事前登録 v0.2 の protocol.yaml と違う")
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
            problems.append(f"seed {s}: meta の protocol の写しの中身が、事前登録 v0.2 の protocol と違う")
        if sha != file_sha:
            problems.append(f"seed {s}: meta の protocol の SHA-256 が、確定済みの protocol.yaml と違う")
        if meta.get("mode") == "formal" and (runs[s].get("run", {}).get("plan") != PREREGISTERED["formal_plan"]
                                             or runs[s].get("run", {}).get("levels") != PREREGISTERED["levels"]):
            problems.append(f"seed {s}: 本番の Plan・段の組が事前登録の値と違う")
    if len(copies) > 1 or len(shas) > 1:
        problems.append("個体によって meta の protocol の写しが違う")
    if len(copies) == 1:
        problems += [f"protocol の写し：{p}" for p in _preregistered_values(json.loads(next(iter(copies))))]
    return problems


def _preregistered_values(proto: dict) -> list[str]:
    out = []
    pr = PREREGISTERED
    try:
        jc, tl, br, j, wt = proto["judgment"]["J_C"], proto["timeline"], proto["brain"], proto["judgment"], proto["weights"]
        if (proto["experiment"], proto["kind"]) != (pr["experiment"], pr["kind"]):
            out.append("experiment・kind")
        if jc["min_population"] != pr["min_population"] or j["outcomes"] != pr["outcomes"] or jc["level"] != pr["k0"]:
            out.append("J_C.min_population・outcomes・level")
        if _number(jc["alpha"]["per_direction"]) != pr["alpha_per_direction"] \
                or _number(jc["alpha"]["two_sided"]) != pr["alpha_two_sided"]:
            out.append("J_C.alpha")
        table = {int(m): k for m, k in j["k2_of_m"].items()}
        if sorted(table) != list(range(pr["min_population"], pr["individuals"] + 1)) \
                or any(table[m] != k2(m, pr["alpha_per_direction"]) for m in table) or table.get(200) != pr["k2_200"]:
            out.append("k2_of_m")
        if (tl["experience_E"]["windows"], tl["experience_E"]["pulses"], tl["boundary_P_E"], tl["test_U"]["windows"],
                tl["test_U"]["pulses"], tl["body_pulses"]) != (pr["experience_windows"], pr["experience_pulses"],
                                                              pr["boundary_P_E"], pr["test_windows"], pr["test_pulses"],
                                                              pr["body_pulses"]):
            out.append("timeline")
        if (_number(br["w_min"]), _number(br["w_max"]), _number(br["initial_weight_w0"])) != \
                (_number(pr["w_min"]), _number(pr["w_max"]), _number(pr["w0"])):
            out.append("brain.weights")
        if {k: proto["world"]["rule_c"][k] for k in pr["rule_c"]} != pr["rule_c"]:
            out.append("world.rule_c")
        if (wt["scheme"], wt["levels"], wt["k0"], wt["u"]) != (pr["scheme"], pr["levels"], pr["k0"], U_SIGN):
            out.append("weights")
        if {k: {r: _number(v) for r, v in proto["extremes"][k].items()} for k in ("X1", "X2")} != \
                {k: {r: _number(v) for r, v in pr["extremes"][k].items()} for k in ("X1", "X2")}:
            out.append("extremes")
        if _number(proto["f1_tolerance"]) != _number(pr["f1_tolerance"]):
            out.append("f1_tolerance")
        for key in ("seeds", "smoke_seeds", "synthetic_seeds"):
            if proto[key] != pr[key]:
                out.append(key)
        if (proto["inherited_gate_set"]["declaration"], proto["inherited_gate_set"]["sha256"]) != (GATE_FILE, GATE_SHA256):
            out.append("inherited_gate_set")
    except (KeyError, TypeError, AttributeError, ValueError):
        out.append("判定に関わる欄が読めない")
    return out


def gate_problems(runs: dict, repo: Path = REPO_ROOT) -> list[str]:
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
    checks, mismatches = 0, []
    seeds = sorted(runs)
    binding = protocol_problems(runs) + gate_problems(runs)
    checks, mismatches = checks + 2, mismatches + binding
    manifests = {json.dumps(runs[s].get("meta", {}).get("manifest"), sort_keys=True) for s in seeds}
    checks += 1
    if len(manifests) > 1:
        mismatches.append("個体によって meta の設計図が違う")
    for s in seeds:
        checks += 1
        try:
            mismatches += [f"seed {s}: {p}" for p in operation_problems(runs[s])]
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
            mismatches.append(f"seed {s}: 操作の確認の記録を読めない（{type(e).__name__}）")
    checks += 1
    if not isinstance(report, dict) or report.get("valid") is not True:
        return {"checks": checks, "mismatches": mismatches + ["report.valid"], "recomputed": None}
    try:
        mine = expected_report(runs, measurement_commit)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError, AttributeError) as e:
        return {"checks": checks, "mismatches": mismatches + [f"生の記録から report を組み立て直せない（{type(e).__name__}）"],
                "recomputed": None}
    if mine["mode"] is None:
        mismatches.append("個体によって meta の mode が違う")
    n, found = compare(mine, report)
    j, est = mine["judgment"], mine["estimate"]
    return {"checks": checks + n, "mismatches": mismatches + found,
            "recomputed": {"outcome": j["outcome"],
                           "J_C": {k: j["J_C"][k] for k in ("level", "m_nonzero", "m_def", "counts", "status", "direction", "k2")},
                           "E_C": {"m_def": est["m_def"], "p_nz_count": est["p_nz"]["count"],
                                   "p_any_count": est["p_any"]["count"], "cancellations": est["cancellations"]}}}


# ---- 測定の来歴と全件性（0042 と同じ） ------------------------------------------------------------------------

def _seed_name(name: str) -> bool:
    return bool(name) and set(name) <= DIGITS and str(int(name)) == name


def seed_set_problems(mode: str | None, seeds: list[int]) -> list[str]:
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
        if len(seeds) != PREREGISTERED["individuals"]:
            problems.append(f"本番の個体の数が {PREREGISTERED['individuals']} ではない")
    elif not seeds:
        problems.append("seed がない")
    return problems


def read_directory(out: Path) -> tuple[dict, dict, list[str]]:
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
