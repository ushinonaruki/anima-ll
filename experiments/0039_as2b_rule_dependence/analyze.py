"""実験 0039 の記録の解析（確定した事前登録 v0.2 に従う。正本は README・protocol.yaml。#179 merge `ba7ffba`）。

0037 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、結果の写しの照合）を引き継ぐ（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid
2. 操作の確認 O2〜O14（README §8）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   判定の量を計算・表示しない。O1 は、run.py が seed に触れる前に測定の commit で走らせた契約テストの記録を確かめる（o1_check）
3. 判定（README §3〜§6）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 個体ごと：共通の部分の k*、適格外 (a)・定まらない (b)・構造上の恒等・命題 S-1 の札、11 系の窓の数と A1 の割合 s、
     §3.2 のすべての対比の差と符号
   - J_7：m ＜ 10 なら判定不能。向きごとの個体の数 ≥ k₂(m) で、その向きで成立。J_W は、J_7 が成立したときだけ判定する（固定の順序）
   - Clopper–Pearson の 95% は、判定の成立・不成立・未判定に依らず m ≥ 1 で計算する
   - §6.1 の記述の対照（D^{W′}・D^F・Z・P、二つの 9 つの組の表）と、§6.2 の R1〜R9（判定に使わない）
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0039_as2b_rule_dependence/analyze.py                    # 本番（data/experiments/0039）
  python experiments/0039_as2b_rule_dependence/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
  python experiments/0039_as2b_rule_dependence/analyze.py --verify-copy <写し>   # 本番の出力先と写しの照合
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
# 確定済みの事前登録の正本（v0.2、#179 merge `ba7ffba`）。生の記録の meta に保存した protocol の写しと SHA-256 を、これと照らす
PROTOCOL_SHA256 = hashlib.sha256((REPO / PROTOCOL_PATH).read_bytes()).hexdigest()
PROTOCOL_AS_STORED = json.loads(json.dumps(PROTOCOL))      # raw は JSON なので、写しは JSON を通した形で照らす
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0039")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure",) + tuple(f"O{i}" for i in range(2, 15))
REPORT, LOG = "report.json", "analysis_log.jsonl"
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py")
O1_FILE = "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
BLIND_KEYS = {"checks", "raw_sha256"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
F1_TOLERANCE = 1e-15          # O14：組の和と w_max の差（浮動小数の誤差の範囲。AS1 の契約テスト i5・0037 と同じ）


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


G = load(f"guard_{EXPERIMENT}_analyze", REPO / HERE / "guard.py")
M = load(f"measure_{EXPERIMENT}_analyze", REPO / HERE / "measure.py")
ALIGN = load(f"alignment_{EXPERIMENT}_analyze", REPO / HERE / "alignment.py")
AX = load(f"analysis_{EXPERIMENT}_analyze", REPO / HERE / "analysis.py")     # 事前登録の解析（命題 S-1 の E_S）
A, AS1 = M.A, M.AS1
W_MAX = float(PROTOCOL["brain"]["w_max"])
W0 = float(PROTOCOL["brain"]["initial_weight_w0"])
GATE_DECLARATION, GATE_SHA256 = M.gate_declaration(PROTOCOL)
E_S = AX.silence_bound(AX.c0_values(), AX.gate_set())["E_S"]                # 命題 S-1（README §7.2）。札だけに使う
OUTCOMES = (*A.ACTION_IDS, A.TIE, A.NONE)

# §3.2 の対比：名前 → (a, b)。差は s(a) − s(b)（protocol の quantities.contrasts と同じ）
CONTRASTS = {"D": ("B_A1", "B_A2"), "D_W": ("G_A1_WA1", "G_A1_WA2"), "D_W_rev": ("G_A2_WA1", "G_A2_WA2"),
             "D_F": ("F_A1", "F_A2"), "Z_A1": ("B_A1", "G_A1_WA1"), "Z_A2": ("B_A2", "G_A2_WA2"),
             "P_A1": ("B_A1", "F_A1"), "P_A2": ("B_A2", "F_A2")}
WITHIN_RULE = {"Z_A1": "A1", "Z_A2": "A2", "P_A1": "A1", "P_A2": "A2"}   # 同じ規則の中の比べ：規則 c が指す行動の割合 s_c で書く
MUST_REPORT = ("D_W_rev", "D_F")
DESCRIPTIVE = ("Z_A1", "Z_A2", "P_A1", "P_A2")
PREFIX_PAIRS = (("B_A1", "B_A2"), ("F_A1", "F_A2"))                       # 規則 c だけが違う対（SE-1）
PREFIX_OF = {"D_F": "F_A1"}                                              # 適格外 (a) を決める共通の部分（ほかは本体）
SIGNS = ("+", "-", "0")


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def record_of(run: Mapping, name: str) -> Mapping:
    return run["G"][name] if name in M.G_SYSTEMS else run["bodies"][name]


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
    """A1 の割合 s ＝ #A1／(#A1 ＋ #A2)。決まった窓が 0 なら定まらない。"""
    return Fraction(counts["A1"], counts["decided"]) if counts["decided"] else None


def share_of(counts: Mapping, action: str) -> Fraction | None:
    """行動 action の割合（A1 なら s、A2 なら 1 − s）。同じ規則の中の比べ（Z・P）にだけ使う。"""
    s = share(counts)
    return None if s is None else (s if action == "A1" else 1 - s)


def first_decided(layer_a: list) -> dict | None:
    return next((r for r in layer_a if r["outcome"] in A.ACTION_IDS), None)


def prefix_label(layer_a: list, e_windows: int) -> dict:
    """共通の部分の k*（最初の決まった窓）と、適格外 (a) の札（README §4.1）。E の窓の記録だけで決まる。"""
    first = first_decided(layer_a)
    k_star = None if first is None else first["window"]
    ineligible = k_star is None or k_star > e_windows
    kind = None
    if ineligible:
        e_outs = [r["outcome"] for r in layer_a if r["window"] <= e_windows]
        kind = "a1_all_none" if all(o == A.NONE for o in e_outs) else "a2_ties_only"
    return {"k_star": k_star, "ineligible_a": ineligible, "ineligible_kind": kind}


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
    """窓の結末の記録が最初に違った窓の番号（違わなければ None）。"""
    return next((x["window"] for x, y in zip(la, lb) if x != y), None)


def _ends(cid: str) -> tuple[str, str]:
    src, tgt = cid.split(".main->")
    return src, tgt


def pair_sums(weights: Mapping[str, float]) -> dict[str, float]:
    sums: dict[str, float] = {}
    for cid, w in sorted(weights.items()):
        key = "|".join(sorted(_ends(cid)))
        sums[key] = sums.get(key, 0.0) + w
    return sums


def _role_names(roles: Mapping) -> dict[str, str]:
    return {roles["cue"]: "cue", roles["source1"]: "source1", roles["source2"]: "source2"}


def margin(unit_state: Mapping) -> float:
    """余裕 g ＝ c／(1 − λ) − θ（出生時の Unit の値から。README §7.2）。"""
    d = unit_state["dynamics"]
    return d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]


def _frac(x: Fraction | None) -> dict | None:
    return None if x is None else {"num": x.numerator, "den": x.denominator, "value": float(x)}


def individual(run: Mapping) -> dict:
    """1 個体の量（README §3・§4.1・§4.2・§6）。生の記録だけから計算する。"""
    plan = M.Plan(**run["plan"])
    e, k_all, p_e, end = plan.e_windows, plan.count, plan.p_e, plan.end
    roles = run["roles"]
    names = _role_names(roles)
    layer = {n: record_of(run, n)["layer_a"] for n in M.SYSTEMS}
    counts_e = {n: window_counts(layer[n], 1, e) for n in M.SYSTEMS}
    counts_u = {n: window_counts(layer[n], e + 1, k_all) for n in M.SYSTEMS}
    prefix = {"B": prefix_label(layer["B_A1"], e), "F": prefix_label(layer["F_A1"], e)}
    contrasts = {}
    for name, (a, b) in CONTRASTS.items():
        action = WITHIN_RULE.get(name, "A1")
        sa, sb = share_of(counts_u[a], action), share_of(counts_u[b], action)
        defined = sa is not None and sb is not None
        ineligible = prefix["F" if PREFIX_OF.get(name) == "F_A1" else "B"]["ineligible_a"]
        missing = [x for x, s in ((a, sa), (b, sb)) if s is None]
        diff = (sa - sb) if defined else None
        contrasts[name] = {
            "share_of": action, "a": _frac(sa), "b": _frac(sb),
            "defined": defined,
            "undefined_kind": None if defined else ("both_systems" if len(missing) == 2 else "one_system"),
            "ineligible_a": ineligible,
            "in_population": defined and not ineligible,
            "difference": _frac(diff), "sign": None if diff is None else sign(diff),
            "n_U_diff": counts_u[a]["decided"] - counts_u[b]["decided"],
            "A1_U_diff": counts_u[a]["A1"] - counts_u[b]["A1"],
        }
    w = run["boundary"]["W"]
    identity = w["A1"] == w["A2"]
    role_cid = {cid: f"{names[_ends(cid)[0]]}->{names[_ends(cid)[1]]}" for cid in run["W_0"]}
    # 命題 S-1 の札（出生時の値から）と、それに反する発火の有無（どの系でも）
    units = run["birth_units"]
    g = {names[u]: margin(units[u]) for u in names}
    silent = {role: g[role] < -E_S for role in ("source1", "source2")}
    fired = {u for n in M.SYSTEMS for _, u in record_of(run, n)["activity"]}
    violations = sorted(role for role in ("source1", "source2")
                        if silent[role] and roles[role] in fired)
    # R5：本体が受けた結果の刺激（世界の予約の記録から）。SE-2：行動 ID が c の決まった窓の数に等しい
    consequences = {}
    for n in M.BODIES + M.FROZEN_BODIES:
        rows = [r for r in record_of(run, n)["world_end"]["reserved"] if r[1] == A.CONSEQUENCE]
        c = M.RULE_OF[n]
        consequences[n] = {"E": sum(1 for r in rows if r[3] <= p_e), "U": sum(1 for r in rows if r[3] > p_e),
                           "decided_windows_of_c": {"E": counts_e[n][c], "U": counts_u[n][c]}}
    # R6：最初に分かれた Pulse・窓
    divergence = {}
    for a, b in PREFIX_PAIRS:
        divergence[f"{a}|{b}"] = {"firing": first_divergence(run["bodies"][a]["activity"], run["bodies"][b]["activity"], 1, end),
                                  "window": first_window_divergence(layer[a], layer[b])}
    for a, b in M.PAIRS:
        divergence[f"{a}|{b}"] = {"firing": first_divergence(run["G"][a]["activity"], run["G"][b]["activity"], p_e + 1, end),
                                  "window": first_window_divergence(layer[a], layer[b]), "lower_bound_pulse": p_e + 2}
    # R7：発火の数（役ごと）。複製の系の記録は U だけ
    firing = {}
    for n in M.SYSTEMS:
        act = record_of(run, n)["activity"]
        firing[n] = {"U": {names[u]: sum(1 for p, x in act if x == u and p > p_e) for u in names}}
        if n not in M.G_SYSTEMS:
            firing[n]["E"] = {names[u]: sum(1 for p, x in act if x == u and p <= p_e) for u in names}
    return {
        "roles": {k: roles[k] for k in ("cue", "source1", "source2")},
        "birth": {names[u]: {"threshold": units[u]["dynamics"]["threshold"],
                             "intrinsic_drive": units[u]["dynamics"]["intrinsic_drive_per_second"], "margin_g": g[names[u]]}
                  for u in names},
        "S1": {"silent_source": silent, "violations": violations},
        "prefix": prefix,
        "structural_identity": identity,
        "counts_E": {n: counts_e[n] for n in M.SYSTEMS},
        "counts_U": {n: counts_u[n] for n in M.SYSTEMS},
        "s_U": {n: _frac(share(counts_u[n])) for n in M.SYSTEMS},
        "s_E": {n: _frac(share(counts_e[n])) for n in M.BODIES},
        "contrasts": contrasts,
        "W": {c: {role_cid[cid]: w[c][cid] for cid in sorted(role_cid)} for c in ("A1", "A2")},
        "W_diff": {role_cid[cid]: w["A1"][cid] - w["A2"][cid] for cid in sorted(role_cid)},
        "pair_sums": {c: pair_sums(w[c]) for c in ("A1", "A2")},
        "consequences": consequences,
        "first_divergence": divergence,
        "firing": firing,
    }


# ---- 判定（README §4・§5） -----------------------------------------------------------------------------

def binom_upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, j) for j in range(k, m + 1)), 2 ** m)


def k2_of_m(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと。分数で厳密に）。"""
    alpha = Fraction(str(PROTOCOL["judgment"]["J_7"]["alpha"]["per_direction"]))
    return next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """二項の和の二分法（0036・0037 と同じ）。"""
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
    """§5.2：m ≥ 1 なら必ず計算する（判定に使わない）。m ＝ 0 なら計算できない。"""
    if n < 1:
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "m = 0"}
    return {"computed": True, "interval": list(clopper_pearson(x, n)), "numerator": x, "denominator": n}


def sign_table(group: list[Mapping], name: str) -> dict:
    """一つの対比の、分母（in_population）と向きごとの数・割合・Clopper–Pearson の 95% 区間。"""
    pop = [v for v in group if v["contrasts"][name]["in_population"]]
    m = len(pop)
    counts = {s: sum(1 for v in pop if v["contrasts"][name]["sign"] == s) for s in SIGNS}
    return {"m": m, "counts": counts,
            "proportion": {s: (counts[s] / m if m else None) for s in ("+", "-")},
            "interval": {s: interval(counts[s], m) for s in ("+", "-")}}


def decide(table: Mapping) -> dict:
    """向きごとの個体の数 ≥ k₂(m) で、その向きで成立（README §4.3）。m ＜ 10 なら判定不能。"""
    j = PROTOCOL["judgment"]
    m = table["m"]
    if m < j["J_7"]["min_population"]:
        return {"status": "inconclusive", "direction": None, "k2": None, "tail_probability": None}
    k = j["k2_of_m"][m]
    if k != k2_of_m(m):
        raise ValueError(f"protocol の k₂({m}) ＝ {k} が二項の計算と違う")
    plus, minus = table["counts"]["+"], table["counts"]["-"]
    direction = "+" if plus >= k else ("-" if minus >= k else None)
    return {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
            "tail_probability": float(binom_upper_tail(m, k))}


def judge(individuals: Mapping[str, Mapping]) -> dict:
    """J_7 と J_W（固定の順序）と、二つを合わせた結果（README §4.3・§4.6）。数と区間は、判定の成否に依らず必ず出す。"""
    group = list(individuals.values())
    t7, tw = sign_table(group, "D"), sign_table(group, "D_W")
    j7 = decide(t7)
    if j7["status"] == "established":
        jw = decide(tw)
    else:
        jw = {"status": "not_tested", "direction": None, "k2": None, "tail_probability": None}
    if j7["status"] == "inconclusive":
        outcome = "inconclusive"
    elif j7["status"] == "not_established":
        outcome = "J_7_not_established"
    elif jw["status"] != "established":
        outcome = "J_7_only"
    else:
        outcome = "both_same_direction" if jw["direction"] == j7["direction"] else "both_opposite_direction"
    return {"J_7": t7 | j7, "J_W": tw | jw, "outcome": outcome,
            "combined_claim": "two conditional results side by side; no same-individual mediation is claimed (README §0.2)"}


def five_numbers(values: list) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null。0036・0037 と同じ）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def cross_table(group: list[Mapping], x: str, y: str) -> dict:
    """二つの対比の両方の分母に入る個体の、符号の 9 つの組（記述。判定に替えない）。片方だけに入る個体の数も並べる。"""
    both = [v for v in group if v["contrasts"][x]["in_population"] and v["contrasts"][y]["in_population"]]
    cells = {f"{a}{b}": 0 for a in SIGNS for b in SIGNS}
    for v in both:
        cells[v["contrasts"][x]["sign"] + v["contrasts"][y]["sign"]] += 1
    return {"order": [x, y], "in_both": len(both),
            f"only_{x}": sum(1 for v in group if v["contrasts"][x]["in_population"] and not v["contrasts"][y]["in_population"]),
            f"only_{y}": sum(1 for v in group if v["contrasts"][y]["in_population"] and not v["contrasts"][x]["in_population"]),
            "cells": cells}


def descriptive_controls(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.1：記述の対照（検定しない）。主の判定と同じ形の分母。適格外・定まらない個体は別の表に並べる。"""
    group = list(individuals.values())
    out = {"contrasts": {n: {"required": n in MUST_REPORT} | sign_table(group, n) for n in MUST_REPORT + DESCRIPTIVE},
           "cross_tables": {"D_W|D_W_rev": cross_table(group, "D_W", "D_W_rev"), "D|D_W": cross_table(group, "D", "D_W")}}
    # 適格外 (a) の個体：定まる対比の符号を、別の表に並べる（判定にも、上の全体の数にも入れない）
    ineligible = {}
    for name in CONTRASTS:
        rows = [(s, v["contrasts"][name]) for s, v in sorted(individuals.items()) if v["contrasts"][name]["ineligible_a"]]
        defined = [c for _, c in rows if c["defined"]]
        counts = {s: sum(1 for c in defined if c["sign"] == s) for s in SIGNS}
        ineligible[name] = {"individuals": [s for s, _ in rows], "defined": len(defined), "counts": counts,
                            "interval": {s: interval(counts[s], len(defined)) for s in ("+", "-")}}
    out["ineligible_a"] = ineligible
    out["undefined_b"] = {name: {kind: sorted(s for s, v in individuals.items()
                                              if not v["contrasts"][name]["ineligible_a"]
                                              and v["contrasts"][name]["undefined_kind"] == kind)
                                 for kind in ("one_system", "both_systems")} for name in CONTRASTS}
    return out


def auxiliary(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.2 の R1〜R9 の全体の数（判定に使わない。R8 の区間は judgment と descriptive_controls にある）。"""
    vals = list(individuals.values())
    eligible = [v for v in vals if not v["prefix"]["B"]["ineligible_a"]]
    violations = sum(len(v["S1"]["violations"]) for v in vals)
    silent = [v for v in vals if any(v["S1"]["silent_source"].values())]
    out = {"R1": {
        "individuals": len(vals),
        "ineligible_a": {kind: sum(1 for v in vals if v["prefix"]["B"]["ineligible_kind"] == kind)
                         for kind in ("a1_all_none", "a2_ties_only")},
        "ineligible_a_F": {kind: sum(1 for v in vals if v["prefix"]["F"]["ineligible_kind"] == kind)
                           for kind in ("a1_all_none", "a2_ties_only")},
        "k_star": five_numbers([v["prefix"]["B"]["k_star"] for v in vals if v["prefix"]["B"]["k_star"] is not None]),
        "structural_identity_in_J_W_population": sum(1 for v in vals if v["structural_identity"]
                                                     and v["contrasts"]["D_W"]["in_population"]),
        # 命題 S-1：反する発火があれば、その件数を開示し、札の報告を取り下げる（README §7.2。判定は S-1 に依らない）
        "S1": {"E_S": E_S, "violations": violations, "labels_withdrawn": violations > 0,
               "individuals_with_silent_source": None if violations else len(silent),
               "of_which_in_J_7_population": None if violations else sum(1 for v in silent if v["contrasts"]["D"]["in_population"])},
    }}
    out["R2"] = {n: {"n_U": five_numbers([v["counts_U"][n]["decided"] for v in vals]),
                     "tie_U": five_numbers([v["counts_U"][n]["tie"] for v in vals]),
                     "none_U": five_numbers([v["counts_U"][n]["none"] for v in vals]),
                     "s_U": five_numbers([v["s_U"][n]["value"] for v in vals if v["s_U"][n] is not None])}
                 for n in M.SYSTEMS}
    out["R3"] = {}
    for name in CONTRASTS:
        pop = [v["contrasts"][name] for v in vals if v["contrasts"][name]["in_population"]]
        diffs = [c["difference"]["value"] for c in pop]
        out["R3"][name] = {"difference": five_numbers(diffs), "abs_difference": five_numbers([abs(x) for x in diffs]),
                           "n_U_diff": five_numbers([c["n_U_diff"] for c in pop]),
                           "A1_U_diff": five_numbers([c["A1_U_diff"] for c in pop])}
    conns = sorted(eligible[0]["W_diff"]) if eligible else []
    out["R4"] = {"W_A1": {c: five_numbers([v["W"]["A1"][c] for v in eligible]) for c in conns},
                 "W_A2": {c: five_numbers([v["W"]["A2"][c] for v in eligible]) for c in conns},
                 "abs_W_diff": {c: five_numbers([abs(v["W_diff"][c]) for v in eligible]) for c in conns},
                 "pair_sum_max_abs_deviation": max((abs(s - W_MAX) for v in vals for c in ("A1", "A2")
                                                    for s in v["pair_sums"][c].values()), default=None),
                 "window_weights": "kept in the raw records (bodies.B_A1 / B_A2 window_weights)"}
    out["R5"] = {n: {part: five_numbers([v["consequences"][n][part] for v in vals]) for part in ("E", "U")}
                 | {"equals_decided_windows_of_c": all(v["consequences"][n][p] == v["consequences"][n]["decided_windows_of_c"][p]
                                                       for v in vals for p in ("E", "U"))}
                 for n in M.BODIES + M.FROZEN_BODIES}
    out["R6"] = {}
    for key in (vals[0]["first_divergence"] if vals else {}):
        rows = [v["first_divergence"][key] for v in vals]
        out["R6"][key] = {"firing": {"none": sum(1 for r in rows if r["firing"] is None),
                                     "pulses": five_numbers([r["firing"] for r in rows if r["firing"] is not None])},
                          "window": {"none": sum(1 for r in rows if r["window"] is None),
                                     "windows": five_numbers([r["window"] for r in rows if r["window"] is not None])}}
    out["R7"] = {n: {part: {role: five_numbers([v["firing"][n][part][role] for v in vals])
                            for role in ("cue", "source1", "source2")}
                     for part in (("E", "U") if n not in M.G_SYSTEMS else ("U",))} for n in M.SYSTEMS}
    out["R9"] = {n: {"s_E": five_numbers([v["s_E"][n]["value"] for v in vals if v["s_E"][n] is not None]),
                     "s_U": five_numbers([v["s_U"][n]["value"] for v in vals if v["s_U"][n] is not None]),
                     "note": "within-body before/after; not a counterfactual contrast"} for n in M.BODIES}
    return out


# ---- 操作の確認（README §8） -----------------------------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "birth_units", "connection_order", "W_0", "bodies", "boundary", "G"}
END_KEYS = {"activity", "sensory", "delta_log", "layer_a", "layer_b", "audit", "world_end", "sigma_end_sha256",
            "history", "pulse_end"}
BODY_KEYS = {"B_A1": END_KEYS | {"sigma_0", "window_weights", "first_intent"},
             "B_A2": END_KEYS | {"sigma_0", "window_weights", "first_intent"},
             "F_A1": END_KEYS | {"sigma_0", "pulse_weights", "first_intent"},
             "F_A2": END_KEYS | {"sigma_0", "pulse_weights", "first_intent"},
             "B_A1_rerun": END_KEYS | {"sigma_p_e", "sigma_end"}}
G_KEYS = END_KEYS | {"pulse_weights", "sigma_after_first"}
BOUNDARY_KEYS = {"steps", "W", "sigma_p_e", "sigma_a", "sigma_b"}
AUDIT_KEYS = {"ok", "matched", "only_in_layer_a", "only_in_layer_b", "win_windows", "issued",
              "identity_issued_plus_carried_equals_wins", "duplicate_delta_ids", "carried_over_windows", "log_matches_world"}
EMPTY_INTERVENTIONS = {"active": [], "frozen": {}}


def _prefix_allowed(path) -> bool:
    """k* の意図の Pulse の後に、規則 c だけが違う二つの系で違ってよい欄：世界の規則 c と、結果の予約（予約の列と、次の予約の番号）。"""
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


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, out["structure"])
        if not out["structure"]:
            for name, f in (("O3", _o3), ("O4", _o4), ("O5", _o5), ("O6", _o6), ("O7", _o7), ("O8", _o8), ("O9", _o9),
                            ("O10", _o10), ("O11", _o11), ("O13", _o13), ("O14", _o14)):
                try:
                    f(run, out[name])
                except Exception as e:                       # noqa: BLE001  記録の形が壊れていても止めずに、その確認を不成立にする
                    out[name].append(f"記録を読めない：{e!r}")
            try:
                _o2(data, mode, out["O2"])
            except Exception as e:                           # noqa: BLE001
                out["O2"].append(f"記録を読めない：{e!r}")
        _o12(seed, mode, out["O12"])
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
        out.append("bodies の系の組・欄が違う")
    if set(run["G"]) != set(M.G_SYSTEMS) or any(set(run["G"][n]) != G_KEYS for n in M.G_SYSTEMS):
        out.append("G の系の組・欄が違う")
    b = run["boundary"]
    if set(b) != BOUNDARY_KEYS or set(b["W"]) != {"A1", "A2"} or set(b["sigma_p_e"]) != set(M.BODIES) \
            or set(b["sigma_a"]) != set(M.G_SYSTEMS) or set(b["sigma_b"]) != set(M.G_SYSTEMS):
        out.append("boundary の欄・系の組が違う")
    if out:
        return
    for n in M.SYSTEMS:
        want = AUDIT_KEYS - set(M.CLONE_AUDIT_DROPS) if n in M.G_SYSTEMS else AUDIT_KEYS
        if set(record_of(run, n)["audit"]) != want:
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
    if len(run["W_0"]) != 6 or set(run["W_0"].values()) != {W0} or run["connection_order"] != sorted(run["W_0"]):
        out.append("W_0 が出生時の値（6 本とも w0）ではないか、接続の順が違う")
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


def _o2(data, mode, out) -> None:
    """関門の組（README §1.1）：宣言の SHA-256 と、すべての系の予定・o・W・L・世界・役・本体の長さ。"""
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
        rec = record_of(run, n)
        rule = {"cue_receptor": run["roles"]["cue_receptor"], "delay": plan.delay, "rule_c": M.RULE_OF[n],
                "respond": True, "multiplicity": AS1.PER_RESERVATION}
        if rec["world_end"]["rule"] != rule:
            out.append(f"{n}：世界の規則（L・規則 c・手がかりの Receptor・応じる・多重度）が違う")
        if [[r["window"], r["open"], r["close"]] for r in rec["layer_a"]] != windows:
            out.append(f"{n}：窓（番号・区間）が、宣言の予定・o・W から作ったものと違う")
        if [[r[1], r[2], r[3]] for r in rec["world_end"]["reserved"] if r[1] == A.CUE] != cues:
            out.append(f"{n}：手がかりの予約が、宣言の予定と違う")
        if rec["pulse_end"] != plan.end:
            out.append(f"{n}：終わりの Pulse が {rec['pulse_end']}（本体の長さは {plan.end}）")
    for n in M.BODIES:
        ex = run["boundary"]["sigma_p_e"][n]["exit"]
        if ex["windows"] != windows or ex["action_of"] != action_of:
            out.append(f"{n}：出口の窓の写し・行動 ID の対応が違う")


def _o3(run, out) -> None:
    """CT-E10 の突合を、保存した層 A・層 B・来歴のログから計算し直す。50 窓への到達、終わりに未発行の予定がないこと。"""
    plan = _plan(run)
    for n in M.SYSTEMS:
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
            out.append(f"{n}：{plan.count} 窓に到達していない（窓の番号の重複・欠落・余分）")
        want_log = sorted(lb) if n not in M.G_SYSTEMS else sorted(x for x in lb if x[0] > plan.p_e)
        if sorted(rec["delta_log"]) != want_log:
            out.append(f"{n}：来歴のログの意図が、世界の受けた意図の記録と違う")
        au = rec["audit"]
        ok = (au["only_in_layer_a"] == [] and au["only_in_layer_b"] == [] and au["duplicate_delta_ids"] == 0
              and au["identity_issued_plus_carried_equals_wins"] is True and au["carried_over_windows"] == []
              and au["win_windows"] == wins and au["issued"] == len(lb) and au["matched"] == len(lb))
        if n not in M.G_SYSTEMS:
            ok = ok and au["ok"] is True and au["log_matches_world"] is True
        if not ok:
            out.append(f"{n}：道具の突合の記録が ok でないか、計算し直した値と違う")


def _o4(run, out) -> None:
    """R-7 の対（SE-1）：Pulse 0 の Σ の違いは規則 c だけ。窓 1〜k* の記録が同じ。k* の意図の Pulse の処理の後の脳の側の Σ が同じ。"""
    for a, b in PREFIX_PAIRS:
        ra, rb = run["bodies"][a], run["bodies"][b]
        if sorted(tuple(p) for p in AS1.sigma_diff(ra["sigma_0"], rb["sigma_0"])) != [("world", "rule", "rule_c")]:
            out.append(f"{a} と {b} の Pulse 0 の Σ の違いが、規則 c だけではない")
        fa, fb = first_decided(ra["layer_a"]), first_decided(rb["layer_a"])
        if (fa is None) != (fb is None):
            out.append(f"{a} と {b} で、最初の決まった窓の有無が違う")
            continue
        if fa is None:
            if ra["first_intent"] is not None or rb["first_intent"] is not None:
                out.append(f"{a}・{b}：決まった窓がないのに、最初の意図の Σ がある")
            if any(ra[k] != rb[k] for k in ("activity", "sensory", "layer_a", "layer_b")):
                out.append(f"{a} と {b}：決まった窓がないのに、発火・感覚・層 A・層 B が違う")
            continue
        k = fa["window"]
        if ra["layer_a"][:k] != rb["layer_a"][:k]:
            out.append(f"{a} と {b} の窓 1〜k* の記録が違う")
            continue
        t = fa["decision_pulse"] + 1
        ia, ib = ra["first_intent"], rb["first_intent"]
        if ia is None or ib is None or ia["pulse"] != t or ib["pulse"] != t \
                or ia["sigma"]["pulse"] != t or ib["sigma"]["pulse"] != t:
            out.append(f"{a}・{b}：k* の意図の Pulse（決定の翌 Pulse）の処理の後の Σ がない")
            continue
        if not all(_prefix_allowed(p) for p in AS1.sigma_diff(ia["sigma"], ib["sigma"])):
            out.append(f"{a} と {b} の、k* の意図の Pulse の後の脳の側の Σ（世界の規則 c と予約のほか）が違う")
        if [x for x in ra["activity"] if x[0] <= t] != [x for x in rb["activity"] if x[0] <= t]:
            out.append(f"{a} と {b} の、k* の意図の Pulse までの発火が違う")


def _o5(run, out) -> None:
    """世界の規則（CT-W1・W3）：源の Receptor の出来事が 0。結果は、行動 ID が規則 c の意図にだけ、意図の Pulse ＋ L − 1。"""
    plan = _plan(run)
    cue_r = run["roles"]["cue_receptor"]
    for n in M.SYSTEMS:
        rec = record_of(run, n)
        w = rec["world_end"]
        if any(r != cue_r for _, r in rec["sensory"]) or any(row[1] != cue_r for row in w["realized"]):
            out.append(f"{n}：手がかりの Receptor のほかに感覚の出来事がある（K1）")
        want = sorted([cue_r, p + plan.delay - 1, did] for p, did, _src, act in rec["layer_b"] if act == M.RULE_OF[n])
        got = sorted([r[2], r[3], r[4]] for r in w["reserved"] if r[1] == A.CONSEQUENCE)
        if got != want:
            out.append(f"{n}：結果の予約が、行動 ID が規則 c の意図ごとに意図の Pulse ＋ L − 1 へ 1 つ、だけになっていない")
        if any(r[1] not in (A.CUE, A.CONSEQUENCE) for r in w["reserved"]) or w["cancelled"]:
            out.append(f"{n}：手がかり・結果のほかの予約か、取り消しがある")
        if w["pending"] or any(len(rids) != 1 or cnt != 1 for _p, _r, rids, cnt in w["realized"]):
            out.append(f"{n}：終わりに成立していない予約があるか、予約が同じ Pulse に重なった")
        if sorted(_expand_realized(w)) != sorted([r[3], r[2]] for r in w["reserved"]):
            out.append(f"{n}：成立した感覚の出来事が、手がかりと結果の予約と違う")
        got_sensory = _expand_realized(w) if n not in M.G_SYSTEMS else [x for x in _expand_realized(w) if x[0] > plan.p_e]
        if rec["sensory"] != got_sensory:
            out.append(f"{n}：来歴のログの感覚の出来事が、世界の成立の記録と違う")
    for n in M.G_SYSTEMS:
        src = run["bodies"][M.BACKGROUND[n]]["world_end"]
        if [x for x in _expand_realized(run["G"][n]["world_end"]) if x[0] <= plan.p_e] \
                != [x for x in _expand_realized(src) if x[0] <= plan.p_e]:
            out.append(f"{n}：E の成立の記録が、複製の元の本体と違う")


def _o6(run, out) -> None:
    """LC1 の FREEZE（SE-3）：F^c の 6 本の重みが、すべての Pulse で W_0。"""
    end, w0 = _plan(run).end, _as_row(run, run["W_0"])
    for n in M.FROZEN_BODIES:
        rows = run["bodies"][n]["pulse_weights"]
        if [p for p, _ in rows] != list(range(1, end + 1)):
            out.append(f"{n}：Pulse ごとの重みの記録が 1〜終わりにそろっていない")
        if any(w != w0 for _, w in rows):
            out.append(f"{n}：ある Pulse で、6 本の重みが W_0 と違う")
        if run["bodies"][n]["history"] != [[0, M.E_LABEL, _freeze(run)]]:
            out.append(f"{n}：介入の履歴が、境界 0 での 6 本の FREEZE（一度だけ）ではない")


def expected_steps(run) -> list:
    plan, six = _plan(run), _six(run)
    p_e, end = plan.p_e, plan.end
    steps = [["S0", n, p_e, "advance_to", {"from": 0}] for n in M.BODIES]
    steps += [["S1", n, p_e, "read_weights", None] for n in M.BODIES]
    steps += [["S2", n, p_e, "clone", {"from": M.BACKGROUND[n]}] for n in M.G_SYSTEMS]
    steps += [["S3", n, p_e, "transplant", {"to": f"W_{key}", "intervention_state_at_transplant": EMPTY_INTERVENTIONS}]
              for n, key in M.TRANSPLANTS.items()]
    steps += [["S4", n, p_e, "declare", {"FREEZE": six, "trace_policy": AS1.ADVANCE}] for n in M.G_SYSTEMS]
    steps += [["S5", n, end, "advance_to", {"from": p_e}] for n in M.BODIES + M.G_SYSTEMS]
    return steps


def _o7(run, out) -> None:
    """境界の順序と差の目録（README §2.4）。S0 の時点の未決の窓・予定・予約、(a) S3 の直後、(b) S4 の直後。"""
    plan = _plan(run)
    p_e, b = plan.p_e, run["boundary"]
    if b["steps"] != expected_steps(run):
        out.append("S0〜S5 の記録が、決めた順序・Pulse・操作と違う（移植の時の介入の状態が空でないものを含む）")
    for n in M.BODIES:
        s = b["sigma_p_e"][n]
        ex = s["exit"]
        if s["pulse"] != p_e or ex["pending"] is not None or ex["reports"] != {} or ex["reports_pulse"] is not None \
                or ex["cursor"] != plan.e_windows:
            out.append(f"S0：{n} に未決の窓・出す予定の意図があるか、P_E の Σ ではない")
        if any(r[1] != A.CUE for r in s["world"]["pending"]):
            out.append(f"S0：{n} の世界に、手がかりのほかの予約（結果の予約）が残っている")
        if b["W"][M.RULE_OF[n]] != _weights_of(s) or s["interventions"] != EMPTY_INTERVENTIONS:
            out.append(f"S1：{n} の重みが記録した W と違うか、本体に介入がある")
        if run["bodies"][n]["history"] != []:
            out.append(f"{n}：本体に介入の宣言の履歴がある")
    for n in M.G_SYSTEMS:
        sa, sb = b["sigma_a"][n], b["sigma_b"][n]
        own = M.RULE_OF[n]
        base = b["sigma_a"][f"G_{own}_W{own}"]
        target = b["W"][M.FROZEN_VALUE[n]]
        if sa["pulse"] != p_e or sb["pulse"] != p_e:
            out.append(f"{n}：Σ (a)・(b) の Pulse の番号が P_E ではない（S1〜S4 のあいだに Pulse を進めた）")
        if sa["interventions"] != EMPTY_INTERVENTIONS:
            out.append(f"(a) {n} の介入の状態が空ではない")
        if _weights_of(sa) != target:
            out.append(f"(a) {n} の重みが移植の先（W_{M.FROZEN_VALUE[n]}）と違う")
        want = [("connections", cid, "weight") for cid in _six(run) if b["W"][own][cid] != target[cid]]
        if sorted(tuple(p) for p in AS1.sigma_diff(base, sa)) != sorted(want):
            out.append(f"(a) {n} と、移植しない複製の Σ の違いが、移植した重みだけではない")
        if n == f"G_{own}_W{own}" and AS1.sigma_diff(b["sigma_p_e"][M.BACKGROUND[n]], sa):
            out.append(f"(a) {n} の Σ が、複製の元の本体の P_E の Σ と違う")
        frozen = sb["interventions"]["frozen"]
        if sb["interventions"]["active"] != _freeze(run) or set(frozen) != set(run["W_0"]):
            out.append(f"(b) {n} の U の介入が 6 本の FREEZE（advance）ではない")
        elif any(frozen[cid] != {"weight": v["weight"], "pre_trace": v["pre_trace"], "post_trace": v["post_trace"],
                                 "policy": AS1.ADVANCE} for cid, v in sb["connections"].items()):
            out.append(f"(b) {n} の FREEZE の値が、宣言の時点の重み・痕跡と違う")
        if any(p[0] != "interventions" for p in AS1.sigma_diff(sa, sb)):
            out.append(f"(b) {n}：S4 で、介入の状態のほかが変わった")
        if sb["world"] != b["sigma_b"][f"G_{own}_W{own}"]["world"]:
            out.append(f"(b) {n} の、これからの軌道を決める世界の状態が、同じ背景の系と違う")
        if run["G"][n]["history"] != [[p_e, M.S4_LABEL, _freeze(run)]]:
            out.append(f"{n}：介入の履歴が、P_E での U の FREEZE の宣言（一度だけ）ではない")


def _o8(run, out) -> None:
    """U の FREEZE：G の 6 系で、6 本の重みが U のすべての Pulse で宣言の値。"""
    plan = _plan(run)
    for n in M.G_SYSTEMS:
        rows = run["G"][n]["pulse_weights"]
        if [p for p, _ in rows] != list(range(plan.p_e + 1, plan.end + 1)):
            out.append(f"{n}：U の Pulse ごとの重みの記録がそろっていない")
        if any(w != _as_row(run, run["boundary"]["W"][M.FROZEN_VALUE[n]]) for _, w in rows):
            out.append(f"{n}：U のある Pulse で、6 本の重みが宣言の値（W_{M.FROZEN_VALUE[n]}）と違う")


def _o9(run, out) -> None:
    """恒等（SE-4・SE-8）：自分の重みの移植。W^{A1} ＝ W^{A2} なら、移植の系も同じ。"""
    pairs = list(M.IDENTITIES)
    if run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"]:
        pairs += list(M.PAIRS)
    for a, b in pairs:
        for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end_sha256"):
            if run["G"][a][key] != run["G"][b][key]:
                out.append(f"{b} が U で {a} と違う（{key}）")
                break


def _o10(run, out) -> None:
    """Pulse P_E ＋ 1 の一致（SE-6）。保存した Pulse P_E ＋ 1 の処理の後の Σ から照合する。"""
    plan = _plan(run)
    first, end = plan.p_e + 1, plan.end
    for a, b in M.PAIRS:
        ua, ub = run["G"][a], run["G"][b]
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


def _o11(run, out) -> None:
    """量の計算：層 A から数え直した窓の結末が、層 B の意図の記録（窓ごとの行動 ID）と一致する。"""
    plan = _plan(run)
    windows = [tuple(w) for w in plan.schedule().windows]
    for n in M.SYSTEMS:
        rec = record_of(run, n)
        problems = layer_a_problems(rec["layer_a"], windows, run["roles"])
        if problems:
            out.append(f"{n}：層 A の記録が整合しない（{problems[0]}）")
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


def _o12(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed {seed} は {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5。関門の 31001〜31040 を含む）")


def _o13(run, out) -> None:
    """記録の非干渉と、関門の本体との同一：B′^{A1} が B^{A1} と同じ。Σ は、保存した全体の値どうしで比べる（SHA-256 は補助）。"""
    r, m = run["bodies"][M.RERUN], run["bodies"]["B_A1"]
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log"):
        if r[key] != m[key]:
            out.append(f"B′^{{A1}} の {key} が B^{{A1}} と違う")
    diff = AS1.sigma_diff(r["sigma_p_e"], run["boundary"]["sigma_p_e"]["B_A1"])
    if diff:
        out.append(f"B′^{{A1}} の P_E の Σ が B^{{A1}} と違う（{[list(x) for x in diff[:3]]}）")
    if M.sigma_sha256(r["sigma_end"]) != r["sigma_end_sha256"] or r["sigma_end_sha256"] != m["sigma_end_sha256"]:
        out.append("B′^{A1} の終わりの Σ が、B^{A1} の終わりの Σ（SHA-256）と違う")
    if r["sigma_end"]["pulse"] != _plan(run).end or r["sigma_p_e"]["pulse"] != _plan(run).p_e or r["history"] != []:
        out.append("B′^{A1} の Σ の Pulse が P_E・終わりではないか、介入の履歴がある")


def _o14(run, out) -> None:
    """F1（SE-7）：本体の P_E の組の和と、移植の後の系の組の和が w_max。"""
    sums = {c: pair_sums(run["boundary"]["W"][c]) for c in ("A1", "A2")}
    for c, s in sums.items():
        if len(s) != 3 or any(abs(x - W_MAX) > F1_TOLERANCE for x in s.values()):
            out.append(f"B^{{{c}}} の P_E の組の和が w_max から離れている")
    for n in M.G_SYSTEMS:
        if pair_sums(_weights_of(run["boundary"]["sigma_a"][n])) != sums[M.FROZEN_VALUE[n]]:
            out.append(f"{n} の組の和が、移植の先の本体の組の和と違う")


# ---- 記録の確認・前提・report（0037 と同じ） ----------------------------------------------------------

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


def check_blinded(data: Mapping, seed: int, mode: str = "smoke") -> dict[str, str]:
    """smoke の盲検の記録の確かめ（0037 と同じ）。O12（seed の範囲）は記録に頼らずここで確かめ直す。"""
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
    o12: list[str] = []
    _o12(seed, mode, o12)
    if o12:
        status["O12"] = "fail"
    return status


def o1_check(out: Path, commit: str | None, repo: Path | None = None) -> list[str]:
    """O1 の証拠（0037 と同じ）。テストのファイルの SHA-256 は repo（省略したときは呼んだ時点の REPO）のものと比べる。"""
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
                "failed_checks": {str(s): v for s, v in failed.items()}, "judgment": None}
    individuals = {str(s): individual(data["run"]) for s, data in sorted(runs.items())}
    return {"mode": mode, "valid": True, "O1": {"status": o1_status, "problems": o1},
            "gate_declaration_sha256": GATE_SHA256,
            "judgment": judge(individuals),
            "descriptive_controls": descriptive_controls(individuals),
            "individuals": individuals, "auxiliary": auxiliary(individuals)}


def verify_results_copy(src: Path, dst: Path) -> list[str]:
    """出力先 src と写し dst の照合（0037 と同じ）。鍵のファイル（run.lock）は写さない。"""
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
    with open(out / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "start", "at": G.now_iso(), "inputs": shas}) + "\n")
    o1 = o1_check(out, records["measurement_commit"])
    if records["state"] == "failed":
        report = {"mode": mode, "valid": False, "record_problems": records["problems"],
                  "O1": ("fail" if o1 else "ok") if mode == "smoke" else {"status": "fail" if o1 else "ok", "problems": o1},
                  "judgment": None}
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
