"""実験 0036 の記録の解析（確定した事前登録 v0.2 に従う。正本は README・protocol.yaml。#162 merge `dd2973f`）。

0035 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、結果の写しの照合）を引き継ぐ（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid
2. 操作の確認 O2〜O12（README §7）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   判定の量を計算・表示しない。O1 は、run.py が seed に触れる前に測定の commit で走らせた契約テストの記録を確かめる（o1_check）
3. 判定（README §3〜§5）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 出来事ごと：§3.2 の符号の規則（打ち切りの Pulse が系ごとに違う）で、s_e・s_fix・s_chg・逆の順・s_blk・s_none・s_cf
   - 個体ごと：判定の母集団（本体の W の出来事が 10 以上。本体だけで決まる）、n_i・k_i・r_i・P_i（n_i ≥ 1 かつ 10 k_i ≥ n_i）
   - J_P：m ＜ 10 なら判定不能。P_i の数 ≥ k(m) で成立。R6 は m ＜ 10 なら計算しない（判定不能とは別の欄）
   - §6.1 の必ず報告する対照（2 × 2・抑制。P_blk_i ＝ n ≥ 1 かつ 10k ≥ n、n ＝ 0 の個体は別に数える）と、§6.2 の R1〜R10
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0036_as1_other_unit_firing/analyze.py                    # 本番（data/experiments/0036）
  python experiments/0036_as1_other_unit_firing/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
"""

import argparse
import dataclasses
import gzip
import importlib.util
import json
import math
import re
import statistics
from collections.abc import Iterable, Mapping
from fractions import Fraction
from pathlib import Path

import yaml

from anima_ll.unit.dynamics.activity_dynamics import ActivityState
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0036")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure", "O2", "O3", "O4", "O5", "O6", "O7", "O8", "O9", "O10", "O11", "O12")
SIGNS = ("+", "0", "-")
REPORT, LOG = "report.json", "analysis_log.jsonl"
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as1_other_unit_firing_0036.py")
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
A = M.A
RECEPTOR_WEIGHT = float(PROTOCOL["brain"]["receptor_weight"])
C = Fraction(str(PROTOCOL["judgment"]["per_individual"]["c"]))          # 0.1 ＝ 1/10
POPULATION_MIN_EVENTS = int(C.denominator / C.numerator)                 # 10 ＝ 1/c（README §4.3）

# 出来事ごとの対比（README §3.3）：名前 → (X, Y)。τ_Y − τ_X。F は本体
PAIRS = {"e": ("F", "N"), "fix": ("F_fixN", "N"), "chg": ("F", "F_fixN"), "fix_rev": ("F", "N_fixF"),
         "chg_rev": ("N_fixF", "N"), "blk": ("F_blk", "N_blk"), "none": ("F_none", "N_none"), "cf": ("F_cf", "N_cf")}
PATTERNS = ("no_change", "only_B_differs", "only_A_differs", "both_differ", "sign_return")


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


# ---- 符号（README §3.2）と、二経路近似（0035 §3） ---------------------------------------------------

def first_after(pulses: Iterable[int], t: int, horizon: int) -> int | None:
    later = [p for p in pulses if t < p <= t + horizon]
    return min(later) if later else None


def censored_sign(tau_x: int | None, c_x: int, tau_y: int | None, c_y: int) -> str:
    """τ_Y − τ_X の符号（README §3.2）。打ち切りの側は「τ ＞ その系の打ち切りの Pulse」とだけ分かる。"""
    if tau_x is not None and tau_y is not None:
        return "+" if tau_y > tau_x else "-" if tau_y < tau_x else "0"
    if tau_x is not None:
        return "+" if c_y >= tau_x else "?"
    if tau_y is not None:
        return "-" if c_x >= tau_y else "?"
    return "?"


def difference(tau_x: int | None, tau_y: int | None) -> int | None:
    return tau_y - tau_x if tau_x is not None and tau_y is not None else None


def predicted_sign(tau_hat_f: int | None, tau_hat_n: int | None) -> str:
    """ŝ：0035 §3.1 の表（両方なしのときは 0）。"""
    if tau_hat_f is not None and tau_hat_n is not None:
        return "+" if tau_hat_n > tau_hat_f else "-" if tau_hat_n < tau_hat_f else "0"
    if tau_hat_f is not None:
        return "+"
    if tau_hat_n is not None:
        return "-"
    return "0"


def _unit(state: Mapping) -> tuple[SimpleActivityDynamics, ActivityState]:
    d = state["dynamics"]
    if d.get("kind") != "simple_activity":
        raise ValueError(f"未知の力学：{d.get('kind')}")
    dyn = SimpleActivityDynamics(decay_per_second=d["decay_per_second"], threshold=d["threshold"],
                                 refractory_pulses=d["refractory_pulses"],
                                 intrinsic_drive_per_second=d["intrinsic_drive_per_second"],
                                 adaptation_increment=d["adaptation_increment"],
                                 adaptation_tau_seconds=d["adaptation_tau_seconds"])
    return dyn, ActivityState(state["activity"], state["refractory_remaining"], state["adaptation"], state["fire_count"])


def two_path(sigma_t: Mapping, source: str, receiver: str, horizon: int, *,
             receptor_weight: float = RECEPTOR_WEIGHT) -> tuple[int | None, int | None, str]:
    """0035 §3 の二経路近似（0035 の analyze.two_path と同じ式。入力は Σ_t と定数だけ）。R7 と O11 に使う。"""
    t = int(sigma_t["pulse"])
    w_rs = float(sigma_t["connections"][f"{receiver}.main->{source}"]["weight"])
    drives = [(d[1], float(d[2])) for d in sigma_t["drives"]]
    in_r = sum(w for target, w in drives if target == receiver)
    in_s = sum(w for target, w in drives if target == source)
    taus = {}
    for world in ("F", "N"):
        dyn_r, st_r = _unit(sigma_t["units"][receiver])
        dyn_s, st_s = _unit(sigma_t["units"][source])
        receiver_fired_prev = False
        tau = None
        for p in range(t + 1, t + horizon + 1):
            s_r = (in_r if p == t + 1 else 0.0) + (receptor_weight if world == "F" and p == t + 2 else 0.0)
            s_s = (in_s if p == t + 1 else 0.0) + (w_rs if receiver_fired_prev else 0.0)
            st_r, fired_r = dyn_r.advance(st_r, s_r, 1.0)
            st_s, fired_s = dyn_s.advance(st_s, s_s, 1.0)
            receiver_fired_prev = fired_r is not None
            if fired_s is not None:
                tau = p
                break
        taus[world] = tau
    return taus["F"], taus["N"], predicted_sign(taus["F"], taus["N"])


def _p_like(n: int, k: int) -> bool:
    """個体の事象の形（README §4.1・§6.1）：n ≥ 1 かつ k ≥ c n（c ＝ 1/10 なら 10 k ≥ n）。整数で比べる。"""
    return n >= 1 and k * C.denominator >= n * C.numerator


def pattern(s_a: str, s_fix: str, s_e: str) -> str:
    """R5 の五つの型（設計メモ §6.4）。比較 A ＝ s_a と s_fix、比較 B ＝ s_fix と s_e。三つとも ？ でないこと。"""
    a_same, b_same = s_a == s_fix, s_fix == s_e
    if a_same and b_same:
        return "no_change"
    if a_same:
        return "only_B_differs"
    if b_same:
        return "only_A_differs"
    return "sign_return" if s_e == s_a else "both_differ"


def _other_pulses(firings: list, other: str, lo: int, hi: int) -> list[int]:
    return [p for p, u in firings if u == other and lo < p <= hi]


def event_quantities(run: Mapping, ev: Mapping) -> dict:
    """出来事ごとの量（README §3.3・§6.2 の R1・R7・R9）。F は本体の記録、ほかは系の記録から。"""
    roles, body, plan = run["roles"], run["body"], run["plan"]
    t, h = ev["t"], plan["horizon"]
    S = ev["systems"]
    tau_f = first_after([p for p, _ in body["intents"]], t, h)
    tc = {"F": (tau_f, t + h)}
    for name in M.SYSTEMS:
        tc[name] = (S[name]["tau"], S[name]["censor"])
    out = {"t": t, "e_pulse": ev["e"]["pulse"],
           "tau": {k: v[0] for k, v in tc.items()},
           "stopped_at": {"F": tau_f if tau_f is not None else t + h, **{k: S[k]["stopped_at"] for k in M.SYSTEMS}},
           "censor": {k: v[1] for k, v in tc.items()}}
    for key, (x, y) in PAIRS.items():
        (tx, cx), (ty, cy) = tc[x], tc[y]
        out[f"d_{key}"] = difference(tx, ty)
        out[f"s_{key}"] = censored_sign(tx, cx, ty, cy)
    hat_f, hat_n, s_hat = two_path(ev["sigma_t"], roles["source"], roles["receiver"], h)
    out.update({"tau_hat_F": hat_f, "tau_hat_N": hat_n, "s_hat": s_hat})
    stop_f, stop_n = out["stopped_at"]["F"], S["N"]["stopped_at"]
    other = roles["other"]
    sc1 = tau_f is not None and stop_n >= tau_f
    sc2 = (_other_pulses(body["activity"], other, t, tau_f) == _other_pulses(S["N"]["firings"], other, t, tau_f)) if sc1 else None
    lo = min(stop_f, stop_n)
    out.update({"shortcut_1": sc1, "shortcut_2": sc2, "shortcut": bool(sc1 and sc2),
                "other_same_F_N": _other_pulses(body["activity"], other, t, lo) == _other_pulses(S["N"]["firings"], other, t, lo)})
    return out


def _pair_counts(events: list[dict], key: str) -> dict:
    """s_e と s_key がどちらも ？ でない出来事の数（n）と、そのうち違う数（k）と、P の形。"""
    ev = [e for e in events if e["s_e"] != "?" and e[f"s_{key}"] != "?"]
    k = sum(1 for e in ev if e[f"s_{key}"] != e["s_e"])
    return {"n": len(ev), "k": k, "P": _p_like(len(ev), k), "zero_evaluable": len(ev) == 0}


def _pattern_counts(events: list[dict], key_a: str) -> dict:
    obs = [e for e in events if "?" not in (e[f"s_{key_a}"], e["s_fix"], e["s_e"])]
    counts = {p: 0 for p in PATTERNS}
    for e in obs:
        counts[pattern(e[f"s_{key_a}"], e["s_fix"], e["s_e"])] += 1
    return {"denominator": len(obs), "unobservable": len(events) - len(obs), **counts}


def individual(run: Mapping) -> dict:
    """個体ごとの量（README §4.1）と、§6 の記録の元。母集団は本体の W の出来事の数だけで決まる（A3）。"""
    events = [event_quantities(run, ev) for ev in run["events"]]
    n_events = len(events)
    main = _pair_counts(events, "fix")
    roles = run["roles"]
    return {
        "applicable": n_events >= 1,
        "in_population": n_events >= POPULATION_MIN_EVENTS,
        "roles": dict(roles),
        "birth_units": run["body"]["birth_units"],
        "events_in_window": n_events,
        "n_i": main["n"], "k_i": main["k"], "r_i": main["k"] / main["n"] if main["n"] else None, "P_i": main["P"],
        "unevaluable": n_events - main["n"],
        "censored_s_e": sum(1 for e in events if e["s_e"] == "?"),
        "censored_s_fix": sum(1 for e in events if e["s_fix"] == "?"),
        "P1_d_chg_nonzero": sum(1 for e in events if e["d_chg"] not in (None, 0)),
        "P1_s_chg_nonzero": sum(1 for e in events if e["s_chg"] in ("+", "-")),
        "control": {"blk": _pair_counts(events, "blk"), "none": _pair_counts(events, "none")},
        "reverse": {**_pair_counts(events, "fix_rev"),
                    "agree_fix_and_fix_rev": sum(1 for e in events if "?" not in (e["s_fix"], e["s_fix_rev"])
                                                 and e["s_fix"] == e["s_fix_rev"]),
                    "both_observable": sum(1 for e in events if "?" not in (e["s_fix"], e["s_fix_rev"]))},
        "patterns": {"blk": _pattern_counts(events, "blk"), "none": _pattern_counts(events, "none")},
        "two_path": {k: {"observable": sum(1 for e in events if e[f"s_{k}"] != "?"),
                         "agree": sum(1 for e in events if e[f"s_{k}"] != "?" and e["s_hat"] == e[f"s_{k}"])}
                     for k in ("e", "blk", "none")},
        "estimand_B": {"d_e_minus_d_cf_nonzero": sum(1 for e in events if e["d_e"] is not None and e["d_cf"] is not None
                                                     and e["d_e"] != e["d_cf"]),
                       "s_e_ne_s_cf": sum(1 for e in events if "?" not in (e["s_e"], e["s_cf"]) and e["s_e"] != e["s_cf"])},
        "shortcut": {"holds": sum(1 for e in events if e["shortcut"]),
                     "condition_1_fails": sum(1 for e in events if not e["shortcut_1"]),
                     "other_same_F_N": sum(1 for e in events if e["other_same_F_N"])},
        "source_fires_whole_run": sum(1 for _, u in run["body"]["activity"] if u == roles["source"]),
        "events": events,
    }


def binom_upper_tail(m: int, k: int) -> float:
    return sum(math.comb(m, j) for j in range(k, m + 1)) / 2 ** m


def k_of_m(m: int, alpha: float) -> int:
    return next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    a = 1 - level

    def cdf(k: int, p: float) -> float:
        return sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(0, k + 1))

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


def judge(individuals: Mapping[str, Mapping]) -> dict:
    """J_P（README §4.2）と、同じ分母の R6。R6 は m ＜ 10 なら計算しない（J_P の判定不能とは別の欄）。"""
    j = PROTOCOL["judgment"]["J_P"]
    population = [s for s, v in individuals.items() if v["in_population"]]
    m = len(population)
    holds = sum(1 for s in population if individuals[s]["P_i"])
    if m < j["min_population"]:
        out = {"m": m, "count_P_i": holds, "k": None, "status": "inconclusive"}
        r6 = {"computed": False, "interval": None, "numerator": holds, "denominator": m,
              "reason": f"m = {m} < {j['min_population']}: the interval is not computed (separate from the J_P status)"}
        return {"J_P": out, "R6": r6}
    k = j["k_of_m"][m]
    if k != k_of_m(m, j["alpha"]):
        raise ValueError(f"protocol の k({m}) ＝ {k} が二項の計算と違う")
    out = {"m": m, "count_P_i": holds, "k": k, "tail_probability": binom_upper_tail(m, k),
           "status": "established" if holds >= k else "not_established"}
    r6 = {"computed": True, "interval": list(clopper_pearson(holds, m)), "numerator": holds, "denominator": m}
    return {"J_P": out, "R6": r6}


def five_numbers(values: list[int]) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def reported_control(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.1：必ず報告する対照（判定の母集団。検定はしない）。分母は m で、評価できる出来事なしの個体を含む。"""
    population = [s for s, v in individuals.items() if v["in_population"]]
    out = {}
    for key in ("blk", "none"):
        per = {s: individuals[s]["control"][key] for s in population}
        diffs = [e["d_e"] - e[f"d_{key}"] for s in population for e in individuals[s]["events"]
                 if e["d_e"] is not None and e[f"d_{key}"] is not None]
        out[key] = {"m": len(population),
                    "no_evaluable_event": sum(1 for v in per.values() if v["zero_evaluable"]),
                    "count_P": sum(1 for v in per.values() if v["P"]),
                    "events_s_e_ne": sum(v["k"] for v in per.values()),
                    "events_evaluable": sum(v["n"] for v in per.values()),
                    "d_e_minus_d": five_numbers(diffs),
                    "per_individual": per}
    return out


def auxiliary(individuals: Mapping[str, Mapping], runs: Mapping[int, dict]) -> dict:
    """§6.2 の R2・R4・R5・R7・R8・R9・R10 の全体の数（判定に使わない。出来事を独立の標本として扱わない）。"""
    vals = list(individuals.values())
    population = [v for v in vals if v["in_population"]]

    def total(path):
        return sum(path(v) for v in vals)

    weights = {str(s): {p: {"weights": {c: v["weight"] for c, v in st.items()},
                            "traces": {c: {"pre_trace": v["pre_trace"], "post_trace": v["post_trace"]} for c, v in st.items()},
                            "pair_sums": {"-".join(k): v for k, v in A.pair_sums(st).items()}}
                        for p, st in data["run"]["body"]["checkpoints"].items()}
               for s, data in sorted(runs.items())}
    return {
        "R2": {"applicable": sum(1 for v in vals if v["applicable"]), "in_population": len(population),
               "n_i_distribution": five_numbers([v["n_i"] for v in population]),
               "unevaluable_in_population": sum(v["unevaluable"] for v in population),
               "population_with_n_i_below_10": sum(1 for v in population if v["n_i"] < POPULATION_MIN_EVENTS),
               # 小さい分母（1 ≤ n_i ≤ 9）では 1 つの符号の違いで P_i が成り立つので、その成立の数を分けて残す（README §4.3・§12）
               "P_i_with_n_i_1_to_9": sum(1 for v in population if 1 <= v["n_i"] < POPULATION_MIN_EVENTS and v["P_i"]),
               "P_i_with_n_i_10_or_more": sum(1 for v in population if v["n_i"] >= POPULATION_MIN_EVENTS and v["P_i"]),
               "P1_d_chg_nonzero": total(lambda v: v["P1_d_chg_nonzero"]),
               "P1_s_chg_nonzero": total(lambda v: v["P1_s_chg_nonzero"])},
        "R4_reverse": {"population_count_P": sum(1 for v in population if v["reverse"]["P"]),
                       "events_evaluable": total(lambda v: v["reverse"]["n"]),
                       "events_s_e_ne": total(lambda v: v["reverse"]["k"]),
                       "agree_fix_and_fix_rev": total(lambda v: v["reverse"]["agree_fix_and_fix_rev"]),
                       "both_observable": total(lambda v: v["reverse"]["both_observable"])},
        "R5_patterns": {k: {p: total(lambda v, k=k, p=p: v["patterns"][k][p])
                            for p in ("denominator", "unobservable", *PATTERNS)} for k in ("blk", "none")},
        "R7_two_path": {k: {f: total(lambda v, k=k, f=f: v["two_path"][k][f]) for f in ("observable", "agree")}
                        for k in ("e", "blk", "none")},
        "R8_estimand_B": {f: total(lambda v, f=f: v["estimand_B"][f]) for f in ("d_e_minus_d_cf_nonzero", "s_e_ne_s_cf")},
        "R9_shortcut": {f: total(lambda v, f=f: v["shortcut"][f]) for f in ("holds", "condition_1_fails", "other_same_F_N")},
        "R10_weights": weights,
    }


# ---- 操作の確認（README §7。生の記録から） -------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "body", "clone_check", "events", "rerun", "rerun_plain"}
BODY_KEYS = {"intents", "sensory", "activity", "realized", "pending_end", "checkpoints", "checkpoint_sigma_sha256", "birth_units"}
EVENT_KEYS = {"t", "intent_delta_id", "e", "sigma_t", "body_pending", "n_branch_sigma_sha256", "systems", "plain"}
SYSTEM_KEYS = {"tau", "stopped_at", "censor", "firings", "sensory", "pending_branch", "pending_stop", "sigma_stop_sha256",
               "control", "interventions", "history", "masked", "baseline_weights", "pulse_weights"}
N_PRIME_KEYS = {"tau", "stopped_at", "censor", "sensory", "sigma_stop_sha256", "pending_branch"}
PLAIN_KEYS = {"tau", "stopped_at", "firings"}
RERUN_KEYS = {"intents", "sensory", "activity", "sigma_sha256"}
RERUN_PLAIN_KEYS = {"intents", "sensory", "activity", "pulse", "sigma_end_sha256"}


def _expected_sensory(pending_rows: list, t: int, stop: int) -> list[list]:
    """分岐の時点の予約の列から決まる感覚の出来事の列（予約の Pulse が (t, stop] に入るもの 1 つにつき 1 つ）。"""
    return sorted([[row[3], row[2]] for row in pending_rows if t < row[3] <= stop])


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, out["structure"])
        if not out["structure"]:
            for name, f in (("O2", _o2), ("O3", _o3), ("O4", _o4), ("O5", _o5), ("O7", _o7), ("O8", _o8),
                            ("O9", _o9), ("O10", _o10), ("O11", _o11), ("O12", _o12)):
                try:
                    f(run, out[name])
                except Exception as e:                       # 記録の形が壊れていても止めずに、その確認を不成立にする
                    out[name].append(f"記録を読めない：{e!r}")
        _o6(seed, mode, out["O6"])
    except Exception as e:
        out["structure"].append(f"記録を読めない：{e!r}")
    return out


def _structure(data, mode, seed, plan, out) -> None:
    run = data.get("run", {})
    if set(data) != {"meta", "run"}:
        out.append(f"raw の最上位の欄が {sorted(data)}")
    if set(run) != RUN_KEYS:
        out.append(f"run の欄が {sorted(run)}（判定の量の欄を raw に入れない）")
        return
    if set(run["body"]) != BODY_KEYS or set(run["rerun"]) != RERUN_KEYS or set(run["rerun_plain"]) != RERUN_PLAIN_KEYS:
        out.append("body・rerun・rerun_plain の欄が違う")
    if run["seed"] != seed:
        out.append(f"seed が {run['seed']}")
    want = plan or M.formal_plan(PROTOCOL)
    if mode in ("formal", "smoke") and plan is not None and plan != M.formal_plan(PROTOCOL):
        out.append("本番・smoke では protocol の Plan だけを使う")
    if run["plan"] != json.loads(json.dumps(dataclasses.asdict(want))):
        out.append("raw の plan が使う Plan と違う")
    if run["roles"] != A.assign_roles(seed).as_dict():
        out.append("役の割り当てが assign_roles と違う")
    meta = data.get("meta", {})
    for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode), ("seed", seed)):
        if meta.get(k) != v:
            out.append(f"meta の {k} が {meta.get(k)}")
    if meta.get("manifest") != M.manifest_raw():
        out.append("meta の設計図が AS1 の設計図と違う")
    want_blind = {"smoke": True, "formal": False}.get(mode)
    if not isinstance(meta.get("blind"), bool) or (want_blind is not None and meta["blind"] is not want_blind):
        out.append(f"meta の blind が {meta.get('blind')}（smoke は盲検、本番は盲検でない）")
    for ev in run["events"]:
        S = ev.get("systems", {}) if isinstance(ev, dict) else {}
        ok = (isinstance(ev, dict) and set(ev) == EVENT_KEYS and set(S) == set(M.SYSTEMS)
              and set(ev["plain"]) == set(M.PLAIN)
              and all(set(S[n]) == (N_PRIME_KEYS if n == "N_prime" else SYSTEM_KEYS) for n in M.SYSTEMS)
              and all(set(ev["plain"][n]) == PLAIN_KEYS for n in M.PLAIN))
        if not ok:
            out.append(f"出来事 t={ev.get('t') if isinstance(ev, dict) else '?'} の欄が違う")
            break


def _o2(run, out) -> None:
    roles, body, plan = run["roles"], run["body"], run["plan"]
    intents = [p for p, _ in body["intents"]]
    fires = [p for p, u in body["activity"] if u == roles["source"]]
    if intents != fires:
        out.append("意図の Pulse の列が、源の発火の Pulse の列と違う（IC-1）")
    expected = [[p + 1, roles["consequence_receptor"]] for p in intents if p + 1 <= plan["body_runs_to"]]
    if body["sensory"] != expected:
        out.append("感覚の出来事が、意図ごとに t + 1 の結果の Receptor へ 1 つ、だけになっていない（WC-2・外の刺激なし）")
    if any(r == roles["source_receptor"] for _, r in body["sensory"]):
        out.append("源の Receptor に刺激がある（K1）")
    if any(len(rids) != 1 or n != 1 for _, _, rids, n in body["realized"]):
        out.append("結果の予約が同じ Pulse に重なった（W-2）")


def _o3(run, out) -> None:
    cc, plan = run["clone_check"], run["plan"]
    if not cc or cc["at"] != plan["clone_check_at"] or cc["until"] != plan["clone_check_until"]:
        out.append("介入なしの複製の記録がない、か区間が違う")
        return
    if cc["sigma_body"] != cc["sigma_clone"]:
        out.append(f"Pulse {cc['until']} で、介入なしの複製の Σ が本体と違う（CT-Σ1）")
    body_act = [x for x in run["body"]["activity"] if cc["at"] < x[0] <= cc["until"]]
    if cc["activity_clone"] != body_act:
        out.append("介入なしの複製の発火の列が本体と違う")


def _stop_f(run, ev) -> tuple[int | None, int]:
    t, h = ev["t"], run["plan"]["horizon"]
    tau_f = first_after([p for p, _ in run["body"]["intents"]], t, h)
    return tau_f, (tau_f if tau_f is not None else t + h)


def _o4(run, o4) -> None:
    """README §7 の O4 の詳細：(a) 分岐の時点の予約の列、(b) 止まる Pulse までの感覚の出来事の列、(c) 最初の意図で新しく
    作られる予約は比べない（pending_stop は記録だけ）。"""
    roles, body, plan = run["roles"], run["body"], run["plan"]
    intents = body["intents"]
    expected_t = [p for p, _ in intents if plan["window_first"] <= p + 1 <= plan["window_last"]]
    if [ev["t"] for ev in run["events"]] != expected_t:
        o4.append("出来事の集まりが、本体の区間 W のすべての結果の予約と違う（A3 の適用の対象）")
    delta_of = {p: d for p, d in intents}
    for ev in run["events"]:
        t, e = ev["t"], ev["e"]
        where = f"出来事 t={t}"
        if (e["origin"], e["pulse"], e["receptor"]) != (delta_of.get(t), t + 1, roles["consequence_receptor"]) \
                or ev["intent_delta_id"] != delta_of.get(t):
            o4.append(f"{where}：e が t の意図の結果の予約ではない")
        e_rows = [row for row in ev["body_pending"] if row[0] == e["rid"]]
        if len(e_rows) != 1:
            o4.append(f"{where}：本体の分岐の時点の予約の列に e が 1 つだけない")
            continue
        minus_e = [row for row in ev["body_pending"] if row[0] != e["rid"]]
        _, stop_f = _stop_f(run, ev)
        body_sens = sorted(x for x in body["sensory"] if t < x[0] <= stop_f)
        if body_sens != _expected_sensory(ev["body_pending"], t, stop_f):
            o4.append(f"{where}：本体の感覚の出来事が、分岐の時点の予約から決まる列と違う")
        for name in M.SYSTEMS:
            s = ev["systems"][name]
            cancelled = name in M.E_CANCELLED
            if s["pending_branch"] != (minus_e if cancelled else ev["body_pending"]):                       # (a)
                o4.append(f"{where}・{name}：分岐の時点の予約の列が、本体の列{'から e だけを除いたもの' if cancelled else ''}と違う")
            stop = s["stopped_at"]
            if sorted(s["sensory"]) != _expected_sensory(s["pending_branch"], t, stop):                    # (b)
                o4.append(f"{where}・{name}：(t, 止まった Pulse] の感覚の出来事が、分岐の時点の予約から決まる列と違う")
            lo = min(stop, stop_f)
            x_sens = sorted(x for x in s["sensory"] if t < x[0] <= lo)
            b_sens = sorted(x for x in body["sensory"] if t < x[0] <= lo)
            if cancelled:
                if [e["pulse"], e["receptor"]] in b_sens:
                    b_sens.remove([e["pulse"], e["receptor"]])
                else:
                    o4.append(f"{where}・{name}：共通の区間の本体に e の感覚の出来事がない")
            if x_sens != b_sens:
                o4.append(f"{where}・{name}：共通の区間 (t, min(止まった Pulse, stop_F)] の感覚の出来事が本体{'から e を除いたもの' if cancelled else ''}と違う")


def expected_censor(ev: Mapping, name: str, h: int) -> int:
    """README §3.1：固定した系（o:=N・o:=F）は参照の系の止まった Pulse、ほかは t ＋ H。"""
    ref = M.FORCED.get(name)
    return ev["systems"][ref]["stopped_at"] if ref is not None else ev["t"] + h


def _stop_ok(s: Mapping, t: int, censor: int) -> bool:
    stop = s["stopped_at"]
    return t < stop <= censor and ((s["tau"] is not None and s["tau"] == stop) or (s["tau"] is None and stop == censor))


def _firings_ok(firings, t: int, stop: int) -> bool:
    return all(t < p <= stop for p, _ in firings) and firings == sorted(firings, key=lambda x: x[0])


def _o5(run, o5) -> None:
    """(a) Σ_t と分岐の時点の N の Σ（0035 と同じ）。(b) すべての系で、打ち切りの Pulse・止まった Pulse・τ が合い、保存した
    源の発火から計算し直した τ が記録と一致する（N′ は発火を残さないので止まった Pulse と打ち切りだけ）。"""
    roles, h = run["roles"], run["plan"]["horizon"]
    for ev in run["events"]:
        t, e, sig = ev["t"], ev["e"], ev["sigma_t"]
        where = f"出来事 t={t}"
        if sig.get("pulse") != t:
            o5.append(f"{where}：Σ_t の Pulse が t ではない")
            continue
        if sig["world"]["pending"] != ev["body_pending"]:
            o5.append(f"{where}：Σ_t の予約の列が、本体の分岐の時点の予約の列と違う")
        try:
            expected = M.expected_n_branch_sigma(sig, e)
        except StopIteration:
            o5.append(f"{where}：Σ_t の予約の列に e がない")
            continue
        if M.sigma_sha256(expected) != ev["n_branch_sigma_sha256"]:
            o5.append(f"{where}：分岐の時点の N の Σ が、Σ_t から e の予約だけを取り消したものと違う")
        records = [(n, ev["systems"][n]) for n in M.SYSTEMS] + [(f"{n}_plain", ev["plain"][n]) for n in M.PLAIN]
        for name, s in records:
            base = name.removesuffix("_plain")
            censor = expected_censor(ev, base, h)
            if not name.endswith("_plain") and s["censor"] != censor:
                o5.append(f"{where}・{name}：打ち切りの Pulse が {censor} ではない")
            if not _stop_ok(s, t, censor):
                o5.append(f"{where}・{name}：止まった Pulse と τ が合わない")
            if "firings" not in s:
                continue
            if not _firings_ok(s["firings"], t, s["stopped_at"]):
                o5.append(f"{where}・{name}：発火の記録が (t, 止まった Pulse] の外にあるか、順に並んでいない")
            if first_after([p for p, u in s["firings"] if u == roles["source"]], t, censor - t) != s["tau"]:
                o5.append(f"{where}・{name}：保存した発火から計算した τ が、記録した τ と違う")


def _o6(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed {seed} が {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5）")


def _o7(run, o7) -> None:
    """(a)・(b) は 0035 と同じ。rerun_plain は他の Unit を包まない本体（measure.body_rerun_plain）。
    (c) F_fixN・F_blk・F_cf と、Pulse ごとの記録をしない走り直しの τ・止まった Pulse・すべての Unit の発火。"""
    body, rerun, plain, plan = run["body"], run["rerun"], run["rerun_plain"], run["plan"]
    for key in ("intents", "sensory", "activity"):
        if rerun[key] != body[key]:
            o7.append(f"本体の {key} が、記録も分岐もしない走り直しと違う")
        if plain[key] != body[key]:
            o7.append(f"本体の {key} が、途中で Σ を読まず他の Unit を包まない走り直しと違う")
    end = str(plan["body_runs_to"])
    if plain["pulse"] != plan["body_runs_to"] or end not in body["checkpoint_sigma_sha256"] \
            or plain["sigma_end_sha256"] != body["checkpoint_sigma_sha256"][end]:
        o7.append("最後の Pulse の本体の Σ が、途中で Σ を読まず他の Unit を包まない走り直しの Σ と違う")
    want_pulses = {str(p) for p in plan["checkpoints"]} | {str(ev["t"]) for ev in run["events"]}
    if set(rerun["sigma_sha256"]) != want_pulses or set(body["checkpoint_sigma_sha256"]) != {str(p) for p in plan["checkpoints"]}:
        o7.append("Σ を比べる Pulse の組が、チェックポイントと出来事の t の組と違う")
        return
    for p, sha in body["checkpoint_sigma_sha256"].items():
        if rerun["sigma_sha256"][p] != sha:
            o7.append(f"Pulse {p}：本体の Σ が、走り直しの Σ と違う")
    for ev in run["events"]:
        where = f"出来事 t={ev['t']}"
        if rerun["sigma_sha256"][str(ev["t"])] != M.sigma_sha256(ev["sigma_t"]):
            o7.append(f"{where}：保存した Σ_t が、走り直しの同じ Pulse の Σ と違う")
        n, n2 = ev["systems"]["N"], ev["systems"]["N_prime"]
        if (n["tau"], n["stopped_at"], n["sensory"], n["sigma_stop_sha256"]) != \
                (n2["tau"], n2["stopped_at"], n2["sensory"], n2["sigma_stop_sha256"]):
            o7.append(f"{where}：系 N と、追加の記録をしない N′ が違う")
        for name in M.PLAIN:
            a, b = ev["systems"][name], ev["plain"][name]
            if (a["tau"], a["stopped_at"], a["firings"]) != (b["tau"], b["stopped_at"], b["firings"]):
                o7.append(f"{where}：{name} と、Pulse ごとの記録をしない走り直しが違う")


def _o8(run, o8) -> None:
    """発火の時刻の固定：列が参照の系の他の Unit の発火の列（∅ は空）で、区間・打ち切りが合い、固定した系の他の Unit の発火が
    列のとおりで、列が自然な決まり方と違った Pulse の記録が列と合う。固定しない系には固定の記録がない。"""
    other = run["roles"]["other"]
    for ev in run["events"]:
        t, S = ev["t"], ev["systems"]
        where = f"出来事 t={t}"
        for name in M.SYSTEMS:
            s = S[name]
            if name not in M.FORCED:
                if name != "N_prime" and s["control"] is not None:
                    o8.append(f"{where}・{name}：固定しない系に固定の記録がある")
                continue
            ctrl, ref = s["control"], M.FORCED[name]
            if not isinstance(ctrl, dict) or set(ctrl) != {"schedule", "after", "until", "overrides"}:
                o8.append(f"{where}・{name}：固定の記録がない、か欄が違う")
                continue
            want = [] if ref is None else _other_pulses(S[ref]["firings"], other, t, S[ref]["stopped_at"])
            if ctrl["schedule"] != want:
                o8.append(f"{where}・{name}：列が、参照の系の他の Unit の発火の列と違う")
            if ctrl["after"] != t or ctrl["until"] != s["censor"]:
                o8.append(f"{where}・{name}：固定の区間が (t, 打ち切りの Pulse] ではない")
            if s["stopped_at"] > s["censor"]:
                o8.append(f"{where}・{name}：止まった Pulse が打ち切りの Pulse を越える")
            stop = s["stopped_at"]
            if _other_pulses(s["firings"], other, t, stop) != [p for p in ctrl["schedule"] if p <= stop]:
                o8.append(f"{where}・{name}：他の Unit の発火が列のとおりではない")
            ov = ctrl["overrides"]
            if [p for p, _ in ov] != sorted({p for p, _ in ov}) or any(
                    not (t < p <= stop) or kind != ("fire" if p in ctrl["schedule"] else "hold") for p, kind in ov):
                o8.append(f"{where}・{name}：列が自然な決まり方と違った Pulse の記録が、列と合わない")
        if "F_fixN" in ev["plain"]:
            p = ev["plain"]["F_fixN"]
            want = S["F_fixN"]["control"]["schedule"] if isinstance(S["F_fixN"]["control"], dict) else None
            if want is None or _other_pulses(p["firings"], other, t, p["stopped_at"]) != [x for x in want if x <= p["stopped_at"]]:
                o8.append(f"{where}：F_fixN の走り直しの他の Unit の発火が列のとおりではない")


def _interventions_ok(s: Mapping, t: int, name: str, targets: list[str], six: list[str]) -> bool:
    active = []
    if name in M.BLOCKED:
        active.append([A.FB1, sorted(targets), A.ADVANCE])
    if name in M.FROZEN:
        active.append([A.FREEZE, sorted(six), A.ADVANCE])
    history = [[t, name, active]] if active else []
    return s["interventions"]["active"] == active and s["history"] == history


def _o9(run, o9) -> None:
    """伝達の遮断：t ＋ 1 から止まった Pulse までのすべての Pulse で、対象の 2 本に渡した重みが 0 で、渡した重みが中の重みと
    違った接続は対象の 2 本だけ。宣言は Pulse t の境界の一度だけ。遮断しない系に遮断の記録・宣言がない。"""
    roles = run["roles"]
    targets = list(M.block_targets(A.Roles(roles["source"], roles["receiver"], roles["other"])))
    for ev in run["events"]:
        t, S = ev["t"], ev["systems"]
        six = sorted(ev["sigma_t"]["connections"])                # 可塑的な 6 本（Σ の接続の状態は可塑的な接続だけ）
        for name in M.SYSTEMS:
            if name == "N_prime":
                continue
            s, where = S[name], f"出来事 t={t}・{name}"
            if name not in M.BLOCKED:
                if s["masked"] is not None:
                    o9.append(f"{where}：遮断しない系に遮断の記録がある")
                if any(iv[0] == A.FB1 for iv in s["interventions"]["active"]):
                    o9.append(f"{where}：遮断しない系に FB-1 の宣言がある")
                continue
            masked = s["masked"]
            if not isinstance(masked, list) or [r[0] for r in masked] != list(range(t + 1, s["stopped_at"] + 1)):
                o9.append(f"{where}：遮断の記録が t ＋ 1 から止まった Pulse までそろっていない")
                continue
            if any(r[1] != [0.0, 0.0] for r in masked):
                o9.append(f"{where}：対象の伝達に渡した重みが 0 でない Pulse がある")
            if any(not set(r[2]) <= set(targets) for r in masked):
                o9.append(f"{where}：対象の外の接続で、渡した重みが中の重みと違う")
            if not _interventions_ok(s, t, name, targets, six):
                o9.append(f"{where}：介入の宣言が、Pulse t の境界の一度だけの遮断（と停止）ではない")


def _o10(run, o10) -> None:
    """恒等の条件：F^{o:=F} ＝ F′（τ・止まった Pulse・すべての Unit の発火・止まった Pulse の Σ）、F′ ＝ 本体の記録
    （τ・止まった Pulse・すべての Unit の発火）、近道の (1)・(2) が成り立つ出来事で F^{o:=N} ＝ F（τ・すべての Unit の発火）。"""
    body, other = run["body"], run["roles"]["other"]
    for ev in run["events"]:
        t, S = ev["t"], ev["systems"]
        where = f"出来事 t={t}"
        fp, ff = S["F_prime"], S["F_fixF"]
        keys = ("tau", "stopped_at", "firings", "sigma_stop_sha256")
        if tuple(fp[k] for k in keys) != tuple(ff[k] for k in keys):
            o10.append(f"{where}：F^{{o:=F}} が F′ と一致しない")
        tau_f, stop_f = _stop_f(run, ev)
        body_firings = [x for x in body["activity"] if t < x[0] <= stop_f]
        if (fp["tau"], fp["stopped_at"], fp["firings"]) != (tau_f, stop_f, body_firings):
            o10.append(f"{where}：F′ が本体の記録と一致しない")
        n = S["N"]
        sc1 = tau_f is not None and n["stopped_at"] >= tau_f
        if sc1 and _other_pulses(body["activity"], other, t, tau_f) == _other_pulses(n["firings"], other, t, tau_f):
            fx = S["F_fixN"]
            if (fx["tau"], fx["firings"]) != (tau_f, body_firings):
                o10.append(f"{where}：近道の (1)・(2) が成り立つのに、F^{{o:=N}} が F と一致しない")


def _o11(run, o11) -> None:
    """二経路近似との一致：可塑性を止めた遮断・抑制の系の τ（打ち切りを含む）が、Σ_t から計算した τ̂ と一致する。"""
    roles, h = run["roles"], run["plan"]["horizon"]
    for ev in run["events"]:
        S = ev["systems"]
        hat_f, hat_n, _ = two_path(ev["sigma_t"], roles["source"], roles["receiver"], h)
        got = {"F_blk_cf": hat_f, "F_none_cf": hat_f, "N_blk_cf": hat_n, "N_none_cf": hat_n}
        for name, hat in got.items():
            if S[name]["tau"] != hat:
                o11.append(f"出来事 t={ev['t']}・{name}：τ が二経路近似の τ̂ と違う")


def _o12(run, o12) -> None:
    """可塑性の停止：止めた系で、分岐の時点の 6 本の重み（Σ_t の重み）が、t ＋ 1 から止まった Pulse まで変わらない。"""
    roles = run["roles"]
    targets = list(M.block_targets(A.Roles(roles["source"], roles["receiver"], roles["other"])))
    for ev in run["events"]:
        t, S = ev["t"], ev["systems"]
        sigma_w = {cid: v["weight"] for cid, v in sorted(ev["sigma_t"]["connections"].items())}
        for name in M.SYSTEMS:
            if name == "N_prime":
                continue
            s, where = S[name], f"出来事 t={t}・{name}"
            if name not in M.FROZEN:
                if s["baseline_weights"] is not None or s["pulse_weights"] is not None:
                    o12.append(f"{where}：止めない系に停止の記録がある")
                if any(iv[0] == A.FREEZE for iv in s["interventions"]["active"]):
                    o12.append(f"{where}：止めない系に FREEZE の宣言がある")
                continue
            pw = s["pulse_weights"]
            if s["baseline_weights"] != sigma_w:
                o12.append(f"{where}：分岐の時点の重みが Σ_t の重みと違う")
            if not isinstance(pw, list) or [r[0] for r in pw] != list(range(t + 1, s["stopped_at"] + 1)):
                o12.append(f"{where}：重みの記録が t ＋ 1 から止まった Pulse までそろっていない")
                continue
            if any(r[1] != sigma_w for r in pw):
                o12.append(f"{where}：止めた重みが動いた Pulse がある")
            if not _interventions_ok(s, t, name, targets, sorted(sigma_w)):
                o12.append(f"{where}：介入の宣言が、Pulse t の境界の一度だけの停止（と遮断）ではない")


# ---- 記録の確認・前提・report（0035 と同じ） ----------------------------------------------------------

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
    """smoke の盲検の記録の確かめ（0035 と同じ）。O6 は記録に頼らずここで確かめ直す。"""
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
                    and meta.get("manifest") == M.manifest_raw())
    except (KeyError, TypeError, AttributeError):
        ok_shape = False
    if not ok_shape:
        return status
    status = dict(blind["checks"])
    o6: list[str] = []
    _o6(seed, mode, o6)
    if o6:
        status["O6"] = "fail"
    return status


def o1_check(out: Path, commit: str | None, repo: Path | None = None) -> list[str]:
    """O1 の証拠（0035 と同じ）。テストのファイルの SHA-256 は repo（省略したときは呼んだ時点の REPO）のものと比べる。"""
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
    j = judge(individuals)
    return {"mode": mode, "valid": True, "O1": {"status": o1_status, "problems": o1},
            "judgment": {"J_P": j["J_P"]}, "R6": j["R6"], "reported_control": reported_control(individuals),
            "individuals": individuals, "auxiliary": auxiliary(individuals, runs)}


def verify_results_copy(src: Path, dst: Path) -> list[str]:
    """出力先 src と写し dst の照合（0035 と同じ）。鍵のファイル（run.lock）は写さない。"""
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
