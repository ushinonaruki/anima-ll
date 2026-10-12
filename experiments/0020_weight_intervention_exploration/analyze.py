"""探索 0020 の記録の解析（探索の設計 v0.2 に従う。判定を置かない）。正本は protocol.yaml。

1. 実行の記録（開始・終了の記録、結果の sha256。guard.py）と、データの完全性（mode・seed・commit）を確かめる（README §5・§7.1）
2. 操作の確認（README §5）を、保存した生の記録から再検証する。分岐の記録は、保存した値を信じず、両腕の全発火の列から
   最初の差を計算し直して照合する。1 つでも満たされなければ invalid とし、記録の量は計算するが「invalid のデータの記録」と明記する
3. 記録（README §4）を、生の記録から個体ごとに全件計算する。holds／fails へは換算しない
4. 要約は個体の数え上げだけ（記述）。都合のよい個体を選ばない（全 100 個体を per_seed に出す）

使い方:
  python experiments/0020_weight_intervention_exploration/analyze.py [data/experiments/0020]
  python experiments/0020_weight_intervention_exploration/analyze.py <フォルダ> --check   # 道具の通しの確認（操作の確認だけ）
"""

import gzip
import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import yaml

from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window

REPO = Path(__file__).resolve().parents[2]
HERE = Path("experiments/0020_weight_intervention_exploration")
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
DEFAULT_DIR = Path("data/experiments/0020")
MODES = ("exploration", "check")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load("alignment_0020", REPO / HERE / "alignment.py")
W = load("world_0020", REPO / HERE / "world.py")
G = load("guard_0020", REPO / HERE / "guard.py")
END = W.experience_end(PROTOCOL)
TOTAL = W.total_pulses(PROTOCOL)
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
SPEC = W.plasticity(PROTOCOL)
FIELDS = ("weight", "pre_trace", "post_trace")


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def sign_relation(a: float, b: float) -> str:
    """2 つの量の符号の関係。0 同士を「向きの一致」に数えない（README §4）。"""
    if a == 0 and b == 0:
        return "both_zero"
    if a == 0 or b == 0:
        return "one_zero"
    return "agree" if (a > 0) == (b > 0) else "disagree"


# ---- 実行の記録・データの完全性 --------------------------------------------------------------------

def completeness(data: dict, mode: str) -> list[str]:
    """mode・experiment・kind・commit・protocol・設計図・seed の完全性（README §5）。空のデータは valid にしない。"""
    problems = []
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    runs = data.get("runs")
    if mode not in MODES:
        problems.append(f"未知の解析の mode（{mode}）")
    if meta.get("experiment") != "0020" or meta.get("kind") != "exploration":
        problems.append("データの experiment・kind が 0020・exploration ではない")
    if meta.get("mode") != mode:
        problems.append(f"データの mode（{meta.get('mode')!r}）が解析の mode（{mode}）と違う（探索と通しの確認を混ぜない）")
    if not G.SHA_RE.match(str(meta.get("git_commit", ""))):
        problems.append(f"データの git_commit が 40 桁の commit ではない（{meta.get('git_commit')!r}）")
    if meta.get("protocol") != PROTOCOL:
        problems.append("データの protocol が今の protocol.yaml と違う")
    if meta.get("manifest") != W.manifest_raw(PROTOCOL):
        problems.append("データの設計図が今の設計図と違う")
    if not isinstance(runs, list) or not runs:
        problems.append("個体が 1 つもない（空のデータは valid にしない）")
        runs = runs if isinstance(runs, list) else []
    got = [r.get("seed") if isinstance(r, dict) else None for r in runs]
    if len(set(got)) != len(got):
        problems.append("seed が重複している")
    if meta.get("seeds") != got:
        problems.append("meta の seed の列と、実データの seed の列が違う")
    if mode == "exploration":
        s = PROTOCOL["seeds"]
        if got != list(range(s["first"], s["last"] + 1)):
            problems.append(f"探索の seed が protocol の 13001〜13100 の全件ではない（{len(got)} 個体）")
    elif mode == "check":
        s = PROTOCOL["synthetic_seeds"]
        if any(not isinstance(x, int) or not s["first"] <= x <= s["last"] for x in got):
            problems.append("通しの確認に合成・確認専用の範囲の外の seed が使われた")
    return problems


def verify_records(records: dict | None, data: dict, mode: str) -> list[str]:
    """開始・終了の記録と結果の sha256 を、データの meta と照合する（README §7.1）。"""
    problems = []
    records = records or {}
    start, fin, sha = records.get("start"), records.get("finish"), records.get("runs_sha256")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    commit, seeds = meta.get("git_commit"), meta.get("seeds")
    if start is None:
        problems.append("開始の記録（run_started.json）がない")
    if fin is None:
        problems.append("終了の記録（run_finished.json）がない")
    if start is None or fin is None:
        return problems
    if fin.get("status") != "completed":
        problems.append(f"終了の記録が completed ではない（{fin.get('status')!r}：{fin.get('reason')}）")
    if start.get("mode") != mode or fin.get("mode") != mode:
        problems.append("開始・終了の記録の mode が解析の mode と違う")
    if not (start.get("git_commit") == fin.get("git_commit_start") == fin.get("git_commit_end") == commit):
        problems.append("開始・終了の記録の commit とデータの commit が一致しない")
    if not (start.get("seeds") == fin.get("seeds") == seeds):
        problems.append("開始・終了の記録の seed の列とデータの seed の列が一致しない")
    if sha is None or fin.get("runs_sha256") != sha:
        problems.append("結果のファイルの sha256 が終了の記録と違う")
    if start.get("protocol_sha256") != G.sha256_file(REPO / PROTOCOL_PATH):
        problems.append("開始の記録の protocol.yaml の sha256 が今のものと違う")
    return problems


# ---- 発火の列・分岐の独立な再検証 -----------------------------------------------------------------

def spikes_at(spikes: list, pulse: int) -> list[str]:
    return sorted(u for p, u in spikes if p == pulse)


def well_formed(spikes: list, start: int, end: int) -> list[str]:
    problems = []
    if any(not (start < p <= end) for p, _ in spikes):
        problems.append(f"発火の列に {start + 1}〜{end} の外の Pulse がある")
    if any(b[0] < a[0] for a, b in zip(spikes, spikes[1:])):
        problems.append("発火の列が Pulse の順に並んでいない")
    if len({(p, u) for p, u in spikes}) != len(spikes):
        problems.append("発火の列に同じ (Pulse, Unit) が重複している")
    return problems


def first_difference(spikes_c: list, spikes_i: list) -> tuple[int, list[str]] | None:
    """両腕の全発火の列から、最初に違う Pulse と、そこで片方だけが発火した Unit を計算する（保存した分岐の記録を使わない）。"""
    by = []
    for sp in (spikes_c, spikes_i):
        d = defaultdict(set)
        for p, u in sp:
            d[p].add(u)
        by.append(d)
    for p in sorted(set(by[0]) | set(by[1])):
        if by[0][p] != by[1][p]:
            return p, sorted(by[0][p] ^ by[1][p])
    return None


def advance_connections(conns0: dict, spikes: list, start: int, end: int) -> dict:
    """start の終わりの接続の状態から、その腕の発火の列で end の終わりまで、本体の 1 Pulse の更新を呼んで進める。"""
    fired = defaultdict(set)
    for p, u in spikes:
        fired[p].add(u)
    out = {}
    for cid, st0 in conns0.items():
        src, dst = W.unit_of(cid)
        st = PlasticState(weight=st0["weight"], pre_trace=st0["pre_trace"], post_trace=st0["post_trace"])
        for p in range(start + 1, end + 1):
            st = balanced_pair_window(st, pre_fired=src in fired[p], post_fired=dst in fired[p], delta_time=DT, spec=SPEC)
        out[cid] = {"weight": st.weight, "pre_trace": st.pre_trace, "post_trace": st.post_trace}
    return out


def check_divergence(arms: dict, fork: dict, start: int, end: int, tol: float) -> list[str]:
    """分岐の記録の独立な再検証（README §5）。全発火の列から最初の差を計算し直し、
    None・Pulse・Unit・t − 1／t の発火のコピー・直前 2 Pulse の接続の状態と fire_count・発火の判定の再構成を照合する。"""
    sp = arms["spikes"]
    problems = []
    for arm in W.ARMS:
        problems += [f"{arm}: {p}" for p in well_formed(sp[arm], start, end)]
    fd = first_difference(sp["control"], sp["intervention"])
    dv = arms.get("divergence")
    if fd is None:
        if dv is not None:
            problems.append("両腕の全発火の列は一度も分かれないのに、分岐の記録がある")
        return problems
    t, units = fd
    if dv is None:
        problems.append(f"両腕の全発火の列は Pulse {t} で分かれるのに、分岐の記録がない")
        return problems
    if dv.get("pulse") != t or sorted(dv.get("units", [])) != units:
        problems.append(f"分岐の記録の Pulse・Unit（{dv.get('pulse')}、{dv.get('units')}）が、全発火の列から求めたもの（{t}、{units}）と違う")
    for arm in W.ARMS:
        for key, p in (("t-1", t - 1), ("t", t)):
            copy = dv["spikes"][key][arm]
            if any(q != p for q, _ in copy) or sorted(u for _, u in copy) != spikes_at(sp[arm], p):
                problems.append(f"{arm}: 分岐の記録の発火のコピー（{key}）が全発火の列と違う")
    before = dv.get("before", {})
    if t - 2 < start or before.get("t-2") is None:
        problems.append(f"分岐の直前 2 Pulse の状態がない（分岐 {t}）")
        return problems
    for arm in W.ARMS:
        for key, p in (("t-2", t - 2), ("t-1", t - 1)):
            rec = advance_connections(fork[arm]["connections"], sp[arm], start, p)
            stored = before[key][arm]["connections"]
            if set(rec) != set(stored) or any(abs(rec[c][f] - stored[c][f]) > tol for c in rec for f in FIELDS):
                problems.append(f"{arm}: 分岐の直前（{key}）の接続の状態が、介入の直後の状態と全発火の列からの再構成と違う")
            for uid, st in before[key][arm]["units"].items():
                expected = fork[arm]["units"][uid]["fire_count"] + sum(1 for q, u in sp[arm] if u == uid and q <= p)
                if st["fire_count"] != expected:
                    problems.append(f"{arm}: 分岐の直前（{key}）の {uid} の fire_count が全発火の列と合わない")
        rec = W.reconstruct_firing(before["t-1"][arm]["units"], before["t-2"][arm]["connections"],
                                   [[t - 1, u] for u in spikes_at(sp[arm], t - 1)], DT)
        if sorted(u for u, r in rec.items() if r["fires"]) != spikes_at(sp[arm], t):
            problems.append(f"{arm}: 分岐の Pulse {t} の発火の判定の再構成が、全発火の列の実際の発火と合わない")
    return problems


# ---- 操作の確認（生の記録から） ------------------------------------------------------------------

def arm_spikes(run: dict, arm: str) -> list[list]:
    return run["arms"]["spikes"][arm]


def affine_all(run: dict, arm: str) -> dict:
    """各腕・各接続の affine の係数（介入の直後の状態から、その腕の自分の発火の列で）。"""
    fork = run["fork"][arm]["connections"]
    spikes = arm_spikes(run, arm)
    out = {}
    for cid, st in fork.items():
        src, dst = W.unit_of(cid)
        out[cid] = W.affine(st, [p for p, u in spikes if u == src], [p for p, u in spikes if u == dst],
                            END, TOTAL, SPEC, DT)
    return out


def check_run(run: dict, tol_replay: float, tol_affine: float) -> list[str]:
    seed, conds, tag = run["seed"], run["conditions"], f"seed {run['seed']}"
    units = run["roles"]["units"]
    problems = [f"{tag}: {p}" for p in W.check_stimulus_counts(
        PROTOCOL, seed, {c: conds[c]["sensory"] for c in W.CONDITIONS})]
    if any(p > END for c in W.CONDITIONS for p, _ in conds[c]["sensory"]):
        problems.append(f"{tag}: 経験の終わりより後に感覚の出来事がある")
    d = W.first_divergence(PROTOCOL, seed)
    if d != run["first_divergence_history"]:
        problems.append(f"{tag}: 札が最初に違う Pulse が刺激の列と合わない")
    o, s = conds["ordered"], conds["shuffled"]
    if o["birth"] != s["birth"]:
        problems.append(f"{tag}: 2 条件の出生時の状態が違う")
    if d is not None and ([a for a in o["activity"] if a[0] < d] != [a for a in s["activity"] if a[0] < d]
                          or o["before_divergence"] != s["before_divergence"]):
        problems.append(f"{tag}: 札が最初に違う Pulse より前の発火・状態が 2 条件で違う")
    for c in W.CONDITIONS:
        err = W.replay_error(PROTOCOL, [a for a in conds[c]["activity"] if a[0] <= END],
                             W.weights(conds[c]["connections_12000"]), END)
        if not err < tol_replay:
            problems.append(f"{tag} {c}: 12000 の再生の計算と記録の重みの差 {err}")
    # control は ordered の本体そのもの：12001 以降の発火が arms の control と一致
    if [a for a in o["activity"] if a[0] > END] != arm_spikes(run, "control"):
        problems.append(f"{tag}: control の発火が ordered の本体の記録と違う")
    if run["arms"]["connections_24000"]["control"] != o["connections_24000"]:
        problems.append(f"{tag}: control の 24000 の接続の状態が ordered の本体と違う")
    # 何も変えない複製が control と一致
    if (run["twin"]["activity"] != arm_spikes(run, "control")
            or run["twin"]["connections_24000"] != run["arms"]["connections_24000"]["control"]):
        problems.append(f"{tag}: clone_identity")
    # 介入：4 本 ＝ shuffled の 12000、それ以外は control と同じ
    fc, fi = run["fork"]["control"], run["fork"]["intervention"]
    ids = W.four_ids(units)
    target_ids = {ids[k] for k in W.TARGETS}
    if fc["units"] != fi["units"] or fc["units"] != o["units_12000"]:
        problems.append(f"{tag}: 介入の直後の Unit の状態が 2 腕で違う")
    if fc["connections"] != o["connections_12000"]:
        problems.append(f"{tag}: control の介入の直後の接続が ordered の 12000 と違う")
    for cid, v in fc["connections"].items():
        e = fi["connections"][cid]
        if e["pre_trace"] != v["pre_trace"] or e["post_trace"] != v["post_trace"]:
            problems.append(f"{tag}: {cid} の痕跡が介入で変わった")
        if cid not in target_ids and e["weight"] != v["weight"]:
            problems.append(f"{tag}: 対象外の {cid} の重みが介入で変わった")
    if any(fi["connections"][ids[k]]["weight"] != s["connections_12000"][ids[k]]["weight"] for k in W.TARGETS):
        problems.append(f"{tag}: 介入腕の 4 本が shuffled の 12000 の値と違う")
    # 12001 の発火は 2 腕で同じ（12001 の駆動は 12000 の冒頭に固定した重みで凍結済み）
    first = END + 1
    if spikes_at(arm_spikes(run, "control"), first) != spikes_at(arm_spikes(run, "intervention"), first):
        problems.append(f"{tag}: 12001 の発火が 2 腕で違う")
    # 各腕の 24000 の重み ＝ その腕の自分の発火の列からの再構成（本体の更新を呼ぶ道筋・affine の両方）
    for arm in W.ARMS:
        conns = run["arms"]["connections_24000"][arm]
        for cid, a in affine_all(run, arm).items():
            w0 = run["fork"][arm]["connections"][cid]["weight"]
            rec = conns[cid]["weight"]
            if not abs(a["w_end"] - rec) < tol_affine or not abs(a["S"] * w0 + a["B"] - rec) < tol_affine:
                problems.append(f"{tag} {arm}: {cid} の 24000 の重みが自分の発火の列からの再構成と合わない")
    # 分岐の記録の独立な再検証
    problems += [f"{tag}: {p}" for p in check_divergence(run["arms"], run["fork"], END, TOTAL, tol_affine)]
    return problems


# ---- 記録（判定に使わない。README §4） ------------------------------------------------------------

def record_run(run: dict) -> dict:
    u = run["roles"]["units"]
    ids = W.four_ids(u)
    W13 = load("world_0013_for_0020", REPO / "experiments/0013_self_amplified_asymmetry/world.py")
    aff = {arm: affine_all(run, arm) for arm in W.ARMS}
    w0 = {arm: W.target_weights(run["fork"][arm]["connections"], u) for arm in W.ARMS}
    wT = {arm: W.target_weights(run["arms"]["connections_24000"][arm], u) for arm in W.ARMS}
    coef = {arm: {k: {f: aff[arm][ids[k]][f] for f in ("S", "log_S", "B", "pot", "dep", "n_factors_lt_1")}
                  for k in ("AB", "AC")} for arm in W.ARMS}
    dS = {k: coef["intervention"][k]["S"] - coef["control"][k]["S"] for k in ("AB", "AC")}
    dB = {k: coef["intervention"][k]["B"] - coef["control"][k]["B"] for k in ("AB", "AC")}

    def M(base: dict) -> dict:
        m = {k: dS[k] * base[k] + dB[k] for k in ("AB", "AC")}   # R(base, s_I) − R(base, s_C)（反実仮想）
        return m | {"W": m["AB"] - m["AC"]}

    M_I, M_C = M(w0["intervention"]), M(w0["control"])
    J = {k: M_I[k] - M_C[k] for k in ("AB", "AC", "W")}
    contrast = lambda w: w["AB"] - w["AC"]
    dW0 = contrast(w0["intervention"]) - contrast(w0["control"])
    dWT = contrast(wT["intervention"]) - contrast(wT["control"])
    spikes = run["arms"]["spikes"]
    counts = {arm: {r: sum(1 for _, x in spikes[arm] if x == u[r]) for r in ("A", "B", "C")} for arm in W.ARMS}
    birth = run["conditions"]["ordered"]["birth"]
    fd = first_difference(spikes["control"], spikes["intervention"])     # 保存した分岐の記録ではなく全列から
    div = None
    if fd is not None:
        t, units_ = fd
        dv = run["arms"]["divergence"]
        div = {"pulse": t, "units": units_, "roles": sorted(r for r in ("A", "B", "C") if u[r] in units_)}
        if dv is not None and dv.get("pulse") == t and dv.get("before", {}).get("t-2") is not None:
            div["reconstruction"] = {arm: W.reconstruct_firing(dv["before"]["t-1"][arm]["units"],
                                                               dv["before"]["t-2"][arm]["connections"],
                                                               [[t - 1, x] for x in spikes_at(spikes[arm], t - 1)], DT)
                                     for arm in W.ARMS}
    s = run["conditions"]["shuffled"]
    nat = lambda c, k: W.w_contrast(W.weights(run["conditions"][c][k]), u)
    return {
        "rho_birth": {r: W13.rho(birth[u[r]]) for r in ("A", "B", "C")},
        "spike_counts_12001_24000": counts,
        "A_silent": {arm: counts[arm]["A"] == 0 for arm in W.ARMS},
        "min_margin": run["arms"]["min_margin"],
        "divergence": div,
        "trains_identical": fd is None,
        "delta_targets_12000": {k: w0["intervention"][k] - w0["control"][k] for k in W.TARGETS},
        "delta_targets_24000": {k: wT["intervention"][k] - wT["control"][k] for k in W.TARGETS},
        "dW0": dW0, "dWT": dWT,
        "sign_dW0_times_dWT": _sign(dW0) * dWT,
        "abs_dWT_minus_abs_dW0": abs(dWT) - abs(dW0),
        "affine": coef,
        "dS": dS, "dB": dB,
        "M_I": M_I, "M_C": M_C, "J": J,
        "M_sign_relation": {k: sign_relation(M_I[k], M_C[k]) for k in ("AB", "AC", "W")},
        "underflow_audit": {arm: {k: coef[arm][k]["S"] == 0.0 and math.isfinite(coef[arm][k]["log_S"])
                                  for k in ("AB", "AC")} for arm in W.ARMS},
        "natural": {"D_12000": nat("ordered", "connections_12000") - nat("shuffled", "connections_12000"),
                    "D_24000": nat("ordered", "connections_24000") - nat("shuffled", "connections_24000"),
                    "A_spikes_shuffled_12001_24000": sum(1 for p, x in s["activity"] if x == u["A"] and p > END)},
    }


def summarize(per: dict) -> dict:
    """数え上げだけ（記述）。holds／fails へ換算しない。"""
    vals = list(per.values())
    rho_lt1 = [v for v in vals if v["rho_birth"]["A"] < 1]
    relation = lambda key: {c: sum(v["M_sign_relation"][key] == c for v in vals)
                            for c in ("agree", "disagree", "one_zero", "both_zero")}
    return {
        "individuals": len(vals),
        "A_silent_control": sum(v["A_silent"]["control"] for v in vals),
        "A_silent_intervention": sum(v["A_silent"]["intervention"] for v in vals),
        "silence_status_differs_between_arms": sum(v["A_silent"]["control"] != v["A_silent"]["intervention"] for v in vals),
        "rho_A_lt_1": len(rho_lt1),
        "rho_A_lt_1_and_A_silent": {arm: sum(v["A_silent"][arm] for v in rho_lt1) for arm in W.ARMS},
        "rho_A_ge_1_and_A_silent": {arm: sum(v["A_silent"][arm] for v in vals if v["rho_birth"]["A"] >= 1)
                                    for arm in W.ARMS},
        "trains_identical": sum(v["trains_identical"] for v in vals),
        "sign_dW0_times_dWT_gt_0": sum(v["sign_dW0_times_dWT"] > 0 for v in vals),
        "abs_dWT_gt_abs_dW0": sum(v["abs_dWT_minus_abs_dW0"] > 0 for v in vals),
        "M_sign_relation_W": relation("W"),
        "M_sign_relation_AB": relation("AB"),
        "M_sign_relation_AC": relation("AC"),
        "underflow_any": sum(any(x for a in v["underflow_audit"].values() for x in a.values()) for v in vals),
    }


def analyze(data: dict, mode: str, records: dict | None) -> dict:
    """mode：exploration（探索）か check（道具の通しの確認）。records：guard.read_records の値（開始・終了の記録と sha256）。"""
    problems = completeness(data, mode) + verify_records(records, data, mode)
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    tol_r, tol_a = PROTOCOL["checks"]["replay_history_12000"], PROTOCOL["checks"]["affine_matches_runtime"]
    for r in runs:
        try:
            problems += check_run(r, tol_r, tol_a)
        except (KeyError, TypeError, ValueError, IndexError) as e:
            problems.append(f"seed {r.get('seed') if isinstance(r, dict) else '?'}: 記録の形が想定と違う（{e!r}）")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    base = {"experiment": "0020", "kind": "exploration", "mode": mode, "git_commit": meta.get("git_commit"),
            "seeds": meta.get("seeds"), "valid": not problems, "problems": problems}
    if mode != "exploration":
        return base | {"note": "道具の通しの確認（操作の確認だけ）。記録の量は計算・表示していない"}
    try:
        per = {str(r["seed"]): record_run(r) for r in runs}
    except (KeyError, TypeError, ValueError, IndexError) as e:
        return base | {"note": f"記録の形が想定と違い、記録の量を計算できなかった（{e!r}）"}
    return base | {"note": "探索（判定なし）。全個体を記録し、holds／fails へ換算しない" +
                           ("" if not problems else "。invalid のデータの記録である"),
                   "summary": summarize(per), "per_seed": per}


def analyze_folder(folder: Path, mode: str) -> dict:
    records = G.read_records(folder)
    if not (folder / G.RUNS).exists():
        return {"experiment": "0020", "kind": "exploration", "mode": mode, "valid": False,
                "problems": ["結果のファイル（runs.json.gz）がない"], "records": records}
    return analyze(read(folder / G.RUNS), mode, records)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "check" if "--check" in sys.argv else "exploration"
    folder = Path(args[0]) if args else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze_folder(folder, mode)
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    if mode == "check":
        print("【道具の通しの確認。記録の量は計算していない】")
    elif "summary" in report:
        print("summary:", json.dumps(report["summary"], ensure_ascii=False))
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
