"""実験 0034 の記録の解析（確定した事前登録 v0.2 に従う。正本は README・protocol.yaml）。

0023〜0033 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検）を引き継ぐ（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
   （違えば何も読まず・書かず、判定の量を計算・表示せずに止まる）
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら、実験全体を invalid として
   記録と操作の確認だけを報告する（判定しない）
2. 操作の確認 O2〜O6（README §7）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、判定の量を
   計算・表示しない。O1（測定の commit で契約テストが通ること）は、解析の道具の HEAD ＝ 測定の commit を確かめたうえで、その commit の
   契約テストの結果（道具の PR・測定の記録）に委ねる（解析はテストを走らせない）
3. 判定（README §2〜§5）：本番・合成で、すべての seed が completed で invalid がないときだけ、出来事ごとの符号 s_e、個体ごとの
   n₊・n₋・n₀・n_?・P_i、適用できる個体の数 m（本体の出来事の有無だけで決まる）、J_A、補助の記録（R2〜R6）を計算して report に書く。
   smoke では判定の量も現象に関する数値（出来事の数・τ・重み）も計算・表示・保存しない（確認の結果 ok・fail と、成り立たなかった確認の
   名前だけを書く）
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0034_as1_feedback_next_intent/analyze.py                    # 本番（data/experiments/0034）
  python experiments/0034_as1_feedback_next_intent/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
"""

import argparse
import dataclasses
import gzip
import importlib.util
import json
import math
import statistics
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0034")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure", "O2", "O3", "O4", "O5", "O6")
SYSTEMS = ("N", "F_CF", "N_CF", "F_FB", "N_FB")
REPORT, LOG = "report.json", "analysis_log.jsonl"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


G = load(f"guard_{EXPERIMENT}_analyze", REPO / HERE / "guard.py")
M = load(f"measure_{EXPERIMENT}_analyze", REPO / HERE / "measure.py")
ALIGN = load(f"alignment_{EXPERIMENT}_analyze", REPO / HERE / "alignment.py")
A = M.A
PLASTIC = sorted(p.connection_id for p in A.parse_neuroarchitecture(A.as1_manifest_raw()).projections if p.plastic)


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


# ---- 出来事ごとの量（README §2.3） --------------------------------------------------------------

def first_after(pulses: Iterable[int], t: int, horizon: int) -> int | None:
    later = [p for p in pulses if t < p <= t + horizon]
    return min(later) if later else None


def sign_of(tau_f: int | None, tau_n: int | None) -> str:
    """打ち切りは値を埋めず、分かる符号だけを使う（README §2.3 の表）。"""
    if tau_f is not None and tau_n is not None:
        d = tau_n - tau_f
        return "+" if d > 0 else "-" if d < 0 else "0"
    if tau_f is not None:
        return "+"
    if tau_n is not None:
        return "-"
    return "?"


def difference(tau_f: int | None, tau_n: int | None) -> int | None:
    return tau_n - tau_f if tau_f is not None and tau_n is not None else None


def event_quantities(run: Mapping, ev: Mapping) -> dict:
    plan = run["plan"]
    intents = [p for p, _ in run["body"]["intents"]]
    t, h = ev["t"], plan["horizon"]
    tau_f = first_after(intents, t, h)
    sy = ev["systems"]
    tau_n = sy["N"]["tau"]
    d_e = difference(tau_f, tau_n)
    d_cf = difference(sy["F_CF"]["tau"], sy["N_CF"]["tau"])
    d_fb = difference(sy["F_FB"]["tau"], sy["N_FB"]["tau"])
    return {"t": t, "e_pulse": ev["e"]["pulse"], "tau_F": tau_f, "tau_N": tau_n, "d_e": d_e, "s_e": sign_of(tau_f, tau_n),
            "tau_F_CF": sy["F_CF"]["tau"], "tau_N_CF": sy["N_CF"]["tau"], "d_CF": d_cf,
            "B": d_e - d_cf if d_e is not None and d_cf is not None else None,
            "tau_F_FB": sy["F_FB"]["tau"], "tau_N_FB": sy["N_FB"]["tau"], "d_FB": d_fb,
            "s_FB": sign_of(sy["F_FB"]["tau"], sy["N_FB"]["tau"])}


def individual(run: Mapping) -> dict:
    """個体ごとの量（README §2.4）。適用できるかどうかは、本体の区間 W の出来事の有無だけで決まる。"""
    events = [event_quantities(run, ev) for ev in run["events"]]
    counts = {k: sum(1 for e in events if e["s_e"] == s) for k, s in
              (("n_plus", "+"), ("n_minus", "-"), ("n_zero", "0"), ("n_unknown", "?"))}
    applicable = len(run["events"]) >= 1
    known = [e["d_e"] for e in events if e["d_e"] is not None]
    source = run["roles"]["source"]
    fires = [p for p, u in run["body"]["activity"] if u == source]
    intervals = [b - a for a, b in zip(fires, fires[1:])]
    return {
        "applicable": applicable,
        **counts,
        "P_i": bool(applicable and counts["n_plus"] > counts["n_minus"]),
        "events_in_window": len(run["events"]),
        "fraction_nonzero": (sum(1 for d in known if d != 0) / len(known)) if known else None,
        "median_d_e": statistics.median(known) if known else None,
        "intervals": ({"count": len(intervals), "min": min(intervals), "median": statistics.median(intervals),
                       "max": max(intervals)} if intervals else None),
        "B": {"known": sum(1 for e in events if e["B"] is not None),
              "nonzero": sum(1 for e in events if e["B"] not in (None, 0))},
        "FB": {"same_sign_as_s_e": sum(1 for e in events if e["s_FB"] == e["s_e"]), "events": len(events)},
        "events": events,
    }


def binom_upper_tail(m: int, k: int) -> float:
    return sum(math.comb(m, j) for j in range(k, m + 1)) / 2 ** m


def k_of_m(m: int, alpha: float) -> int:
    return next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """二項の割合の Clopper–Pearson の区間（補助の記録 R6。判定に使わない）。"""
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
    """J_A（README §4・§5）。m ＜ min_applicable なら判定不能。"""
    j = PROTOCOL["judgment"]["J_A"]
    applicable = [s for s, v in individuals.items() if v["applicable"]]
    m = len(applicable)
    holds = sum(1 for s in applicable if individuals[s]["P_i"])
    if m < j["min_applicable"]:
        return {"m": m, "count_P_i": holds, "k": None, "status": "inconclusive", "clopper_pearson_95": None}
    k = j["k_of_m"][m]
    if k != k_of_m(m, j["alpha"]):
        raise ValueError(f"protocol の k({m}) ＝ {k} が二項の計算と違う")
    return {"m": m, "count_P_i": holds, "k": k, "tail_probability": binom_upper_tail(m, k),
            "status": "established" if holds >= k else "not_established",
            "clopper_pearson_95": list(clopper_pearson(holds, m))}


# ---- 操作の確認（README §7。生の記録から） -------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "body", "clone_check", "events"}
BODY_KEYS = {"intents", "sensory", "activity", "realized", "pending_end", "checkpoints", "birth_units"}
EVENT_KEYS = {"t", "intent_delta_id", "e", "body_pending", "n_pending", "systems"}
SYSTEM_KEYS = {"tau", "stopped_at", "sensory", "interventions", "history", "masked_weights", "weight_changes"}


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
            _o4_o5(run, out["O4"], out["O5"])
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
    if set(run["body"]) != BODY_KEYS:
        out.append(f"body の欄が {sorted(run['body'])}")
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
    for ev in run["events"]:
        if set(ev) != EVENT_KEYS or set(ev["systems"]) != set(SYSTEMS) or any(set(s) != SYSTEM_KEYS for s in ev["systems"].values()):
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


def _o4_o5(run, o4, o5) -> None:
    roles, body, plan = run["roles"], run["body"], run["plan"]
    intents = body["intents"]
    h = plan["horizon"]
    expected_t = [p for p, _ in intents if plan["window_first"] <= p + 1 <= plan["window_last"]]
    if [ev["t"] for ev in run["events"]] != expected_t:
        o4.append("出来事の集まりが、本体の区間 W のすべての結果の予約と違う（A3 の適用の対象）")
    delta_of = {p: d for p, d in intents}
    all_six = PLASTIC
    feedback = f"{roles['receiver']}.main->{roles['source']}"
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
        sy = ev["systems"]
        for name, s in sy.items():
            pending = ev["body_pending"] if name.startswith("F") else ev["n_pending"]
            stop = s["stopped_at"]
            if not (t < stop <= t + h) or (s["tau"] is not None and s["tau"] != stop) or (s["tau"] is None and stop != t + h):
                o4.append(f"{where}：{name} の止まった Pulse と τ が合わない")
            if sorted(s["sensory"]) != _expected_sensory(pending, t, stop):
                o4.append(f"{where}：{name} の感覚の出来事が、分岐の時点の予約から決まる列と違う（CT-Σ5）")
        n_stop = min(x for x in (tau_f, sy["N"]["tau"], t + h) if x is not None)   # min(τ_F, τ_N, t + H)。τ は t より後
        n_sens = sorted(x for x in sy["N"]["sensory"] if t < x[0] <= n_stop)
        b_minus_e = sorted(x for x in body["sensory"] if t < x[0] <= n_stop)
        if [e["pulse"], e["receptor"]] in b_minus_e:
            b_minus_e.remove([e["pulse"], e["receptor"]])
        else:
            o4.append(f"{where}：本体に e の感覚の出来事がない")
        if n_sens != b_minus_e:
            o4.append(f"{where}：N の感覚の出来事が、本体から e の 1 つを除いたものではない")
        # 介入の宣言（一度だけ、Pulse t の境界、解除しない）
        expect = {"N": [], "F_CF": [["FREEZE", all_six, "advance"]], "N_CF": [["FREEZE", all_six, "advance"]],
                  "F_FB": [["FB1", [feedback], "advance"]], "N_FB": [["FB1", [feedback], "advance"]]}
        for name, s in sy.items():
            if s["interventions"]["active"] != expect[name]:
                o5.append(f"{where}：{name} の宣言している介入が違う")
            hist = s["history"]
            if (name == "N" and hist) or (name != "N" and (len(hist) != 1 or hist[0][0] != t)):
                o5.append(f"{where}：{name} の宣言が、Pulse t の境界の一度だけになっていない")
        for name in ("F_CF", "N_CF"):
            wc = sy[name]["weight_changes"]                  # Pulse ごとの末尾の重みの、変わった時点の列（監査 026）
            if not wc or len(wc) != 1 or wc[0][0] != t:
                o5.append(f"{where}：{name} の FREEZE の区間で可塑的な重みが変わった")
            frozen = sy[name]["interventions"]["frozen"]
            if wc and (sorted(frozen) != PLASTIC or any(frozen[c]["weight"] != wc[0][1].get(c) for c in frozen)
                       or any(v.get("policy") != "advance" for v in frozen.values())):
                o5.append(f"{where}：{name} の FREEZE の宣言の時点の基準が、分岐の時点の重みと違う")
        if sy["F_CF"]["weight_changes"] and sy["N_CF"]["weight_changes"] \
                and sy["F_CF"]["weight_changes"][0][1] != sy["N_CF"]["weight_changes"][0][1]:
            o5.append(f"{where}：F_CF と N_CF の分岐の時点の重みが違う")
        for name in ("F_FB", "N_FB"):
            mw = sy[name]["masked_weights"]
            if mw is None or len(mw) != sy[name]["stopped_at"] - t or any(w != 0.0 for w in mw):
                o5.append(f"{where}：{name} で 受 → 源 の伝達に渡す重みが 0 になっていない")


def _o6(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed {seed} が {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5）")


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


def analyze_runs(runs: Mapping[int, dict], mode: str, plan: "M.Plan | None" = None) -> dict:
    """生の記録（seed → raw）から、確認と（本番・合成で、すべて成り立てば）判定の report の中身を作る。"""
    checks = {s: check_seed(data, mode, s, plan) for s, data in sorted(runs.items())}
    failed = {s: {k: v for k, v in c.items() if v} for s, c in checks.items() if any(c.values())}
    if mode == "smoke":                                      # 盲検：確認の ok・fail と、成り立たなかった確認の名前だけ
        return {"mode": "smoke", "checks": {str(s): {k: ("fail" if v else "ok") for k, v in c.items()} for s, c in checks.items()},
                "valid": not failed}
    if failed:
        return {"mode": mode, "valid": False, "failed_checks": {str(s): v for s, v in failed.items()},
                "judgment": None}
    individuals = {str(s): individual(data["run"]) for s, data in sorted(runs.items())}
    weights = {str(s): {p: {"weights": {c: v["weight"] for c, v in st.items()}, "pair_sums": {"-".join(k): v for k, v in
                                                                                             A.pair_sums(st).items()}}
                        for p, st in data["run"]["body"]["checkpoints"].items()}
               for s, data in sorted(runs.items())}
    return {"mode": mode, "valid": True, "judgment": {"J_A": judge(individuals)},
            "individuals": individuals, "R5_weights": weights,
            "O1": "the contract tests at the measurement commit (not re-run by analyze.py)"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", type=Path, default=None)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
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
    if records["state"] == "failed":
        report = {"mode": mode, "valid": False, "record_problems": records["problems"], "judgment": None}
    else:
        report = analyze_runs(runs, mode)
    G.verify_clean_commit(REPO, records["measurement_commit"])
    report["measurement_commit"] = records["measurement_commit"]
    G.write_once(out / REPORT, json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    with open(out / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "complete", "at": G.now_iso(), "inputs": shas}) + "\n")
    print(f"report: {out / REPORT}")


if __name__ == "__main__":
    main()
