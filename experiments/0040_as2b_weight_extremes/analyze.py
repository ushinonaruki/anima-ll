"""実験 0040 の記録の解析（事前登録 v0.3 に従う。正本は README・protocol.yaml。v0.2 は #184 merge `9a8651a`、v0.3 は観測の区分の補足）。

0039 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、protocol の結び付き、結果の写しの照合）を引き継ぐ（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid
2. 操作の確認 O2〜O12（README §8）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   判定と推定の量を計算・表示しない。O1 は、run.py が seed に触れる前に測定の commit で走らせた契約テストの記録を確かめる（o1_check）
3. 判定と推定（README §3〜§6）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 個体ごと：定まらない札・系 S-1′ の札・軌道が分かれなかった札、7 系の窓の数と A1 の割合 s、§3.2 のすべての対比の差と符号
   - J_A：m ＜ 10 なら判定不能。向きごとの個体の数 ≥ k₂(m) で、その向きで成立
   - E_A（判定ではない）：p_change・p_＋・p_−・p_flip と Clopper–Pearson の 95%、|D^X| の分布。有効で m ≥ 1 なら必ず計算する
   - §6.1 の記述の対照（D^M・Δ^1・Δ^2・D^X_E、二つの 9 つの組の表、定まらない個体の表）と、§6.2 の R1〜R9（判定に使わない）
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0040_as2b_weight_extremes/analyze.py                    # 本番（data/experiments/0040）
  python experiments/0040_as2b_weight_extremes/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
  python experiments/0040_as2b_weight_extremes/analyze.py --verify-copy <写し>   # 本番の出力先と写しの照合
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
# 事前登録の正本（v0.3）。生の記録の meta に保存した protocol の写しと SHA-256 を、これと照らす
PROTOCOL_SHA256 = hashlib.sha256((REPO / PROTOCOL_PATH).read_bytes()).hexdigest()
PROTOCOL_AS_STORED = json.loads(json.dumps(PROTOCOL))      # raw は JSON なので、写しは JSON を通した形で照らす
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0040")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure",) + tuple(f"O{i}" for i in range(2, 13))
REPORT, LOG = "report.json", "analysis_log.jsonl"
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py")
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
AX = load(f"analysis_{EXPERIMENT}_analyze", REPO / HERE / "analysis.py")     # 事前登録の解析（系 S-1′ の E_S）
A, AS1 = M.A, M.AS1
W_MIN, W_MAX = float(PROTOCOL["brain"]["w_min"]), float(PROTOCOL["brain"]["w_max"])
W0 = float(PROTOCOL["brain"]["initial_weight_w0"])
GATE_DECLARATION, GATE_SHA256 = M.gate_declaration(PROTOCOL)
E_S = AX.silence_bound(AX.c0_values(), AX.gate_set())["E_S"]                # 系 S-1′（README §7.2）。札だけに使う
VALUES = M.intervention_values(W_MIN, W_MAX, W0)                            # README §2.3（C0 の値から）
OUTCOMES = (*A.ACTION_IDS, A.TIE, A.NONE)

# §3.2 の対比：名前 → (a, b)。差は s(a) − s(b)（protocol の quantities.contrasts と同じ）。D_X_E だけ窓 1〜25 の s_E で比べる
CONTRASTS = {"D_X": ("X1", "X2"), "D_M": ("M1", "M2"), "Delta_1": ("X1", "X0"), "Delta_2": ("X0", "X2"), "D_X_E": ("X1", "X2")}
INTERVAL_OF = {"D_X_E": "E"}
MUST_REPORT = ("D_M", "Delta_1", "Delta_2", "D_X_E")
CROSS_TABLES = (("D_X", "D_M"), ("Delta_1", "Delta_2"))
SIGNS = ("+", "-", "0")
ROLES3 = ("cue", "source1", "source2")


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


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


def role_cids(roles: Mapping) -> dict[str, str]:
    """役の名前（protocol の intervention_values の鍵）→ 接続の識別子。源どうしの 2 本も含む。"""
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


def individual(run: Mapping) -> dict:
    """1 個体の量（README §3・§4.1・§4.2・§6）。生の記録だけから計算する。"""
    plan = M.Plan(**run["plan"])
    e, k_all, last_e, end = plan.e_windows, plan.count, plan.last_e_pulse, plan.end
    roles = run["roles"]
    names = _role_names(roles)
    systems = run["systems"]
    layer = {n: systems[n]["layer_a"] for n in M.SYSTEMS}
    counts = {"E": {n: window_counts(layer[n], 1, e) for n in M.SYSTEMS},
              "U": {n: window_counts(layer[n], e + 1, k_all) for n in M.SYSTEMS}}
    shares = {part: {n: share(counts[part][n]) for n in M.SYSTEMS} for part in ("E", "U")}
    contrasts = {}
    for name, (a, b) in CONTRASTS.items():
        part = INTERVAL_OF.get(name, "U")
        sa, sb = shares[part][a], shares[part][b]
        defined = sa is not None and sb is not None
        missing = [x for x, s in ((a, sa), (b, sb)) if s is None]
        diff = (sa - sb) if defined else None
        contrasts[name] = {
            "interval": part, "a": _frac(sa), "b": _frac(sb),
            "defined": defined,
            "undefined_kind": None if defined else ("both_systems" if len(missing) == 2 else "one_system"),
            "in_population": defined,
            "difference": _frac(diff), "sign": None if diff is None else sign(diff),
            "decided_diff": counts[part][a]["decided"] - counts[part][b]["decided"],
            "A1_diff": counts[part][a]["A1"] - counts[part][b]["A1"],
        }
    half = Fraction(1, 2)
    sx1, sx2 = shares["U"]["X1"], shares["U"]["X2"]
    flip = None if sx1 is None or sx2 is None else (sx1 - half) * (sx2 - half) < 0
    # 系 S-1′ の札（出生時の値から）と、それに反する発火の有無（どの系でも）
    units = run["birth_units"]
    g = {names[u]: margin(units[u]) for u in names}
    silent = {role: g[role] < -E_S for role in ("source1", "source2")}
    fired = {u for n in M.SYSTEMS for _, u in systems[n]["activity"]}
    violations = sorted(role for role in ("source1", "source2") if silent[role] and roles[role] in fired)
    # R5：最初に分かれた Pulse・窓
    divergence = {f"{a}|{b}": {"firing": first_divergence(systems[a]["activity"], systems[b]["activity"], 1, end),
                               "window": first_window_divergence(layer[a], layer[b])} for a, b in M.PAIRS}
    # R6：発火の数（役ごと）。R9：U の各窓の c_k と c_k ＋ 1 の源の発火の数
    cues_u = [c for k, c in enumerate(plan.schedule().cues, start=1) if k > e]
    before = {p for c in cues_u for p in (c, c + 1)}
    firing, pre_window = {}, {}
    for n in M.SYSTEMS:
        act = systems[n]["activity"]
        firing[n] = {"E": {names[u]: sum(1 for p, x in act if x == u and p <= last_e) for u in names},
                     "U": {names[u]: sum(1 for p, x in act if x == u and p > last_e) for u in names}}
        pre_window[n] = {role: sum(1 for p, x in act if x == roles[role] and p in before) for role in ("source1", "source2")}
    # R7：意図の数と、結果の予約・刺激の数（0 のはず）
    world = {n: {"intents": len(systems[n]["layer_b"]),
                 "consequence_reservations": sum(1 for r in systems[n]["world_end"]["reserved"] if r[1] == A.CONSEQUENCE)}
             for n in M.SYSTEMS}
    # R4：T0・T1・T2 の 6 本の重み（役の名前で）と組の和
    by_role = {cid: role for role, cid in role_cids(roles).items()}
    weights = {t: {n: {by_role[cid]: w for cid, w in _weights_of(run["pulse_0"][f"sigma_{t}"][n]).items()}
                   for n in M.RECORDED} for t in ("T0", "T1", "T2")}
    weights["end_X1_rerun"] = {by_role[cid]: w for cid, w in _weights_of(systems[M.RERUN]["sigma_end"]).items()}
    sums = {n: pair_sums(_weights_of(run["pulse_0"]["sigma_T2"][n])) for n in M.RECORDED}
    sums[M.RERUN] = pair_sums(_weights_of(systems[M.RERUN]["sigma_end"]))
    return {
        "roles": {k: roles[k] for k in ROLES3},
        "birth": {names[u]: {"threshold": units[u]["dynamics"]["threshold"],
                             "intrinsic_drive": units[u]["dynamics"]["intrinsic_drive_per_second"], "margin_g": g[names[u]]}
                  for u in names},
        "S1_prime": {"silent_source": silent, "violations": violations},
        "never_diverged_X1_X2": divergence["X1|X2"]["firing"] is None,
        "counts_E": counts["E"], "counts_U": counts["U"],
        "s_U": {n: _frac(shares["U"][n]) for n in M.SYSTEMS},
        "s_E": {n: _frac(shares["E"][n]) for n in M.SYSTEMS},
        "contrasts": contrasts,
        "flip": flip,
        "weights": weights, "pair_sums": sums,
        "first_divergence": divergence,
        "firing": firing, "pre_window_firing_U": pre_window,
        "world": world,
    }


# ---- 判定と推定（README §4・§5） -----------------------------------------------------------------------------

def binom_upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, j) for j in range(k, m + 1)), 2 ** m)


def k2_of_m(m: int) -> int:
    """P(Bin(m, 1/2) ≥ k) ≤ 0.025 となる最小の k（向きごと。分数で厳密に）。"""
    alpha = Fraction(str(PROTOCOL["judgment"]["J_A"]["alpha"]["per_direction"]))
    return next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """二項の和の二分法（0036〜0039 と同じ）。"""
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
    ja = PROTOCOL["judgment"]["J_A"]
    m = table["m"]
    if m < ja["min_population"]:
        return {"status": "inconclusive", "direction": None, "k2": None, "tail_probability": None}
    k = PROTOCOL["judgment"]["k2_of_m"][m]
    if k != k2_of_m(m):
        raise ValueError(f"protocol の k₂({m}) ＝ {k} が二項の計算と違う")
    plus, minus = table["counts"]["+"], table["counts"]["-"]
    direction = "+" if plus >= k else ("-" if minus >= k else None)
    return {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
            "tail_probability": float(binom_upper_tail(m, k))}


def judge(individuals: Mapping[str, Mapping]) -> dict:
    """J_A（README §4.3）。数と区間は、判定の成否に依らず必ず出す。"""
    table = sign_table(list(individuals.values()), "D_X")
    d = decide(table)
    outcome = {"inconclusive": "inconclusive", "not_established": "not_established"}.get(d["status"]) \
        or {"+": "plus", "-": "minus"}[d["direction"]]
    return {"J_A": table | d, "outcome": outcome}


def five_numbers(values: list) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null。0036〜0039 と同じ）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def estimate(individuals: Mapping[str, Mapping]) -> dict:
    """主の推定 E_A（README §4.4。判定ではない。閾値を置かない）。分母は J_A と同じ m。"""
    pop = [v for v in individuals.values() if v["contrasts"]["D_X"]["in_population"]]
    m = len(pop)
    signs = Counter(v["contrasts"]["D_X"]["sign"] for v in pop)
    changed = signs["+"] + signs["-"]
    flips = sum(1 for v in pop if v["flip"])
    diffs = [abs(v["contrasts"]["D_X"]["difference"]["value"]) for v in pop]
    return {"m": m,
            "p_change": {"count": changed, "proportion": changed / m if m else None, "interval": interval(changed, m)},
            "p_plus": {"count": signs["+"], "proportion": signs["+"] / m if m else None, "interval": interval(signs["+"], m)},
            "p_minus": {"count": signs["-"], "proportion": signs["-"] / m if m else None, "interval": interval(signs["-"], m)},
            "p_flip": {"count": flips, "proportion": flips / m if m else None, "interval": interval(flips, m)},
            "abs_D_X": {"all": five_numbers(diffs), "changed": five_numbers([x for x in diffs if x != 0])},
            "note": "estimate only; no threshold; not a judgment (README section 4.4)"}


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
    """README §6.1：必ず報告する記述の対照（検定しない）。主の判定と同じ形の分母。定まらない個体は別の表に並べる。"""
    group = list(individuals.values())
    out = {"contrasts": {}, "cross_tables": {f"{x}|{y}": cross_table(group, x, y) for x, y in CROSS_TABLES}}
    for n in MUST_REPORT:
        pop = [v["contrasts"][n]["difference"]["value"] for v in group if v["contrasts"][n]["in_population"]]
        out["contrasts"][n] = sign_table(group, n) | {"difference": five_numbers(pop)}
    out["undefined"] = {name: {kind: sorted(s for s, v in individuals.items() if v["contrasts"][name]["undefined_kind"] == kind)
                               for kind in ("one_system", "both_systems")} for name in CONTRASTS}
    return out


def auxiliary(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.2 の R1〜R9 の全体の数（判定に使わない。R8 の区間は judgment・estimate・descriptive_controls にある）。"""
    vals = list(individuals.values())
    violations = sum(len(v["S1_prime"]["violations"]) for v in vals)
    silent = [v for v in vals if any(v["S1_prime"]["silent_source"].values())]
    out = {"R1": {
        "individuals": len(vals),
        "undefined_D_X": {kind: sum(1 for v in vals if v["contrasts"]["D_X"]["undefined_kind"] == kind)
                          for kind in ("one_system", "both_systems")},
        "never_diverged_X1_X2": sum(1 for v in vals if v["never_diverged_X1_X2"]),
        "never_diverged_X1_X2_in_J_A_population": sum(1 for v in vals if v["never_diverged_X1_X2"]
                                                      and v["contrasts"]["D_X"]["in_population"]),
        # 系 S-1′：反する発火があれば、その件数を開示し、札の報告を取り下げる（README §7.2。判定は S-1′ に依らない）
        "S1_prime": {"E_S": E_S, "violations": violations, "labels_withdrawn": violations > 0,
                     "individuals_with_silent_source": None if violations else len(silent),
                     "of_which_in_J_A_population": None if violations else sum(1 for v in silent
                                                                                if v["contrasts"]["D_X"]["in_population"])},
    }}
    out["R2"] = {n: {part: {"decided": five_numbers([v[f"counts_{part}"][n]["decided"] for v in vals]),
                            "tie": five_numbers([v[f"counts_{part}"][n]["tie"] for v in vals]),
                            "none": five_numbers([v[f"counts_{part}"][n]["none"] for v in vals]),
                            "s": five_numbers([v[f"s_{part}"][n]["value"] for v in vals if v[f"s_{part}"][n] is not None])}
                     for part in ("E", "U")} for n in M.SYSTEMS}
    out["R3"] = {}
    for name in CONTRASTS:
        pop = [v["contrasts"][name] for v in vals if v["contrasts"][name]["in_population"]]
        diffs = [c["difference"]["value"] for c in pop]
        out["R3"][name] = {"difference": five_numbers(diffs), "abs_difference": five_numbers([abs(x) for x in diffs]),
                           "decided_diff": five_numbers([c["decided_diff"] for c in pop]),
                           "A1_diff": five_numbers([c["A1_diff"] for c in pop])}
    out["R4"] = {"pair_sum_equals_w_max_exactly": all(s == W_MAX for v in vals for n in M.SYSTEMS
                                                      for s in v["pair_sums"][n].values()),
                 "T2_values_by_system": {n: vals[0]["weights"]["T2"][n] for n in M.RECORDED} if vals else None,
                 "end_values_X1_rerun": vals[0]["weights"]["end_X1_rerun"] if vals else None,
                 "pulse_weights": "kept in the raw records (systems.<name>.pulse_weights); constant under FREEZE (O6)"}
    out["R5"] = {}
    for key in (vals[0]["first_divergence"] if vals else {}):
        rows = [v["first_divergence"][key] for v in vals]
        out["R5"][key] = {"firing": {"none": sum(1 for r in rows if r["firing"] is None),
                                     "pulses": five_numbers([r["firing"] for r in rows if r["firing"] is not None])},
                          "window": {"none": sum(1 for r in rows if r["window"] is None),
                                     "windows": five_numbers([r["window"] for r in rows if r["window"] is not None])}}
    out["R6"] = {n: {part: {role: five_numbers([v["firing"][n][part][role] for v in vals]) for role in ROLES3}
                     for part in ("E", "U")} for n in M.SYSTEMS}
    out["R7"] = {n: {"intents": five_numbers([v["world"][n]["intents"] for v in vals]),
                     "consequence_reservations_total": sum(v["world"][n]["consequence_reservations"] for v in vals)}
                 for n in M.SYSTEMS}
    out["R9"] = {n: {role: five_numbers([v["pre_window_firing_U"][n][role] for v in vals]) for role in ("source1", "source2")}
                 | {"note": "firings at c_k and c_k + 1 of each U window; not caused by that cue; descriptive only"}
                 for n in M.SYSTEMS}
    return out


# ---- 操作の確認（README §8） -----------------------------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "birth_units", "connection_order", "W_0", "values", "pulse_0", "systems"}
END_KEYS = {"activity", "sensory", "delta_log", "layer_a", "layer_b", "audit", "world_end", "sigma_end", "sigma_end_sha256",
            "history", "pulse_end"}
# 観測の 6 系は Pulse ごとの重みを実測して持つ。X1′ は終わりの記録だけ（README §2.2 の観測の区分。v0.3）
SYSTEM_KEYS = {n: END_KEYS | {"pulse_weights"} for n in M.RECORDED} | {M.RERUN: END_KEYS}
PULSE_0_KEYS = {"steps", "sigma_T0", "sigma_T1", "sigma_T2"}
AUDIT_KEYS = {"ok", "matched", "only_in_layer_a", "only_in_layer_b", "win_windows", "issued",
              "identity_issued_plus_carried_equals_wins", "duplicate_delta_ids", "carried_over_windows", "log_matches_world"}
EMPTY_INTERVENTIONS = {"active": [], "frozen": {}}


def _plan(run) -> "M.Plan":
    return M.Plan(**run["plan"])


def _six(run) -> list[str]:
    return sorted(run["W_0"])


def _freeze(run) -> list:
    return [["FREEZE", _six(run), AS1.ADVANCE]]


def _as_row(run, weights: Mapping[str, float]) -> list[float]:
    return [weights[cid] for cid in run["connection_order"]]


def _windows(plan) -> list[list[int]]:
    return [list(w) for w in plan.schedule().windows]


def _expand_realized(world: Mapping) -> list:
    """世界の成立の記録を、感覚の出来事の列 [Pulse, Receptor]（個数の分だけ並べる）にする。"""
    return [[pulse, receptor] for pulse, receptor, _rids, n in world["realized"] for _ in range(n)]


def target_weights(run, name: str) -> dict[str, float]:
    """系 name の T1 以後の 6 本の重み（README §2.3 の表。移植しない X0 は出生時の値）。"""
    out = dict(run["W_0"])
    key = M.TRANSPLANTED.get(name)
    if key is not None:
        cids = role_cids(run["roles"])
        out |= {cids[role]: VALUES[key][role] for role in M.ROLE_KEYS}
    return dict(sorted(out.items()))


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, out["structure"])
        if not out["structure"]:
            for name, f in (("O3", _o3), ("O4", _o4), ("O5", _o5), ("O6", _o6), ("O7", _o7), ("O8", _o8), ("O9", _o9),
                            ("O10", _o10), ("O11", _o11)):
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
    if set(run["systems"]) != set(SYSTEM_KEYS) or any(set(run["systems"][n]) != keys for n, keys in SYSTEM_KEYS.items()):
        out.append("systems の系の組・欄が違う")
    p0 = run["pulse_0"]
    if set(p0) != PULSE_0_KEYS or any(set(p0[k]) != set(M.RECORDED) for k in ("sigma_T0", "sigma_T1", "sigma_T2")):
        out.append("pulse_0 の欄・系の組が違う")
    if out:
        return
    for n in M.SYSTEMS:
        if set(run["systems"][n]["audit"]) != AUDIT_KEYS:
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
    if run["values"] != json.loads(json.dumps(VALUES)):
        out.append("介入の値が、C0 の w_min・w_max・w0 から作った README §2.3 の表と違う")
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
    """関門の組（README §1.1）：宣言の SHA-256 と、すべての系の予定・o・W・L・世界・役・本体の長さ。すべての系で respond は偽。"""
    run, gate = data["run"], data["meta"].get("gate")
    if not isinstance(gate, Mapping) or gate.get("sha256") != GATE_SHA256 or gate.get("declaration") != GATE_DECLARATION:
        out.append("meta の関門の宣言・SHA-256 が、v0.2（protocol の値・リポジトリのファイル）と違う")
        return
    plan = _plan(run)
    if mode in ("formal", "smoke"):
        e_windows = int(PROTOCOL["timeline"]["lead_in_E"]["windows"][1])
        if plan != M.plan_from_declaration(gate["declaration"], e_windows):
            out.append("区間・予定が、関門の宣言から取った値と違う")
    windows = _windows(plan)
    cues = [[A.CUE, run["roles"]["cue_receptor"], c] for c in plan.schedule().cues]
    action_of = {run["roles"]["source1"]: "A1", run["roles"]["source2"]: "A2"}
    rule = {"cue_receptor": run["roles"]["cue_receptor"], "delay": plan.delay, "rule_c": M.RULE_C,
            "respond": False, "multiplicity": AS1.PER_RESERVATION}
    for n in M.SYSTEMS:
        rec = run["systems"][n]
        if rec["world_end"]["rule"] != rule:
            out.append(f"{n}：世界の規則（L・rule_c・手がかりの Receptor・結果を返さない・多重度）が違う")
        if [[r["window"], r["open"], r["close"]] for r in rec["layer_a"]] != windows:
            out.append(f"{n}：窓（番号・区間）が、宣言の予定・o・W から作ったものと違う")
        if [[r[1], r[2], r[3]] for r in rec["world_end"]["reserved"] if r[1] == A.CUE] != cues:
            out.append(f"{n}：手がかりの予約が、宣言の予定と違う")
        if rec["pulse_end"] != plan.end:
            out.append(f"{n}：終わりの Pulse が {rec['pulse_end']}（本体の長さは {plan.end}）")
    for n in M.RECORDED:
        for t in ("T0", "T2"):
            ex = run["pulse_0"][f"sigma_{t}"][n]["exit"]
            if ex["windows"] != windows or ex["action_of"] != action_of:
                out.append(f"{n}：{t} の出口の窓の写し・行動 ID の対応が違う")


def _o3(run, out) -> None:
    """CT-E10 の突合を、保存した層 A・層 B・来歴のログから計算し直す。50 窓への到達、終わりに未発行の予定がないこと。"""
    plan = _plan(run)
    for n in M.SYSTEMS:
        rec = run["systems"][n]
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
        if sorted(rec["delta_log"]) != sorted(lb):
            out.append(f"{n}：来歴のログの意図が、世界の受けた意図の記録と違う")
        au = rec["audit"]
        ok = (au["ok"] is True and au["log_matches_world"] is True and au["only_in_layer_a"] == []
              and au["only_in_layer_b"] == [] and au["duplicate_delta_ids"] == 0
              and au["identity_issued_plus_carried_equals_wins"] is True and au["carried_over_windows"] == []
              and au["win_windows"] == wins and au["issued"] == len(lb) and au["matched"] == len(lb))
        if not ok:
            out.append(f"{n}：道具の突合の記録が ok でないか、計算し直した値と違う")


def expected_steps(run) -> list:
    end, six = _plan(run).end, _six(run)
    build = {"rule_c": M.RULE_C, "respond": False}
    freeze = {"FREEZE": six, "trace_policy": AS1.ADVANCE}

    def t1(n):
        key = M.TRANSPLANTED.get(n)
        if key is None:
            return ["T1", n, 0, "none", None]
        return ["T1", n, 0, "transplant", {"values": key, "intervention_state_at_transplant": EMPTY_INTERVENTIONS}]
    steps = []
    for n in M.RECORDED:
        steps += [["T0", n, 0, "build", build], t1(n), ["T2", n, 0, "declare", freeze]]
    steps += [["T3", n, end, "advance_to", {"from": 0}] for n in M.RECORDED]
    steps += [["T0", M.RERUN, 0, "build", build], t1(M.RERUN), ["T2", M.RERUN, 0, "declare", freeze],
              ["T3", M.RERUN, end, "advance_to", {"from": 0}]]
    return steps


def _o4(run, out) -> None:
    """Pulse 0 の差の目録（SE-A1。README §2.4）：T0〜T2 で Pulse を進めない。(a) T1 の違いは 4 本の重みだけ、(b) T2 の FREEZE。"""
    p0 = run["pulse_0"]
    if p0["steps"] != expected_steps(run):
        out.append("T0〜T3 の記録が、決めた順序・Pulse・操作と違う（移植の時の介入の状態が空でないものを含む）")
    base0 = p0["sigma_T0"]["X0"]
    for n in M.RECORDED:
        s0, s1, s2 = p0["sigma_T0"][n], p0["sigma_T1"][n], p0["sigma_T2"][n]
        if (s0["pulse"], s1["pulse"], s2["pulse"]) != (0, 0, 0):
            out.append(f"{n}：T0〜T2 の Σ の Pulse の番号が 0 ではない（Pulse を進めた）")
        if AS1.sigma_diff(base0, s0):
            out.append(f"{n}：T0 の Σ が、ほかの系と違う（同じ組み立てではない）")
        if s1["interventions"] != EMPTY_INTERVENTIONS:
            out.append(f"(a) {n}：T1 の介入の状態が空ではない")
        target = target_weights(run, n)
        if _weights_of(s1) != target:
            out.append(f"(a) {n}：T1 の重みが README §2.3 の表と違う")
        want = sorted(("connections", cid, "weight") for cid in _six(run) if target[cid] != run["W_0"][cid])
        if sorted(tuple(p) for p in AS1.sigma_diff(p0["sigma_T1"]["X0"], s1)) != want:
            out.append(f"(a) {n}：X0 との T1 の Σ の違いが、移植した重みだけではない")
        frozen = s2["interventions"]["frozen"]
        if s2["interventions"]["active"] != _freeze(run) or set(frozen) != set(run["W_0"]):
            out.append(f"(b) {n}：T2 の介入が 6 本の FREEZE（advance）ではない")
        elif any(frozen[cid] != {"weight": v["weight"], "pre_trace": v["pre_trace"], "post_trace": v["post_trace"],
                                 "policy": AS1.ADVANCE} for cid, v in s2["connections"].items()):
            out.append(f"(b) {n}：T2 の FREEZE の値が、宣言の時点の重み・痕跡と違う")
        if any(p[0] != "interventions" for p in AS1.sigma_diff(s1, s2)):
            out.append(f"(b) {n}：T2 で、介入の状態のほかが変わった")
    if AS1.sigma_diff(p0["sigma_T0"]["X0"], p0["sigma_T1"]["X0"]):
        out.append("(a) X0：移植しないのに、T0 と T1 の Σ が違う")
    for n in M.SYSTEMS:
        if run["systems"][n]["history"] != [[0, M.T2_LABEL, _freeze(run)]]:
            out.append(f"{n}：介入の履歴が、境界 0 での 6 本の FREEZE（一度だけ）ではない")


def _o5(run, out) -> None:
    """世界（SE-A4）：結果の予約・刺激が 0。源の Receptor の出来事が 0。手がかりの Receptor の出来事が、関門の予定の手がかりと一致する。"""
    plan = _plan(run)
    cue_r = run["roles"]["cue_receptor"]
    cues = sorted([c, cue_r] for c in plan.schedule().cues)
    for n in M.SYSTEMS:
        rec = run["systems"][n]
        w = rec["world_end"]
        if any(r[1] != A.CUE for r in w["reserved"]) or w["cancelled"] or w["pending"]:
            out.append(f"{n}：手がかりのほかの予約（結果の予約）・取り消し・終わりに成立していない予約がある")
        if any(len(rids) != 1 or cnt != 1 for _p, _r, rids, cnt in w["realized"]) or sorted(_expand_realized(w)) != cues:
            out.append(f"{n}：成立した感覚の出来事が、関門の予定の手がかりと違う")
        if any(r != cue_r for _, r in rec["sensory"]) or rec["sensory"] != _expand_realized(w):
            out.append(f"{n}：来歴のログの感覚の出来事が、手がかりの Receptor の手がかりだけではない（K1）")
        if len(rec["layer_b"]) != sum(1 for r in rec["layer_a"] if r["winner_unit"] is not None):
            out.append(f"{n}：層 B の意図の数が、層 A の勝ちの窓の数と違う")


def _o6(run, out) -> None:
    """FREEZE（SE-A5）：6 つの系で、6 本の重みが、すべての Pulse で T2 の値。X1′ は足す記録をしないので、終わりの Σ の重みと
    介入の履歴（O4）で確かめ、全 Pulse の一致は O9（X1 と同じ）を通して従う。"""
    end = _plan(run).end
    for n in M.RECORDED:
        rows = run["systems"][n]["pulse_weights"]
        want = _as_row(run, _weights_of(run["pulse_0"]["sigma_T2"][n]))
        if [p for p, _ in rows] != list(range(1, end + 1)):
            out.append(f"{n}：Pulse ごとの重みの記録が 1〜終わりにそろっていない")
        if any(w != want for _, w in rows):
            out.append(f"{n}：ある Pulse で、6 本の重みが T2 の値と違う")
    if _weights_of(run["systems"][M.RERUN]["sigma_end"]) != _weights_of(run["pulse_0"]["sigma_T2"]["X1"]):
        out.append("X1′：終わりの 6 本の重みが、X1 の T2 の値と違う")


def _o7(run, out) -> None:
    """F1 と範囲（SE-A6）：7 系で、各組の 2 本の和が w_max と（二進の浮動小数で）ちょうど同じで、各値が [w_min, w_max]。"""
    weights = {n: _weights_of(run["pulse_0"]["sigma_T2"][n]) for n in M.RECORDED}
    weights[M.RERUN] = _weights_of(run["systems"][M.RERUN]["sigma_end"])
    for n, w in weights.items():
        sums = pair_sums(w)
        if len(sums) != 3 or any(s != W_MAX for s in sums.values()):
            out.append(f"{n}：組の和が w_max とちょうど同じではない")
        if any(not (W_MIN <= x <= W_MAX) for x in w.values()):
            out.append(f"{n}：重みが [w_min, w_max] の外にある")
        if w != target_weights(run, n):
            out.append(f"{n}：重みが README §2.3 の表と違う")


def _same_end(run, a: str, b: str, out: list[str], label: str) -> None:
    """二つの系の終わりの記録の完全な一致（O8・O9。v0.3）：発火・感覚・層 A・層 B・来歴のログの意図・介入の履歴と、終わりの Σ の
    値の全体（主）。SHA-256 は補助：保存した Σ から計算し直した値が、記録した値と、相手の値に一致する。"""
    ra, rb = run["systems"][a], run["systems"][b]
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "history"):
        if ra[key] != rb[key]:
            out.append(f"{label}：{key} が違う")
    end = _plan(run).end
    if ra["sigma_end"]["pulse"] != end or rb["sigma_end"]["pulse"] != end:
        out.append(f"{label}：終わりの Σ の Pulse が終わりではない")
    diff = AS1.sigma_diff(ra["sigma_end"], rb["sigma_end"])
    if diff:
        out.append(f"{label}：終わりの Σ の値が違う（{[list(x) for x in diff[:3]]}）")
    for n, r in ((a, ra), (b, rb)):
        if M.sigma_sha256(r["sigma_end"]) != r["sigma_end_sha256"]:
            out.append(f"{label}：{n} の終わりの Σ の SHA-256 が、保存した Σ から計算し直した値と違う")
    if ra["sigma_end_sha256"] != rb["sigma_end_sha256"]:
        out.append(f"{label}：終わりの Σ の SHA-256 が違う")


def _o8(run, out) -> None:
    """恒等：X0^tr（自分の値の移植）が X0 と同じ（値の完全な一致が主、SHA-256 は補助）。"""
    _same_end(run, "X0", M.IDENTITY, out, "X0^tr と X0")


def _o9(run, out) -> None:
    """記録の非干渉（SE-A8）：X1′ が X1 と同じ（値の完全な一致が主、SHA-256 は補助）。"""
    _same_end(run, "X1", M.RERUN, out, "X1′ と X1")


def _o10(run, out) -> None:
    """共通の始まり（SE-A2）。保存した記録から確かめる限られた確認（README §8 の O10。v0.3）：5 つの値の系で、最初に Unit が発火する
    Pulse t₁ が同じで、t₁ の処理の終わりまで全 Unit の発火・層 A が同じで、最初に分かれた Pulse が t₁ ＋ 1 以後。Unit の内部の状態は
    ここでは確かめない（CT-40-5 の合成の系で直接確かめる）。"""
    systems, end = run["systems"], _plan(run).end
    ref = systems["X0"]
    t1 = min((p for p, _u in ref["activity"]), default=None)

    def layer_upto(la: list) -> list:
        return [r for r in la if r["close"] <= t1 or (r["decision_pulse"] is not None and r["decision_pulse"] <= t1)]
    for n in M.VALUE_SYSTEMS:
        rec = systems[n]
        mine = min((p for p, _u in rec["activity"]), default=None)
        if mine != t1:
            out.append(f"{n}：最初に Unit が発火する Pulse が X0 と違う")
            continue
        if t1 is None:
            if rec["activity"] != ref["activity"] or rec["layer_a"] != ref["layer_a"]:
                out.append(f"{n}：どの Unit も発火しないのに、発火・層 A が X0 と違う")
            continue
        if [x for x in rec["activity"] if x[0] <= t1] != [x for x in ref["activity"] if x[0] <= t1]:
            out.append(f"{n} と X0 の、t₁ までの発火が違う")
        if layer_upto(rec["layer_a"]) != layer_upto(ref["layer_a"]):
            out.append(f"{n} と X0 の、t₁ までの層 A が違う")
        fd = first_divergence(rec["activity"], ref["activity"], 1, end)
        if fd is not None and fd < t1 + 1:
            out.append(f"{n} と X0 の最初に分かれた Pulse が t₁ ＋ 1 より前")


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
        rec = run["systems"][n]
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
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5。関門の 31001〜31040、0039 の 32001〜32399 を含む）")


# ---- 記録の確認・前提・report（0039 と同じ） ----------------------------------------------------------

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
    """smoke の盲検の記録の確かめ（0039 と同じ）。O12（seed の範囲）は記録に頼らずここで確かめ直す。"""
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
    """O1 の証拠（0039 と同じ）。テストのファイルの SHA-256 は repo（省略したときは呼んだ時点の REPO）のものと比べる。"""
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
    """出力先 src と写し dst の照合（0039 と同じ）。鍵のファイル（run.lock）は写さない。"""
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
