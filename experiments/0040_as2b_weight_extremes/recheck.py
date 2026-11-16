"""実験 0040 の独立の検算（README §9.1。標準のライブラリだけ）。

この実験の解析・測定の道具も、anima_ll も、AS2b の道具も、protocol.yaml を読む道具も読み込まない。保存した生の記録
（seeds/<seed>/raw.json.gz）だけから、定義（README §3〜§6）を書き起こし直して report の欄をすべて組み立て直し、report.json と
欄ごとに照合する。判定の閾値などの事前登録の値は、README・protocol.yaml（v0.3。判定の条件は v0.2 と同じ）から書き起こした
PREREGISTERED から取る。生の記録の meta に保存された protocol の写し（meta.protocol・meta.protocol_sha256）は、次のことを確かめる
だけに使う（0039 の道具 v0.3 と同じ形）
- 全個体にあり、全個体で同じであること
- 写しの中身全体を JSON に正規化したもののハッシュが、事前登録 v0.3 の protocol の固定のハッシュ（PROTOCOL_JSON_SHA256）と同じであること
  （PREREGISTERED で個別に照らさない欄の改変も見つける）
- SHA-256 が、リポジトリの確定済みの protocol.yaml のバイト列の SHA-256（PROTOCOL_FILE_SHA256）と同じであること
- 写しの中の判定に関わる値が、PREREGISTERED と同じであること。k₂(m) の表は、二項から求め直した値と同じであること
どれかが欠けたり違ったりすれば、食い違いとして数える。

report との照合（recheck。PR #185 のレビュー 5924138620 の修正必須 1）
- 生の記録から、report と同じ形の期待値を作る：mode・valid・O1・関門の宣言の SHA-256、判定 J_A、推定 E_A、§6.1 の記述の対照
  （数・割合・区間・差の分布、二つの 9 つの組の表、定まらない個体の表）、個体ごとの量（窓の数・s・対比・入れ替わり・札・重み・
  組の和・最初に分かれた Pulse と窓・発火の数・窓の前の発火・世界の記録）、補助の記録 R1〜R7・R9
- 期待値と report を、欄の組・列の長さ・葉の値まで、すべての欄で比べる（compare）。葉の値は、型（真偽・文字列・null・数）も比べる。
  数はちょうど同じであることを求める。許す違いは、計算の書き方が解析と違う二つだけ：Clopper–Pearson の端点（二分法の書き方）と
  系 S-1′ の E_S（設計図から書き起こした式）で、絶対値 1e-9 まで
- 操作の確認の主なもの（O3〜O11）を、別の書き方で

測定の来歴と全件性（recheck_directory。同じレビューの修正必須 2。guard・解析の道具の確かめに頼らず、ファイルを直接読む）
- seeds/ の下は、seed の名前（先頭に 0 のない 10 進）のフォルダだけで、各フォルダは開始の記録・終了の記録・raw の 3 つだけを持つ
- 終了の記録が completed で、raw のファイルの SHA-256・バイト数が終了の記録と同じ
- フォルダの名前・開始の記録・終了の記録・raw の meta・raw の run の seed が同じ。experiment・kind・mode が開始・終了・meta で同じ
- 測定の commit：開始の記録 ＝ 終了の記録の measurement_commit_end ＝ raw の meta（40 桁）で、全 seed で一つ。report の
  measurement_commit と O1 の記録の commit も、それと同じ
- protocol の SHA-256：開始の記録 ＝ raw の meta ＝ 確定済みの protocol.yaml（PROTOCOL_FILE_SHA256）
- 関門の宣言：raw の meta の SHA-256 ＝ 固定の値（GATE_SHA256）＝ リポジトリの宣言のファイル。meta の宣言の中身 ＝ そのファイル
- seed の組：本番は 33001〜33200 の 200 個体がちょうど（欠け・余り・範囲の外がない）。合成は合成の範囲の中。
  smoke の盲検の記録は、この検算の対象ではない（食い違いとして数える）
- O1 の記録：欄の組、commit、終了コード 0、すべて通った結果の行、走らせた契約テストの組、テストのファイルの SHA-256
  （この検算が置かれたリポジトリのファイルと照らす。測定の commit で走らせる）

使い方（結果を保存したフォルダを渡す。測定の commit で、計算の後で一度だけ）:
  python experiments/0040_as2b_weight_extremes/recheck.py <フォルダ> [--write <結果の JSON>]
"""

import argparse
import gzip
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

SYSTEMS = ["X1", "X2", "M1", "M2", "X0", "X0_tr", "X1_rerun"]
RECORDED = SYSTEMS[:6]
RERUN = "X1_rerun"
# 対比：名前 → (a, b, 区間)
CONTRASTS = {"D_X": ("X1", "X2", "U"), "D_M": ("M1", "M2", "U"), "Delta_1": ("X1", "X0", "U"),
             "Delta_2": ("X0", "X2", "U"), "D_X_E": ("X1", "X2", "E")}
TABLES = ["D_M", "Delta_1", "Delta_2", "D_X_E"]
CROSS = [("D_X", "D_M"), ("Delta_1", "Delta_2")]
PAIRS = [("X1", "X2"), ("M1", "M2"), ("X1", "X0"), ("X2", "X0")]          # R5 の対（README §6.2）
ROLES3 = ("cue", "source1", "source2")
SOURCES = ("source1", "source2")
KINDS = ("one_system", "both_systems")
ACTIONS = ("A1", "A2")
SIGNS = ("+", "-", "0")
# report の決まった文（README §4.4・§6.2。解析の道具と同じ文を、ここに書き起こす）
NOTES = {"estimate": "estimate only; no threshold; not a judgment (README section 4.4)",
         "R4": "kept in the raw records (systems.<name>.pulse_weights); constant under FREEZE (O6)",
         "R9": "firings at c_k and c_k + 1 of each U window; not caused by that cue; descriptive only"}
HEX = set("0123456789abcdef")
DIGITS = set("0123456789")
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROTOCOL_FILE = HERE / "protocol.yaml"
# 事前登録 v0.3 の protocol.yaml（v0.2 は #184 merge `9a8651a`。v0.3 は #186 merge `1ad6334`、観測の区分の補足）を、raw の meta と同じ形
# （YAML を読み、JSON を通した形）にして正規化した JSON の SHA-256。正規化：json.dumps(写し, sort_keys=True, ensure_ascii=False,
# separators=(",", ":")) の UTF-8。値は契約テストで、正本から計算し直して照らす
PROTOCOL_JSON_SHA256 = "5e4fa28eb3473748afc392bfd05064c50c1c931218ccae063fc021d74c57af87"
PROTOCOL_FILE_SHA256 = "62c15db4340eac25b78fd4cff31e90983fd13850f914a9dc36ec5616fa787fda"   # 同じ正本のファイルのバイト列
# 引き継ぐ関門の宣言 v0.2（protocol の inherited_gate_set。#184 で確定）のファイルと、そのバイト列の SHA-256
GATE_FILE = "experiments/0038_as2b_forward_gate/gate_declaration.json"
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
# 事前登録（v0.2 で確定した判定の条件。v0.3 でも同じ）から書き起こした値：README §1.2・§2.3・§4.3・§5.1・§9.2、protocol.yaml の
# judgment・timeline・brain・seeds。判定はこの値で計算し、meta の protocol の写しは、これと照らすだけに使う
PREREGISTERED = {
    "experiment": "0040", "kind": "preregistered_test",
    "alpha_per_direction": Fraction(1, 40), "alpha_two_sided": Fraction(1, 20),
    "min_population": 10,
    "k2_range": (10, 200),
    "lead_in_windows": [1, 25], "trial_windows": [26, 50], "lead_in_pulses": [1, 1065], "runs_to": 2072,
    "w_min": 0.0, "w_max": 0.01, "w0": 0.005,
    "respond": False,
    "seeds": {"first": 33001, "last": 33200}, "smoke_seeds": {"first": 33201, "last": 33206},
    "synthetic_seeds": {"first": 33301, "last": 33399},
    "formal_plan": {"first": 41, "spacing": 41, "count": 50, "offset": 2, "length": 19, "delay": 2, "e_windows": 25},
}
W_MAX, W0 = PREREGISTERED["w_max"], PREREGISTERED["w0"]
HI, LO = W_MAX * 3 / 4, W_MAX / 4
# README §2.3 の表：系 → (C→源1, 源1→C, C→源2, 源2→C)。源どうしは w0。X0 は移植しない（w0）
TABLE = {"X1": (W_MAX, 0.0, 0.0, W_MAX), "X2": (0.0, W_MAX, W_MAX, 0.0), "M1": (HI, LO, LO, HI), "M2": (LO, HI, HI, LO),
         "X0": (W0, W0, W0, W0), "X0_tr": (W0, W0, W0, W0), "X1_rerun": (W_MAX, 0.0, 0.0, W_MAX)}
# 出力先のファイル（README §9.4。guard.py・analyze.py と同じ名前を、ここに書き起こす）
START, FINISH, RAW, SEEDS_DIR = "run_started.json", "run_finished.json", "raw.json.gz", "seeds"
REPORT, O1_FILE = "report.json", "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py")
RECHECKED_MODES = {"formal": "seeds", "synthetic": "synthetic_seeds"}          # smoke（盲検の記録）は対象ではない
LOOSE = 1e-9                                                                   # 計算の書き方が違う欄だけに許す違い


def geometry(plan: dict) -> dict:
    cues = [plan["first"] + plan["spacing"] * k for k in range(plan["count"])]
    windows = [(k + 1, c + plan["offset"], c + plan["offset"] + plan["length"] - 1) for k, c in enumerate(cues)]
    return {"cues": cues, "windows": windows, "last_e": cues[plan["e_windows"]] - 1, "end": windows[-1][2] + plan["delay"]}


def sign_of(x: Fraction) -> str:
    return "+" if x > 0 else "-" if x < 0 else "0"


def bound_e_s(manifest: dict, plan: dict) -> float:
    """命題 S-1 の E_S ＝ w_max [(1 ＋ λ^g1)／(1 − λ^(g1 ＋ g2)) ＋ 2／(1 − λ^d)]（系 S-1′ も同じ値。README §7.2 を書き起こしたもの）。"""
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


# ---- 個体ごとの量（README §3・§4.1・§4.2・§6） ---------------------------------------------------------------

def role_cids(roles: dict) -> dict:
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


def sums_by_pair(weights: dict) -> dict:
    """組の和（鍵は二つの Unit の名前を名前の順に並べて | でつないだもの。和は接続の識別子の順に足す）。"""
    out: dict[str, float] = {}
    for cid, w in sorted(weights.items()):
        key = "|".join(sorted(cid.split(".main->")))
        out[key] = out.get(key, 0.0) + w
    return out


def firing_at(activity: list, end: int) -> dict:
    """Pulse 1〜end の、Pulse ごとの発火した Unit の数え上げ（同じ Unit の重なりも数える）。"""
    out: dict[int, Counter] = {}
    for p, u in activity:
        if 1 <= p <= end:
            out.setdefault(p, Counter())[u] += 1
    return out


def first_split(act_a: list, act_b: list, end: int) -> int | None:
    a, b = firing_at(act_a, end), firing_at(act_b, end)
    return min((p for p in set(a) | set(b) if a.get(p, Counter()) != b.get(p, Counter())), default=None)


def first_window_split(la: list, lb: list) -> int | None:
    for x, y in zip(la, lb):
        if x != y:
            return x["window"]
    return None


def window_count(layer_a: list, lo: int, hi: int) -> dict:
    outs = Counter(r["outcome"] for r in layer_a if lo <= r["window"] <= hi)
    return {"windows": sum(outs.values()), "decided": outs["A1"] + outs["A2"], "A1": outs["A1"], "A2": outs["A2"],
            "tie": outs["tie"], "none": outs["none"]}


def individual(data: dict) -> dict:
    """1 個体の量を、report の individuals の欄と同じ形で書き起こす。"""
    run, plan = data["run"], data["run"]["plan"]
    geo = geometry(plan)
    e, k_all, end, last_e = plan["e_windows"], plan["count"], geo["end"], geo["last_e"]
    roles, sysrec = run["roles"], run["systems"]
    name_of = {roles[r]: r for r in ROLES3}
    counts = {"E": {n: window_count(sysrec[n]["layer_a"], 1, e) for n in SYSTEMS},
              "U": {n: window_count(sysrec[n]["layer_a"], e + 1, k_all) for n in SYSTEMS}}
    shares = {part: {n: (Fraction(c["A1"], c["decided"]) if c["decided"] else None) for n, c in counts[part].items()}
              for part in ("E", "U")}
    contrasts = {}
    for name, (a, b, part) in CONTRASTS.items():
        sa, sb = shares[part][a], shares[part][b]
        defined = sa is not None and sb is not None
        diff = sa - sb if defined else None
        contrasts[name] = {"interval": part, "a": frac(sa), "b": frac(sb), "defined": defined,
                           "undefined_kind": None if defined else KINDS[(sa is None) + (sb is None) - 1],
                           "in_population": defined, "difference": frac(diff),
                           "sign": None if diff is None else sign_of(diff),
                           "decided_diff": counts[part][a]["decided"] - counts[part][b]["decided"],
                           "A1_diff": counts[part][a]["A1"] - counts[part][b]["A1"]}
    s1, s2 = shares["U"]["X1"], shares["U"]["X2"]
    flip = None if s1 is None or s2 is None else (2 * s1 - 1) * (2 * s2 - 1) < 0
    e_s = bound_e_s(data["meta"]["manifest"], plan)
    units = run["birth_units"]
    margin = {}
    for u, role in name_of.items():
        d = units[u]["dynamics"]
        margin[role] = d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]
    silent = {role: margin[role] < -e_s for role in SOURCES}
    fired = {u for n in SYSTEMS for _p, u in sysrec[n]["activity"]}
    split = {f"{a}|{b}": {"firing": first_split(sysrec[a]["activity"], sysrec[b]["activity"], end),
                          "window": first_window_split(sysrec[a]["layer_a"], sysrec[b]["layer_a"])} for a, b in PAIRS}
    before = {p for c in geo["cues"][e:] for p in (c, c + 1)}
    firing, pre = {}, {}
    for n in SYSTEMS:
        act = sysrec[n]["activity"]
        firing[n] = {"E": dict.fromkeys(ROLES3, 0), "U": dict.fromkeys(ROLES3, 0)}
        pre[n] = dict.fromkeys(SOURCES, 0)
        for p, u in act:
            if u in name_of:
                firing[n]["E" if p <= last_e else "U"][name_of[u]] += 1
                if p in before and name_of[u] in SOURCES:
                    pre[n][name_of[u]] += 1
    world = {n: {"intents": len(sysrec[n]["layer_b"]),
                 "consequence_reservations": sum(1 for r in sysrec[n]["world_end"]["reserved"] if r[1] == "consequence")}
             for n in SYSTEMS}
    role_of = {cid: role for role, cid in role_cids(roles).items()}

    def by_role(sigma: dict) -> dict:
        return {role_of[cid]: v["weight"] for cid, v in sorted(sigma["connections"].items())}

    def plain(sigma: dict) -> dict:
        return {cid: v["weight"] for cid, v in sigma["connections"].items()}
    weights = {t: {n: by_role(run["pulse_0"][f"sigma_{t}"][n]) for n in RECORDED} for t in ("T0", "T1", "T2")}
    weights["end_X1_rerun"] = by_role(sysrec[RERUN]["sigma_end"])
    sums = {n: sums_by_pair(plain(run["pulse_0"]["sigma_T2"][n])) for n in RECORDED}
    sums[RERUN] = sums_by_pair(plain(sysrec[RERUN]["sigma_end"]))
    return {
        "roles": {k: roles[k] for k in ROLES3},
        "birth": {role: {"threshold": units[roles[role]]["dynamics"]["threshold"],
                         "intrinsic_drive": units[roles[role]]["dynamics"]["intrinsic_drive_per_second"],
                         "margin_g": margin[role]} for role in ROLES3},
        "S1_prime": {"silent_source": silent,
                     "violations": sorted(r for r in SOURCES if silent[r] and roles[r] in fired)},
        "never_diverged_X1_X2": split["X1|X2"]["firing"] is None,
        "counts_E": counts["E"], "counts_U": counts["U"],
        "s_U": {n: frac(shares["U"][n]) for n in SYSTEMS},
        "s_E": {n: frac(shares["E"][n]) for n in SYSTEMS},
        "contrasts": contrasts,
        "flip": flip,
        "weights": weights, "pair_sums": sums,
        "first_divergence": split,
        "firing": firing, "pre_window_firing_U": pre,
        "world": world,
    }


# ---- 判定・推定・記述の対照・補助の記録（README §4〜§6） ------------------------------------------------------

def upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(math.comb(m, i) for i in range(k, m + 1)), 2 ** m)


def k2(m: int, alpha: Fraction) -> int:
    k = 0
    while upper_tail(m, k) > alpha:
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
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "m = 0"}
    return {"computed": True, "interval": list(exact_interval(x, n)), "numerator": x, "denominator": n}


def table_of(people: list[dict], name: str) -> dict:
    pop = [p["contrasts"][name] for p in people if p["contrasts"][name]["in_population"]]
    m = len(pop)
    signs = Counter(c["sign"] for c in pop)
    counts = {s: signs[s] for s in SIGNS}
    return {"m": m, "counts": counts, "proportion": {s: (counts[s] / m if m else None) for s in ("+", "-")},
            "interval": {s: interval_of(counts[s], m) for s in ("+", "-")}}


def judgment(people: list[dict]) -> dict:
    table = table_of(people, "D_X")
    m = table["m"]
    if m < PREREGISTERED["min_population"]:
        return {"J_A": table | {"status": "inconclusive", "direction": None, "k2": None, "tail_probability": None},
                "outcome": "inconclusive"}
    k = k2(m, PREREGISTERED["alpha_per_direction"])
    direction = "+" if table["counts"]["+"] >= k else "-" if table["counts"]["-"] >= k else None
    return {"J_A": table | {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
                            "tail_probability": float(upper_tail(m, k))},
            "outcome": {"+": "plus", "-": "minus", None: "not_established"}[direction]}


def estimate(people: list[dict]) -> dict:
    pop = [p for p in people if p["contrasts"]["D_X"]["in_population"]]
    m = len(pop)
    signs = Counter(p["contrasts"]["D_X"]["sign"] for p in pop)
    diffs = [abs(p["contrasts"]["D_X"]["difference"]["value"]) for p in pop]

    def part(x: int) -> dict:
        return {"count": x, "proportion": x / m if m else None, "interval": interval_of(x, m)}
    return {"m": m, "p_change": part(signs["+"] + signs["-"]), "p_plus": part(signs["+"]), "p_minus": part(signs["-"]),
            "p_flip": part(sum(1 for p in pop if p["flip"])),
            "abs_D_X": {"all": five(diffs), "changed": five([x for x in diffs if x != 0])}, "note": NOTES["estimate"]}


def controls(people: dict) -> dict:
    group = list(people.values())
    out: dict = {"contrasts": {}, "cross_tables": {}, "undefined": {}}
    for name in TABLES:
        diffs = [p["contrasts"][name]["difference"]["value"] for p in group if p["contrasts"][name]["in_population"]]
        out["contrasts"][name] = table_of(group, name) | {"difference": five(diffs)}
    for x, y in CROSS:
        cells = {a + b: 0 for a in SIGNS for b in SIGNS}
        both = only_x = only_y = 0
        for p in group:
            cx, cy = p["contrasts"][x], p["contrasts"][y]
            if cx["in_population"] and cy["in_population"]:
                both += 1
                cells[cx["sign"] + cy["sign"]] += 1
            elif cx["in_population"]:
                only_x += 1
            elif cy["in_population"]:
                only_y += 1
        out["cross_tables"][f"{x}|{y}"] = {"order": [x, y], "in_both": both, f"only_{x}": only_x, f"only_{y}": only_y,
                                           "cells": cells}
    for name in CONTRASTS:
        out["undefined"][name] = {kind: sorted(k for k, p in people.items() if p["contrasts"][name]["undefined_kind"] == kind)
                                  for kind in KINDS}
    return out


def auxiliary(people: dict, e_s: float | None) -> dict:
    vals = list(people.values())
    violations = sum(len(p["S1_prime"]["violations"]) for p in vals)
    silent = [p for p in vals if any(p["S1_prime"]["silent_source"].values())]
    in_ja = [p["contrasts"]["D_X"]["in_population"] for p in vals]
    out: dict = {"R1": {
        "individuals": len(vals),
        "undefined_D_X": {kind: sum(1 for p in vals if p["contrasts"]["D_X"]["undefined_kind"] == kind) for kind in KINDS},
        "never_diverged_X1_X2": sum(1 for p in vals if p["never_diverged_X1_X2"]),
        "never_diverged_X1_X2_in_J_A_population": sum(1 for p, ok in zip(vals, in_ja) if ok and p["never_diverged_X1_X2"]),
        "S1_prime": {"E_S": e_s, "violations": violations, "labels_withdrawn": violations > 0,
                     "individuals_with_silent_source": None if violations else len(silent),
                     "of_which_in_J_A_population": None if violations else sum(1 for p in silent
                                                                                if p["contrasts"]["D_X"]["in_population"])}}}
    out["R2"] = {n: {part: {"decided": five([p[f"counts_{part}"][n]["decided"] for p in vals]),
                            "tie": five([p[f"counts_{part}"][n]["tie"] for p in vals]),
                            "none": five([p[f"counts_{part}"][n]["none"] for p in vals]),
                            "s": five([p[f"s_{part}"][n]["value"] for p in vals if p[f"s_{part}"][n] is not None])}
                     for part in ("E", "U")} for n in SYSTEMS}
    out["R3"] = {}
    for name in CONTRASTS:
        pop = [p["contrasts"][name] for p in vals if p["contrasts"][name]["in_population"]]
        diffs = [c["difference"]["value"] for c in pop]
        out["R3"][name] = {"difference": five(diffs), "abs_difference": five([abs(x) for x in diffs]),
                           "decided_diff": five([c["decided_diff"] for c in pop]), "A1_diff": five([c["A1_diff"] for c in pop])}
    out["R4"] = {"pair_sum_equals_w_max_exactly": all(s == W_MAX for p in vals for n in SYSTEMS
                                                      for s in p["pair_sums"][n].values()),
                 "T2_values_by_system": {n: vals[0]["weights"]["T2"][n] for n in RECORDED} if vals else None,
                 "end_values_X1_rerun": vals[0]["weights"]["end_X1_rerun"] if vals else None,
                 "pulse_weights": NOTES["R4"]}
    out["R5"] = {}
    for a, b in (PAIRS if vals else []):
        rows = [p["first_divergence"][f"{a}|{b}"] for p in vals]
        out["R5"][f"{a}|{b}"] = {"firing": {"none": sum(1 for r in rows if r["firing"] is None),
                                            "pulses": five([r["firing"] for r in rows if r["firing"] is not None])},
                                 "window": {"none": sum(1 for r in rows if r["window"] is None),
                                            "windows": five([r["window"] for r in rows if r["window"] is not None])}}
    out["R6"] = {n: {part: {role: five([p["firing"][n][part][role] for p in vals]) for role in ROLES3}
                     for part in ("E", "U")} for n in SYSTEMS}
    out["R7"] = {n: {"intents": five([p["world"][n]["intents"] for p in vals]),
                     "consequence_reservations_total": sum(p["world"][n]["consequence_reservations"] for p in vals)}
                 for n in SYSTEMS}
    out["R9"] = {n: {role: five([p["pre_window_firing_U"][n][role] for p in vals]) for role in SOURCES} | {"note": NOTES["R9"]}
                 for n in SYSTEMS}
    return out


def expected_report(runs: dict, measurement_commit: str | None = None) -> dict:
    """保存した生の記録だけから、有効な report の全体（mode・valid・O1・関門の SHA-256・判定・推定・記述の対照・個体・補助の記録）を
    組み立て直す。measurement_commit を渡したときは、その欄も期待値に入れる（解析の main が書き足す欄）。"""
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
    return where.endswith((".interval[0]", ".interval[1]")) or where == "report.auxiliary.R1.S1_prime.E_S"


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


# ---- 操作の確認の主なもの（別の書き方で） -----------------------------------------------------------------

def _pair_sums(weights: dict) -> dict:
    sums: dict[frozenset, float] = {}
    for cid, value in sorted(weights.items()):
        src, tgt = cid.split(".main->")
        sums[frozenset((src, tgt))] = sums.get(frozenset((src, tgt)), 0.0) + value
    return sums


def operation_problems(data: dict) -> list[str]:
    run = data["run"]
    plan, roles = run["plan"], run["roles"]
    geo = geometry(plan)
    end, windows = geo["end"], geo["windows"]
    order, cue_r = run["connection_order"], roles["cue_receptor"]
    action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    four = [f"{c}.main->{s1}", f"{s1}.main->{c}", f"{c}.main->{s2}", f"{s2}.main->{c}"]
    sysrec = run["systems"]
    problems = []
    for n in SYSTEMS:
        r = sysrec[n]
        la, lb = r["layer_a"], r["layer_b"]
        # O11：層 A の欄の整合
        if [x["window"] for x in la] != [k for k, _a, _b in windows]:
            problems.append(f"O11 {n}: 窓の番号")
        for x, (k, a, b) in zip(la, windows):
            d = x["decision_pulse"]
            if x["outcome"] in ACTIONS:
                ok = (a <= d <= b and x["action"] == x["outcome"] == action_of.get(x["winner_unit"])
                      and x["emit_pulse"] == d + 1 and x["emitted"] is True)
            elif x["outcome"] == "tie":
                ok = a <= d <= b and x["winner_unit"] is None and x["action"] is None and not x["emitted"]
            else:
                ok = x["outcome"] == "none" and d is None and x["winner_unit"] is None and not x["emitted"]
            if not ok or (x["open"], x["close"]) != (a, b):
                problems.append(f"O11 {n}: 窓 {k}")
        # O3：層 A と層 B の一対一、識別子の重複、未発行の予定
        if Counter((x["emit_pulse"], x["winner_unit"], x["action"]) for x in la if x["emitted"]) \
                != Counter((p, src, act) for p, _did, src, act in lb):
            problems.append(f"O3 {n}: 層 A と層 B")
        if len({did for _p, did, _s, _a in lb}) != len(lb):
            problems.append(f"O3 {n}: 識別子の重複")
        if any(x["winner_unit"] is not None and not x["emitted"] for x in la):
            problems.append(f"O3 {n}: 未発行の予定")
        # O5：結果の予約・刺激がない。感覚の出来事は手がかりの Receptor の手がかりだけ
        if any(row[1] != "cue" for row in r["world_end"]["reserved"]):
            problems.append(f"O5 {n}: 手がかりのほかの予約")
        if sorted(tuple(x) for x in r["sensory"]) != sorted((cue, cue_r) for cue in geo["cues"]):
            problems.append(f"O5 {n}: 感覚の出来事")
        # O4：介入の履歴は境界 0 での 6 本の FREEZE だけ
        if r["history"] != [[0, "T2", [["FREEZE", sorted(order), "advance"]]]]:
            problems.append(f"O4 {n}: 介入の履歴")
    # O4・O7：T1・T2 の重みが README §2.3 の表、組の和がちょうど w_max、範囲の中
    for n in RECORDED:
        for t in ("T1", "T2"):
            w = {cid: v["weight"] for cid, v in run["pulse_0"][f"sigma_{t}"][n]["connections"].items()}
            want = dict.fromkeys(order, W0) | dict(zip(four, TABLE[n], strict=True))
            if w != want:
                problems.append(f"O4 {n} {t}: 重み")
            if any(s != W_MAX for s in _pair_sums(w).values()) or any(not 0.0 <= v <= W_MAX for v in w.values()):
                problems.append(f"O7 {n} {t}: 組の和・範囲")
        # O6：Pulse ごとの重みが T2 の値
        t2 = {cid: v["weight"] for cid, v in run["pulse_0"]["sigma_T2"][n]["connections"].items()}
        rows = sysrec[n]["pulse_weights"]
        if [p for p, _w in rows] != list(range(1, end + 1)) or any(w != [t2[cid] for cid in order] for _p, w in rows):
            problems.append(f"O6 {n}")
    rerun_w = {cid: v["weight"] for cid, v in sysrec[RERUN]["sigma_end"]["connections"].items()}
    if rerun_w != dict.fromkeys(order, W0) | dict(zip(four, TABLE[RERUN], strict=True)):
        problems.append("O6 X1_rerun: 終わりの重み")
    # O8・O9：終わりの記録の完全な一致。終わりの Σ は値の全体で比べ（主）、SHA-256 は保存した Σ から求め直して照らす（補助）
    for check, a, b in (("O8", "X0", "X0_tr"), ("O9", "X1", RERUN)):
        ra, rb = sysrec[a], sysrec[b]
        if any(ra[k] != rb[k] for k in ("activity", "sensory", "layer_a", "layer_b", "history")) or ra["sigma_end"] != rb["sigma_end"]:
            problems.append(f"{check} {b}")
        for r in (ra, rb):
            text = json.dumps(r["sigma_end"], separators=(",", ":"), sort_keys=True)
            if hashlib.sha256(text.encode("utf-8")).hexdigest() != r["sigma_end_sha256"] or r["sigma_end_sha256"] != rb["sigma_end_sha256"]:
                problems.append(f"{check} {b}: SHA-256")
                break
    # O10 の一部：最初の発火の Pulse t₁ が値の系で同じで、そこまでの発火が同じ
    firsts = {n: min((p for p, _u in sysrec[n]["activity"]), default=None) for n in ("X1", "X2", "M1", "M2", "X0")}
    if len(set(firsts.values())) != 1:
        problems.append("O10 t1")
    else:
        t1 = firsts["X0"]
        if t1 is not None and any([x for x in sysrec[n]["activity"] if x[0] <= t1] != [x for x in sysrec["X0"]["activity"] if x[0] <= t1]
                                  for n in firsts):
            problems.append("O10 t1 までの発火")
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
        problems.append("照らす protocol.yaml が、事前登録 v0.3 の protocol.yaml と違う")
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
            problems.append(f"seed {s}: meta の protocol の写しの中身が、事前登録 v0.3 の protocol と違う")
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
    """写しの中の、判定に関わる値と PREREGISTERED の照合。k₂(m) の表は、二項から求め直した値と照らす。"""
    out = []
    try:
        j, tl, pr, br = proto["judgment"], proto["timeline"], PREREGISTERED, proto["brain"]
        if (proto["experiment"], proto["kind"]) != (pr["experiment"], pr["kind"]):
            out.append("experiment・kind")
        if j["J_A"]["min_population"] != pr["min_population"]:
            out.append("J_A.min_population")
        if _number(j["J_A"]["alpha"]["per_direction"]) != pr["alpha_per_direction"] \
                or _number(j["J_A"]["alpha"]["two_sided"]) != pr["alpha_two_sided"]:
            out.append("J_A.alpha")
        lo, hi = pr["k2_range"]
        table = {int(m): k for m, k in j["k2_of_m"].items()}
        if table != {m: k2(m, pr["alpha_per_direction"]) for m in range(lo, hi + 1)}:
            out.append("k2_of_m")
        if (tl["lead_in_E"]["windows"], tl["trial_U"]["windows"], tl["lead_in_E"]["pulses"], tl["runs_to"]) != \
                (pr["lead_in_windows"], pr["trial_windows"], pr["lead_in_pulses"], pr["runs_to"]):
            out.append("timeline")
        if (_number(br["w_min"]), _number(br["w_max"]), _number(br["initial_weight_w0"])) != \
                (_number(pr["w_min"]), _number(pr["w_max"]), _number(pr["w0"])):
            out.append("brain.weights")
        if proto["world"]["respond"] is not pr["respond"]:
            out.append("world.respond")
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
        except (KeyError, TypeError, ValueError, IndexError) as e:
            mismatches.append(f"seed {s}: 操作の確認の記録を読めない（{type(e).__name__}）")
    checks += 1
    if not isinstance(report, dict) or report.get("valid") is not True:
        return {"checks": checks, "mismatches": mismatches + ["report.valid"], "recomputed": None}
    try:
        mine = expected_report(runs, measurement_commit)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError) as e:
        return {"checks": checks, "mismatches": mismatches + [f"生の記録から report を組み立て直せない（{type(e).__name__}）"],
                "recomputed": None}
    if mine["mode"] is None:
        mismatches.append("個体によって meta の mode が違う")
    n, found = compare(mine, report)
    j, est = mine["judgment"], mine["estimate"]
    return {"checks": checks + n, "mismatches": mismatches + found,
            "recomputed": {"outcome": j["outcome"],
                           "J_A": {k: j["J_A"][k] for k in ("m", "counts", "status", "direction", "k2")},
                           "E_A": {"m": est["m"], "p_change_count": est["p_change"]["count"],
                                   "p_flip_count": est["p_flip"]["count"]}}}


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
    elif not seeds:
        problems.append("seed がない")
    return problems


def read_directory(out: Path) -> tuple[dict, dict, list[str]]:
    """出力先の seeds/ を、guard・解析の道具に頼らずに読む。(runs, 記録, 食い違い) を返す。
    seed ごとに：フォルダの名前と中身、終了の記録の status と raw の SHA-256・バイト数、四つの seed の一致、
    experiment・kind・mode と測定の commit・protocol の SHA-256 の、開始・終了の記録と raw の meta の結び付き。"""
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
