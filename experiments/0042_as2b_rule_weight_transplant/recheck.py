"""実験 0042 の独立の検算（README §9.1。標準のライブラリだけ）。

この実験の解析・測定の道具も、事前登録の analysis.py も、anima_ll も、AS2b の道具も、protocol.yaml を読む道具も読み込まない。
保存した生の記録（seeds/<seed>/raw.json.gz）だけから、定義（README §3〜§6）を書き起こし直して report の欄をすべて組み立て直し、
report.json と欄ごとに照合する。判定の閾値などの事前登録の値は、README・protocol.yaml（v0.2。#195 merge `49d99e4`）から
書き起こした PREREGISTERED から取る。生の記録の meta に保存された protocol の写し（meta.protocol・meta.protocol_sha256）は、
次のことを確かめるだけに使う（0040 の道具 v0.3・0041 と同じ形）
- 全個体にあり、全個体で同じであること
- 写しの中身全体を JSON に正規化したもののハッシュが、事前登録 v0.2 の protocol の固定のハッシュ（PROTOCOL_JSON_SHA256）と同じであること
  （PREREGISTERED で個別に照らさない欄の改変も見つける）
- SHA-256 が、リポジトリの確定済みの protocol.yaml のバイト列の SHA-256（PROTOCOL_FILE_SHA256）と同じであること
- 写しの中の判定に関わる値が、PREREGISTERED と同じであること。k₂(m)（m ＝ 10〜200）は、二項から求め直した値と同じであること
どれかが欠けたり違ったりすれば、食い違いとして数える。

report との照合（recheck）
- 生の記録から、report と同じ形の期待値を作る：mode・valid・O1・関門の宣言の SHA-256、判定 J_T、推定 E_T（p_nz・p_any・打ち消しを含む）、
  §6.1 の必ず報告する記述、個体ごとの量（17 系の窓の数と s、§3.2 の量と符号、T_any、k*、札、δ、重み、結果の刺激、最初に分かれた
  Pulse と窓、発火の数）、補助の記録 R1〜R9
- s と §3.2 の量は、層 A の窓の結末から数え直した分数で、定義をここに書き下して計算する（事前登録の analysis.py を読み込まない）
- 期待値と report を、欄の組・列の長さ・葉の値まで、すべての欄で比べる（compare）。葉の値は、型（真偽・文字列・null・数）も比べる。
  数はちょうど同じであることを求める。許す違いは、計算の書き方が解析と違う二つだけ：Clopper–Pearson の端点（二分法の書き方）と
  命題 S-1 の E_S（設計図から書き起こした式）で、絶対値 1e-9 まで
- 操作の確認の主なもの（O3〜O14）を、別の書き方で

測定の来歴と全件性（recheck_directory。guard・解析の道具の確かめに頼らず、ファイルを直接読む）
- seeds/ の下は、seed の名前（先頭に 0 のない 10 進）のフォルダだけで、各フォルダは開始の記録・終了の記録・raw の 3 つだけを持つ
- 終了の記録が completed で、raw のファイルの SHA-256・バイト数が終了の記録と同じ
- フォルダの名前・開始の記録・終了の記録・raw の meta・raw の run の seed が同じ。experiment・kind・mode が開始・終了・meta で同じ
- 測定の commit：開始の記録 ＝ 終了の記録の measurement_commit_end ＝ raw の meta（40 桁）で、全 seed で一つ。report の
  measurement_commit と O1 の記録の commit も、それと同じ
- protocol の SHA-256：開始の記録 ＝ raw の meta ＝ 確定済みの protocol.yaml（PROTOCOL_FILE_SHA256）
- 関門の宣言：raw の meta の SHA-256 ＝ 固定の値（GATE_SHA256）＝ リポジトリの宣言のファイル。meta の宣言の中身 ＝ そのファイル
- seed の組：本番は 35001〜35200 の 200 個体がちょうど（欠け・余り・範囲の外がない）。合成は合成の範囲の中。
  smoke の盲検の記録は、この検算の対象ではない（食い違いとして数える）
- O1 の記録：欄の組、commit、終了コード 0、すべて通った結果の行、走らせた契約テストの組、テストのファイルの SHA-256
  （この検算が置かれたリポジトリのファイルと照らす。測定の commit で走らせる）

使い方（結果を保存したフォルダを渡す。測定の commit で、計算の後で一度だけ）:
  python experiments/0042_as2b_rule_weight_transplant/recheck.py <フォルダ> [--write <結果の JSON>]
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
ZEROS = ("Z-1", "Z-2")
ROLES3 = ("cue", "source1", "source2")
SOURCES = ("source1", "source2")
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")
# 17 系（README §2.2 の表から書き起こす）。本体・観測しない本体・複製の系
BODIES = ["B_A1", "B_A2"]
RERUN = "B_A1_rerun"
CLONES = ["G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr", "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr",
          "G_A1_X1", "G_A1_X2", "G_A2_X1", "G_A2_X2", "N_A1_WA1", "N_A1_WA2", "N_A2_WA2", "N_A2_WA1"]
ALL = BODIES + [RERUN] + CLONES
RULE = {"B_A1": "A1", "B_A2": "A2", RERUN: "A1",
        "G_A1_WA1": "A1", "G_A1_WA2": "A1", "G_A1_WA1_tr": "A1", "G_A1_X1": "A1", "G_A1_X2": "A1",
        "N_A1_WA1": "A1", "N_A1_WA2": "A1",
        "G_A2_WA2": "A2", "G_A2_WA1": "A2", "G_A2_WA2_tr": "A2", "G_A2_X1": "A2", "G_A2_X2": "A2",
        "N_A2_WA2": "A2", "N_A2_WA1": "A2"}
# U の 6 本の重み（W^{A1}・W^{A2}・端の X1・X2）と、S3 での移植の先（G^c[W^c]・N^c[W^c] は移植しない）
U_WEIGHTS = {"G_A1_WA1": "A1", "G_A1_WA2": "A2", "G_A1_WA1_tr": "A1", "G_A2_WA2": "A2", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2",
             "G_A1_X1": "X1", "G_A1_X2": "X2", "G_A2_X1": "X1", "G_A2_X2": "X2",
             "N_A1_WA1": "A1", "N_A1_WA2": "A2", "N_A2_WA2": "A2", "N_A2_WA1": "A1"}
NOT_TRANSPLANTED = {"G_A1_WA1", "G_A2_WA2", "N_A1_WA1", "N_A2_WA2"}
NO_FEEDBACK = {"N_A1_WA1", "N_A1_WA2", "N_A2_WA2", "N_A2_WA1"}
T_SYSTEMS = ["G_A1_WA1", "G_A1_WA2", "G_A2_WA1", "G_A2_WA2"]
PAIRS_R6 = [("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"), ("G_A1_X1", "G_A1_X2"), ("G_A2_X1", "G_A2_X2"),
            ("N_A1_WA1", "N_A1_WA2"), ("N_A2_WA2", "N_A2_WA1"), ("G_A1_WA1", "N_A1_WA1"), ("G_A2_WA2", "N_A2_WA2")]
PAIRS_SE_T5 = [("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"), ("G_A1_WA1", "G_A1_X1"), ("G_A1_WA1", "G_A1_X2"),
               ("G_A2_WA2", "G_A2_X1"), ("G_A2_WA2", "G_A2_X2"), ("N_A1_WA1", "N_A1_WA2"), ("N_A2_WA2", "N_A2_WA1")]
PAIRS_SE_T6 = [("G_A1_WA1", "N_A1_WA1"), ("G_A2_WA2", "N_A2_WA2")]
PAIRS_SE_T4 = [("G_A1_WA1", "G_A1_WA1_tr"), ("G_A2_WA2", "G_A2_WA2_tr")]
PAIRS_SE_T7 = [("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"), ("N_A1_WA1", "N_A1_WA2"), ("N_A2_WA2", "N_A2_WA1")]
NAMES = ("T_A1", "T_A2", "T", "BE_WA1", "BE_WA2", "BE", "TE_F", "D", "S_A1", "S_A2", "S", "TN_A1", "TN_A2", "TN",
         "K_A1", "K_A2", "Z_A1", "Z_A2")
CROSS = ("D", "S", "TN", "delta")
CLASSES = ("plus", "minus", "structural_zero", "structural_identity", "both_zero", "cancellation", "undefined")
# report の決まった文（README §3.2・§4.4・§6.2。解析の道具と同じ文を、ここに書き起こす）
NOTES = {"estimate": "estimate only; no threshold; not a judgment (README section 4.4)",
         "p_nz": "share of individuals whose summed T is nonzero; not the share whose choice changed (cancellations are T = 0)",
         "p_any": "share of individuals in which the weight swap changed the U share in at least one background; descriptive",
         "prominence": "report m_nonzero / m_def, p_nz and p_any with their intervals with the same prominence as the J_T direction",
         "identity": "TE_F = (T + BE) / 2 is arithmetic only; never a true decomposition (README section 3.2)",
         "R8": "Clopper-Pearson 95% intervals are in judgment.J_T, estimate and descriptive_controls",
         "R4": "the six weights of every clone after S3 are W_A1, W_A2, X1 or X2 (O6 (a), O11)",
         "R9": "within-body before/after; not a counterfactual contrast"}
HEX = set("0123456789abcdef")
DIGITS = set("0123456789")
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROTOCOL_FILE = HERE / "protocol.yaml"
# 事前登録 v0.2 の protocol.yaml（#195 merge `49d99e4`）を、raw の meta と同じ形（YAML を読み、JSON を通した形）にして正規化した
# JSON の SHA-256。正規化：json.dumps(写し, sort_keys=True, ensure_ascii=False, separators=(",", ":")) の UTF-8。
# 値は契約テストで、正本から計算し直して照らす
PROTOCOL_JSON_SHA256 = "32ddbd1ddf30081caf15c779ed9d04ad0d34c306d8116992244e0675896a2180"
PROTOCOL_FILE_SHA256 = "709010ef964d945f09522ab279b1c725e0042bcf51a526a0a67cda0ff506b170"   # 同じ正本のファイルのバイト列
# 引き継ぐ関門の宣言 v0.2（protocol の inherited_gate_set）のファイルと、そのバイト列の SHA-256
GATE_FILE = "experiments/0038_as2b_forward_gate/gate_declaration.json"
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
# 事前登録 v0.2 から書き起こした値：README §1.2・§2・§4.3・§5.1・§8・§9.2、protocol.yaml の judgment・timeline・brain・world・
# systems・extremes・seeds。判定はこの値で計算し、meta の protocol の写しは、これと照らすだけに使う
PREREGISTERED = {
    "experiment": "0042", "kind": "preregistered_test",
    "alpha_per_direction": Fraction(1, 40), "alpha_two_sided": Fraction(1, 20), "min_population": 10, "individuals": 200,
    "k2_200": 115, "outcomes": ["invalid", "inconclusive", "not_established", "plus", "minus"],
    "experience_windows": [1, 25], "experience_pulses": [1, 1065], "boundary_P_E": 1065,
    "test_windows": [26, 50], "test_pulses": [1066, 2072], "body_pulses": 2072,
    "w_min": 0.0, "w_max": 0.01, "w0": 0.005, "f1_tolerance": 1e-12,
    "rule_c": {"B_A1": "A1", "B_A2": "A2", "B_A1_rerun": "A1"}, "per_individual": ALL,
    "extremes": {"X1": {"C_to_source1": 0.01, "source1_to_C": 0.0, "C_to_source2": 0.0, "source2_to_C": 0.01,
                        "source1_to_source2": 0.005, "source2_to_source1": 0.005},
                 "X2": {"C_to_source1": 0.0, "source1_to_C": 0.01, "C_to_source2": 0.01, "source2_to_C": 0.0,
                        "source1_to_source2": 0.005, "source2_to_source1": 0.005}},
    "seeds": {"first": 35001, "last": 35200}, "smoke_seeds": {"first": 35201, "last": 35206},
    "synthetic_seeds": {"first": 35301, "last": 35399},
    "formal_plan": {"first": 41, "spacing": 41, "count": 50, "offset": 2, "length": 19, "delay": 2, "e_windows": 25},
}
W_MIN, W_MAX, W0 = PREREGISTERED["w_min"], PREREGISTERED["w_max"], PREREGISTERED["w0"]
# 出力先のファイル（README §9.4。guard.py・analyze.py と同じ名前を、ここに書き起こす）
START, FINISH, RAW, SEEDS_DIR = "run_started.json", "run_finished.json", "raw.json.gz", "seeds"
REPORT, O1_FILE = "report.json", "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py",
                  "tests/integration/test_as2b_rule_weight_direction_0041.py",
                  "tests/integration/test_as2b_rule_weight_transplant_0042.py")
RECHECKED_MODES = {"formal": "seeds", "synthetic": "synthetic_seeds"}          # smoke（盲検の記録）は対象ではない
LOOSE = 1e-9                                                                   # 計算の書き方が違う欄だけに許す違い


def geometry(plan: dict) -> dict:
    cues = [plan["first"] + plan["spacing"] * k for k in range(plan["count"])]
    windows = [(k + 1, c + plan["offset"], c + plan["offset"] + plan["length"] - 1) for k, c in enumerate(cues)]
    e = plan["e_windows"]
    return {"cues": cues, "windows": windows, "e": e, "p_e": cues[e] - 1, "end": windows[-1][2] + plan["delay"]}


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


def valued(x: Fraction | None) -> dict:
    return {"value": frac(x), "sign": None if x is None else sign_of(x)}


# ---- 個体ごとの量（README §3・§4.1・§6） ---------------------------------------------------------------

def role_cids(roles: dict) -> dict:
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


def records_of(run: dict) -> dict:
    return {**run["bodies"], **run["clones"]}


def window_count(layer_a: list, lo: int, hi: int) -> dict:
    outs = Counter(r["outcome"] for r in layer_a if lo <= r["window"] <= hi)
    return {"windows": sum(outs.values()), "decided": outs["A1"] + outs["A2"], "A1": outs["A1"], "A2": outs["A2"],
            "tie": outs["tie"], "none": outs["none"]}


def a1_share(counts: dict) -> Fraction | None:
    return None if counts["decided"] == 0 else Fraction(counts["A1"], counts["decided"])


def definitions(s: dict) -> dict:
    """README §3.2 を、ここに書き起こしたもの（分数。使う s が一つでも定まらなければ、その量は定まらない）。"""
    def minus(a, b):
        return None if a is None or b is None else a - b

    def plus(a, b):
        return None if a is None or b is None else a + b

    def of_c(name, c):                      # s_c：規則 c が指す行動の割合
        return None if s[name] is None else (s[name] if c == "A1" else 1 - s[name])
    t1, t2 = minus(s["G_A1_WA1"], s["G_A1_WA2"]), minus(s["G_A2_WA1"], s["G_A2_WA2"])
    b1, b2 = minus(s["G_A1_WA1"], s["G_A2_WA1"]), minus(s["G_A1_WA2"], s["G_A2_WA2"])
    x1, x2 = minus(s["G_A1_X1"], s["G_A1_X2"]), minus(s["G_A2_X1"], s["G_A2_X2"])
    n1, n2 = minus(s["N_A1_WA1"], s["N_A1_WA2"]), minus(s["N_A2_WA1"], s["N_A2_WA2"])
    t = plus(t1, t2)
    return {"T_A1": t1, "T_A2": t2, "T": t, "T_any": None if t is None else (t1 != 0 or t2 != 0),
            "BE_WA1": b1, "BE_WA2": b2, "BE": plus(b1, b2), "TE_F": minus(s["G_A1_WA1"], s["G_A2_WA2"]),
            "D": minus(s["B_A1"], s["B_A2"]), "S_A1": x1, "S_A2": x2, "S": plus(x1, x2),
            "TN_A1": n1, "TN_A2": n2, "TN": plus(n1, n2),
            "K_A1": minus(of_c("G_A1_WA1", "A1"), of_c("N_A1_WA1", "A1")),
            "K_A2": minus(of_c("G_A2_WA2", "A2"), of_c("N_A2_WA2", "A2")),
            "Z_A1": minus(of_c("B_A1", "A1"), of_c("G_A1_WA1", "A1")),
            "Z_A2": minus(of_c("B_A2", "A2"), of_c("G_A2_WA2", "A2"))}


def max_pair_gap(weights: dict) -> Fraction:
    """組（二つの Unit のあいだの 2 本）ごとの正確な和と w_max の差の絶対値の最大。"""
    by_pair: dict[tuple, list] = {}
    for cid, w in weights.items():
        by_pair.setdefault(tuple(sorted(cid.split(".main->"))), []).append(Fraction(w))
    return max(abs(sum(ws, Fraction(0)) - Fraction(W_MAX)) for ws in by_pair.values())


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


def conn_weights(sigma: dict) -> dict:
    return {cid: v["weight"] for cid, v in sigma["connections"].items()}


def individual(data: dict) -> dict:
    """1 個体の量を、report の individuals の欄と同じ形で書き起こす。"""
    run, plan = data["run"], data["run"]["plan"]
    geo = geometry(plan)
    e, k_all, p_e, end = geo["e"], plan["count"], geo["p_e"], geo["end"]
    roles, rec = run["roles"], records_of(run)
    name_of = {roles[r]: r for r in ROLES3}
    counts_e = {n: window_count(rec[n]["layer_a"], 1, e) for n in ALL}
    counts_u = {n: window_count(rec[n]["layer_a"], e + 1, k_all) for n in ALL}
    s = {n: a1_share(counts_u[n]) for n in ALL}
    q = definitions(s)
    decided = [r["window"] for r in rec["B_A1"]["layer_a"] if r["window"] <= e and r["outcome"] in ACTIONS]
    ks = decided[0] if decided else None
    zero = None if ks is not None else ("Z-1" if counts_e["B_A1"]["none"] == counts_e["B_A1"]["windows"] else "Z-2")
    w = run["boundary"]["W"]
    same = ks is not None and w["A1"] == w["A2"]
    t = q["T"]
    if t is None:
        cls = "undefined"
    elif t != 0:
        cls = "plus" if t > 0 else "minus"
    elif ks is None:
        cls = "structural_zero"
    elif same:
        cls = "structural_identity"
    else:
        cls = "both_zero" if q["T_A1"] == 0 == q["T_A2"] else "cancellation"
    cid_of = role_cids(roles)
    wa1 = {r: Fraction(w["A1"][cid_of[r]]) for r in ROLES6}
    wa2 = {r: Fraction(w["A2"][cid_of[r]]) for r in ROLES6}
    delta = (wa1["C_to_source1"] - wa2["C_to_source1"]) - (wa1["C_to_source2"] - wa2["C_to_source2"])
    e_s = bound_e_s(data["meta"]["manifest"], plan)
    units = run["birth_units"]
    margin = {}
    for u, role in name_of.items():
        dyn = units[u]["dynamics"]
        margin[role] = dyn["intrinsic_drive_per_second"] / (1 - dyn["decay_per_second"]) - dyn["threshold"]
    silent = {role: margin[role] < -e_s for role in SOURCES}
    fired = {u for n in ALL for _p, u in rec[n]["activity"]}
    consequences = {}
    for n in BODIES + CLONES:
        pulses = [row[3] for row in rec[n]["world_end"]["reserved"] if row[1] == "consequence"]
        consequences[n] = {"E": sum(1 for p in pulses if p <= p_e), "U": sum(1 for p in pulses if p > p_e),
                           "decided_windows_of_c": {"E": counts_e[n][RULE[n]], "U": counts_u[n][RULE[n]]}}
    split = {"B_A1|B_A2": {"firing": first_split(rec["B_A1"]["activity"], rec["B_A2"]["activity"], 1, end),
                           "window": first_outcome_split(rec["B_A1"]["layer_a"], rec["B_A2"]["layer_a"])}}
    for a, b in PAIRS_R6:
        split[f"{a}|{b}"] = {"firing": first_split(rec[a]["activity"], rec[b]["activity"], p_e + 1, end),
                             "window": first_outcome_split(rec[a]["layer_a"], rec[b]["layer_a"])}
    firing = {}
    for n in ALL:
        by_part = {"U": dict.fromkeys(ROLES3, 0)}
        if n not in CLONES:
            by_part["E"] = dict.fromkeys(ROLES3, 0)
        for p, u in rec[n]["activity"]:
            part = "U" if p > p_e else "E"
            if part in by_part and u in name_of:
                by_part[part][name_of[u]] += 1
        firing[n] = by_part
    return {
        "roles": {k: roles[k] for k in ROLES3},
        "birth": {role: {"threshold": units[roles[role]]["dynamics"]["threshold"],
                         "intrinsic_drive": units[roles[role]]["dynamics"]["intrinsic_drive_per_second"],
                         "margin_g": margin[role]} for role in ROLES3},
        "S1": {"silent_source": silent, "violations": sorted(r for r in SOURCES if silent[r] and roles[r] in fired)},
        "k_star": ks,
        "zero_label": zero,
        "structural_identity": same,
        "class": cls,
        "undefined_systems": [n for n in T_SYSTEMS if s[n] is None],
        "T_any": q["T_any"],
        "quantities": {k: valued(q[k]) for k in NAMES},
        "delta": valued(delta),
        "counts_E": counts_e,
        "counts_U": counts_u,
        "s_U": {n: frac(s[n]) for n in ALL},
        "s_E": {n: frac(a1_share(counts_e[n])) for n in BODIES},
        "W": {"A1": {r: w["A1"][cid_of[r]] for r in ROLES6}, "A2": {r: w["A2"][cid_of[r]] for r in ROLES6}},
        "W_abs_diff": {r: float(abs(wa1[r] - wa2[r])) for r in ROLES6},
        "pair_deviation": {c: float(max_pair_gap(w[c])) for c in ACTIONS},
        "clone_pair_deviation": float(max(max_pair_gap(conn_weights(run["boundary"]["sigma_a"][n])) for n in CLONES)),
        "consequences": consequences,
        "first_divergence": split,
        "firing": firing,
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
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "denominator = 0"}
    return {"computed": True, "interval": list(exact_interval(x, n)), "numerator": x, "denominator": n}


def share_of(x: int, n: int) -> dict:
    return {"count": x, "denominator": n, "proportion": x / n if n else None, "interval": interval_of(x, n)}


def judgment(people: list[dict]) -> dict:
    by_class = Counter(p["class"] for p in people)
    plus, minus = by_class["plus"], by_class["minus"]
    m = plus + minus
    m_def = len(people) - by_class["undefined"]
    counts = {"+": plus, "-": minus, "0": m_def - m, "undefined": by_class["undefined"]}
    j = {"m_nonzero": m, "m_def": m_def, "counts": counts}
    if m < PREREGISTERED["min_population"]:
        j |= {"status": "inconclusive", "direction": None, "k2": None, "tail_probability": None}
        outcome = "inconclusive"
    else:
        k = k2(m, PREREGISTERED["alpha_per_direction"])
        direction = "+" if plus >= k else "-" if minus >= k else None
        j |= {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
              "tail_probability": float(upper_tail(m, k))}
        outcome = {"+": "plus", "-": "minus", None: "not_established"}[direction]
    return {"J_T": j, "outcome": outcome, "prominence": NOTES["prominence"]}


def spread(people: list[dict]) -> dict:
    """E_T の割合の欄（README §4.4。分母は T が定まる個体の数、p_dir だけ 0 でない個体の数）。"""
    defined = [p for p in people if p["class"] != "undefined"]
    n = len(defined)
    c = Counter(p["class"] for p in defined)
    nz = c["plus"] + c["minus"]
    return {"m_def": n, "m_nonzero": nz, "p_nz": share_of(nz, n), "p_any": share_of(sum(1 for p in defined if p["T_any"]), n),
            "p_plus": share_of(c["plus"], n), "p_minus": share_of(c["minus"], n), "p_dir": share_of(c["plus"], nz),
            "cancellations": c["cancellation"]}


def estimate(people: list[dict]) -> dict:
    out = spread(people)
    sizes = [abs(p["quantities"]["T"]["value"]["value"]) for p in people if p["class"] != "undefined"]
    und = [p for p in people if p["class"] == "undefined"]
    out["abs_T"] = {"defined": five(sizes), "nonzero": five([x for x in sizes if x != 0])}
    out["undefined"] = {"count": len(und),
                        "by_number_of_undefined_systems": {str(k): sum(1 for p in und if len(p["undefined_systems"]) == k)
                                                           for k in range(1, 5)},
                        "by_background": {c: sum(1 for p in und if any(n.split("_")[1] == c for n in p["undefined_systems"]))
                                          for c in ACTIONS}}
    out["notes"] = {k: NOTES[k] for k in ("estimate", "p_nz", "p_any", "prominence")}
    return out


def _q(p: dict, name: str) -> dict:
    return p["delta"] if name == "delta" else p["quantities"][name]


def table_of(people: list[dict], name: str) -> dict:
    defined = [_q(p, name) for p in people if _q(p, name)["sign"] is not None]
    n = len(defined)
    c = Counter(x["sign"] for x in defined)
    counts = {s: c[s] for s in SIGNS}
    values = [x["value"]["value"] for x in defined]
    return {"defined": n, "undefined": len(people) - n, "counts": counts,
            "proportion": {s: share_of(counts[s], n) for s in ("+", "-")},
            "plus_among_nonzero": share_of(counts["+"], counts["+"] + counts["-"]),
            "distribution": five(values), "abs_distribution": five([abs(v) for v in values])}


def signs_table(people: list[dict], x: str, y: str) -> dict:
    sx = [_q(p, x)["sign"] for p in people]
    sy = [_q(p, y)["sign"] for p in people]
    cells = {a + b: 0 for a in SIGNS for b in SIGNS}
    for a, b in zip(sx, sy):
        if a is not None and b is not None:
            cells[a + b] += 1
    return {"order": [x, y], "in_both": sum(cells.values()),
            f"only_{x}": sum(1 for a, b in zip(sx, sy) if a is not None and b is None),
            f"only_{y}": sum(1 for a, b in zip(sx, sy) if b is not None and a is None), "cells": cells}


def controls(people: dict) -> dict:
    group = list(people.values())
    out = {"quantities": {k: table_of(group, k) for k in NAMES + ("delta",)}}
    per_bg = signs_table(group, "T_A1", "T_A2")
    opposite = Counter(p["quantities"]["T"]["sign"] for p in group
                       if {p["quantities"]["T_A1"]["sign"], p["quantities"]["T_A2"]["sign"]} == {"+", "-"})
    per_bg["opposite_cells_by_sign_of_T"] = {s: opposite[s] for s in SIGNS}
    out["per_background"] = per_bg
    out["two_by_two"] = {"s_U": {n: five([p["s_U"][n]["value"] for p in group if p["s_U"][n] is not None]) for n in T_SYSTEMS},
                         "identity_note": NOTES["identity"]}
    out["cross_with_T"] = {x: signs_table(group, x, "T") for x in CROSS}
    out["diverged_subpopulation"] = spread([p for p in group if p["k_star"] is not None])
    withdrawn = any(p["S1"]["violations"] for p in group)

    def seeds_with(cond) -> list:
        return sorted(k for k, p in people.items() if cond(p))
    out["zero_table"] = {
        "structural_zero": {z: seeds_with(lambda p, z=z: p["class"] == "structural_zero" and p["zero_label"] == z) for z in ZEROS},
        "structural_identity": seeds_with(lambda p: p["class"] == "structural_identity"),
        "both_zero": seeds_with(lambda p: p["class"] == "both_zero"),
        "cancellation": seeds_with(lambda p: p["class"] == "cancellation"),
        "undefined": {k: p["undefined_systems"] for k, p in sorted(people.items()) if p["class"] == "undefined"},
        "structurally_silent_source": None if withdrawn else seeds_with(lambda p: any(p["S1"]["silent_source"].values())),
    }
    return out


def auxiliary(people: dict, e_s: float | None) -> dict:
    vals = list(people.values())
    violations = sum(len(p["S1"]["violations"]) for p in vals)
    cls = Counter(p["class"] for p in vals)
    out: dict = {"R1": {
        "individuals": len(vals),
        "classes": {c: cls[c] for c in CLASSES},
        "zero_labels": {z: sum(1 for p in vals if p["zero_label"] == z) for z in ZEROS},
        "k_star": five([p["k_star"] for p in vals if p["k_star"] is not None]),
        "structural_identity": sum(1 for p in vals if p["structural_identity"]),
        "S1": {"E_S": e_s, "violations": violations, "labels_withdrawn": violations > 0,
               "individuals_with_silent_source": None if violations else
               sum(1 for p in vals if any(p["S1"]["silent_source"].values()))}}}
    out["R2"] = {}
    for n in ALL:
        out["R2"][n] = {part: {k: five([p[f"counts_{part}"][n][k] for p in vals]) for k in ("decided", "A1", "A2", "tie", "none")}
                        for part in ("E", "U")}
        out["R2"][n]["s_U"] = five([p["s_U"][n]["value"] for p in vals if p["s_U"][n] is not None])
    out["R3"] = {}
    for k in NAMES + ("delta",):
        xs = [_q(p, k)["value"]["value"] for p in vals if _q(p, k)["value"] is not None]
        out["R3"][k] = {"value": five(xs), "abs_value": five([abs(x) for x in xs])}
    out["R4"] = {"W_A1": {r: five([p["W"]["A1"][r] for p in vals]) for r in ROLES6},
                 "W_A2": {r: five([p["W"]["A2"][r] for p in vals]) for r in ROLES6},
                 "abs_W_diff": {r: five([p["W_abs_diff"][r] for p in vals]) for r in ROLES6},
                 "pair_sum_max_abs_deviation": max([x for p in vals for x in p["pair_deviation"].values()], default=None),
                 "clones_after_transplant": {"weights": NOTES["R4"],
                                             "pair_sum_max_abs_deviation": max([p["clone_pair_deviation"] for p in vals],
                                                                               default=None)}}
    out["R5"] = {}
    for n in BODIES + CLONES:
        rows = [p["consequences"][n] for p in vals]
        if n in NO_FEEDBACK:
            ok = all(r["E"] == r["decided_windows_of_c"]["E"] and r["U"] == 0 for r in rows)
        else:
            ok = all(r["E"] == r["decided_windows_of_c"]["E"] and r["U"] == r["decided_windows_of_c"]["U"] for r in rows)
        out["R5"][n] = {"E": five([r["E"] for r in rows]), "U": five([r["U"] for r in rows]), "as_expected": ok}
    out["R6"] = {}
    for key in (["B_A1|B_A2"] + [f"{a}|{b}" for a, b in PAIRS_R6]) if vals else []:
        f = [p["first_divergence"][key]["firing"] for p in vals]
        w = [p["first_divergence"][key]["window"] for p in vals]
        out["R6"][key] = {"firing": {"none": f.count(None), "pulses": five([x for x in f if x is not None])},
                          "window": {"none": w.count(None), "windows": five([x for x in w if x is not None])}}
    out["R7"] = {n: {part: {r: five([p["firing"][n][part][r] for p in vals]) for r in ROLES3}
                     for part in (("U",) if n in CLONES else ("E", "U"))} for n in ALL}
    out["R8"] = NOTES["R8"]
    out["R9"] = {n: {"s_E": five([p["s_E"][n]["value"] for p in vals if p["s_E"][n] is not None]),
                     "s_U": five([p["s_U"][n]["value"] for p in vals if p["s_U"][n] is not None]),
                     "note": NOTES["R9"]} for n in BODIES}
    return out


def expected_report(runs: dict, measurement_commit: str | None = None) -> dict:
    """保存した生の記録だけから、有効な report の全体を組み立て直す。measurement_commit を渡したときは、その欄も期待値に入れる。"""
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


# ---- 操作の確認の主なもの（O3〜O14。別の書き方で） -----------------------------------------------------------

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


def _with_weights(sigma: dict, weights: dict, respond: bool | None = None) -> str:
    """Σ の 6 本の重み（と世界の応答）を置き換えた、正規化した JSON の文字列。"""
    s = copy.deepcopy(sigma)
    for cid, w in weights.items():
        s["connections"][cid]["weight"] = w
    if respond is not None:
        s["world"]["rule"]["respond"] = respond
    return json.dumps(s, sort_keys=True, separators=(",", ":"))


def operation_problems(data: dict) -> list[str]:
    run = data["run"]
    plan, roles = run["plan"], run["roles"]
    geo = geometry(plan)
    e, p_e, end, windows, L = geo["e"], geo["p_e"], geo["end"], geo["windows"], plan["delay"]
    order, cue_r = run["connection_order"], roles["cue_receptor"]
    action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    rec, b = records_of(run), run["boundary"]
    w = b["W"]
    values = {"A1": w["A1"], "A2": w["A2"], "X1": run["X"]["X1"], "X2": run["X"]["X2"]}
    problems = []

    def f1_ok(ws: dict) -> bool:
        return sorted(ws) == sorted(order) and all(W_MIN <= x <= W_MAX for x in ws.values()) \
            and max_pair_gap(ws) <= Fraction(PREREGISTERED["f1_tolerance"])
    for n in ALL:
        r = rec[n]
        la, lb = r["layer_a"], r["layer_b"]
        # O14：層 A の欄の整合（50 窓）と、層 A の決まった窓ごとの行動 ID が、層 B の意図（Pulse − 1 が窓の中）と同じ
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
        # O3：層 A と層 B の一対一、識別子の重複、未発行の予定、来歴のログ
        if Counter((x["emit_pulse"], x["winner_unit"], x["action"]) for x in la if x["emitted"]) \
                != Counter((p, src, act) for p, _did, src, act in lb):
            problems.append(f"O3 {n}: 層 A と層 B")
        if len({did for _p, did, _s, _a in lb}) != len(lb):
            problems.append(f"O3 {n}: 識別子の重複")
        if any(x["winner_unit"] is not None and not x["emitted"] for x in la):
            problems.append(f"O3 {n}: 未発行の予定")
        if sorted(r["delta_log"]) != sorted(x for x in lb if n not in CLONES or x[0] > p_e):
            problems.append(f"O3 {n}: 来歴のログ")
        # O5：結果は応じる区間の規則 c の意図にだけ、意図の Pulse ＋ L − 1。感覚の出来事は手がかりの Receptor だけ
        world = r["world_end"]
        live = [x for x in lb if x[3] == RULE[n] and (n not in NO_FEEDBACK or x[0] <= p_e)]
        cons = sorted((row[3], row[4]) for row in world["reserved"] if row[1] == "consequence")
        if cons != sorted((p + L - 1, did) for p, did, _s, _a in live):
            problems.append(f"O5 {n}: 結果の予約")
        if len(cons) != sum(1 for x in la if x["outcome"] == RULE[n] and (n not in NO_FEEDBACK or x["window"] <= e)):
            problems.append(f"O5 {n}: 結果の刺激の数")
        if any(rc != cue_r for _p, rc in r["sensory"]) or any(row[1] not in ("cue", "consequence") or row[2] != cue_r
                                                              for row in world["reserved"]) or world["pending"]:
            problems.append(f"O5 {n}: 感覚の出来事・予約")
        if world["rule"]["rule_c"] != RULE[n] or world["rule"]["respond"] is not (n not in NO_FEEDBACK) \
                or world["rule"]["delay"] != L:
            problems.append(f"O5 {n}: 世界の規則")
        if r["world_switches"] != ([[p_e, "S3'", False]] if n in NO_FEEDBACK else []):
            problems.append(f"O5 {n}: 世界の切り替え")
        if _sha(r["sigma_end"]) != r["sigma_end_sha256"] or r["pulse_end"] != end:
            problems.append(f"O14 {n}: 終わりの Σ")
    # O4：R-7 の対。Pulse 0 は規則 c だけが違う。k* がなければ P_E まで規則 c だけ。あれば k* の意図の Pulse の後の脳の側が同じ
    a1, a2 = rec["B_A1"], rec["B_A2"]
    rule = [("world", "rule", "rule_c")]
    if _without(a1["sigma_0"], rule) != _without(a2["sigma_0"], rule):
        problems.append("O4: Pulse 0")
    decided = [x for x in a1["layer_a"] if x["window"] <= e and x["outcome"] in ACTIONS]
    if not decided:
        if any([x for x in a1[k] if x[0] <= p_e] != [x for x in a2[k] if x[0] <= p_e] for k in ("activity", "sensory")) \
                or _without(b["sigma_p_e"]["B_A1"], rule) != _without(b["sigma_p_e"]["B_A2"], rule) \
                or w["A1"] != w["A2"] or a1["first_intent"] is not None or a2["first_intent"] is not None:
            problems.append("O4: k* がない個体")
    else:
        k, t = decided[0]["window"], decided[0]["decision_pulse"] + 1
        fa, fb = a1["first_intent"], a2["first_intent"]
        brain = rule + [("world", "pending"), ("world", "reserved"), ("world", "next_rid")]
        if a1["layer_a"][:k] != a2["layer_a"][:k] or fa is None or fb is None or fa["pulse"] != t or fb["pulse"] != t \
                or _without(fa["sigma"], brain) != _without(fb["sigma"], brain):
            problems.append("O4: k* の意図の Pulse")
    # O12：P_E の Σ（未決の窓・意図・結果の予約がない）と、記録した W・SHA-256。O14：δ の計算し直し
    for n in BODIES:
        sp = b["sigma_p_e"][n]
        ex = sp["exit"]
        if sp["pulse"] != p_e or ex["pending"] is not None or ex["cursor"] != e or ex["reports"] \
                or any(row[1] != "cue" for row in sp["world"]["pending"]):
            problems.append(f"O12 {n}")
        if conn_weights(sp) != w[RULE[n]] or b["sigma_p_e_sha256"][n] != _sha(sp) \
                or sp["interventions"] != {"active": [], "frozen": {}} or rec[n]["history"] != []:
            problems.append(f"O12 {n}: W・Σ")
    # O6：境界の順序と差の目録
    six = sorted(order)
    want = [["S0", n, p_e, "advance_to", {"from": 0}] for n in BODIES]
    want += [["S1", n, p_e, "read_weights_and_sigma", None] for n in BODIES]
    want += [["S2", n, p_e, "clone", {"from": "B_" + RULE[n]}] for n in CLONES]
    want += [["S3", n, p_e, "transplant", {"to": ("W_" + U_WEIGHTS[n]) if U_WEIGHTS[n] in ACTIONS else U_WEIGHTS[n],
                                           "intervention_state_at_transplant": {"active": [], "frozen": {}}}]
             for n in CLONES if n not in NOT_TRANSPLANTED]
    want += [["S3'", n, p_e, "switch_world", {"respond": False}] for n in CLONES if n in NO_FEEDBACK]
    want += [["S4", n, p_e, "declare", {"FREEZE": six, "trace_policy": "advance"}] for n in CLONES]
    want += [["S5", n, end, "advance_to", {"from": p_e}] for n in BODIES + CLONES]
    if b["steps"] != want:
        problems.append("O6: S0〜S5")
    freeze = [["FREEZE", six, "advance"]]
    for n in CLONES:
        sa, sb = b["sigma_a"][n], b["sigma_b"][n]
        home = b["sigma_a"]["G_" + RULE[n] + "_W" + RULE[n]]
        if sa["pulse"] != p_e or sb["pulse"] != p_e or sa["interventions"] != {"active": [], "frozen": {}}:
            problems.append(f"O6 {n}: (a) の Pulse・介入")
        if conn_weights(sa) != values[U_WEIGHTS[n]]:
            problems.append(f"O6 {n}: (a) の重み")
        if _with_weights(sa, conn_weights(home), respond=True) != _with_weights(home, conn_weights(home)) \
                or sa["world"]["rule"]["respond"] is not (n not in NO_FEEDBACK):
            problems.append(f"O6 {n}: (a) の差の目録")
        if _with_weights(home, {}) != _with_weights(b["sigma_p_e"]["B_" + RULE[n]], {}):
            problems.append(f"O6 {n}: (a) の複製の元")
        frozen = {cid: {"weight": v["weight"], "pre_trace": v["pre_trace"], "post_trace": v["post_trace"], "policy": "advance"}
                  for cid, v in sb["connections"].items()}
        if sb["interventions"] != {"active": freeze, "frozen": frozen} \
                or _without(sa, [("interventions",)]) != _without(sb, [("interventions",)]):
            problems.append(f"O6 {n}: (b)")
        if rec[n]["history"] != [[p_e, "S4", freeze]]:
            problems.append(f"O6 {n}: 介入の履歴")
        # O7：U のすべての Pulse で、6 本の重みが宣言の値
        target = [values[U_WEIGHTS[n]][cid] for cid in order]
        rows = rec[n]["pulse_weights"]
        if [p for p, _x in rows] != list(range(p_e + 1, end + 1)) or any(x != target for _p, x in rows):
            problems.append(f"O7 {n}")
        # O5：E は複製の元と同じ
        src = rec["B_" + RULE[n]]
        if rec[n]["layer_a"][:e] != src["layer_a"][:e] or [x for x in rec[n]["layer_b"] if x[0] <= p_e] \
                != [x for x in src["layer_b"] if x[0] <= p_e]:
            problems.append(f"O5 {n}: E")
    # O8：恒等（自分の値の移植、W^{A1} ＝ W^{A2} なら他方の重み）
    keys = ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end")
    for x, y in PAIRS_SE_T4 + (PAIRS_SE_T7 if w["A1"] == w["A2"] else []):
        if any(rec[x][k] != rec[y][k] for k in keys):
            problems.append(f"O8: {x}・{y}")
    # O9：Pulse P_E ＋ 1 の一致（発火・層 A・Unit の内部の状態）と、最初に分かれた Pulse が P_E ＋ 2 以後
    for x, y in PAIRS_SE_T5:
        fx, fy = rec[x]["sigma_after_first"], rec[y]["sigma_after_first"]
        same_first = Counter(u for p, u in rec[x]["activity"] if p == p_e + 1) == \
            Counter(u for p, u in rec[y]["activity"] if p == p_e + 1)
        split = first_split(rec[x]["activity"], rec[y]["activity"], p_e + 1, end)
        if fx["pulse"] != p_e + 1 or fy["pulse"] != p_e + 1 or fx["units"] != fy["units"] or fx["exit"] != fy["exit"] \
                or not same_first or (split is not None and split < p_e + 2) \
                or [d[:2] + d[3:] for d in fx["drives"]] != [d[:2] + d[3:] for d in fy["drives"]]:
            problems.append(f"O9: {x}・{y}")
    # O10：帰還の対は、最初の U の結果の刺激の前まで同じ
    for x, y in PAIRS_SE_T6:
        first = min((row[3] for row in rec[x]["world_end"]["reserved"] if row[1] == "consequence" and row[3] > p_e),
                    default=end + 1)
        before = [k for k in ("activity", "sensory", "layer_b", "delta_log")
                  if [v for v in rec[x][k] if v[0] < first] != [v for v in rec[y][k] if v[0] < first]]
        closed = [[r for r in rec[z]["layer_a"] if (r["decision_pulse"] if r["decision_pulse"] is not None else r["close"]) < first]
                  for z in (x, y)]
        if before or closed[0] != closed[1]:
            problems.append(f"O10: {x}・{y}")
    # O11：範囲と F1（W と、移植の後の 14 系）。端の値が事前登録の値
    cid_of = role_cids(roles)
    if run["X"] != {k: {cid_of[r]: v for r, v in PREREGISTERED["extremes"][k].items()} for k in ("X1", "X2")}:
        problems.append("O11: X1・X2")
    if not all(f1_ok(w[c]) for c in ACTIONS) or not all(f1_ok(conn_weights(b["sigma_a"][n])) for n in CLONES):
        problems.append("O11: 範囲・F1")
    # O13：B′^{A1} と B^{A1} の完全な一致（値が主、SHA-256 は補助）
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
    """写しの中身全体の、正規化した JSON の SHA-256（PROTOCOL_JSON_SHA256 と同じ正規化）。"""
    text = json.dumps(proto, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def protocol_problems(runs: dict, protocol_file: Path = PROTOCOL_FILE) -> list[str]:
    """全個体の meta の protocol の写しが、そろってあり、確定済みの protocol.yaml と PREREGISTERED に結び付くこと。"""
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
        if meta.get("mode") == "formal" and runs[s].get("run", {}).get("plan") != PREREGISTERED["formal_plan"]:
            problems.append(f"seed {s}: 本番の Plan が事前登録の値と違う")
    if len(copies) > 1 or len(shas) > 1:
        problems.append("個体によって meta の protocol の写しが違う")
    if len(copies) == 1:
        problems += [f"protocol の写し：{p}" for p in _preregistered_values(json.loads(next(iter(copies))))]
    return problems


def _preregistered_values(proto: dict) -> list[str]:
    """写しの中の、判定に関わる値と PREREGISTERED の照合。k₂(m) は、二項から求め直した値と照らす。"""
    out = []
    pr = PREREGISTERED
    try:
        jt, tl, br, j = proto["judgment"]["J_T"], proto["timeline"], proto["brain"], proto["judgment"]
        if (proto["experiment"], proto["kind"]) != (pr["experiment"], pr["kind"]):
            out.append("experiment・kind")
        if jt["min_population"] != pr["min_population"] or j["outcomes"] != pr["outcomes"]:
            out.append("J_T.min_population・outcomes")
        if _number(jt["alpha"]["per_direction"]) != pr["alpha_per_direction"] \
                or _number(jt["alpha"]["two_sided"]) != pr["alpha_two_sided"]:
            out.append("J_T.alpha")
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
        if proto["systems"]["per_individual"] != pr["per_individual"]:
            out.append("systems.per_individual")
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
                           "J_T": {k: j["J_T"][k] for k in ("m_nonzero", "m_def", "counts", "status", "direction", "k2")},
                           "E_T": {"m_def": est["m_def"], "p_nz_count": est["p_nz"]["count"],
                                   "p_any_count": est["p_any"]["count"], "cancellations": est["cancellations"]}}}


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
        if len(seeds) != PREREGISTERED["individuals"]:
            problems.append(f"本番の個体の数が {PREREGISTERED['individuals']} ではない")
    elif not seeds:
        problems.append("seed がない")
    return problems


def read_directory(out: Path) -> tuple[dict, dict, list[str]]:
    """出力先の seeds/ を、guard・解析の道具に頼らずに読む。(runs, 記録, 食い違い) を返す。"""
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
