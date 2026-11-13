"""実験 0039 の独立の検算（README §9.1。標準のライブラリだけ）。

この実験の解析・測定の道具も、anima_ll も、AS2b の道具も、protocol.yaml を読む道具も読み込まない。保存した生の記録
（seeds/<seed>/raw.json.gz）だけから、定義（README §3〜§6）を書き起こし直して計算し、report.json と一つずつ照合する。
判定の閾値などの事前登録の値は、README・protocol.yaml（v0.2）から書き起こした PREREGISTERED から取る。生の記録の meta に保存された
protocol の写し（meta.protocol・meta.protocol_sha256）は、次のことを確かめるだけに使う（v0.2 の修正。レビュー 5877646345）
- 全個体にあり、全個体で同じであること
- 写しの中身全体を JSON に正規化したもののハッシュが、確定済み v0.2 の protocol の固定のハッシュ（PROTOCOL_JSON_SHA256）と
  同じであること（v0.3。判定の順序の記述など、PREREGISTERED で個別に照らさない欄の改変も見つける。レビュー 5883922143）
- SHA-256 が、リポジトリの確定済みの protocol.yaml のバイト列の SHA-256 と同じであること
- 写しの中の判定に関わる値が、PREREGISTERED と同じであること。k₂(m) の表は、二項から求め直した値と同じであること
どれかが欠けたり違ったりすれば、食い違いとして数える。

計算し直すもの
- 個体ごと：共通の部分の k*、適格外 (a)・定まらない (b)・構造上の恒等（W^{A1} と W^{A2} の比べ）・命題 S-1 の札（θ・c から）、
  11 系の U の窓の数と A1 の割合、§3.2 のすべての対比の差と符号
- 判定：m・向きごとの数・k₂(m)（分数の二項から求め直す）・上側の確率・status・固定の順序の扱い・二つを合わせた結果、
  Clopper–Pearson の端点
- §6.1 の記述の対照（数・区間、二つの 9 つの組の表、適格外・定まらない個体の表）と、R1 の数
- 操作の確認の主なもの（O3〜O6・O8〜O11・O13・O14）を、別の書き方で

使い方（結果を保存したフォルダを渡す。計算の後で一度だけ）:
  python experiments/0039_as2b_rule_dependence/recheck.py <フォルダ> [--write <結果の JSON>]
"""

import argparse
import gzip
import hashlib
import json
import math
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

SYSTEMS = ["B_A1", "B_A2", "B_A1_rerun", "F_A1", "F_A2", "G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr",
           "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr"]
CLONES = SYSTEMS[5:]
RULE = {name: name.split("_")[1] for name in SYSTEMS}
WEIGHTS_OF = {"G_A1_WA1": "A1", "G_A1_WA2": "A2", "G_A1_WA1_tr": "A1", "G_A2_WA2": "A2", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2"}
SAME_WEIGHTS = [("G_A1_WA1", "G_A1_WA1_tr"), ("G_A2_WA2", "G_A2_WA2_tr")]
OTHER_WEIGHTS = [("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1")]
RULE_PAIRS = [("B_A1", "B_A2"), ("F_A1", "F_A2")]
# 対比：名前 → (a, b, 割合を取る行動, 適格外 (a) を決める系)
CONTRASTS = {"D": ("B_A1", "B_A2", "A1", "B_A1"), "D_W": ("G_A1_WA1", "G_A1_WA2", "A1", "B_A1"),
             "D_W_rev": ("G_A2_WA1", "G_A2_WA2", "A1", "B_A1"), "D_F": ("F_A1", "F_A2", "A1", "F_A1"),
             "Z_A1": ("B_A1", "G_A1_WA1", "A1", "B_A1"), "Z_A2": ("B_A2", "G_A2_WA2", "A2", "B_A1"),
             "P_A1": ("B_A1", "F_A1", "A1", "B_A1"), "P_A2": ("B_A2", "F_A2", "A2", "B_A1")}
TABLES = ["D_W_rev", "D_F", "Z_A1", "Z_A2", "P_A1", "P_A2"]
ACTIONS = ("A1", "A2")
SHA256_HEX = set("0123456789abcdef")
PROTOCOL_FILE = Path(__file__).resolve().parent / "protocol.yaml"
# 確定済み v0.2 の protocol.yaml（#179 merge `ba7ffba`、ファイルの SHA-256 c5f491a5…ea06）を、raw の meta と同じ形
# （YAML を読み、JSON を通した形）にして正規化した JSON の SHA-256。正規化：json.dumps(写し, sort_keys=True,
# ensure_ascii=False, separators=(",", ":")) の UTF-8。値は契約テストで、正本から計算し直して照らす
PROTOCOL_JSON_SHA256 = "da03701edada2a902c576052c34b55b8ce0ff07afe2d1291b5a8ddb538ae2d40"
PROTOCOL_FILE_SHA256 = "c5f491a5256a475727016ce086e29db01a22a77f8d991f2ea6a98c3135b8ea06"   # 同じ正本のファイルのバイト列
# 事前登録 v0.2（#179 merge `ba7ffba`）から書き起こした値：README §1.1・§1.2・§4.3・§5.1・§9.2、protocol.yaml の
# judgment・timeline・brain・seeds。判定はこの値で計算し、meta の protocol の写しは、これと照らすだけに使う
PREREGISTERED = {
    "experiment": "0039",
    "alpha_per_direction": Fraction(1, 40), "alpha_two_sided": Fraction(1, 20),
    "min_population": {"J_7": 10, "J_W": 10},
    "k2_range": (10, 200),
    "experience_windows": [1, 25], "trial_windows": [26, 50], "P_E": 1065, "runs_to": 2072,
    "w_max": 0.01,
    "seeds": {"first": 32001, "last": 32200}, "smoke_seeds": {"first": 32201, "last": 32206},
    "synthetic_seeds": {"first": 32301, "last": 32399},
    "formal_plan": {"first": 41, "spacing": 41, "count": 50, "offset": 2, "length": 19, "delay": 2, "e_windows": 25},
}


def rec(run: dict, name: str) -> dict:
    return run["G"][name] if name in CLONES else run["bodies"][name]


def geometry(plan: dict) -> dict:
    cues = [plan["first"] + plan["spacing"] * k for k in range(plan["count"])]
    windows = [(k + 1, c + plan["offset"], c + plan["offset"] + plan["length"] - 1) for k, c in enumerate(cues)]
    return {"cues": cues, "windows": windows, "p_e": cues[plan["e_windows"]] - 1, "end": windows[-1][2] + plan["delay"]}


def u_counts(layer_a: list, e_windows: int) -> Counter:
    return Counter(r["outcome"] for r in layer_a if r["window"] > e_windows)


def a_share(counts: Counter, action: str) -> Fraction | None:
    decided = counts["A1"] + counts["A2"]
    return Fraction(counts[action], decided) if decided else None


def sign_of(x: Fraction) -> str:
    return "+" if x > 0 else "-" if x < 0 else "0"


def first_decided_window(layer_a: list) -> dict | None:
    for r in layer_a:
        if r["outcome"] in ACTIONS:
            return r
    return None


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


def individual(data: dict) -> dict:
    run, plan = data["run"], data["run"]["plan"]
    e = plan["e_windows"]
    counts = {n: u_counts(rec(run, n)["layer_a"], e) for n in SYSTEMS}
    prefix = {}
    for key, name in (("B", "B_A1"), ("F", "F_A1")):
        la = rec(run, name)["layer_a"]
        first = first_decided_window(la)
        k = None if first is None else first["window"]
        out = k is None or k > e
        kind = None
        if out:
            kind = "a1_all_none" if all(r["outcome"] == "none" for r in la if r["window"] <= e) else "a2_ties_only"
        prefix[key] = {"k_star": k, "ineligible_a": out, "ineligible_kind": kind}
    contrasts = {}
    for name, (a, b, action, pre) in CONTRASTS.items():
        sa, sb = a_share(counts[a], action), a_share(counts[b], action)
        defined = sa is not None and sb is not None
        ineligible = prefix["F" if pre == "F_A1" else "B"]["ineligible_a"]
        missing = (sa is None) + (sb is None)
        contrasts[name] = {
            "defined": defined, "ineligible_a": ineligible, "in_population": defined and not ineligible,
            "undefined_kind": None if defined else ("both_systems" if missing == 2 else "one_system"),
            "difference": (sa - sb) if defined else None, "sign": sign_of(sa - sb) if defined else None,
            "n_U_diff": (counts[a]["A1"] + counts[a]["A2"]) - (counts[b]["A1"] + counts[b]["A2"]),
            "A1_U_diff": counts[a]["A1"] - counts[b]["A1"]}
    e_s = bound_e_s(data["meta"]["manifest"], plan)
    roles = run["roles"]
    fired = {u for n in SYSTEMS for _p, u in rec(run, n)["activity"]}
    silent, violations = {}, []
    for role in ("source1", "source2"):
        d = run["birth_units"][roles[role]]["dynamics"]
        g = d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]
        silent[role] = g < -e_s
        if silent[role] and roles[role] in fired:
            violations.append(role)
    return {"prefix": prefix, "contrasts": contrasts, "counts": counts,
            "structural_identity": run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"],
            "silent": silent, "violations": violations}


# ---- 判定（README §4・§5） -----------------------------------------------------------------------------

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


def table_of(people: list[dict], name: str) -> dict:
    pop = [p["contrasts"][name] for p in people if p["contrasts"][name]["in_population"]]
    signs = Counter(c["sign"] for c in pop)
    return {"m": len(pop), "counts": {s: signs[s] for s in ("+", "-", "0")}}


def decision(table: dict, alpha: Fraction, min_population: int) -> dict:
    m = table["m"]
    if m < min_population:
        return {"status": "inconclusive", "direction": None, "k2": None}
    k = k2(m, alpha)
    direction = "+" if table["counts"]["+"] >= k else "-" if table["counts"]["-"] >= k else None
    return {"status": "established" if direction else "not_established", "direction": direction, "k2": k}


def judgment(people: list[dict]) -> dict:
    alpha, least = PREREGISTERED["alpha_per_direction"], PREREGISTERED["min_population"]
    t7, tw = table_of(people, "D"), table_of(people, "D_W")
    d7 = decision(t7, alpha, least["J_7"])
    dw = decision(tw, alpha, least["J_W"]) if d7["status"] == "established" \
        else {"status": "not_tested", "direction": None, "k2": None}
    if d7["status"] == "inconclusive":
        outcome = "inconclusive"
    elif d7["status"] == "not_established":
        outcome = "J_7_not_established"
    elif dw["status"] != "established":
        outcome = "J_7_only"
    else:
        outcome = "both_same_direction" if dw["direction"] == d7["direction"] else "both_opposite_direction"
    return {"J_7": t7 | d7, "J_W": tw | dw, "outcome": outcome}


# ---- 操作の確認の主なもの（別の書き方で） -----------------------------------------------------------------

def operation_problems(data: dict) -> list[str]:
    run = data["run"]
    plan, roles = run["plan"], run["roles"]
    geo = geometry(plan)
    p_e, end, windows = geo["p_e"], geo["end"], geo["windows"]
    order, cue_r = run["connection_order"], roles["cue_receptor"]
    action_of = {roles["source1"]: "A1", roles["source2"]: "A2"}
    problems = []
    for n in SYSTEMS:
        r = rec(run, n)
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
        # O5：結果は、行動 ID が規則 c の意図にだけ、意図の Pulse ＋ L − 1。源の Receptor の出来事はない
        got = sorted((row[3], row[4]) for row in r["world_end"]["reserved"] if row[1] == "consequence")
        want = sorted((p + plan["delay"] - 1, did) for p, did, _src, act in lb if act == RULE[n])
        if got != want:
            problems.append(f"O5 {n}: 結果の予約")
        if any(receptor != cue_r for _p, receptor in r["sensory"]):
            problems.append(f"O5 {n}: 手がかりの Receptor のほかの出来事")
    w0 = [run["W_0"][c] for c in order]
    for n in ("F_A1", "F_A2"):                                         # O6
        rows = run["bodies"][n]["pulse_weights"]
        if [p for p, _w in rows] != list(range(1, end + 1)) or any(w != w0 for _p, w in rows):
            problems.append(f"O6 {n}")
    for n in CLONES:                                                   # O8
        want = [run["boundary"]["W"][WEIGHTS_OF[n]][c] for c in order]
        rows = run["G"][n]["pulse_weights"]
        if [p for p, _w in rows] != list(range(p_e + 1, end + 1)) or any(w != want for _p, w in rows):
            problems.append(f"O8 {n}")
    same = list(SAME_WEIGHTS)
    if run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"]:
        same += OTHER_WEIGHTS
    for a, b in same:                                                  # O9
        if any(run["G"][a][k] != run["G"][b][k] for k in ("activity", "layer_a", "layer_b", "sigma_end_sha256")):
            problems.append(f"O9 {a} {b}")
    for a, b in OTHER_WEIGHTS:                                         # O10：最初に分かれる Pulse は P_E ＋ 2 以後
        fa, fb = Counter(map(tuple, run["G"][a]["activity"])), Counter(map(tuple, run["G"][b]["activity"]))
        differing = [p for (p, _u) in (fa - fb) + (fb - fa)]
        if differing and min(differing) < p_e + 2:
            problems.append(f"O10 {a} {b}")
    for a, b in RULE_PAIRS:                                            # O4：窓 1〜k* の記録が同じ
        la, lb = run["bodies"][a]["layer_a"], run["bodies"][b]["layer_a"]
        first = first_decided_window(la)
        upto = len(la) if first is None else first["window"]
        if la[:upto] != lb[:upto]:
            problems.append(f"O4 {a} {b}")
    for key in ("activity", "layer_a", "layer_b"):                     # O13
        if run["bodies"]["B_A1_rerun"][key] != run["bodies"]["B_A1"][key]:
            problems.append(f"O13 {key}")
    if run["bodies"]["B_A1_rerun"]["sigma_end_sha256"] != run["bodies"]["B_A1"]["sigma_end_sha256"]:
        problems.append("O13 sigma_end")
    w_max = PREREGISTERED["w_max"]
    for c in ACTIONS:                                                  # O14
        w = run["boundary"]["W"][c]
        sums: dict[frozenset, float] = {}
        for cid, value in sorted(w.items()):
            src, tgt = cid.split(".main->")
            sums[frozenset((src, tgt))] = sums.get(frozenset((src, tgt)), 0.0) + value
        if len(sums) != 3 or any(abs(s - w_max) > 1e-15 for s in sums.values()):
            problems.append(f"O14 W_{c}")
    return problems


# ---- protocol の写しと、確定済みの事前登録の結び付き（v0.2） ------------------------------------------------

def _number(x) -> Fraction | None:
    try:
        return Fraction(str(x))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def canonical_protocol_sha256(proto: dict) -> str:
    """写しの中身全体の、正規化した JSON の SHA-256（PROTOCOL_JSON_SHA256 と同じ正規化）。"""
    text = json.dumps(proto, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def protocol_problems(runs: dict, protocol_file: Path = PROTOCOL_FILE) -> list[str]:
    """全個体の meta の protocol の写しが、そろってあり、確定済みの protocol.yaml と PREREGISTERED に結び付くこと。"""
    problems = []
    file_sha = hashlib.sha256(protocol_file.read_bytes()).hexdigest()
    if file_sha != PROTOCOL_FILE_SHA256:
        problems.append("照らす protocol.yaml が、確定済み v0.2 の protocol.yaml と違う")
    copies, shas = set(), set()
    for s in sorted(runs):
        meta = runs[s].get("meta", {})
        proto, sha = meta.get("protocol"), meta.get("protocol_sha256")
        if not isinstance(proto, dict) or not isinstance(sha, str) or len(sha) != 64 or not set(sha) <= SHA256_HEX:
            problems.append(f"seed {s}: meta に protocol の写し・SHA-256 がない")
            continue
        copies.add(json.dumps(proto, sort_keys=True, ensure_ascii=False))
        shas.add(sha)
        if canonical_protocol_sha256(proto) != PROTOCOL_JSON_SHA256:
            problems.append(f"seed {s}: meta の protocol の写しの中身が、確定済み v0.2 の protocol と違う")
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
        j, tl, pr = proto["judgment"], proto["timeline"], PREREGISTERED
        if proto["experiment"] != pr["experiment"]:
            out.append("experiment")
        for name in ("J_7", "J_W"):
            if j[name]["min_population"] != pr["min_population"][name]:
                out.append(f"{name}.min_population")
        if _number(j["J_7"]["alpha"]["per_direction"]) != pr["alpha_per_direction"] \
                or _number(j["J_7"]["alpha"]["two_sided"]) != pr["alpha_two_sided"]:
            out.append("J_7.alpha")
        lo, hi = pr["k2_range"]
        table = {int(m): k for m, k in j["k2_of_m"].items()}
        if table != {m: k2(m, pr["alpha_per_direction"]) for m in range(lo, hi + 1)}:
            out.append("k2_of_m")
        if (tl["experience_E"]["windows"], tl["trial_U"]["windows"], tl["P_E"], tl["runs_to"]) != \
                (pr["experience_windows"], pr["trial_windows"], pr["P_E"], pr["runs_to"]):
            out.append("timeline")
        if _number(proto["brain"]["w_max"]) != _number(pr["w_max"]):
            out.append("brain.w_max")
        for key in ("seeds", "smoke_seeds", "synthetic_seeds"):
            if proto[key] != pr[key]:
                out.append(key)
    except (KeyError, TypeError, AttributeError, ValueError):
        out.append("判定に関わる欄が読めない")
    return out


# ---- report との照合 ------------------------------------------------------------------------------------

class Tally:
    def __init__(self) -> None:
        self.checks = 0
        self.mismatches: list[str] = []

    def same(self, mine, theirs, where: str) -> None:
        self.checks += 1
        if mine != theirs:
            self.mismatches.append(where)

    def close(self, mine: float, theirs: float, where: str, tol: float = 1e-9) -> None:
        self.checks += 1
        if theirs is None or abs(mine - theirs) > tol:
            self.mismatches.append(where)


def _fraction_of(x: dict | None) -> Fraction | None:
    return None if x is None else Fraction(x["num"], x["den"])


def _compare_table(t: Tally, mine: dict, theirs: dict, where: str) -> None:
    t.same(mine["m"], theirs["m"], f"{where}.m")
    t.same(mine["counts"], theirs["counts"], f"{where}.counts")
    for s in ("+", "-"):
        iv = theirs["interval"][s]
        t.same((mine["counts"][s], mine["m"]), (iv["numerator"], iv["denominator"]), f"{where}.interval[{s}].fraction")
        t.same(mine["m"] >= 1, iv["computed"], f"{where}.interval[{s}].computed")
        if mine["m"] >= 1 and iv["computed"]:
            lo, hi = exact_interval(mine["counts"][s], mine["m"])
            t.close(lo, iv["interval"][0], f"{where}.interval[{s}].lower")
            t.close(hi, iv["interval"][1], f"{where}.interval[{s}].upper")


def recheck(runs: dict, report: dict) -> dict:
    """runs：seed → 生の記録（meta に protocol の写しを含む）。report：解析の report。照合の数と、食い違いの一覧を返す。"""
    t = Tally()
    seeds = sorted(runs)
    binding = protocol_problems(runs)                                 # 写しが欠けても、違っても、食い違いとして数える
    t.checks += 1
    t.mismatches += binding
    for s in seeds:
        for p in operation_problems(runs[s]):
            t.mismatches.append(f"seed {s}: {p}")
        t.checks += 1
    t.same(bool(report.get("valid")), True, "report.valid")
    if not report.get("valid"):
        return {"checks": t.checks, "mismatches": t.mismatches, "recomputed": None}
    mine = {str(s): individual(runs[s]) for s in seeds}
    people = [mine[k] for k in sorted(mine)]
    theirs = report["individuals"]
    t.same(sorted(mine), sorted(theirs), "individuals: seed の組")
    for key in sorted(set(mine) & set(theirs)):
        a, b = mine[key], theirs[key]
        t.same(a["prefix"], b["prefix"], f"{key}.prefix")
        t.same(a["structural_identity"], b["structural_identity"], f"{key}.structural_identity")
        t.same(a["silent"], b["S1"]["silent_source"], f"{key}.S1.silent_source")
        t.same(a["violations"], b["S1"]["violations"], f"{key}.S1.violations")
        for n in SYSTEMS:
            c, d = a["counts"][n], b["counts_U"][n]
            t.same((c["A1"], c["A2"], c["tie"], c["none"]), (d["A1"], d["A2"], d["tie"], d["none"]), f"{key}.counts_U.{n}")
            t.same(a_share(c, "A1"), _fraction_of(b["s_U"][n]), f"{key}.s_U.{n}")
        for name in CONTRASTS:
            c, d = a["contrasts"][name], b["contrasts"][name]
            for field in ("defined", "ineligible_a", "in_population", "undefined_kind", "sign", "n_U_diff", "A1_U_diff"):
                t.same(c[field], d[field], f"{key}.contrasts.{name}.{field}")
            t.same(c["difference"], _fraction_of(d["difference"]), f"{key}.contrasts.{name}.difference")
    # 判定
    j_mine, j_theirs = judgment(people), report["judgment"]
    t.same(j_mine["outcome"], j_theirs["outcome"], "judgment.outcome")
    for name in ("J_7", "J_W"):
        a, b = j_mine[name], j_theirs[name]
        for field in ("status", "direction", "k2"):
            t.same(a[field], b[field], f"judgment.{name}.{field}")
        _compare_table(t, a, b, f"judgment.{name}")
        if a["k2"] is not None:
            t.close(float(upper_tail(a["m"], a["k2"])), b["tail_probability"], f"judgment.{name}.tail_probability", 1e-15)
    # 記述の対照
    dc = report["descriptive_controls"]
    for name in TABLES:
        _compare_table(t, table_of(people, name), dc["contrasts"][name], f"descriptive_controls.{name}")
    for x, y in (("D_W", "D_W_rev"), ("D", "D_W")):
        cells = Counter()
        both = only_x = only_y = 0
        for p in people:
            cx, cy = p["contrasts"][x], p["contrasts"][y]
            if cx["in_population"] and cy["in_population"]:
                both += 1
                cells[cx["sign"] + cy["sign"]] += 1
            elif cx["in_population"]:
                only_x += 1
            elif cy["in_population"]:
                only_y += 1
        table = dc["cross_tables"][f"{x}|{y}"]
        t.same((both, only_x, only_y), (table["in_both"], table[f"only_{x}"], table[f"only_{y}"]), f"cross_tables.{x}|{y}.sizes")
        t.same({k: cells[k] for k in table["cells"]}, table["cells"], f"cross_tables.{x}|{y}.cells")
    for name in CONTRASTS:
        out = [k for k in sorted(mine) if mine[k]["contrasts"][name]["ineligible_a"]]
        defined = [mine[k]["contrasts"][name] for k in out if mine[k]["contrasts"][name]["defined"]]
        signs = Counter(c["sign"] for c in defined)
        table = dc["ineligible_a"][name]
        t.same((out, len(defined), {s: signs[s] for s in ("+", "-", "0")}),
               (table["individuals"], table["defined"], table["counts"]), f"ineligible_a.{name}")
        for kind in ("one_system", "both_systems"):
            want = sorted(k for k in mine if not mine[k]["contrasts"][name]["ineligible_a"]
                          and mine[k]["contrasts"][name]["undefined_kind"] == kind)
            t.same(want, dc["undefined_b"][name][kind], f"undefined_b.{name}.{kind}")
    # R1
    r1 = report["auxiliary"]["R1"]
    t.same(len(people), r1["individuals"], "R1.individuals")
    for key, field in (("B", "ineligible_a"), ("F", "ineligible_a_F")):
        kinds = Counter(p["prefix"][key]["ineligible_kind"] for p in people)
        t.same({k: kinds[k] for k in ("a1_all_none", "a2_ties_only")}, r1[field], f"R1.{field}")
    t.same(sum(1 for p in people if p["structural_identity"] and p["contrasts"]["D_W"]["in_population"]),
           r1["structural_identity_in_J_W_population"], "R1.structural_identity_in_J_W_population")
    violations = sum(len(p["violations"]) for p in people)
    t.same(violations, r1["S1"]["violations"], "R1.S1.violations")
    t.same(None if violations else sum(1 for p in people if any(p["silent"].values())),
           r1["S1"]["individuals_with_silent_source"], "R1.S1.individuals_with_silent_source")
    return {"checks": t.checks, "mismatches": t.mismatches,
            "recomputed": {"outcome": j_mine["outcome"],
                           "J_7": {k: j_mine["J_7"][k] for k in ("m", "counts", "status", "direction", "k2")},
                           "J_W": {k: j_mine["J_W"][k] for k in ("m", "counts", "status", "direction", "k2")}}}


def recheck_directory(out: Path) -> dict:
    runs, files, starts = {}, {}, {}
    for path in sorted((out / "seeds").glob("*/raw.json.gz")):
        raw = path.read_bytes()
        files[str(path.relative_to(out))] = hashlib.sha256(raw).hexdigest()
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
        runs[data["meta"]["seed"]] = data
        start = path.parent / "run_started.json"                    # 開始の記録（guard）の protocol の SHA-256
        starts[data["meta"]["seed"]] = json.loads(start.read_text(encoding="utf-8")) if start.exists() else None
    report_path = out / "report.json"
    files[report_path.name] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    result = recheck(runs, json.loads(report_path.read_text(encoding="utf-8")))
    for s in sorted(starts):
        result["checks"] += 1
        st = starts[s]
        if not isinstance(st, dict) or st.get("protocol_sha256") != runs[s]["meta"].get("protocol_sha256"):
            result["mismatches"].append(f"seed {s}: 開始の記録の protocol の SHA-256 が、meta の写しと違うか、開始の記録がない")
    return result | {"individuals": len(runs), "sha256": files}


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
