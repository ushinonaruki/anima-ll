"""実験 0043 の記録の解析（確定した事前登録 v0.2 に従う。正本は README・protocol.yaml。#200 merge `8fee59e`）。

0039〜0042 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、raw の meta と開始・終了の記録の結び付き、結果の写しの照合）を引き継ぐ
（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid。
   raw の meta の測定の commit・protocol の SHA-256・seed を、開始・終了の記録と直接照らす（provenance_problems）
2. 操作の確認 O2〜O15（README §8）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   成り立たなかった確認だけを報告し、判定・推定・記述を計算・表示しない（README §4.9）。O1 は、run.py が seed に触れる前に測定の commit で
   走らせた契約テストの記録を確かめる（o1_check）
3. 判定（README §3〜§6）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 個体ごと：作った系の窓の数と A1 の割合 s（分数）、§3.2 の量（事前登録の analysis.py の quantities）、§4.1 の値の区分
     （analysis.py の value_class。範囲の外 → s が定まらない → 構造上の 0 → 測った 0 → 0 でない）、§4.2 の合算の条件、§4.3 の分け方、
     §6.2 の比べへの適格、k*、札、δ(e)、命題 S-1 の札
   - J_C（k ＝ 2）：C_2 が定まり 0 でない個体の数 m≠ が 10 未満なら判定不能（閾値と比べない）。向きごとの個体の数 ≥ k₂(m≠) で成立
   - E_C：p_nz・p_any・p_＋・p_−（分母 m_def）、p_dir（分母 m≠）と Clopper–Pearson の 95%、打ち消しの数、|C_2| の分布、定まらない個体の数。
     分母が 0 の割合・区間は定めない
   - §6 の必ず報告する記述と R1〜R9（判定に使わない）
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0043_as2b_natural_difference_scaling/analyze.py                    # 本番（data/experiments/0043）
  python experiments/0043_as2b_natural_difference_scaling/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
  python experiments/0043_as2b_natural_difference_scaling/analyze.py --verify-copy <写し>   # 本番の出力先と写しの照合
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
# 確定済みの事前登録の正本（v0.2、#200 merge `8fee59e`）。生の記録の meta に保存した protocol の写しと SHA-256 を、これと照らす
PROTOCOL_SHA256 = hashlib.sha256((REPO / PROTOCOL_PATH).read_bytes()).hexdigest()
PROTOCOL_AS_STORED = json.loads(json.dumps(PROTOCOL))      # raw は JSON なので、写しは JSON を通した形で照らす
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0043")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure",) + tuple(f"O{i}" for i in range(2, 16))
REPORT, LOG = "report.json", "analysis_log.jsonl"
CONTRACT_TESTS = tuple(PROTOCOL["tools"]["contract_tests"]) + ("tests/integration/test_as2b_natural_difference_scaling_0043.py",)
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
AX = load(f"analysis_{EXPERIMENT}_analyze", REPO / HERE / "analysis.py")     # 事前登録の解析（量・区分・重みの算術・E_S）
A, AS1 = M.A, M.AS1
W_MIN = float(PROTOCOL["brain"]["w_min"])
W_MAX = float(PROTOCOL["brain"]["w_max"])
W0 = float(PROTOCOL["brain"]["initial_weight_w0"])
F1_TOLERANCE = float(PROTOCOL["f1_tolerance"])                               # O11（README §8）
MIN_M = int(PROTOCOL["judgment"]["J_C"]["min_population"])
K0 = int(PROTOCOL["judgment"]["J_C"]["level"])
FORMAL_LEVELS = M.protocol_levels(PROTOCOL)
GATE_DECLARATION, GATE_SHA256 = M.gate_declaration(PROTOCOL)
E_S = AX.silence_bound(AX.c0_values(), AX.gate_set())["E_S"]                # 命題 S-1（README §7.2）。札だけに使う
OUTCOMES = (*A.ACTION_IDS, A.TIE, A.NONE)
SIGNS = ("+", "-", "0")
SOURCES = ("source1", "source2")
BG = M.BACKGROUNDS
DEFINED = AX.DEFINED_CLASSES                    # 区分 3〜5（構造上の 0・測った 0・0 でない）
OTHER_QUANTITIES = ("T_A1", "T_A2", "T", "S_A1", "S_A2", "S", "D", "Z_A1", "Z_A2")
INDIVIDUAL_CLASSES = ("plus", "minus", "structural_zero", "both_zero", "cancellation", "undefined")
STRUCTURAL_LABELS_C = ("Z-1", "Z-2", "identity", "rounding_coincidence")
STRUCTURAL_LABELS_DU = ("delta_zero", "rounding_coincidence")
INELIGIBLE_REASONS = ("C_out_of_range", "Du_out_of_range", "s_undefined", "C_structural_zero", "Du_structural_zero")
NOTES = {"estimate": "estimate only; no threshold; not a judgment (README section 4.5)",
         "p_nz": "share of individuals whose summed C_2 is nonzero; not the share whose choice changed (cancellations are C_2 = 0)",
         "p_any": "share of individuals in which at least one background has C_2_c != 0; descriptive",
         "prominence": "report m_nonzero / m_def, p_nz and p_any with their intervals with the same prominence as the J_C direction",
         "artificial": "k >= 2 weights are artificial (the natural difference stretched); never a statement about natural weights (README section 0.4)",
         "levels": "levels other than k0 = 2 are descriptive; differences between levels include the change of the surviving individuals (README section 6.1)",
         "comparison": "C_k (rule meaning) and D^u_k (weight-direction meaning) have different sign meanings; only tables split by the sign of delta(e) are shown; only the magnitude of delta is matched (README section 6.2)",
         "R8": "Clopper-Pearson 95% intervals are in judgment.J_C, estimate and descriptive"}


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def levels_of(run: Mapping) -> tuple[int, ...]:
    return tuple(int(k) for k in run["levels"])


def built_of(run: Mapping) -> tuple[str, ...]:
    """作った複製の系（clone_names の順）。"""
    return tuple(n for n in M.clone_names(levels_of(run)) if n in run["clones"])


def systems_of(run: Mapping) -> tuple[str, ...]:
    return M.BODIES + (M.RERUN,) + built_of(run)


def record_of(run: Mapping, name: str) -> Mapping:
    return run["clones"][name] if name in run["clones"] else run["bodies"][name]


# ---- 量（README §3） -------------------------------------------------------------------------------

def sign(x) -> str:
    return "+" if x > 0 else ("-" if x < 0 else "0")


def window_counts(layer_a: list, lo: int, hi: int) -> dict:
    """窓 lo〜hi の結末の数（README §3.1）。"""
    outs = [r["outcome"] for r in layer_a if lo <= r["window"] <= hi]
    c = Counter(outs)
    return {"windows": len(outs), "decided": c["A1"] + c["A2"], "A1": c["A1"], "A2": c["A2"],
            "tie": c[A.TIE], "none": c[A.NONE]}


def share(counts: Mapping) -> Fraction | None:
    """A1 の割合 s ＝ #A1／(#A1 ＋ #A2)。決まった窓が 0 なら定まらない（0 にしない）。"""
    return Fraction(counts["A1"], counts["decided"]) if counts["decided"] else None


def k_star(layer_a: list, e: int) -> int | None:
    """E の共通の部分の最初の決まった窓（窓 1〜e の中。なければ None）。README §3.4。"""
    return next((r["window"] for r in layer_a if r["window"] <= e and r["outcome"] in A.ACTION_IDS), None)


def zero_label(layer_a: list, e: int) -> str | None:
    """k* がない個体の札：Z-1（E のすべての窓が発火なし）・Z-2（引き分けがあり、決まった窓はない）。"""
    if k_star(layer_a, e) is not None:
        return None
    outs = [r["outcome"] for r in layer_a if r["window"] <= e]
    return "Z-1" if all(o == A.NONE for o in outs) else "Z-2"


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
    """窓の結末が最初に違った窓の番号（違わなければ None。R6）。"""
    return next((x["window"] for x, y in zip(la, lb) if x["outcome"] != y["outcome"]), None)


def _ends(cid: str) -> tuple[str, str]:
    src, tgt = cid.split(".main->")
    return src, tgt


def pair_deviation(weights: Mapping[str, float]) -> Fraction:
    """3 つの組の、2 本の重みの丸めた後の和と w_max の差の絶対値の最大（保存した binary64 の値の正確な分数で）。"""
    sums: dict[str, Fraction] = {}
    for cid, w in weights.items():
        key = "|".join(sorted(_ends(cid)))
        sums[key] = sums.get(key, Fraction(0)) + Fraction(w)
    return max(abs(s - Fraction(W_MAX)) for s in sums.values())


def _role_names(roles: Mapping) -> dict[str, str]:
    return {roles["cue"]: "cue", roles["source1"]: "source1", roles["source2"]: "source2"}


def role_cids(roles: Mapping) -> dict[str, str]:
    return M.role_cids(roles)


def by_role(roles: Mapping, weights: Mapping[str, float]) -> dict[str, float]:
    """接続の ID → 重み を、役の名前 → 重み にする。"""
    return {r: weights[cid] for r, cid in role_cids(roles).items()}


def margin(unit_state: Mapping) -> float:
    """余裕 g ＝ c／(1 − λ) − θ（出生時の Unit の値から。README §7.2）。"""
    d = unit_state["dynamics"]
    return d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]


def _frac(x: Fraction | None) -> dict | None:
    return None if x is None else {"num": x.numerator, "den": x.denominator, "value": float(x)}


def _quantity(x) -> dict:
    return {"value": _frac(x), "sign": None if x is None else sign(x)}


def delta_of(roles: Mapping, w_a1: Mapping[str, float], w_a2: Mapping[str, float]) -> Fraction:
    """δ(e)（0041 §3.2 の定義）：保存した binary64 の値の正確な分数で。"""
    c = role_cids(roles)
    a1 = Fraction(w_a1[c["C_to_source1"]]) - Fraction(w_a2[c["C_to_source1"]])
    a2 = Fraction(w_a1[c["C_to_source2"]]) - Fraction(w_a2[c["C_to_source2"]])
    return a1 - a2


def written_out_quantities(levels, s: Mapping) -> dict:
    """README §3.2 の定義の書き下し（analysis.py の quantities と独立に書く。段の組を引数に取る。O14 の照合にも使う）。
    s は系の名前 → A1 の割合（作らない系・定まらない系は None）。"""
    def d(a, b):
        return None if s.get(a) is None or s.get(b) is None else s[a] - s[b]

    def add(x, y):
        return None if x is None or y is None else x + y

    def d_c(c, a, b):                                       # s_c：c ＝ A1 なら s、A2 なら 1 − s
        x = d(a, b)
        return x if x is None or c == "A1" else -x
    q = {}
    for k in levels:
        for c in BG:
            q[f"C{k}_{c}"] = d(f"G_{c}_P{k}", f"G_{c}_M{k}")
            q[f"up{k}_{c}"] = d(f"G_{c}_P{k}", f"G_{c}_base")
            q[f"dn{k}_{c}"] = d(f"G_{c}_base", f"G_{c}_M{k}")
            q[f"Du{k}_{c}"] = d(f"G_{c}_UP{k}", f"G_{c}_UM{k}")
        q[f"C{k}"] = add(q[f"C{k}_A1"], q[f"C{k}_A2"])
        q[f"C{k}_any"] = None if q[f"C{k}"] is None else (q[f"C{k}_A1"] != 0 or q[f"C{k}_A2"] != 0)
        q[f"Du{k}"] = add(q[f"Du{k}_A1"], q[f"Du{k}_A2"])
    q["T_A1"] = d("G_A1_base", "G_A1_M1") if 1 in levels else None
    q["T_A2"] = d("G_A2_P1", "G_A2_base") if 1 in levels else None
    q["T"] = add(q["T_A1"], q["T_A2"])
    q["S_A1"], q["S_A2"] = d("G_A1_X1", "G_A1_X2"), d("G_A2_X1", "G_A2_X2")
    q["S"] = add(q["S_A1"], q["S_A2"])
    q["D"] = d("B_A1", "B_A2")
    q["Z_A1"] = d_c("A1", "B_A1", "G_A1_base")
    q["Z_A2"] = d_c("A2", "B_A2", "G_A2_base")
    return q


def quantities_of(levels, s: Mapping) -> dict:
    """§3.2 の量。本番の段の組では、事前登録の analysis.py の quantities をそのまま使う（O14 が書き下しと照らす）。"""
    if tuple(levels) == AX.LEVELS:
        return AX.quantities({n: s.get(n) for n in AX.FULL_BODIES + AX.U_SYSTEMS if n != M.RERUN})
    return written_out_quantities(levels, s)


def _endpoint_weights(run: Mapping, name: str):
    return run["endpoints"][name]["weights"]


def classes_for(run: Mapping, s: Mapping, c: str, k: int, kind: str) -> tuple:
    """(個体, c, k) の C（kind ＝ "C"）か D^u（"Du"）の、§4.1 の値の区分と値（analysis.py の value_class）。"""
    plus, minus = (f"G_{c}_P{k}", f"G_{c}_M{k}") if kind == "C" else (f"G_{c}_UP{k}", f"G_{c}_UM{k}")
    ep, em = run["endpoints"][plus], run["endpoints"][minus]
    identical = ep["in_range"] and em["in_range"] and ep["weights"] == em["weights"]
    return AX.value_class(ep["in_range"], em["in_range"], s.get(plus), s.get(minus), identical)


def base_class(x: Fraction | None) -> str:
    if x is None:
        return "undefined"
    return "0" if x == 0 else ("1" if x == 1 else "between")


def individual(run: Mapping) -> dict:
    """1 個体の量（README §3・§4・§6）。生の記録だけから計算する。"""
    plan = M.Plan(**run["plan"])
    e, k_all, p_e, end = plan.e_windows, plan.count, plan.p_e, plan.end
    levels = levels_of(run)
    roles = run["roles"]
    names = _role_names(roles)
    systems = systems_of(run)
    built = built_of(run)
    layer = {n: record_of(run, n)["layer_a"] for n in systems}
    counts_e = {n: window_counts(layer[n], 1, e) for n in systems}
    counts_u = {n: window_counts(layer[n], e + 1, k_all) for n in systems}
    s_u = {n: share(counts_u[n]) for n in systems}
    s_all = {n: s_u.get(n) for n in M.BODIES + M.clone_names(levels)}            # 作らない系は None
    q = quantities_of(levels, s_all)
    ks = k_star(layer["B_A1"], e)
    w = run["boundary"]["W"]
    e_zero = w["A1"] == w["A2"]                                                   # 6 本ともビット単位で同じ
    delta = delta_of(roles, w["A1"], w["A2"])
    zl = zero_label(layer["B_A1"], e)

    def c_label(cls: str) -> str | None:
        if cls != "structural_zero":
            return None
        return zl if ks is None else ("identity" if e_zero else "rounding_coincidence")

    def du_label(cls: str) -> str | None:
        if cls != "structural_zero":
            return None
        return "delta_zero" if delta == 0 else "rounding_coincidence"

    per_level = {}
    for k in levels:
        cc = {c: classes_for(run, s_all, c, k, "C") for c in BG}
        dd = {c: classes_for(run, s_all, c, k, "Du") for c in BG}
        c_val = AX.individual_value(cc["A1"], cc["A2"])
        d_val = AX.individual_value(dd["A1"], dd["A2"])
        if c_val != q[f"C{k}"] or d_val != q[f"Du{k}"]:
            raise ValueError("値の区分と合算の値が、§3.2 の量と合わない")            # O14 で確かめる。ここに来ない
        if c_val is None:
            cls = "undefined"
        elif c_val > 0:
            cls = "plus"
        elif c_val < 0:
            cls = "minus"
        elif cc["A1"][0] == "structural_zero" and cc["A2"][0] == "structural_zero":
            cls = "structural_zero"
        elif cc["A1"][1] == 0 and cc["A2"][1] == 0:
            cls = "both_zero"
        else:
            cls = "cancellation"
        elig = {c: AX.comparison_eligible(cc[c][0], dd[c][0]) for c in BG}
        reasons = {}
        for c in BG:
            r = []
            if cc[c][0] == "out_of_range":
                r.append("C_out_of_range")
            if dd[c][0] == "out_of_range":
                r.append("Du_out_of_range")
            if "s_undefined" in (cc[c][0], dd[c][0]):
                r.append("s_undefined")
            if cc[c][0] == "structural_zero":
                r.append("C_structural_zero")
            if dd[c][0] == "structural_zero":
                r.append("Du_structural_zero")
            reasons[c] = r
        per_level[str(k)] = {
            "C": {"value": _quantity(c_val), "class": cls, "any": q[f"C{k}_any"],
                  **{c: {"class": cc[c][0], "value": _quantity(cc[c][1]), "label": c_label(cc[c][0])} for c in BG}},
            "Du": {"value": _quantity(d_val),
                   "structural": any(dd[c][0] == "structural_zero" for c in BG),
                   **{c: {"class": dd[c][0], "value": _quantity(dd[c][1]), "label": du_label(dd[c][0])} for c in BG}},
            "eligible": {**elig, "individual": all(elig.values())},
            "ineligible_reasons": reasons,
            "up": {c: _quantity(q[f"up{k}_{c}"]) for c in BG},
            "dn": {c: _quantity(q[f"dn{k}_{c}"]) for c in BG},
        }
    cid_role = {cid: role for role, cid in role_cids(roles).items()}
    # 命題 S-1 の札（出生時の値から）と、それに反する発火の有無（作ったどの系でも）
    units = run["birth_units"]
    g = {names[u]: margin(units[u]) for u in names}
    silent = {role: g[role] < -E_S for role in SOURCES}
    fired = {u for n in systems for _, u in record_of(run, n)["activity"]}
    violations = sorted(role for role in SOURCES if silent[role] and roles[role] in fired)
    # R5：受けた結果の刺激（世界の予約の記録から）
    consequences = {}
    for n in M.BODIES + built:
        rows = [r for r in record_of(run, n)["world_end"]["reserved"] if r[1] == A.CONSEQUENCE]
        c = M.rule_of(n)
        consequences[n] = {"E": sum(1 for r in rows if r[3] <= p_e), "U": sum(1 for r in rows if r[3] > p_e),
                           "decided_windows_of_c": {"E": counts_e[n][c], "U": counts_u[n][c]}}
    # R6：最初に分かれた Pulse・窓
    divergence = {"B_A1|B_A2": {"firing": first_divergence(run["bodies"]["B_A1"]["activity"],
                                                           run["bodies"]["B_A2"]["activity"], 1, end),
                                "window": first_window_divergence(layer["B_A1"], layer["B_A2"])}}
    for a, b in r6_pairs(run):
        divergence[f"{a}|{b}"] = {"firing": first_divergence(run["clones"][a]["activity"], run["clones"][b]["activity"],
                                                             p_e + 1, end),
                                  "window": first_window_divergence(layer[a], layer[b])}
    # R7：発火の数（役ごと）。複製の系の来歴のログは複製の後（U）だけを持つので、複製の系の E は、複製の元の同じ背景の本体の
    # E の記録（共通の履歴）から数え直し、その由来を E_from に書く（新しい測定・ログは足さない。#201 初回審査の修正必須 3）
    firing = {}
    for n in systems:
        act = record_of(run, n)["activity"]
        own = n in M.BODIES or n == M.RERUN
        source = n if own else M.background_of(n)
        history = act if own else run["bodies"][source]["activity"]
        firing[n] = {"E": {names[u]: sum(1 for p, x in history if x == u and p <= p_e) for u in names},
                     "U": {names[u]: sum(1 for p, x in act if x == u and p > p_e) for u in names},
                     "E_from": source}
    main = per_level[str(K0)]["C"] if str(K0) in per_level else {"class": "undefined"}
    return {
        "roles": {k: roles[k] for k in ("cue", "source1", "source2")},
        "birth": {names[u]: {"threshold": units[u]["dynamics"]["threshold"],
                             "intrinsic_drive": units[u]["dynamics"]["intrinsic_drive_per_second"], "margin_g": g[names[u]]}
                  for u in names},
        "S1": {"silent_source": silent, "violations": violations},
        "k_star": ks,
        "zero_label": zl,
        "e_zero": e_zero,
        "delta_e": _quantity(delta),
        "class": main["class"],
        "levels": per_level,
        "quantities": {name: _quantity(q[name]) for name in OTHER_QUANTITIES},
        "base_class": {c: base_class(s_u.get(f"G_{c}_base")) for c in BG},
        "built": list(built),
        "not_built": {n: run["endpoints"][n]["out_of_range"] for n in M.endpoint_names(levels) if n not in run["clones"]},
        "counts_E": counts_e,
        "counts_U": counts_u,
        "s_U": {n: _frac(s_u[n]) for n in systems},
        "s_E": {n: _frac(share(counts_e[n])) for n in M.BODIES},
        "W": {c: {cid_role[cid]: w[c][cid] for cid in sorted(cid_role)} for c in BG},
        "W_abs_diff": {cid_role[cid]: float(abs(Fraction(w["A1"][cid]) - Fraction(w["A2"][cid]))) for cid in sorted(cid_role)},
        "pair_deviation": {c: float(pair_deviation(w[c])) for c in BG},
        "clone_pair_deviation": float(max(pair_deviation(_weights_of(run["boundary"]["sigma_a"][n])) for n in built)),
        "consequences": consequences,
        "first_divergence": divergence,
        "firing": firing,
    }


def r6_pairs(run: Mapping) -> list[tuple[str, str]]:
    """R6 の対：同じ背景の基の系と作った各複製の系、二つの端の系の対（両方を作ったとき）。"""
    built = set(built_of(run))
    pairs = []
    for c in BG:
        base = f"G_{c}_base"
        pairs += [(base, n) for n in built_of(run) if n != base and M.parse_clone(n)["background"] == c]
        for k in levels_of(run):
            for a, b in ((f"G_{c}_P{k}", f"G_{c}_M{k}"), (f"G_{c}_UP{k}", f"G_{c}_UM{k}")):
                if a in built and b in built:
                    pairs.append((a, b))
        pairs.append((f"G_{c}_X1", f"G_{c}_X2"))
    return pairs


# ---- 判定と推定（README §4・§5） -----------------------------------------------------------------------------

def binom_upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, j) for j in range(k, m + 1)), 2 ** m)


def k2_of_m(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと。分数で厳密に）。"""
    alpha = Fraction(str(PROTOCOL["judgment"]["J_C"]["alpha"]["per_direction"]))
    return next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """二項の和の二分法（0036〜0042 と同じ）。"""
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
    """§5.2：分母が 1 以上なら必ず計算する（判定に使わない）。0 なら定めない（0 にしない）。"""
    if n < 1:
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "denominator = 0"}
    return {"computed": True, "interval": list(clopper_pearson(x, n)), "numerator": x, "denominator": n}


def _part(x: int, n: int) -> dict:
    return {"count": x, "denominator": n, "proportion": x / n if n else None, "interval": interval(x, n)}


def five_numbers(values: list) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null。0036〜0042 と同じ）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def _level(v: Mapping, k) -> Mapping:
    return v["levels"][str(k)]


def judge(individuals: Mapping[str, Mapping]) -> dict:
    """J_C（README §4.4・§4.9）。数は、有効な結果では判定の成否に依らず必ず出す。"""
    vals = [_level(v, K0)["C"] for v in individuals.values()]
    plus = sum(1 for v in vals if v["class"] == "plus")
    minus = sum(1 for v in vals if v["class"] == "minus")
    defined = sum(1 for v in vals if v["class"] != "undefined")
    m = plus + minus
    counts = {"+": plus, "-": minus, "0": defined - m, "undefined": len(vals) - defined}
    if m < MIN_M:                                    # 判定不能：閾値と比べない
        j = {"status": "inconclusive", "direction": None, "k2": None, "tail_probability": None}
        outcome = "inconclusive"
    else:
        k = PROTOCOL["judgment"]["k2_of_m"][m]
        if k != k2_of_m(m):
            raise ValueError(f"protocol の k₂({m}) ＝ {k} が二項の計算と違う")
        direction = "+" if plus >= k else ("-" if minus >= k else None)
        j = {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
             "tail_probability": float(binom_upper_tail(m, k))}
        outcome = {"+": "plus", "-": "minus", None: "not_established"}[direction]
    status = AX.judgment_status(True, plus, minus)
    if status != outcome:
        raise ValueError("判定の出力が、事前登録の judgment_status と違う")
    return {"J_C": {"level": K0, "m_nonzero": m, "m_def": defined, "counts": counts} | j, "outcome": outcome,
            "prominence": NOTES["prominence"], "artificial": NOTES["artificial"]}


def _estimate_over(cs: list[Mapping]) -> dict:
    """C の個体の記録（_level(v, k)["C"]）の列から、E_C の形の推定。"""
    defined = [v for v in cs if v["class"] != "undefined"]
    m_def = len(defined)
    plus = sum(1 for v in defined if v["class"] == "plus")
    minus = sum(1 for v in defined if v["class"] == "minus")
    m = plus + minus
    anyc = sum(1 for v in defined if v["any"] is True)
    cancel = sum(1 for v in defined if v["class"] == "cancellation")
    return {"m_def": m_def, "m_nonzero": m,
            "p_nz": _part(m, m_def), "p_any": _part(anyc, m_def),
            "p_plus": _part(plus, m_def), "p_minus": _part(minus, m_def), "p_dir": _part(plus, m),
            "cancellations": cancel,
            "classes": {c: sum(1 for v in cs if v["class"] == c) for c in INDIVIDUAL_CLASSES}}


def _undefined_reasons(v: Mapping, k) -> dict:
    lv = _level(v, k)["C"]
    return {c: lv[c]["class"] for c in BG if lv[c]["class"] not in DEFINED}


def estimate(individuals: Mapping[str, Mapping]) -> dict:
    """E_C（README §4.5。判定ではない。閾値を置かない）。"""
    vals = list(individuals.values())
    out = _estimate_over([_level(v, K0)["C"] for v in vals])
    defined = [v for v in vals if _level(v, K0)["C"]["class"] != "undefined"]
    abs_c = [abs(_level(v, K0)["C"]["value"]["value"]["value"]) for v in defined]
    undefined = [v for v in vals if _level(v, K0)["C"]["class"] == "undefined"]
    out |= {"level": K0,
            "abs_C2": {"defined": five_numbers(abs_c), "nonzero": five_numbers([x for x in abs_c if x != 0])},
            "undefined": {"count": len(undefined),
                          "by_reason_and_background": {f"{c}:{r}": sum(1 for v in undefined if _undefined_reasons(v, K0).get(c) == r)
                                                       for c in BG for r in ("out_of_range", "s_undefined")}},
            "notes": {k: NOTES[k] for k in ("estimate", "p_nz", "p_any", "prominence", "artificial")}}
    return out


UNDEFINED_REASONS = ("out_of_range", "s_undefined")


def table_of(values: list, reasons: list | None = None) -> dict:
    """一つの量の、README §6 の共通の報告の形（記述。検定しない）：定まる個体の数、「＋」「−」「0」の数、それぞれの割合と区間（分母は
    その量の分母）、0 でない中の＋の割合と区間、分布（最小・四分位・最大）、定まらない個体の数と理由の内訳。
    values は _quantity の列（定まらないものを含む）。reasons は同じ順の、定まらない理由の集合の列（定まる量は空）。reasons を省くのは、
    定まらない個体を含まない表（理由はすべて 0）と、分布だけを使う R3 だけ（定まらない個体があれば理由は null）。
    理由ごとの数は個体の数で、一つの個体に二つの理由（二つの背景で別の理由）があれば両方に数える。定まらない個体の数とは別に示す。"""
    defined = [x for x in values if x["sign"] is not None]
    n = len(defined)
    counts = {s: sum(1 for x in defined if x["sign"] == s) for s in SIGNS}
    nz = counts["+"] + counts["-"]
    vs = [x["value"]["value"] for x in defined]
    if reasons is None:                              # 理由を渡さない表は、定まらない個体を含まない（含めば理由を null にする）
        why = None if n < len(values) else {r: 0 for r in UNDEFINED_REASONS}
    else:
        if len(reasons) != len(values) or any(bool(r) != (x["sign"] is None) for x, r in zip(values, reasons)):
            raise ValueError("定まらない理由の列が、量の列と合わない")
        why = {r: sum(1 for w in reasons if r in w) for r in UNDEFINED_REASONS}
    return {"defined": n, "undefined": len(values) - n, "counts": counts,
            "proportion": {s: _part(counts[s], n) for s in SIGNS},
            "plus_among_nonzero": _part(counts["+"], nz),
            "distribution": five_numbers(vs), "abs_distribution": five_numbers([abs(x) for x in vs]),
            "undefined_reasons": why}


def why_undefined(v: Mapping, pairs) -> set[str]:
    """差の組（系の名前の対）の列を使う量の、定まらない理由の集合（§4.1 の順：その差の系の一方でも作らない系なら範囲の外、どちらも
    作った系で s が定まらなければ s が定まらない）。二つの差の和は、それぞれの差の理由を合わせる。定まる量は空。"""
    out = set()
    for pair in pairs:
        made = [n in M.BODIES or n == M.RERUN or n in v["built"] for n in pair]
        if not all(made):
            out.add("out_of_range")
        elif any(v["s_U"].get(n) is None for n in pair):
            out.add("s_undefined")
    return out


def quantity_pairs(name: str) -> list[tuple[str, str]]:
    """README §3.2 の量が使う差の組（片側の差・中心の差・対称な介入の差・T・S・D・Z）。"""
    for prefix in ("up", "dn", "Du", "C"):
        if name.startswith(prefix) and name[len(prefix)].isdigit():
            body = name[len(prefix):]
            k, _, c = body.partition("_")
            bgs = [c] if c else list(BG)
            if prefix == "up":
                return [(f"G_{b}_P{k}", f"G_{b}_base") for b in bgs]
            if prefix == "dn":
                return [(f"G_{b}_base", f"G_{b}_M{k}") for b in bgs]
            head = ("UP", "UM") if prefix == "Du" else ("P", "M")
            return [(f"G_{b}_{head[0]}{k}", f"G_{b}_{head[1]}{k}") for b in bgs]
    fixed = {"T_A1": [("G_A1_base", "G_A1_M1")], "T_A2": [("G_A2_P1", "G_A2_base")],
             "S_A1": [("G_A1_X1", "G_A1_X2")], "S_A2": [("G_A2_X1", "G_A2_X2")], "D": [("B_A1", "B_A2")],
             "Z_A1": [("B_A1", "G_A1_base")], "Z_A2": [("B_A2", "G_A2_base")]}
    fixed |= {"T": fixed["T_A1"] + fixed["T_A2"], "S": fixed["S_A1"] + fixed["S_A2"]}
    return fixed[name]


def cells(pairs: list[tuple[str, str]]) -> dict:
    return {f"{a}{b}": sum(1 for x, y in pairs if x == a and y == b) for a in SIGNS for b in SIGNS}


def _levels_of_report(individuals: Mapping[str, Mapping]) -> list[int]:
    first = next(iter(individuals.values()), None)
    return [] if first is None else sorted(int(k) for k in first["levels"])


def descriptive(individuals: Mapping[str, Mapping]) -> dict:
    """README §6：必ず報告する記述と、比べの分母（検定しない）。"""
    vals = list(individuals.values())
    levels = _levels_of_report(individuals)
    out: dict = {"notes": {k: NOTES[k] for k in ("levels", "comparison", "artificial")}}
    # §6.1 段ごとの C_k
    out["levels"] = {str(k): _estimate_over([_level(v, k)["C"] for v in vals])
                     | {"C": table_of([_level(v, k)["C"]["value"] for v in vals],
                                      [why_undefined(v, quantity_pairs(f"C{k}")) for v in vals])} for k in levels}
    common = sorted(s for s, v in individuals.items() if all(_level(v, k)["C"]["class"] != "undefined" for k in levels))
    out["common_all_levels"] = {"seeds": common, "count": len(common),
                                "by_level": {str(k): _estimate_over([_level(individuals[s], k)["C"] for s in common])
                                             | {"C": table_of([_level(individuals[s], k)["C"]["value"] for s in common])}
                                             for k in levels}}
    oor: dict = {}
    for k in levels:
        for c in BG:
            for kind, (p, mname) in (("natural", ("P", "M")), ("symmetric", ("UP", "UM"))):
                for side, prefix in (("plus", p), ("minus", mname)):
                    name = f"G_{c}_{prefix}{k}"
                    oor[f"{k}|{c}|{kind}|{side}"] = sum(1 for v in vals if name in v["not_built"])
    by_weight = Counter(f"{prefix_kind(n)}|{r}|{side}" for v in vals for n, rows in v["not_built"].items() for r, side in rows)
    out["out_of_range"] = {"systems": oor, "by_weight_name": dict(sorted(by_weight.items())),
                           "nesting_holds": all(nesting_ok(v, levels) for v in vals)}
    out["per_background"] = {}
    for k in levels:
        both = [(_level(v, k)["C"]["A1"]["value"]["sign"], _level(v, k)["C"]["A2"]["value"]["sign"]) for v in vals]
        full = [(a, b) for a, b in both if a is not None and b is not None]
        out["per_background"][str(k)] = {
            c: table_of([_level(v, k)["C"][c]["value"] for v in vals],
                        [why_undefined(v, quantity_pairs(f"C{k}_{c}")) for v in vals]) for c in BG} | {
            "cells_A1_A2": cells(full), "in_both": len(full),
            "only_one_background": {c: table_of([_level(v, k)["C"][c]["value"] for v in vals
                                                 if _level(v, k)["C"][c]["value"]["sign"] is not None
                                                 and _level(v, k)["C"]["A2" if c == "A1" else "A1"]["value"]["sign"] is None])
                                    for c in BG}}
    out["one_sided"] = {str(k): {c: (lambda rows: {"in_both": len(rows), "cells_up_dn": cells(rows)})(
        [(_level(v, k)["up"][c]["sign"], _level(v, k)["dn"][c]["sign"]) for v in vals
         if _level(v, k)["up"][c]["sign"] is not None and _level(v, k)["dn"][c]["sign"] is not None]) for c in BG}
        for k in levels}
    if str(K0) in (str(k) for k in levels):
        out["base_strata"] = {c: {bc: {s: sum(1 for v in vals if v["base_class"][c] == bc
                                              and _level(v, K0)["C"][c]["value"]["sign"] == s) for s in SIGNS}
                                  | {"C_undefined": sum(1 for v in vals if v["base_class"][c] == bc
                                                        and _level(v, K0)["C"][c]["value"]["sign"] is None)}
                                  for bc in ("0", "1", "between", "undefined")} for c in BG}
    # §6.2 δ をそろえた対称な介入の対照と、比べへの適格
    sym = {}
    for k in levels:
        dus = [_level(v, k)["Du"] for v in vals]
        # 割合の分母は、D^u_k が定まり、どちらの背景も構造上の 0 でない個体。構造上の 0 の個体は分母の外で、数を別に示す。
        # 定まらない個体は、表の「定まらない」に理由ごとに数える（構造上の 0 と混ぜない）
        kept = [v for v, d in zip(vals, dus) if not (d["value"]["sign"] is not None and d["structural"])]
        du_table = table_of([_level(v, k)["Du"]["value"] for v in kept], [why_undefined(v, quantity_pairs(f"Du{k}")) for v in kept])
        du_per_bg = {}
        for c in BG:
            rest = [v for v in vals if _level(v, k)["Du"][c]["class"] != "structural_zero"]
            du_per_bg[c] = table_of([_level(v, k)["Du"][c]["value"] for v in rest],
                                    [why_undefined(v, quantity_pairs(f"Du{k}_{c}")) for v in rest]) | {
                "structural_zero": len(vals) - len(rest)}
        eligible = [(s, v) for s, v in individuals.items() if _level(v, k)["eligible"]["individual"]]
        split = {}
        for name, test in (("delta_plus", lambda v: v["delta_e"]["sign"] == "+"), ("delta_minus", lambda v: v["delta_e"]["sign"] == "-")):
            rows = [(_level(v, k)["C"]["value"]["sign"], _level(v, k)["Du"]["value"]["sign"]) for _s, v in eligible if test(v)]
            split[name] = {"count": len(rows), "cells_C_Du": cells(rows)}
        per_bg = {}
        for c in BG:
            rows = [v for v in vals if _level(v, k)["eligible"][c]]
            per_bg[c] = {name: {"count": sum(1 for v in rows if test(v)),
                                "cells_C_Du": cells([(_level(v, k)["C"][c]["value"]["sign"], _level(v, k)["Du"][c]["value"]["sign"])
                                                     for v in rows if test(v)])}
                         for name, test in (("delta_plus", lambda v: v["delta_e"]["sign"] == "+"),
                                            ("delta_minus", lambda v: v["delta_e"]["sign"] == "-"))}
        inel = {c: {r: sum(1 for v in vals if r in _level(v, k)["ineligible_reasons"][c]) for r in INELIGIBLE_REASONS}
                | {"ineligible": sum(1 for v in vals if not _level(v, k)["eligible"][c])} for c in BG}
        # 個体ごと（README §6.2「不適格の (c, k) と個体の数を、理由ごとに」）：同じ理由が両方の背景にあれば個体として 1 回、別の理由は
        # それぞれ数える。不適格な個体の数は、理由ごとの数の和とは別に示す
        inel["individual"] = {r: sum(1 for v in vals if any(r in _level(v, k)["ineligible_reasons"][c] for c in BG))
                              for r in INELIGIBLE_REASONS} | {
            "ineligible": sum(1 for v in vals if not _level(v, k)["eligible"]["individual"])}
        # D^u_k の個体の排他的な分け方（#200 の Gemini 監査への ChatGPT の要件。README §6.2・protocol の must_report.symmetric_control）：
        # 定まらない・どちらの背景も構造上の 0 でない（割合の分母）・一方の背景だけが構造上の 0（背景・札ごと）・両方の背景が構造上の 0。
        # 一方の背景だけが構造上の 0 でも、両方の背景の端の s が定まれば合算の値は定まり、割合の分母と比べの適格からは外す
        partition = {"undefined": 0, "neither_structural": 0,
                     "one_structural": {c: {lab: 0 for lab in STRUCTURAL_LABELS_DU} for c in BG},
                     "both_structural": {lab: 0 for lab in STRUCTURAL_LABELS_DU}}
        for d in dus:
            structural = [c for c in BG if d[c]["class"] == "structural_zero"]
            if d["value"]["sign"] is None:
                partition["undefined"] += 1
            elif not structural:
                partition["neither_structural"] += 1
            elif len(structural) == 1:
                partition["one_structural"][structural[0]][d[structural[0]]["label"]] += 1
            else:                                   # 札は δ(e) だけで決まるので、二つの背景で同じ
                partition["both_structural"][d["A1"]["label"]] += 1
        sym[str(k)] = {"Du": du_table, "Du_per_background": du_per_bg,
                       "Du_defined_with_structural_zero": sum(1 for d in dus if d["value"]["sign"] is not None and d["structural"]),
                       "Du_partition": partition,
                       "Du_structural_labels": {lab: sum(1 for d in dus for c in BG if d[c]["label"] == lab)
                                                for lab in STRUCTURAL_LABELS_DU},
                       "eligible_individuals": len(eligible), "comparison": split, "comparison_per_background": per_bg,
                       "ineligible": inel}
    all_elig = sorted(s for s, v in individuals.items() if all(_level(v, k)["eligible"]["individual"] for k in levels))
    sym["all_levels_eligible"] = {"seeds": all_elig, "count": len(all_elig),
                                  "by_level": {str(k): {name: cells([(_level(individuals[s], k)["C"]["value"]["sign"],
                                                                      _level(individuals[s], k)["Du"]["value"]["sign"])
                                                                     for s in all_elig if individuals[s]["delta_e"]["sign"] == sg])
                                                        for name, sg in (("delta_plus", "+"), ("delta_minus", "-"))}
                                               for k in levels}}
    out["symmetric_control"] = sym
    # §6.3 そのほか
    qt = {name: table_of([v["quantities"][name] for v in vals], [why_undefined(v, quantity_pairs(name)) for v in vals])
          for name in OTHER_QUANTITIES}
    tt = [(v["quantities"]["T_A1"]["sign"], v["quantities"]["T_A2"]["sign"]) for v in vals]
    out["T"] = {"T": qt["T"], "T_A1": qt["T_A1"], "T_A2": qt["T_A2"],
                "cells_A1_A2": cells([(a, b) for a, b in tt if a is not None and b is not None]),
                "note": "0042-type natural swap in this population; never a re-test of 0042 J_T, never merged"}
    out["sensitivity"] = {"S": qt["S"], "S_A1": qt["S_A1"], "S_A2": qt["S_A2"],
                          "note": "midpoint w0 (not W_c); a positive response is not guaranteed; material for reading a negative only"}
    out["natural_pair"] = {"D": qt["D"]}
    out["plasticity_contrast"] = {"Z_A1": qt["Z_A1"], "Z_A2": qt["Z_A2"]}
    out["delta_e"] = table_of([v["delta_e"] for v in vals]) | {
        "delta_zero_with_e_nonzero": sum(1 for v in vals if v["delta_e"]["sign"] == "0" and not v["e_zero"])}
    k0c = {s: _level(v, K0)["C"] for s, v in individuals.items()} if str(K0) in (str(k) for k in levels) else {}
    out["zero_table"] = {
        "structural_zero": {lab: sorted(s for s, c in k0c.items() if c["class"] == "structural_zero"
                                        and c["A1"]["label"] == lab) for lab in STRUCTURAL_LABELS_C},
        "both_zero": sorted(s for s, c in k0c.items() if c["class"] == "both_zero"),
        "cancellation": sorted(s for s, c in k0c.items() if c["class"] == "cancellation"),
        "undefined": {s: {bg: c[bg]["class"] for bg in BG if c[bg]["class"] not in DEFINED}
                      | {"not_built": sorted(n for n in individuals[s]["not_built"]
                                             if M.parse_clone(n)["kind"] == "natural" and M.parse_clone(n)["level"] == K0)}
                      for s, c in sorted(k0c.items()) if c["class"] == "undefined"},
        # 命題 S-1 に反する発火があれば、札の報告を取り下げる（README §7.2）
        "structurally_silent_source": None if any(v["S1"]["violations"] for v in vals) else
        sorted(s for s, v in individuals.items() if any(v["S1"]["silent_source"].values())),
    }
    out["not_made"] = "no cross tables of sign delta(e), sign S or sign T against sign C_k (other than the comparison table); no correlation test"
    return out


def prefix_kind(name: str) -> str:
    p = M.parse_clone(name)
    return f"{p['kind']}|{'plus' if p['side'] == 1 else 'minus'}"


def nesting_ok(v: Mapping, levels) -> bool:
    """作った端の系が、背景・種類・側ごとに段について入れ子（大きい段で作れたなら、小さい段でも作れた）。"""
    built = set(v["built"])
    for c in BG:
        for prefix in ("P", "M", "UP", "UM"):
            seq = [f"G_{c}_{prefix}{k}" in built for k in levels]
            if any(seq[i + 1] and not seq[i] for i in range(len(seq) - 1)):
                return False
    return True


def auxiliary(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.4 の R1〜R9 の全体の数（判定に使わない。R8 の区間は judgment・estimate・descriptive にある）。"""
    vals = list(individuals.values())
    levels = _levels_of_report(individuals)
    violations = sum(len(v["S1"]["violations"]) for v in vals)
    silent = [v for v in vals if any(v["S1"]["silent_source"].values())]
    all_systems = sorted({n for v in vals for n in v["s_U"]}, key=lambda n: (n not in M.BODIES + (M.RERUN,), n))
    out = {"R1": {
        "individuals": len(vals),
        "classes_at_k0": {c: sum(1 for v in vals if v["class"] == c) for c in INDIVIDUAL_CLASSES},
        "zero_labels": {z: sum(1 for v in vals if v["zero_label"] == z) for z in ("Z-1", "Z-2")},
        "k_star": five_numbers([v["k_star"] for v in vals if v["k_star"] is not None]),
        "e_zero": sum(1 for v in vals if v["e_zero"]),
        # 命題 S-1：反する発火があれば、その件数を開示し、札の報告を取り下げる（README §7.2。判定は S-1 に依らない）
        "S1": {"E_S": E_S, "violations": violations, "labels_withdrawn": violations > 0,
               "individuals_with_silent_source": None if violations else len(silent)},
    }}
    out["R2"] = {n: {part: {k: five_numbers([v[f"counts_{part}"][n][k] for v in vals if n in v[f"counts_{part}"]])
                            for k in ("decided", "A1", "A2", "tie", "none")} for part in ("E", "U")}
                 | {"s_U": five_numbers([v["s_U"][n]["value"] for v in vals if v["s_U"].get(n) is not None]),
                    "built": sum(1 for v in vals if n in v["s_U"])}
                 for n in all_systems}
    r3 = {}
    for k in levels:                                # §3.2 のすべての量：合算の C_k・D^u_k と、背景ごとの C・D^u・片側の差（定まる個体だけ）
        for kind in ("C", "Du"):
            t = table_of([_level(v, k)[kind]["value"] for v in vals])
            r3[f"{kind}{k}"] = {"value": t["distribution"], "abs_value": t["abs_distribution"]}
        for c in BG:
            for name, pick in ((f"C{k}_{c}", lambda lv, c=c: lv["C"][c]["value"]), (f"Du{k}_{c}", lambda lv, c=c: lv["Du"][c]["value"]),
                               (f"up{k}_{c}", lambda lv, c=c: lv["up"][c]), (f"dn{k}_{c}", lambda lv, c=c: lv["dn"][c])):
                t = table_of([pick(_level(v, k)) for v in vals])
                r3[name] = {"value": t["distribution"], "abs_value": t["abs_distribution"]}
    for name in OTHER_QUANTITIES:
        t = table_of([v["quantities"][name] for v in vals])
        r3[name] = {"value": t["distribution"], "abs_value": t["abs_distribution"]}
    t = table_of([v["delta_e"] for v in vals])
    r3["delta_e"] = {"value": t["distribution"], "abs_value": t["abs_distribution"]}
    out["R3"] = r3
    roles6 = M.ROLES6
    out["R4"] = {"W_A1": {r: five_numbers([v["W"]["A1"][r] for v in vals]) for r in roles6},
                 "W_A2": {r: five_numbers([v["W"]["A2"][r] for v in vals]) for r in roles6},
                 "abs_W_diff": {r: five_numbers([v["W_abs_diff"][r] for v in vals]) for r in roles6},
                 "pair_sum_max_abs_deviation": max((v["pair_deviation"][c] for v in vals for c in BG), default=None),
                 "clones_after_transplant": {
                     "weights": "a description, not the measured values: the six weights of every built clone after S3 are kept in the raw (boundary.sigma_a) and equal its endpoint, X1, X2 or W_c (O6 (a), O10, O11)",
                     "pair_sum_max_abs_deviation": max((v["clone_pair_deviation"] for v in vals), default=None)},
                 "not_built": {"systems": sum(len(v["not_built"]) for v in vals),
                               "individuals_with_any": sum(1 for v in vals if v["not_built"])}}
    names5 = sorted({n for v in vals for n in v["consequences"]})
    out["R5"] = {n: {part: five_numbers([v["consequences"][n][part] for v in vals if n in v["consequences"]]) for part in ("E", "U")}
                 | {"as_expected": all(all(v["consequences"][n][p] == v["consequences"][n]["decided_windows_of_c"][p]
                                           for p in ("E", "U")) for v in vals if n in v["consequences"])}
                 for n in names5}
    out["R6"] = {}
    keys = sorted({key for v in vals for key in v["first_divergence"]})
    for key in keys:
        rows = [v["first_divergence"][key] for v in vals if key in v["first_divergence"]]
        out["R6"][key] = {"pairs": len(rows),
                          "firing": {"none": sum(1 for r in rows if r["firing"] is None),
                                     "pulses": five_numbers([r["firing"] for r in rows if r["firing"] is not None])},
                          "window": {"none": sum(1 for r in rows if r["window"] is None),
                                     "windows": five_numbers([r["window"] for r in rows if r["window"] is not None])}}
    out["R7"] = {n: {part: {role: five_numbers([v["firing"][n][part][role] for v in vals if n in v["firing"]])
                            for role in ("cue", "source1", "source2")} for part in ("E", "U")}
                 | {"E_from": n if n in M.BODIES + (M.RERUN,) else M.background_of(n)} for n in all_systems}
    out["R8"] = NOTES["R8"]
    out["R9"] = {n: {"s_E": five_numbers([v["s_E"][n]["value"] for v in vals if v["s_E"][n] is not None]),
                     "s_U": five_numbers([v["s_U"][n]["value"] for v in vals if v["s_U"][n] is not None]),
                     "note": "within-body before/after; not a counterfactual contrast"} for n in M.BODIES}
    return out


# ---- 操作の確認（README §8） -----------------------------------------------------------------------------

RUN_KEYS = {"seed", "plan", "levels", "roles", "birth_units", "connection_order", "W_0", "X", "bodies", "boundary",
            "difference", "endpoints", "clones"}
END_KEYS = {"activity", "sensory", "delta_log", "layer_a", "layer_b", "audit", "world_end", "world_switches", "sigma_end",
            "sigma_end_sha256", "history", "pulse_end"}
BODY_KEYS = {"B_A1": END_KEYS | {"sigma_0", "first_intent"}, "B_A2": END_KEYS | {"sigma_0", "first_intent"},
             M.RERUN: END_KEYS | {"sigma_p_e", "sigma_p_e_sha256"}}
CLONE_KEYS = END_KEYS | {"pulse_weights", "sigma_after_first"}
BOUNDARY_KEYS = {"steps", "W", "sigma_p_e", "sigma_p_e_sha256", "sigma_a", "sigma_b"}
ENDPOINT_KEYS = {"in_range", "out_of_range", "weights"}
AUDIT_KEYS = {"ok", "matched", "only_in_layer_a", "only_in_layer_b", "win_windows", "issued",
              "identity_issued_plus_carried_equals_wins", "duplicate_delta_ids", "carried_over_windows", "log_matches_world"}
EMPTY_INTERVENTIONS = {"active": [], "frozen": {}}


def _prefix_allowed(path) -> bool:
    """k* の意図の Pulse の後に、規則 c だけが違う二つの本体で違ってよい欄：世界の規則 c と、結果の予約（0042 と同じ）。"""
    p = tuple(path)
    return p in (("world", "rule", "rule_c"), ("world", "next_rid")) or p[:2] in (("world", "pending"), ("world", "reserved"))


def _plan(run) -> "M.Plan":
    return M.Plan(**run["plan"])


def _six(run) -> list[str]:
    return sorted(run["W_0"])


def _freeze(run) -> list:
    return [["FREEZE", _six(run), AS1.ADVANCE]]


def _weights_of(sigma: Mapping) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in sorted(sigma["connections"].items())}


def _as_row(run, weights: Mapping[str, float]) -> list[float]:
    return [weights[cid] for cid in run["connection_order"]]


def _windows(plan) -> list[list[int]]:
    return [list(w) for w in plan.schedule().windows]


def _expand_realized(world: Mapping) -> list:
    """世界の成立の記録を、感覚の出来事の列 [Pulse, Receptor]（個数の分だけ並べる）にする。"""
    return [[pulse, receptor] for pulse, receptor, _rids, n in world["realized"] for _ in range(n)]


def target_of(run, name: str) -> dict[str, float]:
    """作った複製の系の U の 6 本の重み（端の値・X1・X2・W^c）。"""
    p = M.parse_clone(name)
    if p["kind"] in ("natural", "symmetric"):
        return _endpoint_weights(run, name)
    if p["kind"] in ("X1", "X2"):
        return run["X"][p["kind"]]
    return run["boundary"]["W"][p["background"]]


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None, levels=None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, levels, out["structure"])
        if not out["structure"]:
            for name, f in (("O3", _o3), ("O4", _o4), ("O5", _o5), ("O6", _o6), ("O7", _o7), ("O8", _o8), ("O9", _o9),
                            ("O10", _o10), ("O11", _o11), ("O12", _o12), ("O13", _o13), ("O14", _o14)):
                try:
                    f(run, out[name])
                except Exception as e:                       # noqa: BLE001  記録の形が壊れていても止めずに、その確認を不成立にする
                    out[name].append(f"記録を読めない：{type(e).__name__}")
            try:
                _o2(data, mode, out["O2"])
            except Exception as e:                           # noqa: BLE001
                out["O2"].append(f"記録を読めない：{type(e).__name__}")
        _o15(seed, mode, out["O15"])
    except Exception as e:                                   # noqa: BLE001
        out["structure"].append(f"記録を読めない：{type(e).__name__}")
    return out


def _structure(data, mode, seed, plan, levels, out) -> None:
    run = data.get("run", {})
    if set(data) != {"meta", "run"}:
        out.append(f"raw の最上位の欄が {sorted(data)}")
    if set(run) != RUN_KEYS:
        out.append(f"run の欄が {sorted(run)}（判定の量の欄を raw に入れない）")
        return
    try:
        lv = M.check_levels(tuple(run["levels"]))
    except (ValueError, TypeError):
        out.append("raw の段の組が、1 以上の整数の重複のない昇順の列ではない")
        return
    if mode in ("formal", "smoke") and (levels is not None or lv != FORMAL_LEVELS):
        out.append("本番・smoke では protocol の段の組だけを使う")
    if levels is not None and lv != tuple(levels):
        out.append("raw の段の組が、使う段の組と違う")
    names = M.clone_names(lv)
    ends = M.endpoint_names(lv)
    if set(run["bodies"]) != set(BODY_KEYS) or any(set(run["bodies"][n]) != keys for n, keys in BODY_KEYS.items()):
        out.append("bodies の系の組・欄が違う")
    if set(run["endpoints"]) != set(ends) or any(set(run["endpoints"][n]) != ENDPOINT_KEYS for n in ends):
        out.append("endpoints の系の組・欄が違う")
        return
    always = {n for n in names if M.parse_clone(n)["kind"] in ("base", "X1", "X2", "tr")}
    want_built = always | {n for n in ends if run["endpoints"][n]["in_range"] is True}
    if set(run["clones"]) != want_built or any(set(run["clones"][n]) != CLONE_KEYS for n in run["clones"]):
        out.append("clones の系の組（基・X1・X2・tr と範囲の中の端の系）・欄が違う")
    for n in ends:
        ep = run["endpoints"][n]
        if not isinstance(ep["in_range"], bool) or (ep["in_range"] != (ep["weights"] is not None)) \
                or (ep["in_range"] != (ep["out_of_range"] == [])):
            out.append(f"{n}：端の記録の範囲・重み・範囲の外の欄が合わない")
    b = run["boundary"]
    built = set(run["clones"])
    if set(b) != BOUNDARY_KEYS or set(b["W"]) != set(BG) or set(b["sigma_p_e"]) != set(M.BODIES) \
            or set(b["sigma_p_e_sha256"]) != set(M.BODIES) or set(b["sigma_a"]) != built or set(b["sigma_b"]) != built:
        out.append("boundary の欄・系の組が違う")
    if set(run["X"]) != {"X1", "X2"}:
        out.append("X の欄が違う")
    if set(run["difference"]) != {"e", "delta_e", "m"} or set(run["difference"]["m"]) != {str(k) for k in lv}:
        out.append("difference の欄が違う")
    if out:
        return
    for n in M.BODIES + (M.RERUN,) + tuple(sorted(built)):
        want = AUDIT_KEYS - set(M.CLONE_AUDIT_DROPS) if n in built else AUDIT_KEYS
        if set(record_of(run, n)["audit"]) != want:
            out.append(f"{n}：道具の突合の記録の欄が違う")
    if run["seed"] != seed:
        out.append("run の seed がフォルダの seed と違う")
    want = plan or M.formal_plan(PROTOCOL)
    if mode in ("formal", "smoke") and plan is not None and plan != M.formal_plan(PROTOCOL):
        out.append("本番・smoke では protocol の Plan だけを使う")
    if run["plan"] != json.loads(json.dumps(dataclasses.asdict(want))):
        out.append("raw の plan が使う Plan と違う")
    if run["roles"] != A.assign_roles(seed).as_dict():
        out.append("役の割り当てが assign_roles と違う")
    if len(run["W_0"]) != 6 or set(run["W_0"].values()) != {W0} or run["connection_order"] != sorted(run["W_0"]):
        out.append("W_0 が出生時の値（6 本とも w0）ではないか、接続の順が違う")
    if set(run["birth_units"]) != set(A.UNITS):
        out.append("出生時の Unit の記録が 3 Unit ではない")
    meta = data.get("meta", {})
    for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode), ("seed", seed)):
        if meta.get(k) != v:
            out.append(f"meta の {k} が違う")
    if meta.get("manifest") != M.manifest_raw():
        out.append("meta の設計図が AS2b の設計図と違う")
    _protocol_binding(meta, out)
    want_blind = {"smoke": True, "formal": False}.get(mode)
    if not isinstance(meta.get("blind"), bool) or (want_blind is not None and meta["blind"] is not want_blind):
        out.append("meta の blind が mode と合わない（smoke は盲検、本番は盲検でない）")


def _protocol_binding(meta: Mapping, out: list[str]) -> None:
    """meta の protocol の写しが存在し、確定済みの protocol.yaml（正本）と一致すること。"""
    if "protocol" not in meta or "protocol_sha256" not in meta:
        out.append("meta に protocol の写し・SHA-256 がない（独立の検算が確定済みの条件で再検証できない）")
        return
    if meta["protocol_sha256"] != PROTOCOL_SHA256:
        out.append("meta の protocol の SHA-256 が、確定済みの protocol.yaml と違う")
    if meta["protocol"] != PROTOCOL_AS_STORED:
        out.append("meta の protocol の写しが、確定済みの protocol.yaml と違う")


def _o2(data, mode, out) -> None:
    """関門の組（README §1.1）：宣言の SHA-256 と、作ったすべての系の予定・o・W・L・世界・役・本体の長さ。本体は介入の履歴が空。"""
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
    for n in systems_of(run):
        rec = record_of(run, n)
        rule = {"cue_receptor": run["roles"]["cue_receptor"], "delay": plan.delay, "rule_c": M.rule_of(n),
                "respond": True, "multiplicity": AS1.PER_RESERVATION}
        if rec["world_end"]["rule"] != rule:
            out.append(f"{n}：世界の規則（L・規則 c・手がかりの Receptor・応じるか・多重度）が違う")
        if [[r["window"], r["open"], r["close"]] for r in rec["layer_a"]] != windows:
            out.append(f"{n}：窓（番号・区間）が、宣言の予定・o・W から作ったものと違う")
        if [[r[1], r[2], r[3]] for r in rec["world_end"]["reserved"] if r[1] == A.CUE] != cues:
            out.append(f"{n}：手がかりの予約が、宣言の予定と違う")
        if rec["pulse_end"] != plan.end:
            out.append(f"{n}：終わりの Pulse が本体の長さと違う")
        ex = rec["sigma_end"]["exit"]
        if ex["windows"] != windows or ex["action_of"] != action_of:
            out.append(f"{n}：出口の窓の写し・行動 ID の対応が違う")
    for n in M.BODIES + (M.RERUN,):
        if run["bodies"][n]["history"] != []:
            out.append(f"{n}：本体に介入の宣言の履歴がある")


def _o3(run, out) -> None:
    """CT-E10 の突合を、保存した層 A・層 B・来歴のログから計算し直す。窓への到達、終わりに未発行の予定がないこと（0042 と同じ）。"""
    plan = _plan(run)
    built = set(run["clones"])
    for n in systems_of(run):
        rec = record_of(run, n)
        la, lb = rec["layer_a"], rec["layer_b"]
        emitted = Counter((r["emit_pulse"], r["winner_unit"], r["action"]) for r in la if r["emitted"])
        received = Counter((p, src, act) for p, _did, src, act in lb)
        wins = sum(1 for r in la if r["winner_unit"] is not None)
        carried = [r["window"] for r in la if r["winner_unit"] is not None and not r["emitted"]]
        ids = [did for _p, did, _src, _act in lb]
        if emitted != received:
            out.append(f"{n}：層 A の「出した」記録と層 B の意図の記録が一対一でない")
        if len(lb) + len(carried) != wins or carried:
            out.append(f"{n}：発行済み ＋ 未発行の予定 ≠ 勝ちの窓、または終わりに未発行の予定がある")
        if len(ids) != len(set(ids)):
            out.append(f"{n}：Delta の識別子が重複している")
        if [r["window"] for r in la] != list(range(1, plan.count + 1)):
            out.append(f"{n}：すべての窓に到達していない（窓の番号の重複・欠落・余分）")
        want_log = sorted(lb) if n not in built else sorted(x for x in lb if x[0] > plan.p_e)
        if sorted(rec["delta_log"]) != want_log:
            out.append(f"{n}：来歴のログの意図が、世界の受けた意図の記録と違う")
        au = rec["audit"]
        ok = (au["only_in_layer_a"] == [] and au["only_in_layer_b"] == [] and au["duplicate_delta_ids"] == 0
              and au["identity_issued_plus_carried_equals_wins"] is True and au["carried_over_windows"] == []
              and au["win_windows"] == wins and au["issued"] == len(lb) and au["matched"] == len(lb))
        if n not in built:
            ok = ok and au["ok"] is True and au["log_matches_world"] is True
        if not ok:
            out.append(f"{n}：道具の突合の記録が ok でないか、計算し直した値と違う")


def _o4(run, out) -> None:
    """R-7 の対（SE-C2）：0042 の O4 と同じ。"""
    plan = _plan(run)
    ra, rb = run["bodies"]["B_A1"], run["bodies"]["B_A2"]
    if sorted(tuple(p) for p in AS1.sigma_diff(ra["sigma_0"], rb["sigma_0"])) != [("world", "rule", "rule_c")]:
        out.append("B_A1 と B_A2 の Pulse 0 の Σ の違いが、規則 c だけではない")
    ka, kb = k_star(ra["layer_a"], plan.e_windows), k_star(rb["layer_a"], plan.e_windows)
    if ka != kb:
        out.append("B_A1 と B_A2 で、E の最初の決まった窓が違う")
        return
    if ka is None:
        sp = run["boundary"]["sigma_p_e"]
        if ra["first_intent"] is not None or rb["first_intent"] is not None:
            out.append("E に決まった窓がないのに、最初の意図の Σ がある")
        if sorted(tuple(p) for p in AS1.sigma_diff(sp["B_A1"], sp["B_A2"])) != [("world", "rule", "rule_c")]:
            out.append("k* がない個体で、P_E の Σ の違いが規則 c だけではない")
        if run["boundary"]["W"]["A1"] != run["boundary"]["W"]["A2"]:
            out.append("k* がない個体で、W^{A1} と W^{A2} が違う")
        for key in ("activity", "sensory"):
            if [x for x in ra[key] if x[0] <= plan.p_e] != [x for x in rb[key] if x[0] <= plan.p_e]:
                out.append(f"k* がない個体で、P_E までの {key} が違う")
        return
    if ra["layer_a"][:ka] != rb["layer_a"][:ka]:
        out.append("B_A1 と B_A2 の窓 1〜k* の記録が違う")
        return
    t = ra["layer_a"][ka - 1]["decision_pulse"] + 1
    ia, ib = ra["first_intent"], rb["first_intent"]
    if ia is None or ib is None or ia["pulse"] != t or ib["pulse"] != t \
            or ia["sigma"]["pulse"] != t or ib["sigma"]["pulse"] != t:
        out.append("k* の意図の Pulse（決定の翌 Pulse）の処理の後の Σ がない")
        return
    if not all(_prefix_allowed(p) for p in AS1.sigma_diff(ia["sigma"], ib["sigma"])):
        out.append("B_A1 と B_A2 の、k* の意図の Pulse の後の脳の側の Σ（世界の規則 c と予約のほか）が違う")
    if [x for x in ra["activity"] if x[0] <= t] != [x for x in rb["activity"] if x[0] <= t]:
        out.append("B_A1 と B_A2 の、k* の意図の Pulse までの発火が違う")


def _o5(run, out) -> None:
    """世界の規則（SE-C3）：源の Receptor の出来事が 0。どの系でも、結果は行動 ID が規則 c の意図にだけ、意図の Pulse ＋ L − 1 に成立し、
    数が行動 ID が c の決まった窓の数に等しい。世界の切り替えの記録がない。複製の系の E は複製の元と同じ。"""
    plan = _plan(run)
    p_e = plan.p_e
    cue_r = run["roles"]["cue_receptor"]
    built = set(run["clones"])
    for n in systems_of(run):
        rec = record_of(run, n)
        w = rec["world_end"]
        if any(r != cue_r for _, r in rec["sensory"]) or any(row[1] != cue_r for row in w["realized"]):
            out.append(f"{n}：手がかりの Receptor のほかに感覚の出来事がある（K1）")
        responding = [x for x in rec["layer_b"] if x[3] == M.rule_of(n)]
        want = sorted([cue_r, p + plan.delay - 1, did] for p, did, _src, _act in responding)
        got = sorted([r[2], r[3], r[4]] for r in w["reserved"] if r[1] == A.CONSEQUENCE)
        if got != want:
            out.append(f"{n}：結果の予約が、行動 ID が規則 c の意図ごとに意図の Pulse ＋ L − 1 へ 1 つ、だけになっていない")
        decided_c = sum(1 for r in rec["layer_a"] if r["outcome"] == M.rule_of(n))
        if len(got) != decided_c:
            out.append(f"{n}：結果の刺激の数が、行動 ID が規則 c の決まった窓の数と違う（SE-C3）")
        if any(r[1] not in (A.CUE, A.CONSEQUENCE) for r in w["reserved"]) or w["cancelled"]:
            out.append(f"{n}：手がかり・結果のほかの予約か、取り消しがある")
        if w["pending"] or any(len(rids) != 1 or cnt != 1 for _p, _r, rids, cnt in w["realized"]):
            out.append(f"{n}：終わりに成立していない予約があるか、予約が同じ Pulse に重なった")
        if sorted(_expand_realized(w)) != sorted([r[3], r[2]] for r in w["reserved"]):
            out.append(f"{n}：成立した感覚の出来事が、手がかりと結果の予約と違う")
        got_sensory = _expand_realized(w) if n not in built else [x for x in _expand_realized(w) if x[0] > p_e]
        if rec["sensory"] != got_sensory:
            out.append(f"{n}：来歴のログの感覚の出来事が、世界の成立の記録と違う")
        if rec["world_switches"] != []:
            out.append(f"{n}：世界の切り替えの記録がある（この実験は切り替えない）")
    for n in built:
        src = run["bodies"][M.background_of(n)]
        rec = run["clones"][n]
        if [x for x in _expand_realized(rec["world_end"]) if x[0] <= p_e] \
                != [x for x in _expand_realized(src["world_end"]) if x[0] <= p_e]:
            out.append(f"{n}：E の成立の記録が、複製の元の本体と違う")
        if rec["layer_a"][:plan.e_windows] != src["layer_a"][:plan.e_windows] \
                or [x for x in rec["layer_b"] if x[0] <= p_e] != [x for x in src["layer_b"] if x[0] <= p_e]:
            out.append(f"{n}：E の層 A・層 B が、複製の元の本体と違う")


def expected_steps(run) -> list:
    plan, six = _plan(run), _six(run)
    p_e, end = plan.p_e, plan.end
    built = built_of(run)
    steps = [["S0", n, p_e, "advance_to", {"from": 0}] for n in M.BODIES]
    steps += [["S1", n, p_e, "read_weights_and_sigma", None] for n in M.BODIES]
    steps += [["S2", n, p_e, "clone", {"from": M.background_of(n)}] for n in built]
    steps += [["S3", n, p_e, "transplant", {"to": M.target_label(n), "intervention_state_at_transplant": EMPTY_INTERVENTIONS}]
              for n in built if M.target_label(n) is not None]
    steps += [["S4", n, p_e, "declare", {"FREEZE": six, "trace_policy": AS1.ADVANCE}] for n in built]
    steps += [["S5", n, end, "advance_to", {"from": p_e}] for n in M.BODIES + built]
    return steps


def _o6(run, out) -> None:
    """境界の順序と差の目録（README §2.5）。(a) S3 の直後、(b) S4 の直後。"""
    plan = _plan(run)
    p_e, b = plan.p_e, run["boundary"]
    if b["steps"] != expected_steps(run):
        out.append("S0〜S5 の記録が、決めた順序・Pulse・操作と違う（作る系の組・移植の時の介入の状態が空でないものを含む）")
    for n in built_of(run):
        sa, sb = b["sigma_a"][n], b["sigma_b"][n]
        own = M.parse_clone(n)["background"]
        base = b["sigma_a"][f"G_{own}_base"]
        target = target_of(run, n)
        if sa["pulse"] != p_e or sb["pulse"] != p_e:
            out.append(f"{n}：Σ (a)・(b) の Pulse の番号が P_E ではない（S1〜S4 のあいだに Pulse を進めた）")
        if sa["interventions"] != EMPTY_INTERVENTIONS:
            out.append(f"(a) {n} の介入の状態が空ではない")
        if _weights_of(sa) != target:
            out.append(f"(a) {n} の重みが、U の重み（{M.target_label(n) or 'W_' + own}）と違う")
        want = [("connections", cid, "weight") for cid in _six(run) if b["W"][own][cid] != target[cid]]
        if sorted(tuple(p) for p in AS1.sigma_diff(base, sa)) != sorted(want):
            out.append(f"(a) {n} と、移植しない複製の Σ の違いが、移植した重みだけではない")
        if n == f"G_{own}_base" and AS1.sigma_diff(b["sigma_p_e"][M.background_of(n)], sa):
            out.append(f"(a) {n} の Σ が、複製の元の本体の P_E の Σ と違う")
        frozen = sb["interventions"]["frozen"]
        if sb["interventions"]["active"] != _freeze(run) or set(frozen) != set(run["W_0"]):
            out.append(f"(b) {n} の U の介入が 6 本の FREEZE（advance）ではない")
        elif any(frozen[cid] != {"weight": v["weight"], "pre_trace": v["pre_trace"], "post_trace": v["post_trace"],
                                 "policy": AS1.ADVANCE} for cid, v in sb["connections"].items()):
            out.append(f"(b) {n} の FREEZE の値が、宣言の時点の重み・痕跡と違う")
        if any(p[0] != "interventions" for p in AS1.sigma_diff(sa, sb)):
            out.append(f"(b) {n}：S4 で、介入の状態のほかが変わった")
        if run["clones"][n]["history"] != [[p_e, M.S4_LABEL, _freeze(run)]]:
            out.append(f"{n}：介入の履歴が、P_E での U の FREEZE の宣言（一度だけ）ではない")


def _o7(run, out) -> None:
    """U の FREEZE：作ったすべての複製の系で、6 本の重みが U のすべての Pulse で宣言の値。"""
    plan = _plan(run)
    for n in built_of(run):
        rows = run["clones"][n]["pulse_weights"]
        if [p for p, _ in rows] != list(range(plan.p_e + 1, plan.end + 1)):
            out.append(f"{n}：U の Pulse ごとの重みの記録がそろっていない")
        target = _as_row(run, target_of(run, n))
        if any(w != target for _, w in rows):
            out.append(f"{n}：U のある Pulse で、6 本の重みが宣言の値と違う")


IDENTITY_KEYS = ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end")


def identity_groups(run) -> list[list[str]]:
    """同じ背景で、U の 6 本の重みがビット単位で同じ、作った複製の系の組（2 つ以上のもの）。基の系と tr、構造上の 0 の系を含む。"""
    groups: dict[tuple, list[str]] = {}
    for n in built_of(run):
        c = M.parse_clone(n)["background"]
        groups.setdefault((c, tuple(_as_row(run, target_of(run, n)))), []).append(n)
    return [g for g in groups.values() if len(g) > 1]


def _o8(run, out) -> None:
    """恒等（SE-C4・SE-C6・SE-C7）：同じ背景で U の重みがビット単位で同じ系は、U で同じ（発火・層 A・層 B・感覚・終わりの Σ）。"""
    for group in identity_groups(run):
        a = group[0]
        for b in group[1:]:
            for key in IDENTITY_KEYS:
                if run["clones"][a][key] != run["clones"][b][key]:
                    out.append(f"{b} が U で {a} と違う（{key}）。重みは同じ")
                    break
    for c in BG:                                              # tr は必ず基の系と同じ組にある
        if not any({f"G_{c}_base", f"G_{c}_tr"} <= set(g) for g in identity_groups(run)):
            out.append(f"G_{c}_tr の重みが G_{c}_base と同じでない")


def _o9(run, out) -> None:
    """Pulse P_E ＋ 1 の一致（SE-C5）。同じ背景の基の系と作った各複製の系の対で、保存した Pulse P_E ＋ 1 の処理の後の Σ から照合する。"""
    plan = _plan(run)
    first, end = plan.p_e + 1, plan.end
    for c in BG:
        a = f"G_{c}_base"
        for b in built_of(run):
            if b == a or M.parse_clone(b)["background"] != c:
                continue
            ua, ub = run["clones"][a], run["clones"][b]
            fa = sorted(u for p, u in ua["activity"] if p == first)
            fb = sorted(u for p, u in ub["activity"] if p == first)
            sa, sb = ua["sigma_after_first"], ub["sigma_after_first"]
            if sa["pulse"] != first or sb["pulse"] != first:
                out.append(f"(a) {a}・{b} の保存した Σ が Pulse P_E ＋ 1 の処理の後ではない")
            if fa != fb or sa["exit"] != sb["exit"]:
                out.append(f"(a) {a} と {b} の Pulse P_E ＋ 1 の発火・層 A が違う")
            if sa["units"] != sb["units"]:
                out.append(f"(a) {a} と {b} の Pulse P_E ＋ 1 の Unit の内部の状態が違う")
            wa, wb = _weights_of(run["boundary"]["sigma_b"][a]), _weights_of(run["boundary"]["sigma_b"][b])
            da, db = sa["drives"], sb["drives"]
            if len(da) != len(db):
                out.append(f"(b) {a} と {b} の届く途中の駆動の数が違う")
            else:
                for x, y in zip(da, db):
                    if x[0] != y[0] or x[1] != y[1] or x[3] != y[3]:
                        out.append(f"(b) {a} と {b} の届く途中の駆動の送り手・受け手・Pulse が違う")
                        break
                    if x[2] != y[2]:
                        cid = f"{x[0]}.main->{x[1]}"
                        if not (cid in wa and wa[cid] != wb[cid] and x[0] in fa and x[3] == first
                                and x[2] == wa[cid] and y[2] == wb[cid]):
                            out.append(f"(b) {a} と {b} の駆動が、重みの差のある接続の送り手の発火の分の外で違う")
                            break
            fd = first_divergence(ua["activity"], ub["activity"], first, end)
            if fd is not None and fd < plan.p_e + 2:
                out.append(f"(c) {a} と {b} の最初に分かれた Pulse が P_E ＋ 2 より前")


def _o10(run, out) -> None:
    """重みの算術（README §2.2・SE-C8）：保存した P_E の Σ から、事前登録の analysis.py の endpoints で、e・δ(e)・m_k と
    すべての端の正確な値・範囲・丸めた値を計算し直して照らす。(a) 作った系の移植の値がビット単位で一致、(b) 作った系の組が範囲の中の端と
    ちょうど一致し、範囲の外の重みの名前と側も一致、(c) V^{A1}_{−1} ＝ W^{A2}・V^{A2}_{+1} ＝ W^{A1}（ビット単位）。"""
    roles = run["roles"]
    levels = levels_of(run)
    sp = run["boundary"]["sigma_p_e"]
    w1, w2 = by_role(roles, _weights_of(sp["B_A1"])), by_role(roles, _weights_of(sp["B_A2"]))
    cids = role_cids(roles)
    e = AX.natural_difference(w1, w2)
    diff = run["difference"]
    if diff["e"] != {r: M.frac_str(e[r]) for r in M.ROLES6} or Fraction(diff["delta_e"]) != AX.delta_of(e) \
            or any(Fraction(diff["m"][str(k)]) != AX.m_of(e, k) for k in levels):
        out.append("記録した e・δ(e)・m_k が、P_E の Σ から計算し直した値と違う")
    for name in M.endpoint_names(levels):
        p = M.parse_clone(name)
        kind = "natural" if p["kind"] == "natural" else "symmetric"
        got = AX.endpoints(w1, w2, p["background"], p["level"], W_MAX, kind)["plus" if p["side"] == 1 else "minus"]
        rec = run["endpoints"][name]
        bad = [[r, "below" if got["exact"][r] < 0 else "above"] for r in M.ROLES6
               if not 0 <= got["exact"][r] <= Fraction(W_MAX)]
        if rec["in_range"] != got["in_range"] or rec["out_of_range"] != bad:
            out.append(f"(b) {name}：範囲・範囲の外の重みの名前と側が、計算し直した値と違う")
            continue
        if got["in_range"]:
            want = {cids[r]: got["weights"][r] for r in M.ROLES6}
            if rec["weights"] != want:
                out.append(f"(a) {name}：記録した端の重みが、計算し直した値とビット単位で違う")
            if name not in run["clones"] or _weights_of(run["boundary"]["sigma_a"][name]) != want:
                out.append(f"(a) {name}：範囲の中の端の系が作られていないか、移植の値が計算し直した値と違う")
        elif name in run["clones"]:
            out.append(f"(b) {name}：範囲の外の端の系が作られている")
    if 1 in levels:
        w = run["boundary"]["W"]
        if run["endpoints"]["G_A1_M1"]["weights"] != w["A2"] or run["endpoints"]["G_A2_P1"]["weights"] != w["A1"]:
            out.append("(c) k ＝ 1 の自然な側の端が、もう一方の本体の重みとビット単位で一致しない")


def _o11(run, out) -> None:
    """重みの範囲と F1（SE-C9・SE-C10）：本体の P_E の重みと、作った複製の系の移植の後の重みが [0, w_max] にあり、組の丸めた後の和と
    w_max の差が固定の許容（10⁻¹²）の内。端の値が protocol と同じ。範囲の中の端の系の組が段について入れ子。"""
    cids = role_cids(run["roles"])
    want_x = {k: {cids[r]: v for r, v in vals.items()} for k, vals in M.extremes(PROTOCOL).items()}
    if run["X"] != want_x:
        out.append("X1・X2 の値が protocol の値（役の名前から接続の ID への写し）と違う")
    sets = {f"W_{c}": run["boundary"]["W"][c] for c in BG}
    sets |= {f"(a) {n}": _weights_of(run["boundary"]["sigma_a"][n]) for n in built_of(run)}
    for label, ws in sets.items():
        if set(ws) != set(run["W_0"]) or any(not (W_MIN <= v <= W_MAX) for v in ws.values()):
            out.append(f"{label}：重みが [w_min, w_max] の外か、6 本の組が違う")
        elif pair_deviation(ws) > Fraction(F1_TOLERANCE):
            out.append(f"{label}：組の丸めた後の和が w_max から固定の許容を超えて離れている（O11 の操作の条件）")
    if not nesting_ok({"built": list(run["clones"])}, levels_of(run)):
        out.append("範囲の中の端の系の組が、段について入れ子になっていない（SE-C10）")


def future_cue_rows(run) -> Counter:
    """P_E の世界に残るべき予約の多重集合（0042 v0.2 と同じ）。"""
    plan = _plan(run)
    cue_r = run["roles"]["cue_receptor"]
    return Counter((A.CUE, cue_r, c, None) for c in plan.schedule().cues if c > plan.p_e)


def pending_problems(run, sigma: Mapping) -> list[str]:
    """保存した P_E の Σ の世界の予約の、宣言の予定との全件の照合（0042 v0.2 と同じ）。"""
    plan = _plan(run)
    cue_r = run["roles"]["cue_receptor"]
    w = sigma["world"]
    pending, reserved = w["pending"], w["reserved"]
    problems = []
    if Counter((r[1], r[2], r[3], r[4]) for r in pending) != future_cue_rows(run):
        problems.append("残る予約が、宣言の予定の U の手がかりちょうど（種類・Receptor・Pulse・由来）ではない")
    rids = [r[0] for r in pending]
    if len(rids) != len(set(rids)) or any(r not in reserved for r in pending):
        problems.append("残る予約の識別子が重複しているか、予約の記録にない")
    if sorted(r[3] for r in reserved if r[1] == A.CUE) != list(plan.schedule().cues) \
            or any(r[2] != cue_r or r[4] is not None for r in reserved if r[1] == A.CUE):
        problems.append("手がかりの予約の記録が、宣言の予定（全窓）と違う")
    return problems


def _o12(run, out) -> None:
    """境界 P_E（SE-C1）：0042 v0.2 の O12 と同じ（未来の手がかりの予約の全件の照合を含む）。"""
    plan = _plan(run)
    b = run["boundary"]
    for n in M.BODIES:
        s = b["sigma_p_e"][n]
        ex = s["exit"]
        if s["pulse"] != plan.p_e or ex["pending"] is not None or ex["reports"] != {} or ex["reports_pulse"] is not None \
                or ex["cursor"] != plan.e_windows:
            out.append(f"S0：{n} に未決の窓・出す予定の意図があるか、P_E の Σ ではない")
        if any(r[1] != A.CUE for r in s["world"]["pending"]):
            out.append(f"S0：{n} の世界に、手がかりのほかの予約（結果の予約）が残っている")
        out.extend(f"S0：{n} の P_E の世界の{p}" for p in pending_problems(run, s))
        if b["W"][M.rule_of(n)] != _weights_of(s) or s["interventions"] != EMPTY_INTERVENTIONS:
            out.append(f"S1：{n} の重みが記録した W と違うか、本体に介入がある")
        if b["sigma_p_e_sha256"][n] != M.sigma_sha256(s):
            out.append(f"{n}：P_E の Σ の SHA-256 が値と合わない")


def _o13(run, out) -> None:
    """記録の非干渉と関門の本体との同一（SE-C15）：0042 の O13 と同じ。"""
    r, m = run["bodies"][M.RERUN], run["bodies"]["B_A1"]
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log"):
        if r[key] != m[key]:
            out.append(f"B′^{{A1}} の {key} が B^{{A1}} と違う")
    if AS1.sigma_diff(r["sigma_p_e"], run["boundary"]["sigma_p_e"]["B_A1"]):
        out.append("B′^{A1} の P_E の Σ が B^{A1} と違う")
    if AS1.sigma_diff(r["sigma_end"], m["sigma_end"]):
        out.append("B′^{A1} の終わりの Σ が B^{A1} と違う")
    if r["sigma_p_e_sha256"] != M.sigma_sha256(r["sigma_p_e"]) or r["sigma_end_sha256"] != m["sigma_end_sha256"]:
        out.append("B′^{A1} の Σ の SHA-256 が、値や B^{A1} と合わない")
    if r["sigma_end"]["pulse"] != _plan(run).end or r["sigma_p_e"]["pulse"] != _plan(run).p_e:
        out.append("B′^{A1} の Σ の Pulse が P_E・終わりではない")


def layer_a_problems(layer_a: list, windows: list, roles: Mapping) -> list[str]:
    """層 A の窓ごとの記録の欄どうしの整合（0042 と同じ）。"""
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


def _o14(run, out) -> None:
    """量の計算：層 A の記録の整合と、層 A から数えた窓ごとの行動 ID が層 B の意図の記録と一致すること。終わりの Σ の SHA-256。
    保存した層 A から数え直した s から、§3.2 の量を書き下しで計算し直し、事前登録の analysis.py の quantities と照らす（本番の段の組）。
    §4.1 の値の区分と §4.2 の合算の値が、§3.2 の量と合うこと。"""
    plan = _plan(run)
    levels = levels_of(run)
    windows = [tuple(w) for w in plan.schedule().windows]
    for n in systems_of(run):
        rec = record_of(run, n)
        problems = layer_a_problems(rec["layer_a"], windows, run["roles"])
        if problems:
            out.append(f"{n}：層 A の記録が整合しない")
            continue
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
        if rec["sigma_end_sha256"] != M.sigma_sha256(rec["sigma_end"]):
            out.append(f"{n}：終わりの Σ の SHA-256 が値と合わない")
    sp, w = run["boundary"]["sigma_p_e"], run["boundary"]["W"]
    if delta_of(run["roles"], _weights_of(sp["B_A1"]), _weights_of(sp["B_A2"])) != delta_of(run["roles"], w["A1"], w["A2"]):
        out.append("P_E の Σ から計算し直した δ(e) が、境界の記録の W からの δ(e) と違う")
    s = {n: share(window_counts(record_of(run, n)["layer_a"], plan.e_windows + 1, plan.count)) for n in systems_of(run)}
    s_all = {n: s.get(n) for n in M.BODIES + M.clone_names(levels)}
    written = written_out_quantities(levels, s_all)
    if levels == AX.LEVELS and quantities_of(levels, s_all) != written:
        out.append("層 A から数え直した s からの §3.2 の量が、定義を書き下した計算と違う")
    for k in levels:
        for kind, key in (("C", "C"), ("Du", "Du")):
            per = {c: classes_for(run, s_all, c, k, kind) for c in BG}
            for c in BG:
                cls, val = per[c]
                if (cls in DEFINED) != (written[f"{key}{k}_{c}"] is not None) or (cls in DEFINED and val != written[f"{key}{k}_{c}"]):
                    out.append(f"段 {k}・背景 {c}：{kind} の値の区分が §3.2 の量と合わない")
            if AX.individual_value(per["A1"], per["A2"]) != written[f"{key}{k}"]:
                out.append(f"段 {k}：{kind} の合算の値が §3.2 の量と合わない")


def _o15(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed は {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append("seed はこれまでに走らせた seed と重なる（D5。関門・0037・0039〜0042 の範囲を含む）")


# ---- 記録の確認・前提・report（0042 と同じ） ----------------------------------------------------------

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
    """raw の中身の meta と、開始・終了の記録の結び付き（0042 と同じ）。"""
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
    """smoke の盲検の記録の確かめ（0042 と同じ）。O15（seed の範囲）は記録に頼らずここで確かめ直す。"""
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
    o15: list[str] = []
    _o15(seed, mode, o15)
    if o15:
        status["O15"] = "fail"
    return status


def o1_check(out: Path, commit: str | None, repo: Path | None = None) -> list[str]:
    """O1 の証拠（0042 と同じ）。テストのファイルの SHA-256 は repo（省略したときは呼んだ時点の REPO）のものと比べる。"""
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


def analyze_runs(runs: Mapping[int, dict], mode: str, plan: "M.Plan | None" = None, levels=None, *, o1: list[str]) -> dict:
    """記録（seed → 本番・合成なら生の記録、smoke なら盲検の記録）と O1 の確かめの結果から、report の中身を作る。
    無効なら、成り立たなかった確認だけを返し、判定・推定・記述を計算しない（README §4.9）。"""
    o1_status = "fail" if o1 else "ok"
    if mode == "smoke":
        checks = {str(s): check_blinded(data, s) for s, data in sorted(runs.items())}
        return {"mode": "smoke", "O1": o1_status, "checks": checks,
                "valid": not o1 and all(v == "ok" for c in checks.values() for v in c.values())}
    checks = {s: check_seed(data, mode, s, plan, levels) for s, data in sorted(runs.items())}
    failed = {s: {k: v for k, v in c.items() if v} for s, c in checks.items() if any(c.values())}
    if failed or o1:
        return {"mode": mode, "valid": False, "outcome": "invalid", "O1": {"status": o1_status, "problems": o1},
                "failed_checks": {str(s): v for s, v in failed.items()}, "judgment": None, "estimate": None,
                "descriptive": None}
    individuals = {str(s): individual(data["run"]) for s, data in sorted(runs.items())}
    judgment = judge(individuals)
    return {"mode": mode, "valid": True, "outcome": judgment["outcome"], "O1": {"status": o1_status, "problems": o1},
            "gate_declaration_sha256": GATE_SHA256,
            "judgment": judgment,
            "estimate": estimate(individuals),
            "descriptive": descriptive(individuals),
            "individuals": individuals, "auxiliary": auxiliary(individuals)}


def verify_results_copy(src: Path, dst: Path) -> list[str]:
    """出力先 src と写し dst の照合（0042 と同じ）。鍵のファイル（run.lock）は写さない。"""
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
        report = {"mode": mode, "valid": False, "outcome": "invalid", "record_problems": records["problems"],
                  "O1": ("fail" if o1 else "ok") if mode == "smoke" else {"status": "fail" if o1 else "ok", "problems": o1},
                  "judgment": None, "estimate": None, "descriptive": None}
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
