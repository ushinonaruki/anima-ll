"""実験 0035 の記録の解析（確定した事前登録 v0.3 に従う。正本は README・protocol.yaml。#156 merge `b71d6fc`）。

0034 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、結果の写しの照合）を引き継ぐ（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid
2. 操作の確認 O2〜O7（README §7）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   判定の量を計算・表示しない。O1 は、run.py が seed に触れる前に測定の commit で走らせた契約テストの記録を確かめる（o1_check）
3. 判定（README §3〜§5）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 出来事ごと：s_e（0034 §2.3 の表）と、保存した Σ_t だけから計算する二経路近似の予測 ŝ（two_path。未来の欄を読まない）
   - 個体ごと：評価できる出来事（s_e ≠ ？）での当たりの数、定数ごとの当たりの数、V_i（s_e が 2 種類以上）、Q_i
   - J_S：m ＝ V_i の個体の数、Q_i の数 ≥ k(m)。m ＜ 10 なら判定不能
   - R6：#{V_i かつ Q_i}/m の Clopper–Pearson の区間。**m ＜ 10 なら計算しない（null）**。これは J_S の「判定不能」とは別の欄で、
     区間を出さない理由を書く（ChatGPT の #156 の再レビューの確認事項）
   - 補助（R1〜R9）。smoke は盲検で、確認ごとの ok・fail だけを書く
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0035_as1_state_dependent_feedback/analyze.py                    # 本番（data/experiments/0035）
  python experiments/0035_as1_state_dependent_feedback/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
"""

import argparse
import dataclasses
import gzip
import importlib.util
import json
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from anima_ll.unit.dynamics.activity_dynamics import ActivityState
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0035")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure", "O2", "O3", "O4", "O5", "O6", "O7")
CLASSES = ("+", "0", "-")
REPORT, LOG = "report.json", "analysis_log.jsonl"
# O1 の証拠（run.record_contract_tests が書き、o1_check が確かめる）
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as1_state_dependent_feedback_0035.py")
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


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


# ---- 符号（0034 §2.3）と、二経路近似の予測（README §3） ----------------------------------------------

def first_after(pulses: Iterable[int], t: int, horizon: int) -> int | None:
    later = [p for p in pulses if t < p <= t + horizon]
    return min(later) if later else None


def sign_of(tau_f: int | None, tau_n: int | None) -> str:
    """s_e：打ち切りは値を埋めず、分かる符号だけを使う（0034 §2.3 の表）。"""
    if tau_f is not None and tau_n is not None:
        return "+" if tau_n > tau_f else "-" if tau_n < tau_f else "0"
    if tau_f is not None:
        return "+"
    if tau_n is not None:
        return "-"
    return "?"


def predicted_sign(tau_hat_f: int | None, tau_hat_n: int | None) -> str:
    """ŝ：README §3.1 の表。0034 の表と同じだが、両方なしのときは 0（予測は ？ を出さない）。"""
    s = sign_of(tau_hat_f, tau_hat_n)
    return "0" if s == "?" else s


def difference(tau_f: int | None, tau_n: int | None) -> int | None:
    return tau_n - tau_f if tau_f is not None and tau_n is not None else None


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


def two_path(sigma_t: Mapping, source: str, receiver: str, horizon: int, *, receptor_weight: float = RECEPTOR_WEIGHT,
             direct_only: bool = False) -> tuple[int | None, int | None, str]:
    """二経路近似（README §3.1）。入力は Σ_t と、変わらない定数（Receptor の重み・H）だけ（未来の欄を受け取らない）。

    源と受の 2 つの Unit と、受 → 源 の接続だけを残す。Unit の式は Core の SimpleActivityDynamics.advance（Δt ＝ 1）。
    重みは Σ_t のまま。F では、受に結果の刺激の重みが t ＋ 2 に届く。受の発火は何回でも追い、そのたびに次の Pulse に
    w(受 → 源) を源へ通す。源の最初の発火 τ̂ で止める（t ＋ H までになければ「なし」）。
    direct_only（R3 の (a)）：受の自発の発火を無視し、F の受の t ＋ 2 の発火の駆動だけを源に通す。
    """
    t = int(sigma_t["pulse"])
    w_rs = float(sigma_t["connections"][f"{receiver}.main->{source}"]["weight"])
    drives = [(d[1], float(d[2])) for d in sigma_t["drives"]]          # (受け手, 重み)。Pulse t に作られ、t ＋ 1 に届く
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
            passes = receiver_fired_prev and (not direct_only or (world == "F" and p == t + 3))
            s_s = (in_s if p == t + 1 else 0.0) + (w_rs if passes else 0.0)
            st_r, fired_r = dyn_r.advance(st_r, s_r, 1.0)
            st_s, fired_s = dyn_s.advance(st_s, s_s, 1.0)
            receiver_fired_prev = fired_r is not None
            if fired_s is not None:
                tau = p
                break
        taus[world] = tau
    return taus["F"], taus["N"], predicted_sign(taus["F"], taus["N"])


def past_rhythm(activity: list, intents: list[int], source: str, receiver: str, t: int) -> str:
    """R3 の (b)：過去のリズムだけの目安（外挿を使わない）。過去の発火が足りなければ 0。"""
    r_fires = [p for p, u in activity if u == receiver and p <= t]
    prev_intents = [p for p in intents if p < t]
    if len(r_fires) < 2 or not prev_intents:
        return "0"
    r_hat = r_fires[-1] + (r_fires[-1] - r_fires[-2])
    src_hat = t + (t - prev_intents[-1])
    return "-" if t + 2 < r_hat < src_hat else "0"


def event_quantities(run: Mapping, ev: Mapping) -> dict:
    roles, body, plan = run["roles"], run["body"], run["plan"]
    intents = [p for p, _ in body["intents"]]
    t, h = ev["t"], plan["horizon"]
    tau_f = first_after(intents, t, h)
    tau_n = ev["N"]["tau"]
    hat_f, hat_n, s_hat = two_path(ev["sigma_t"], roles["source"], roles["receiver"], h)
    _, _, s_direct = two_path(ev["sigma_t"], roles["source"], roles["receiver"], h, direct_only=True)
    u_e = min(x for x in (tau_f, tau_n, t + h) if x is not None)        # 打ち切りの側は t ＋ H（README §6 の R4）
    other = roles["other"]
    other_fired = any(u == other and t < p <= u_e for p, u in body["activity"]) or \
        any(u == other and t < p <= u_e for p, u in ev["N"]["firings"])
    return {"t": t, "e_pulse": ev["e"]["pulse"], "tau_F": tau_f, "tau_N": tau_n, "d_e": difference(tau_f, tau_n),
            "s_e": sign_of(tau_f, tau_n), "tau_hat_F": hat_f, "tau_hat_N": hat_n, "s_hat": s_hat,
            "s_direct": s_direct, "s_rhythm": past_rhythm(body["activity"], intents, roles["source"], roles["receiver"], t),
            "u_e": u_e, "other_fired": other_fired}


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def _q_like(correct: int, class_counts: Mapping[str, int]) -> bool:
    """Q_i の形（README §4.1）：評価できる出来事が 1 つ以上あり、当たりの数 ＞ 最良の定数の当たりの数（等しいときは成り立たない）。
    割合ではなく、同じ分母の整数の数で比べる（浮動小数の丸めで同点を取り違えない）。
    評価できる s_e が 1 種類だけなら最良の定数がすべて当たるので、Q_i は V_i のない個体では構造的に成り立たない（監査 031 の天井）。"""
    n_eval = sum(class_counts.values())
    return bool(n_eval and correct > max(class_counts.values()))


def individual(run: Mapping) -> dict:
    """個体ごとの量（README §4.1）と R2・R3 の記録。適用は本体の W の出来事の有無だけで決まる。
    V_i は評価できる s_e のラベルだけで決まり、ŝ を使わない（§4.3）。評価できる出来事が 0 なら、当たりの割合は null（0 ではない）。
    confusion（R2 の 3 × 3）の鍵は「ŝ|s_e」。source_fires_whole_run と birth_units は、沈黙の理由の記録（§6.1）。"""
    events = [event_quantities(run, ev) for ev in run["events"]]
    n = len(events)
    for k, e in enumerate(events):                         # R3 の (c)：同じ個体の中の巡回のずらし（n ＜ 2 は対象外）
        e["s_shift"] = events[(k + n // 2) % n]["s_hat"] if n >= 2 else None
    evaluable = [e for e in events if e["s_e"] != "?"]
    class_counts = {c: sum(1 for e in evaluable if e["s_e"] == c) for c in CLASSES}
    n_eval = len(evaluable)
    v_i = sum(1 for c in CLASSES if class_counts[c] > 0) >= 2
    correct = {name: sum(1 for e in evaluable if e[key] == e["s_e"])
               for name, key in (("rule", "s_hat"), ("direct", "s_direct"), ("rhythm", "s_rhythm"), ("shift", "s_shift"))}
    confusion = {f"{a}|{b}": sum(1 for e in evaluable if e["s_hat"] == a and e["s_e"] == b) for a in CLASSES for b in CLASSES}
    roles = run["roles"]
    return {
        "applicable": n >= 1,
        "roles": dict(roles),
        "birth_units": run["body"]["birth_units"],
        "events_in_window": n,
        "evaluable": n_eval,
        "counts": {"n_plus": class_counts["+"], "n_zero": class_counts["0"], "n_minus": class_counts["-"],
                   "n_unknown": n - n_eval},
        "V_i": v_i,
        "correct_rule": correct["rule"],
        "acc_rule": _rate(correct["rule"], n_eval),
        "acc_plus": _rate(class_counts["+"], n_eval),
        "acc_zero": _rate(class_counts["0"], n_eval),
        "acc_minus": _rate(class_counts["-"], n_eval),
        "acc_const": _rate(max(class_counts.values()), n_eval) if n_eval else None,
        "Q_i": _q_like(correct["rule"], class_counts),
        "confusion": confusion,
        "alternatives": {name: ({"applicable": False, "correct": None, "acc": None, "Q_like": False}
                                if name == "shift" and n < 2 else          # 負の対照は n ＜ 2 の個体では対象外
                                {"applicable": True, "correct": correct[name], "acc": _rate(correct[name], n_eval),
                                 "Q_like": _q_like(correct[name], class_counts)})
                         for name in ("direct", "rhythm", "shift")},
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
    """J_S（README §4.2）と、同じ分母の R6（§6）。R6 は m ＜ 10 なら計算しない（J_S の判定不能とは別の欄）。"""
    j = PROTOCOL["judgment"]["J_S"]
    decision = [s for s, v in individuals.items() if v["applicable"] and v["V_i"]]
    m = len(decision)
    holds = sum(1 for s in decision if individuals[s]["Q_i"])
    if m < j["min_applicable"]:
        out = {"m": m, "count_Q_i": holds, "k": None, "status": "inconclusive"}
        r6 = {"computed": False, "interval": None, "numerator": holds, "denominator": m,
              "reason": f"m = {m} < {j['min_applicable']}: the interval is not computed (separate from the J_S status)"}
        return {"J_S": out, "R6": r6}
    k = j["k_of_m"][m]
    if k != k_of_m(m, j["alpha"]):
        raise ValueError(f"protocol の k({m}) ＝ {k} が二項の計算と違う")
    out = {"m": m, "count_Q_i": holds, "k": k, "tail_probability": binom_upper_tail(m, k),
           "status": "established" if holds >= k else "not_established"}
    r6 = {"computed": True, "interval": list(clopper_pearson(holds, m)), "numerator": holds, "denominator": m}
    return {"J_S": out, "R6": r6}


def auxiliary(individuals: Mapping[str, Mapping], runs: Mapping[int, dict]) -> dict:
    """R3 の要約・R5・R7・R8・R9（判定に使わない）。"""
    evs = [e for v in individuals.values() for e in v["events"] if e["s_e"] != "?"]
    pooled = {f"{a}|{b}": sum(1 for e in evs if e["s_hat"] == a and e["s_e"] == b) for a in CLASSES for b in CLASSES}
    decision = [s for s, v in individuals.items() if v["applicable"] and v["V_i"]]
    alt = {name: sum(1 for s in decision if individuals[s]["alternatives"][name]["Q_like"]) for name in ("direct", "rhythm", "shift")}
    misses = {s: [{"t": e["t"], "s_hat": e["s_hat"], "s_e": e["s_e"], "other_fired": e["other_fired"]}
                  for e in v["events"] if e["s_e"] != "?" and e["s_hat"] != e["s_e"]] for s, v in individuals.items()}

    def split(es):
        quiet = [e for e in es if not e["other_fired"]]
        fired = [e for e in es if e["other_fired"]]
        return {"other_quiet": {"events": len(quiet), "correct": sum(1 for e in quiet if e["s_hat"] == e["s_e"])},
                "other_fired": {"events": len(fired), "correct": sum(1 for e in fired if e["s_hat"] == e["s_e"])}}

    applicable = [s for s, v in individuals.items() if v["applicable"]]
    outside = {s: {"reason": "no_evaluable" if not individuals[s]["evaluable"] else "single_class",
                   "acc_rule": individuals[s]["acc_rule"]} for s in applicable if not individuals[s]["V_i"]}
    beats = sum(1 for s in applicable if individuals[s]["Q_i"])          # acc_rule ＞ acc_const（v0.1 の形。分母は適用できる個体）
    weights = {str(s): {p: {"weights": {c: v["weight"] for c, v in st.items()},
                            "traces": {c: {"pre_trace": v["pre_trace"], "post_trace": v["post_trace"]} for c, v in st.items()},
                            "pair_sums": {"-".join(k): v for k, v in A.pair_sums(st).items()}}
                        for p, st in data["run"]["body"]["checkpoints"].items()}
               for s, data in sorted(runs.items())}
    return {
        "R3_alternative_Q_like_counts": {"over_decision_individuals": len(decision), **alt},
        "R4_misses": {"per_individual": misses,
                      "pooled": {"misses": sum(len(x) for x in misses.values()),
                                 "other_fired": sum(1 for x in misses.values() for y in x if y["other_fired"])}},
        "R5_pooled_confusion": pooled,
        "R7_weights": weights,
        "R8_by_other_unit": {"pooled": split(evs),
                             "per_individual": {s: split([e for e in v["events"] if e["s_e"] != "?"])
                                                for s, v in individuals.items()}},
        "R9": {"applicable": len(applicable), "outside_decision": outside,
               "all_applicable_beats_const": {"count": beats, "denominator": len(applicable),
                                              "fraction": _rate(beats, len(applicable))}},
    }


# ---- 操作の確認（README §7。生の記録から） -------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "body", "clone_check", "events", "rerun"}
BODY_KEYS = {"intents", "sensory", "activity", "realized", "pending_end", "checkpoints", "checkpoint_sigma_sha256", "birth_units"}
EVENT_KEYS = {"t", "intent_delta_id", "e", "sigma_t", "body_pending", "n_pending", "n_branch_sigma_sha256", "N", "N_prime"}
N_KEYS = {"tau", "stopped_at", "sensory", "sigma_stop_sha256", "firings"}
N_PRIME_KEYS = {"tau", "stopped_at", "sensory", "sigma_stop_sha256"}
RERUN_KEYS = {"intents", "sensory", "activity", "sigma_sha256"}


def _expected_sensory(pending_rows: list, t: int, stop: int) -> list[list]:
    return sorted([[row[3], row[2]] for row in pending_rows if t < row[3] <= stop])


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, out["structure"])
        if not out["structure"]:
            _o2(run, out["O2"])
            _o3(run, out["O3"])
            _o4(run, out["O4"])
            _o5(run, out["O5"])
            _o7(run, out["O7"])
        _o6(seed, mode, out["O6"])
    except Exception as e:                                   # 記録の形が壊れているときも、止めずに invalid にする
        out["structure"].append(f"記録を読めない：{e!r}")
    return out


def _structure(data, mode, seed, plan, out) -> None:
    run = data.get("run", {})
    if set(data) != {"meta", "run"}:
        out.append(f"raw の最上位の欄が {sorted(data)}")
    if set(run) != RUN_KEYS:
        out.append(f"run の欄が {sorted(run)}（判定の量の欄を raw に入れない）")
        return
    if set(run["body"]) != BODY_KEYS or set(run["rerun"]) != RERUN_KEYS:
        out.append("body または rerun の欄が違う")
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
    want_blind = {"smoke": True, "formal": False}.get(mode)            # 合成はどちらでもよい（契約テストのため）
    if not isinstance(meta.get("blind"), bool) or (want_blind is not None and meta["blind"] is not want_blind):
        out.append(f"meta の blind が {meta.get('blind')}（smoke は盲検、本番は盲検でない）")
    for ev in run["events"]:
        if set(ev) != EVENT_KEYS or set(ev["N"]) != N_KEYS or set(ev["N_prime"]) != N_PRIME_KEYS:
            out.append(f"出来事 t={ev.get('t')} の欄が違う")
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


def _stop_ok(s: Mapping, t: int, h: int) -> bool:
    stop = s["stopped_at"]
    return t < stop <= t + h and ((s["tau"] is not None and s["tau"] == stop) or (s["tau"] is None and stop == t + h))


def _o4(run, o4) -> None:
    roles, body, plan = run["roles"], run["body"], run["plan"]
    intents = body["intents"]
    h = plan["horizon"]
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
        if len(e_rows) != 1 or ev["n_pending"] != [row for row in ev["body_pending"] if row[0] != e["rid"]]:
            o4.append(f"{where}：N の予約の列が、本体の予約の列から e だけを除いたものではない")
        tau_f = first_after([p for p, _ in intents], t, h)
        stop_body = min(x for x in (tau_f, t + h) if x is not None)
        body_sens = sorted(x for x in body["sensory"] if t < x[0] <= stop_body)
        if body_sens != _expected_sensory(ev["body_pending"], t, stop_body):
            o4.append(f"{where}：本体の感覚の出来事が、分岐の時点の予約から決まる列と違う")
        s = ev["N"]                                            # N′ は O7 の (b) で N と比べる
        if not _stop_ok(s, t, h):
            o4.append(f"{where}：N の止まった Pulse と τ が合わない")
        if sorted(s["sensory"]) != _expected_sensory(ev["n_pending"], t, s["stopped_at"]):
            o4.append(f"{where}：N の感覚の出来事が、分岐の時点の予約から決まる列と違う（CT-Σ5）")
        n_stop = min(x for x in (tau_f, ev["N"]["tau"], t + h) if x is not None)
        n_sens = sorted(x for x in ev["N"]["sensory"] if t < x[0] <= n_stop)
        b_minus_e = sorted(x for x in body["sensory"] if t < x[0] <= n_stop)
        if [e["pulse"], e["receptor"]] in b_minus_e:
            b_minus_e.remove([e["pulse"], e["receptor"]])
        else:
            o4.append(f"{where}：本体に e の感覚の出来事がない")
        if n_sens != b_minus_e:
            o4.append(f"{where}：N の感覚の出来事が、本体から e の 1 つを除いたものではない")


def _o5(run, o5) -> None:
    """(a) Σ_t と分岐の時点の N の Σ（違いは pending から e を除くことと、cancelled に e を足すことだけ）。
    (b) 保存した N の発火から計算し直した τ_N が、記録した τ_N と一致する（監査 028 を N について閉じる）。"""
    roles, plan = run["roles"], run["plan"]
    h = plan["horizon"]
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
        n = ev["N"]
        firings = n["firings"]
        if any(not (t < p <= n["stopped_at"]) for p, _ in firings) or firings != sorted(firings, key=lambda x: x[0]):
            o5.append(f"{where}：N の発火の記録が (t, 止まった Pulse] の外にあるか、順に並んでいない")
        recomputed = first_after([p for p, u in firings if u == roles["source"]], t, h)
        if recomputed != n["tau"]:
            o5.append(f"{where}：保存した N の発火から計算した τ_N が、記録した τ_N と違う")


def _o6(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed {seed} が {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5）")


def _o7(run, o7) -> None:
    """(a) 本体：記録も分岐もしない走り直しと、意図・感覚・発火の列と、チェックポイントと各 t の Σ が一致する。
    (b) 系 N：追加の記録をしない N′ と、τ_N・止まった Pulse・感覚の出来事・止まった Pulse での Σ が一致する。"""
    body, rerun, plan = run["body"], run["rerun"], run["plan"]
    for key in ("intents", "sensory", "activity"):
        if rerun[key] != body[key]:
            o7.append(f"本体の {key} が、記録も分岐もしない走り直しと違う")
    want_pulses = {str(p) for p in plan["checkpoints"]} | {str(ev["t"]) for ev in run["events"]}
    if set(rerun["sigma_sha256"]) != want_pulses or set(body["checkpoint_sigma_sha256"]) != {str(p) for p in plan["checkpoints"]}:
        o7.append("Σ を比べる Pulse の組が、チェックポイントと出来事の t の組と違う")
        return
    for p, sha in body["checkpoint_sigma_sha256"].items():
        if rerun["sigma_sha256"][p] != sha:
            o7.append(f"Pulse {p}：本体の Σ が、走り直しの Σ と違う")
    for ev in run["events"]:
        if rerun["sigma_sha256"][str(ev["t"])] != M.sigma_sha256(ev["sigma_t"]):
            o7.append(f"出来事 t={ev['t']}：保存した Σ_t が、走り直しの同じ Pulse の Σ と違う")
        n, n2 = ev["N"], ev["N_prime"]
        if (n["tau"], n["stopped_at"], n["sensory"], n["sigma_stop_sha256"]) != \
                (n2["tau"], n2["stopped_at"], n2["sensory"], n2["sigma_stop_sha256"]):
            o7.append(f"出来事 t={ev['t']}：系 N と、追加の記録をしない N′ が違う")


# ---- 記録の確認・前提・report ------------------------------------------------------------------

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
    """smoke の盲検の記録の確かめ。確認の名前 → ok・fail。形が違えば structure を fail にする（理由の文は書かない）。
    O6（seed の範囲と、これまでの seed）は、記録に頼らずここで確かめ直す。"""
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


def o1_check(out: Path, commit: str | None) -> list[str]:
    """O1 の証拠：run.py が測定の commit で契約テストを実際に走らせた記録を確かめる。成り立たない理由の列（空なら成り立つ）。"""
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
            if sha != G.sha256_file(REPO / f):
                problems.append(f"{f} の SHA-256 が、測定の commit のものと違う")
    return problems


def analyze_runs(runs: Mapping[int, dict], mode: str, plan: "M.Plan | None" = None, *, o1: list[str]) -> dict:
    """記録（seed → 本番・合成なら生の記録、smoke なら盲検の記録）と O1 の確かめの結果から、report の中身を作る。"""
    o1_status = "fail" if o1 else "ok"
    if mode == "smoke":                                      # 盲検：確認ごとの ok・fail だけ（理由の文・数値は書かない）
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
            "judgment": {"J_S": j["J_S"]}, "R6": j["R6"], "individuals": individuals,
            "auxiliary": auxiliary(individuals, runs)}


# ---- 結果の写し（protocol の records.save と guard の形の対応。0034 と同じ） ---------------------------------

def verify_results_copy(src: Path, dst: Path) -> list[str]:
    """出力先 src と写し dst の照合。成り立たない理由の列（空なら成り立つ）。鍵のファイル（run.lock）は写さない。"""
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
