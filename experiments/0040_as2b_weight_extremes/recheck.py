"""実験 0040 の独立の検算（README §9.1。標準のライブラリだけ）。

この実験の解析・測定の道具も、anima_ll も、AS2b の道具も、protocol.yaml を読む道具も読み込まない。保存した生の記録
（seeds/<seed>/raw.json.gz）だけから、定義（README §3〜§6）を書き起こし直して計算し、report.json と一つずつ照合する。
判定の閾値などの事前登録の値は、README・protocol.yaml（v0.2）から書き起こした PREREGISTERED から取る。生の記録の meta に保存された
protocol の写し（meta.protocol・meta.protocol_sha256）は、次のことを確かめるだけに使う（0039 の道具 v0.3 と同じ形）
- 全個体にあり、全個体で同じであること
- 写しの中身全体を JSON に正規化したもののハッシュが、確定済み v0.2 の protocol の固定のハッシュ（PROTOCOL_JSON_SHA256）と同じであること
  （PREREGISTERED で個別に照らさない欄の改変も見つける）
- SHA-256 が、リポジトリの確定済みの protocol.yaml のバイト列の SHA-256（PROTOCOL_FILE_SHA256）と同じであること
- 写しの中の判定に関わる値が、PREREGISTERED と同じであること。k₂(m) の表は、二項から求め直した値と同じであること
どれかが欠けたり違ったりすれば、食い違いとして数える。

計算し直すもの
- 個体ごと：定まらない札・系 S-1′ の札（θ・c から）・X1 と X2 の発火が最後まで分かれなかった札、7 系の E・U の窓の数と A1 の割合、
  §3.2 のすべての対比の差と符号、勝ちの多い行動の入れ替わり
- 判定：m・向きごとの数・k₂(m)（分数の二項から求め直す）・上側の確率・status・outcome、Clopper–Pearson の端点
- 推定 E_A：p_change・p_＋・p_−・p_flip の数と区間、|D^X| の分布
- §6.1 の記述の対照（数・区間、二つの 9 つの組の表、定まらない個体の表）と、R1 の数
- 操作の確認の主なもの（O3〜O9・O11）を、別の書き方で

使い方（結果を保存したフォルダを渡す。計算の後で一度だけ）:
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
# 対比：名前 → (a, b, 区間)
CONTRASTS = {"D_X": ("X1", "X2", "U"), "D_M": ("M1", "M2", "U"), "Delta_1": ("X1", "X0", "U"),
             "Delta_2": ("X0", "X2", "U"), "D_X_E": ("X1", "X2", "E")}
TABLES = ["D_M", "Delta_1", "Delta_2", "D_X_E"]
CROSS = [("D_X", "D_M"), ("Delta_1", "Delta_2")]
ACTIONS = ("A1", "A2")
SHA256_HEX = set("0123456789abcdef")
PROTOCOL_FILE = Path(__file__).resolve().parent / "protocol.yaml"
# 確定済み v0.2 の protocol.yaml（#184 merge `9a8651a`）を、raw の meta と同じ形（YAML を読み、JSON を通した形）にして正規化した
# JSON の SHA-256。正規化：json.dumps(写し, sort_keys=True, ensure_ascii=False, separators=(",", ":")) の UTF-8。
# 値は契約テストで、正本から計算し直して照らす
PROTOCOL_JSON_SHA256 = "d68f7a36b2761435601e4a0f9e1c6d41e4eebe4cf9953768fb9a899d0491826d"
PROTOCOL_FILE_SHA256 = "cfb7deae7764cc748ce9839671bf3ff6d0dd4f398cd942fa64eca93010c7120d"   # 同じ正本のファイルのバイト列
# 事前登録 v0.2（#184 merge `9a8651a`）から書き起こした値：README §1.2・§2.3・§4.3・§5.1・§9.2、protocol.yaml の
# judgment・timeline・brain・seeds。判定はこの値で計算し、meta の protocol の写しは、これと照らすだけに使う
PREREGISTERED = {
    "experiment": "0040",
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


def geometry(plan: dict) -> dict:
    cues = [plan["first"] + plan["spacing"] * k for k in range(plan["count"])]
    windows = [(k + 1, c + plan["offset"], c + plan["offset"] + plan["length"] - 1) for k, c in enumerate(cues)]
    return {"cues": cues, "windows": windows, "last_e": cues[plan["e_windows"]] - 1, "end": windows[-1][2] + plan["delay"]}


def part_counts(layer_a: list, e_windows: int, part: str) -> Counter:
    return Counter(r["outcome"] for r in layer_a if (r["window"] <= e_windows) == (part == "E"))


def a1_share(counts: Counter) -> Fraction | None:
    decided = counts["A1"] + counts["A2"]
    return Fraction(counts["A1"], decided) if decided else None


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


def individual(data: dict) -> dict:
    run, plan = data["run"], data["run"]["plan"]
    e = plan["e_windows"]
    sysrec = run["systems"]
    counts = {part: {n: part_counts(sysrec[n]["layer_a"], e, part) for n in SYSTEMS} for part in ("E", "U")}
    contrasts = {}
    for name, (a, b, part) in CONTRASTS.items():
        sa, sb = a1_share(counts[part][a]), a1_share(counts[part][b])
        defined = sa is not None and sb is not None
        missing = (sa is None) + (sb is None)
        ca, cb = counts[part][a], counts[part][b]
        contrasts[name] = {
            "defined": defined, "in_population": defined,
            "undefined_kind": None if defined else ("both_systems" if missing == 2 else "one_system"),
            "difference": (sa - sb) if defined else None, "sign": sign_of(sa - sb) if defined else None,
            "decided_diff": (ca["A1"] + ca["A2"]) - (cb["A1"] + cb["A2"]), "A1_diff": ca["A1"] - cb["A1"]}
    s1, s2 = a1_share(counts["U"]["X1"]), a1_share(counts["U"]["X2"])
    flip = None if s1 is None or s2 is None else (2 * s1 - 1) * (2 * s2 - 1) < 0
    e_s = bound_e_s(data["meta"]["manifest"], plan)
    roles = run["roles"]
    fired = {u for n in SYSTEMS for _p, u in sysrec[n]["activity"]}
    silent, violations = {}, []
    for role in ("source1", "source2"):
        d = run["birth_units"][roles[role]]["dynamics"]
        g = d["intrinsic_drive_per_second"] / (1 - d["decay_per_second"]) - d["threshold"]
        silent[role] = g < -e_s
        if silent[role] and roles[role] in fired:
            violations.append(role)
    never = Counter(map(tuple, sysrec["X1"]["activity"])) == Counter(map(tuple, sysrec["X2"]["activity"]))
    return {"contrasts": contrasts, "counts": counts, "flip": flip, "silent": silent, "violations": violations, "never": never}


# ---- 判定と推定（README §4・§5） -----------------------------------------------------------------------------

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


def judgment(people: list[dict]) -> dict:
    table = table_of(people, "D_X")
    m = table["m"]
    if m < PREREGISTERED["min_population"]:
        return table | {"status": "inconclusive", "direction": None, "k2": None, "outcome": "inconclusive"}
    k = k2(m, PREREGISTERED["alpha_per_direction"])
    direction = "+" if table["counts"]["+"] >= k else "-" if table["counts"]["-"] >= k else None
    outcome = {"+": "plus", "-": "minus", None: "not_established"}[direction]
    return table | {"status": "established" if direction else "not_established", "direction": direction, "k2": k,
                    "outcome": outcome}


def quartiles(values: list) -> dict | None:
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


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
    rerun_w = {cid: v["weight"] for cid, v in sysrec["X1_rerun"]["sigma_end"]["connections"].items()}
    if rerun_w != dict.fromkeys(order, W0) | dict(zip(four, TABLE["X1_rerun"], strict=True)):
        problems.append("O6 X1_rerun: 終わりの重み")
    # O8：恒等
    if any(sysrec["X0"][k] != sysrec["X0_tr"][k] for k in ("activity", "layer_a", "layer_b", "sigma_end_sha256")):
        problems.append("O8 X0_tr")
    # O9：記録の非干渉
    if any(sysrec["X1_rerun"][k] != sysrec["X1"][k] for k in ("activity", "layer_a", "layer_b", "sigma_end_sha256")):
        problems.append("O9 X1_rerun")
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
        j, tl, pr, br = proto["judgment"], proto["timeline"], PREREGISTERED, proto["brain"]
        if proto["experiment"] != pr["experiment"]:
            out.append("experiment")
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


def _compare_interval(t: Tally, x: int, n: int, theirs: dict, where: str) -> None:
    t.same((x, n), (theirs["numerator"], theirs["denominator"]), f"{where}.fraction")
    t.same(n >= 1, theirs["computed"], f"{where}.computed")
    if n >= 1 and theirs["computed"]:
        lo, hi = exact_interval(x, n)
        t.close(lo, theirs["interval"][0], f"{where}.lower")
        t.close(hi, theirs["interval"][1], f"{where}.upper")


def _compare_table(t: Tally, mine: dict, theirs: dict, where: str) -> None:
    t.same(mine["m"], theirs["m"], f"{where}.m")
    t.same(mine["counts"], theirs["counts"], f"{where}.counts")
    for s in ("+", "-"):
        _compare_interval(t, mine["counts"][s], mine["m"], theirs["interval"][s], f"{where}.interval[{s}]")


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
        t.same(a["silent"], b["S1_prime"]["silent_source"], f"{key}.S1_prime.silent_source")
        t.same(a["violations"], b["S1_prime"]["violations"], f"{key}.S1_prime.violations")
        t.same(a["never"], b["never_diverged_X1_X2"], f"{key}.never_diverged_X1_X2")
        t.same(a["flip"], b["flip"], f"{key}.flip")
        for part in ("E", "U"):
            for n in SYSTEMS:
                c, d = a["counts"][part][n], b[f"counts_{part}"][n]
                t.same((c["A1"], c["A2"], c["tie"], c["none"]), (d["A1"], d["A2"], d["tie"], d["none"]), f"{key}.counts_{part}.{n}")
                t.same(a1_share(c), _fraction_of(b[f"s_{part}"][n]), f"{key}.s_{part}.{n}")
        for name in CONTRASTS:
            c, d = a["contrasts"][name], b["contrasts"][name]
            for field in ("defined", "in_population", "undefined_kind", "sign", "decided_diff", "A1_diff"):
                t.same(c[field], d[field], f"{key}.contrasts.{name}.{field}")
            t.same(c["difference"], _fraction_of(d["difference"]), f"{key}.contrasts.{name}.difference")
    # 判定
    j_mine, j_theirs = judgment(people), report["judgment"]
    t.same(j_mine["outcome"], j_theirs["outcome"], "judgment.outcome")
    for field in ("status", "direction", "k2"):
        t.same(j_mine[field], j_theirs["J_A"][field], f"judgment.J_A.{field}")
    _compare_table(t, j_mine, j_theirs["J_A"], "judgment.J_A")
    if j_mine["k2"] is not None:
        t.close(float(upper_tail(j_mine["m"], j_mine["k2"])), j_theirs["J_A"]["tail_probability"], "judgment.J_A.tail_probability", 1e-15)
    # 推定 E_A
    est = report["estimate"]
    m = j_mine["m"]
    pop = [p for p in people if p["contrasts"]["D_X"]["in_population"]]
    t.same(m, est["m"], "estimate.m")
    for name, x in (("p_change", j_mine["counts"]["+"] + j_mine["counts"]["-"]), ("p_plus", j_mine["counts"]["+"]),
                    ("p_minus", j_mine["counts"]["-"]), ("p_flip", sum(1 for p in pop if p["flip"]))):
        t.same(x, est[name]["count"], f"estimate.{name}.count")
        _compare_interval(t, x, m, est[name]["interval"], f"estimate.{name}.interval")
    diffs = [abs(float(p["contrasts"]["D_X"]["difference"])) for p in pop]
    t.same(quartiles(diffs), est["abs_D_X"]["all"], "estimate.abs_D_X.all")
    t.same(quartiles([x for x in diffs if x != 0]), est["abs_D_X"]["changed"], "estimate.abs_D_X.changed")
    # 記述の対照
    dc = report["descriptive_controls"]
    for name in TABLES:
        _compare_table(t, table_of(people, name), dc["contrasts"][name], f"descriptive_controls.{name}")
    for x, y in CROSS:
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
        for kind in ("one_system", "both_systems"):
            want = sorted(k for k in mine if mine[k]["contrasts"][name]["undefined_kind"] == kind)
            t.same(want, dc["undefined"][name][kind], f"undefined.{name}.{kind}")
    # R1
    r1 = report["auxiliary"]["R1"]
    t.same(len(people), r1["individuals"], "R1.individuals")
    kinds = Counter(p["contrasts"]["D_X"]["undefined_kind"] for p in people)
    t.same({k: kinds[k] for k in ("one_system", "both_systems")}, r1["undefined_D_X"], "R1.undefined_D_X")
    t.same(sum(1 for p in people if p["never"]), r1["never_diverged_X1_X2"], "R1.never_diverged_X1_X2")
    violations = sum(len(p["violations"]) for p in people)
    t.same(violations, r1["S1_prime"]["violations"], "R1.S1_prime.violations")
    t.same(None if violations else sum(1 for p in people if any(p["silent"].values())),
           r1["S1_prime"]["individuals_with_silent_source"], "R1.S1_prime.individuals_with_silent_source")
    return {"checks": t.checks, "mismatches": t.mismatches,
            "recomputed": {"outcome": j_mine["outcome"],
                           "J_A": {k: j_mine[k] for k in ("m", "counts", "status", "direction", "k2")},
                           "E_A": {"m": m, "p_change_count": j_mine["counts"]["+"] + j_mine["counts"]["-"],
                                   "p_flip_count": sum(1 for p in pop if p["flip"])}}}


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
