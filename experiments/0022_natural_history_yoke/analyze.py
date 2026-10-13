"""実験 0022 の記録の解析（確定した事前登録 v0.2 に従う。判定なし）。正本は protocol.yaml・README。

1. 実行の記録（開始・終了の記録、結果の sha256。guard.py）と、データの完全性（experiment・kind・mode・seed・commit）を確かめる
2. 操作の確認（README §6、protocol の checks）を、保存した生の記録から個体ごとに再検証する。確認の名前ごとに、
   成り立たなかった理由を個体ごとに残す。1 つでも成り立たなければその個体は invalid。結果の都合で個体を除かない
3. 観測（README §5、protocol の observations）を、生の記録から個体ごとに全件計算する。t_OS・t_YO・t_YS と U は、
   保存した分岐の記録ではなく全発火の列から計算し直す。欠測は null、実際の 0 は 0（observations.missing_values）。
   観測の量は本番（formal）の解析でだけ計算する。通しの確認（check）では操作の確認だけを出す
4. 要約は数え上げと分布の記述だけ。集団の holds／fails・合格の基準・方向の予想・増幅率・区間・まとめた得点は置かない

分岐の Pulse の activity の再構成（numeric.divergence_activity_reconstruction）：分岐の Pulse t の判定の直前の activity を、
t − 1 の状態・t − 2 の重み・t − 1 の発火から独立に再構成し（world.reconstruct_firing）、監査の生記録（world.AuditedDynamics が
記録した、Runtime が実際に Unit に渡した入力からの判定の直前の値）と照合する。t − 3 ＝ t0 − 1 のときの重みは、その腕の基準の
個体（O は ordered、S は shuffled）の記録した発火から出生時の状態を本体の更新で進めて求める。

使い方:
  python experiments/0022_natural_history_yoke/analyze.py                     # 本番（protocol の execution.output_dir を解析し、report はそこにだけ書く）
  python experiments/0022_natural_history_yoke/analyze.py <フォルダ> --check   # 道具の通しの確認（操作の確認だけ。data/experiments の下には書かない）
report は既にあれば上書きしない。書いてはいけない場所を指定したときは、解析の前に、何も読まず・書かずに止まる（report_destination）。
"""

import contextlib
import gzip
import importlib.util
import itertools
import json
import math
import os
import statistics
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
DEFAULT_DIR = Path(PROTOCOL["execution"]["output_dir"])
DATA_ROOT = REPO / "data" / "experiments"          # 本番・他の実験のデータの場所（通しの確認の report は書かない）
OWN_DIR = REPO / DEFAULT_DIR                       # 本番の report を書いてよい唯一の場所
REPORT = "report.json"
SERIES = "differences_series.json.gz"           # 接続ごとの重みの差・痕跡の差の標本ごとの値（本番だけ。report の隣）
MODES = ("formal", "check")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load(f"alignment_{EXPERIMENT}", REPO / HERE / "alignment.py")
W = load(f"world_{EXPERIMENT}", REPO / HERE / "world.py")
G = load(f"guard_{EXPERIMENT}", REPO / HERE / "guard.py")
END = W.experience_end(PROTOCOL)
TOTAL = W.total_pulses(PROTOCOL)
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
SPEC = W.plasticity(PROTOCOL)
KAPPA = math.exp(-DT / SPEC.trace_tau_seconds)      # 痕跡の 1 Pulse の減り方（本体の balanced_pair_window と同じ式）
RATIO = SPEC.amplitude / SPEC.w_max
TOL = PROTOCOL["checks"]["numeric"]
FIELDS = ("weight", "pre_trace", "post_trace")
TRACES = ("pre_trace", "post_trace")
CHECK_NAMES = (list(PROTOCOL["checks"]["inherited"]) + list(PROTOCOL["checks"]["exact"])
               + list(PROTOCOL["checks"]["numeric"]) + ["revalidate_from_raw"])
CONNECTIONS = {"AB": ("A", "B"), "AC": ("A", "C"), "BA": ("B", "A"), "CA": ("C", "A"), "BC": ("B", "C"), "CB": ("C", "B")}
# 主の観測の組の名前（README §5.1）と、分岐の記録の鍵
PAIR_KEY = {"YO": "t_YO", "YS": "t_YS"}


def read(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- 発火の列 ------------------------------------------------------------------------------------

def spikes_at(spikes: list, pulse: int) -> list[str]:
    return sorted(u for p, u in spikes if p == pulse)


def well_formed(spikes: list, start: int, end: int) -> list[str]:
    problems = []
    if any(not (start < p <= end) for p, _ in spikes):
        problems.append(f"発火の列に {start + 1}〜{end} の外の Pulse がある")
    if any(b[0] < a[0] for a, b in itertools.pairwise(spikes)):
        problems.append("発火の列が Pulse の順に並んでいない")
    if len({(p, u) for p, u in spikes}) != len(spikes):
        problems.append("発火の列に同じ (Pulse, Unit) が重複している")
    return problems


def first_difference(a: list, b: list) -> tuple[int, list[str]] | None:
    """2 つの腕の全発火の列から、発火の集合が最初に違う Pulse と、その対称差の Unit を計算する（保存した分岐の記録を使わない）。"""
    fa, fb = W.fired_by_pulse(a), W.fired_by_pulse(b)
    for p in sorted(set(fa) | set(fb)):
        if fa.get(p, set()) != fb.get(p, set()):
            return p, sorted(fa.get(p, set()) ^ fb.get(p, set()))
    return None


def differing(a: list, b: list) -> list[int]:
    fa, fb = W.fired_by_pulse(a), W.fired_by_pulse(b)
    return sorted(p for p in set(fa) | set(fb) if fa.get(p, set()) != fb.get(p, set()))


def spikes_before(run: dict, arm: str, t: int, start: int) -> list[str]:
    """Pulse t の腕の発火。t ＝ start（t0）の発火は W の列に入らないので、基準の個体の経験の記録から読む（合成の記録では空）。"""
    if t > start:
        return spikes_at(run["arms"]["spikes"][arm], t)
    conds = run.get("conditions")
    if t == start and conds:
        return spikes_at(conds[W.NATURAL[W.BASE[arm]]]["activity"], t)
    return []


def plasticity_spikes(run: dict, arm: str) -> list:
    """可塑性の更新に使った発火の列（O・S・twin は自分、yoke の腕は相手の自然な個体。README §2）。"""
    sp = run["arms"]["spikes"]
    return sp[W.SOURCE[arm]] if arm in W.SOURCE else sp[arm]


def replay_arm(run: dict, arm: str, record: Iterable[int] = (), start: int = END, end: int = TOTAL) -> dict:
    """腕の接続の状態を、t0（start）の状態から、可塑性の更新に使った列で end まで再生する（命題 4.8）。"""
    fired = W.fired_by_pulse(plasticity_spikes(run, arm))
    record = list(record)
    return {cid: W.replay(st, cid, fired, start, end, SPEC, DT, record)
            for cid, st in run["fork"][arm]["connections"].items()}


def sample_times(run: dict) -> list[int]:
    return sorted(int(t) for t in run["arms"]["samples"]["O"])


def _weights(conns: Mapping[str, Mapping]) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in conns.items()}


def _states_equal(a: Mapping, b: Mapping) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _state_at(run: dict, arm: str, t: int, end: int) -> Mapping:
    return run["endpoints"][arm] if t == end else run["arms"]["samples"][arm][str(t)]


# ---- 実行の記録・データの完全性 --------------------------------------------------------------------

def completeness(data: dict, mode: str) -> list[str]:
    problems = []
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    runs = data.get("runs")
    if mode not in MODES:
        problems.append(f"未知の解析の mode（{mode}）")
    if meta.get("experiment") != EXPERIMENT or meta.get("kind") != KIND:
        problems.append(f"データの experiment・kind が {EXPERIMENT}・{KIND} ではない")
    if meta.get("mode") != mode:
        problems.append(f"データの mode（{meta.get('mode')!r}）が解析の mode（{mode}）と違う（本番と通しの確認を混ぜない）")
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
    if mode == "formal":
        s = PROTOCOL["seeds"]
        if got != list(range(s["first"], s["last"] + 1)):
            problems.append(f"本番の seed が protocol の {s['first']}〜{s['last']} の全件ではない（{len(got)} 個体）")
    elif mode == "check":
        s = PROTOCOL["synthetic_seeds"]
        if any(not isinstance(x, int) or not s["first"] <= x <= s["last"] for x in got):
            problems.append("通しの確認に合成・確認専用の範囲の外の seed が使われた")
    return problems


def verify_records(records: dict | None, data: dict, mode: str) -> list[str]:
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
    if any(r.get("experiment") != EXPERIMENT or r.get("kind") != KIND for r in (start, fin)):
        problems.append(f"開始・終了の記録の experiment・kind が {EXPERIMENT}・{KIND} ではない")
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


# ---- 分岐の記録の再検証と再構成 -------------------------------------------------------------------

def check_divergence(run: dict, key: str, arms: tuple[str, ...], decide: tuple[str, ...], fd,
                     before_start: Mapping[str, Mapping[str, float]], start: int = END, end: int = TOTAL) -> dict[str, list]:
    """分岐の記録（key ＝ t_OS・t_YO・t_YS）を全発火の列から独立に再検証し、decide の腕の判定・activity を再構成する。
    before_start：基準の個体（O・S）ごとの、t0 − 1 の終わりの重み（t0 ＋ 1 に届く駆動の重み）。"""
    out = {"revalidate_from_raw": [], "divergence_decisions_reconstructed": [], "divergence_activity_reconstruction": []}
    rec, sp = run["arms"][key], run["arms"]["spikes"]
    if fd is None:
        if rec is not None:
            out["revalidate_from_raw"].append(f"{key}：全発火の列では違いがないのに、分岐の記録がある")
        return out
    t, units = fd
    if rec is None:
        out["revalidate_from_raw"].append(f"{key}：全発火の列は Pulse {t} で違うのに、分岐の記録がない")
        return out
    if rec.get("pulse") != t or sorted(rec.get("units", [])) != units:
        out["revalidate_from_raw"].append(
            f"{key}：分岐の記録の Pulse・Unit（{rec.get('pulse')}、{rec.get('units')}）が全発火の列（{t}、{units}）と違う")
    if list(rec.get("arms", [])) != list(arms):
        out["revalidate_from_raw"].append(f"{key}：分岐の記録の腕（{rec.get('arms')}）が {list(arms)} ではない")
    before = rec.get("before") or {}
    for arm in arms:
        for k, p in (("t-1", t - 1), ("t", t)):
            copy_ = rec["spikes"][k][arm]
            if any(q != p for q, _ in copy_) or sorted(u for _, u in copy_) != spikes_at(sp[arm], p):
                out["revalidate_from_raw"].append(f"{key} {arm}：分岐の記録の発火のコピー（{k}）が全発火の列と違う")
    tol = TOL["plasticity_replay_W"]
    reps = {}
    for arm in arms:
        # 直前 2 Pulse の終わりの状態（t − 2 が t0 より前なら t − 1 だけ）を、t0 の状態と可塑性の列からの再生と照合する
        keys = [("t-1", t - 1)] + ([("t-2", t - 2)] if t - 2 >= start and before.get("t-2") is not None else [])
        record = [p for _, p in keys] + ([t - 3] if t - 3 >= start else [])
        reps[arm] = rep = replay_arm(run, arm, record, start, end)
        for k, p in keys:
            stored = before[k][arm]["connections"]
            if set(stored) != set(rep) or any(abs(rep[c]["at"][p][f] - stored[c][f]) > tol for c in rep for f in FIELDS):
                out["revalidate_from_raw"].append(f"{key} {arm}：分岐の直前（{k}）の接続の状態が、t0 の状態と可塑性の列からの再生と違う")
            for uid, st in before[k][arm]["units"].items():
                expected = run["fork"][arm]["units"][uid]["fire_count"] + sum(1 for q, x in sp[arm] if x == uid and q <= p)
                if st["fire_count"] != expected:
                    out["revalidate_from_raw"].append(f"{key} {arm}：分岐の直前（{k}）の {uid} の fire_count が全発火の列と合わない")
    # t ＝ t0 ＋ 1（直前 2 Pulse の 1 つ目が t0 より前）：t − 1 ＝ t0 の状態は複製の記録、t − 2 の重みは出生時からの再生
    if (t - 2 < start or before.get("t-2") is None) and t != start + 1:
        out["revalidate_from_raw"].append(f"{key}：分岐の直前 2 Pulse の状態がない（分岐 {t}）")
        return out
    for arm in decide:
        base = W.BASE[arm]
        if t == start + 1:
            units_tm1, w_tm2 = run["fork"][arm]["units"], dict(before_start[base])
        else:
            units_tm1, w_tm2 = before["t-1"][arm]["units"], _weights(before["t-2"][arm]["connections"])
        dec = W.reconstruct_firing(units_tm1, w_tm2, [[t - 1, x] for x in spikes_before(run, arm, t - 1, start)], DT)
        if sorted(x for x, r in dec.items() if r["fires"]) != spikes_at(sp[arm], t):
            out["divergence_decisions_reconstructed"].append(f"{key} {arm}：Pulse {t} の発火の判定の再構成が実際の発火と合わない")
        audit = (rec.get("audit") or {}).get(arm)
        if not isinstance(audit, dict) or set(audit) != set(dec):
            out["divergence_activity_reconstruction"].append(f"{key} {arm}：Pulse {t} の判定の直前の activity の監査の記録がない・Unit がそろっていない")
            continue
        fired_t = set(spikes_at(sp[arm], t))
        for uid, r in dec.items():
            a = audit[uid]
            if not abs(r["activity_pre"] - a["activity_pre"]) < TOL["divergence_activity_reconstruction"]:
                out["divergence_activity_reconstruction"].append(
                    f"{key} {arm}：Pulse {t} の {uid} の判定の直前の activity の再構成（{r['activity_pre']}）が実際の値（{a['activity_pre']}）と合わない")
            st = units_tm1[uid]
            if (a["pulse"] != t or a["activity_in"] != st["activity"] or a["adaptation_in"] != st["adaptation"]
                    or a["delta_time"] != DT or a["fired"] != (uid in fired_t) or a["probe_fired"]
                    or (a["fired"] and a["activity_out"] != 0.0)
                    or (not a["fired"] and a["activity_out"] != a["activity_pre"])):
                out["revalidate_from_raw"].append(f"{key} {arm}：Pulse {t} の {uid} の監査の記録が、保存した状態・発火と整合しない")
            if not abs(sum(r["drive"].values()) - a["stimulus"]) < TOL["divergence_activity_reconstruction"]:
                out["revalidate_from_raw"].append(f"{key} {arm}：Pulse {t} の {uid} の刺激の再構成が監査の記録と合わない")
        # 補助の監査（契約の確認ではない）：同じ再構成の式を t − 1 でも、保存した t − 1 の状態と照合する
        if t - 2 >= start and before.get("t-2") is not None:
            w3 = (dict(before_start[base]) if t - 3 == start - 1
                  else {c: reps[arm][c]["at"][t - 3]["weight"] for c in reps[arm]})
            prev = W.reconstruct_firing(before["t-2"][arm]["units"], w3,
                                        [[t - 2, x] for x in spikes_before(run, arm, t - 2, start)], DT)
            fired_tm1 = set(spikes_before(run, arm, t - 1, start))
            for uid, r in prev.items():
                got = before["t-1"][arm]["units"][uid]["activity"]
                if (r["fires"] != (uid in fired_tm1) or (uid in fired_tm1 and got != 0.0)
                        or (uid not in fired_tm1 and not abs(r["activity_pre"] - got) < TOL["divergence_activity_reconstruction"])):
                    out["revalidate_from_raw"].append(f"{key} {arm}：補助の監査：Pulse {t - 1} の {uid} の再構成が保存した t − 1 の状態と合わない")
    return out


def contributions(j: str, t: int, t_low: int, common: list, diff_at: Callable[[int], Mapping[str, float]],
                  decay: float, start: int) -> dict[str, float]:
    """K_ij(t) ＝ Σ_{k = max(r_j + 1, t_low)}^{t} λ^(t − k)·Δw_ij(k − 2)·s_i(k − 1)（README §3.2）。送り手ごと。
    common：t − 1 まで共通の発火の列。diff_at(m)：Pulse m の終わりの重みの差 {接続: Δw}。r_j：t より前に j が最後に発火した Pulse。"""
    fired = W.fired_by_pulse(common)
    r = max([p for p, us in fired.items() if j in us and p < t], default=start)
    out: dict[str, float] = {}
    for k in range(max(r + 1, t_low), t + 1):
        diff = diff_at(k - 2)
        for cid, dw in diff.items():
            src, dst = W.unit_of(cid)
            if dst == j:
                out[src] = out.get(src, 0.0) + decay ** (t - k) * dw * (src in fired.get(k - 1, ()))
    return out


def _diff_series(run: dict, a: str, b: str, lo: int, hi: int, start: int = END, end: int = TOTAL) -> Callable[[int], dict[str, float]]:
    """Pulse lo〜hi の終わりの、腕 a と腕 b の重みの差（a − b）。可塑性の列で t0 の状態から再生する。"""
    times = list(range(max(lo, start), hi + 1))
    ra, rb = replay_arm(run, a, times, start, end), replay_arm(run, b, times, start, end)
    table = {m: {cid: ra[cid]["at"][m]["weight"] - rb[cid]["at"][m]["weight"] for cid in ra} for m in times}
    return lambda m: table[m]


def first_difference_contributions(run: dict, pair: str, fd_os, fd_y, start: int = END, end: int = TOTAL) -> dict | None:
    """最初の違い（t_YO か t_YS）の差の接続ごとの寄与（j ∈ U、Δw ＝ w^基準 − w^yoke、下限 t_OS ＋ 2）と、
    判定の直前の activity の実際の差（ã^基準 − ã^yoke。監査の生記録）。該当がなければ None。"""
    if fd_y is None or fd_os is None:
        return None
    base, yoke = W.PAIRS[pair]
    (t_os, _), (t, units) = fd_os, fd_y
    rec = run["arms"][PAIR_KEY[pair]] or {}
    diff = _diff_series(run, base, yoke, t_os, t - 2, start, end)
    audit = rec.get("audit") or {}
    out = {}
    for j in units:
        decay = run["fork"][base]["units"][j]["dynamics"]["decay_per_second"] ** DT
        k = contributions(j, t, t_os + 2, run["arms"]["spikes"][base], diff, decay, start)
        out[j] = {"K": k, "sum": sum(k.values()),
                  "activity_difference": (audit[base][j]["activity_pre"] - audit[yoke][j]["activity_pre"]   # 実際の値（監査の生記録）
                                          if j in audit.get(base, {}) and j in audit.get(yoke, {}) else None)}
    return out


# ---- 操作の確認（生の記録から。README §6） ------------------------------------------------------------

def before_start_weights(run: dict) -> dict[str, dict[str, float]]:
    """基準の個体ごとの t0 − 1 の終わりの重み（記録した経験の発火から、出生時の状態を本体の更新で進める）。"""
    return {nat: W.birth_replay_weights(PROTOCOL, run["conditions"][cond]["activity"], END - 1)
            for nat, cond in W.NATURAL.items()}


def check_run(run: dict, before_start: Mapping[str, Mapping[str, float]] | None = None) -> dict[str, list[str]]:
    """個体の操作の確認。{確認の名前: 成り立たなかった理由の一覧}。before_start：基準の個体ごとの t0 − 1 の重み（省略すると記録から求める）。"""
    out: dict[str, list[str]] = {k: [] for k in CHECK_NAMES}
    if before_start is None:
        before_start = before_start_weights(run)
    check_conditions(run, out)
    check_arms(run, out, END, TOTAL, before_start)
    return out


def check_conditions(run: dict, out: dict[str, list[str]]) -> None:
    """経験の 2 条件の確認（継承した確認）と、自然な 2 個体の t0 の状態が経験の終わりの記録と同じであること。"""
    seed, conds = run["seed"], run["conditions"]
    out["stimulus_counts"] += W.check_stimulus_counts(PROTOCOL, seed, {c: conds[c]["sensory"] for c in W.CONDITIONS})
    if any(p > END for c in W.CONDITIONS for p, _ in conds[c]["sensory"]):
        out["input_free_after_experience"].append("経験の終わりより後に感覚の出来事がある（条件の記録）")
    d = W.first_divergence(PROTOCOL, seed)
    o, s = conds["ordered"], conds["shuffled"]
    if d != run["first_divergence_history"]:
        out["identical_before_label_divergence"].append("札が最初に違う Pulse が刺激の列と合わない")
    if o["birth"] != s["birth"]:
        out["identical_before_label_divergence"].append("2 条件の出生時の状態が違う")
    if d is not None and ([a for a in o["activity"] if a[0] < d] != [a for a in s["activity"] if a[0] < d]
                          or o["before_divergence"] != s["before_divergence"]):
        out["identical_before_label_divergence"].append("札が最初に違う Pulse より前の発火・状態が 2 条件で違う")
    if any(a[0] > END for c in W.CONDITIONS for a in conds[c]["activity"]):
        out["revalidate_from_raw"].append("条件の発火の記録に経験の終わりより後の Pulse がある")
    for c in W.CONDITIONS:
        err = W.replay_error(PROTOCOL, conds[c]["activity"], W.weights(conds[c]["connections_12000"]), END)
        if not err < TOL["replay_history_12000"]:
            out["replay_history_12000"].append(f"{c}：12000 の再生と記録の重みの差 {err}")
    for nat, cond in W.NATURAL.items():
        f = run["fork"][nat]
        if not _states_equal(f["connections"], conds[cond]["connections_12000"]) or not _states_equal(f["units"], conds[cond]["units_12000"]):
            out["fork_is_clone"].append(f"{nat} の t0 の状態が {cond} の経験の終わりの記録と違う")


def check_arms(run: dict, out: dict[str, list[str]], start: int, end: int,
               before_start: Mapping[str, Mapping[str, float]]) -> None:
    """8 つの腕の確認（README §6）。start ＝ t0、end ＝ T。契約テストは合成の短い窓でも同じ関数を呼ぶ。"""
    sp, samples, fork, ends = run["arms"]["spikes"], run["arms"]["samples"], run["fork"], run["endpoints"]
    inflight = run["fork_in_flight"]
    for arm in W.ARMS:
        out["revalidate_from_raw"] += [f"{arm}：{p}" for p in well_formed(sp[arm], start, end)]
    if sorted(samples) != sorted(W.ARMS) or any(sorted(samples[a]) != sorted(samples["O"]) for a in W.ARMS):
        out["revalidate_from_raw"].append("標本の腕・時刻がそろっていない")
    times = sample_times(run)
    if not times or times[0] != start or times[-1] != end:
        out["revalidate_from_raw"].append("標本の時刻が t0 と T を含まない")
    if any(run["arms"]["sensory"][a] for a in W.ARMS):
        out["input_free_after_experience"].append("W の間に感覚の出来事がある腕がある")
    for arm in W.ARMS:
        if not _states_equal(samples[arm][str(start)], fork[arm]):
            out["revalidate_from_raw"].append(f"{arm}：t0 の標本が複製の記録と違う")

    # ---- 複製の確認：t0 の全状態（Unit の状態・接続の状態・次の Pulse に届く駆動）が基準と同じ ----
    for arm in W.ARMS:
        base = W.BASE[arm]
        if arm != base and (not _states_equal(fork[arm], fork[base]) or not _states_equal(inflight[arm], inflight[base])):
            out["fork_is_clone"].append(f"{arm} の t0 の全状態が {base} と違う")

    # ---- 厳密に一致すべきもの：twin・自己 yoke ＝ 基準 ----
    for arm, base, name in (("twin_O", "O", "twin_O_equals_O"), ("twin_S", "S", "twin_S_equals_S"),
                            ("Y_O_from_O", "O", "self_yoke_O_equals_O"), ("Y_S_from_S", "S", "self_yoke_S_equals_S")):
        if sp[arm] != sp[base]:
            out[name].append(f"{arm} の発火が {base} と違う")
        if any(not _states_equal(samples[arm][str(t)], samples[base][str(t)]) for t in times):
            out[name].append(f"{arm} の標本の状態が {base} と違う")
        if not _states_equal(ends[arm], ends[base]):
            out[name].append(f"{arm} の T の状態が {base} と違う")

    # ---- yoke の腕 ＝ 基準（t_OS ＋ 1 まで）と、t_YO・t_YS の下限 ----
    fd_os = first_difference(sp["O"], sp["S"])
    t_os = fd_os[0] if fd_os else None
    fds = {pair: first_difference(sp[b], sp[y]) for pair, (b, y) in W.PAIRS.items()}
    for pair, (base, yoke) in W.PAIRS.items():
        name = "yoke_equals_base_until_t_OS_plus_1"
        if t_os is None:
            if sp[base] != sp[yoke]:
                out[name].append(f"t_OS がないのに、{yoke} の発火が {base} と違う")
            if any(not _states_equal(samples[yoke][str(t)], samples[base][str(t)]) for t in times):
                out[name].append(f"t_OS がないのに、{yoke} の標本の状態が {base} と違う")
            if not _states_equal(ends[yoke], ends[base]):
                out[name].append(f"t_OS がないのに、{yoke} の T の状態が {base} と違う")
        else:
            lim = min(t_os + 1, end)
            if [x for x in sp[base] if x[0] <= lim] != [x for x in sp[yoke] if x[0] <= lim]:
                out[name].append(f"{yoke} と {base} の発火が {lim} までに違う")
            for t in times:
                if t <= t_os + 1 and not _states_equal(samples[yoke][str(t)]["units"], samples[base][str(t)]["units"]):
                    out[name].append(f"{yoke} と {base} の Unit の状態が標本 {t} で違う")
                if t <= t_os - 1 and not _states_equal(samples[yoke][str(t)]["connections"], samples[base][str(t)]["connections"]):
                    out[name].append(f"{yoke} と {base} の接続の状態が標本 {t} で違う")
            rec = run["arms"]["t_OS"]
            if rec is not None and rec.get("pulse") == t_os:
                tm1 = rec["before"]["t-1"]
                if not _states_equal(tm1[yoke]["connections"], tm1[base]["connections"]):
                    out[name].append(f"{yoke} と {base} の接続の状態が {t_os - 1} で違う")
                after = rec.get("after") or {}
                for k in ("t", "t+1"):
                    st = after.get(k)
                    if st is not None and not _states_equal(st[yoke]["units"], st[base]["units"]):
                        out[name].append(f"{yoke} と {base} の Unit の状態が {k}（t_OS ＝ {t_os}）で違う")
        fd = fds[pair]
        if fd is not None and (t_os is None or fd[0] < t_os + 2):
            out["t_Y_at_least_t_OS_plus_2"].append(f"{PAIR_KEY[pair]}（{fd[0]}）が t_OS（{t_os}）＋ 2 より前、または t_OS がない")

    # ---- 再生・数値 ----
    check_at = sorted(set(times) | {end})
    for arm in W.ARMS:
        rep = replay_arm(run, arm, check_at, start, end)
        for cid, r in rep.items():
            if r["clipped"]:
                out["no_clipping"].append(f"{arm}：{cid} の更新で切り詰めが働いた（Pulse {r['clipped'][:3]}…）")
            w0 = fork[arm]["connections"][cid]["weight"]
            for t in check_at:
                stored = _state_at(run, arm, t, end)["connections"][cid]
                if any(not abs(r["at"][t][f] - stored[f]) < TOL["plasticity_replay_W"] for f in FIELDS):
                    out["plasticity_replay_W"].append(f"{arm} {t}：{cid} の状態が t0 の状態と可塑性の列からの再生と合わない")
            if not abs(r["S"] * w0 + r["B"] - ends[arm]["connections"][cid]["weight"]) < TOL["plasticity_replay_W"]:
                out["plasticity_replay_W"].append(f"{arm}：{cid} の T の重みが affine の係数からの値と合わない")
    for arm in W.ARMS:
        for t in check_at:
            state = _state_at(run, arm, t, end)
            for cid, v in state["connections"].items():
                if not 0.0 <= v["weight"] <= SPEC.w_max:
                    out["no_clipping"].append(f"{arm} {t}：{cid} の重みが [0, w_max] の外")
                src, dst = W.unit_of(cid)
                back = state["connections"][W.connection_id(dst, src)]["weight"]
                if not abs(v["weight"] + back - SPEC.w_max) < TOL["pair_sum"]:
                    out["pair_sum"].append(f"{arm} {t}：{cid} の組の和が w_max と違う")
    # 痕跡の差の減り方（命題 4.1）：yoke の腕と、同じ可塑性の入力を受ける相手の自然な個体
    for yoke in ("Y_O_from_S", "Y_S_from_O"):
        partner, base = W.SOURCE[yoke], W.BASE[yoke]
        for t in check_at:
            sy, sp_ = _state_at(run, yoke, t, end)["connections"], _state_at(run, partner, t, end)["connections"]
            for cid in sy:
                for f in TRACES:
                    expected = KAPPA ** (t - start) * (fork[base]["connections"][cid][f] - fork[partner]["connections"][cid][f])
                    if not abs((sy[cid][f] - sp_[cid][f]) - expected) < TOL["trace_difference_decay"]:
                        out["trace_difference_decay"].append(f"{yoke} − {partner} {t}：{cid} の {f} の差が κ^(t−t0)·ΔX と合わない")
    # P の恒等式（命題 4.3）：P ＝ w^A − w^B ＝ Φ^B·δω ＋ T^B（A ＝ yoke の腕、B ＝ 同じ可塑性の入力を受ける相手の自然な個体）
    for yoke in ("Y_O_from_S", "Y_S_from_O"):
        for problem in p_identity(run, yoke, start, end, check_at):
            out["P_identity"].append(problem)
    # 分岐の記録の再検証・判定と activity の再構成
    fd_map = {"t_OS": fd_os, "t_YO": fds["YO"], "t_YS": fds["YS"]}
    for key, arms_, decide in (("t_OS", W.AUDITED, W.NATURAL_PAIR), ("t_YO", W.PAIRS["YO"], W.PAIRS["YO"]),
                               ("t_YS", W.PAIRS["YS"], W.PAIRS["YS"])):
        for name, problems in check_divergence(run, key, tuple(arms_), tuple(decide), fd_map[key], before_start, start, end).items():
            out[name] += problems
    # t_OS の直後の記録の再検証（t と t ＋ 1 の Unit の状態の fire_count・発火のコピー）
    rec = run["arms"]["t_OS"]
    if fd_os is not None and rec is not None:
        after = rec.get("after") or {}
        for k, p in (("t", t_os), ("t+1", t_os + 1)):
            st = after.get(k)
            if st is None:
                if p <= end:
                    out["revalidate_from_raw"].append(f"t_OS：{k} の状態の記録がない")
                continue
            for arm in W.AUDITED:
                for uid, u_ in st[arm]["units"].items():
                    expected = fork[arm]["units"][uid]["fire_count"] + sum(1 for q, x in sp[arm] if x == uid and q <= p)
                    if u_["fire_count"] != expected:
                        out["revalidate_from_raw"].append(f"t_OS {arm}：{k} の {uid} の fire_count が全発火の列と合わない")
        copy_ = (rec.get("spikes_after") or {}).get("t+1")
        if t_os + 1 <= end:
            if copy_ is None:
                out["revalidate_from_raw"].append("t_OS：t ＋ 1 の発火のコピーがない")
            else:
                for arm in W.AUDITED:
                    if any(q != t_os + 1 for q, _ in copy_[arm]) or sorted(u for _, u in copy_[arm]) != spikes_at(sp[arm], t_os + 1):
                        out["revalidate_from_raw"].append(f"t_OS {arm}：t ＋ 1 の発火のコピーが全発火の列と違う")
    # 最初の違いの分解の恒等式
    if not out["revalidate_from_raw"]:
        for pair in W.PAIRS:
            for j, c in (first_difference_contributions(run, pair, fd_os, fds[pair], start, end) or {}).items():
                if c["activity_difference"] is None:
                    out["first_difference_decomposition_identity"].append(f"{PAIR_KEY[pair]} {j}：判定の直前の activity の監査の記録がない")
                elif not abs(c["sum"] - c["activity_difference"]) < TOL["first_difference_decomposition_identity"]:
                    out["first_difference_decomposition_identity"].append(
                        f"{PAIR_KEY[pair]} {j}：Σ K（{c['sum']}）≠ ã^基準 − ã^yoke（{c['activity_difference']}）")


def p_identity(run: dict, yoke: str, start: int, end: int, check_at: Iterable[int]) -> list[str]:
    """命題 4.3 を、t0 の状態と相手の自然な個体の発火の列から独立に計算し、保存した w^A − w^B と照合する。

    A ＝ yoke の腕（基準の t0 の状態）、B ＝ 相手の自然な個体。どちらも B の発火で可塑性を更新する。
    Φ^B ＝ Π σ^B（B 自身の痕跡と発火から）、T^B(t) ＝ σ^B(t)·T^B(t − 1) ＋ e^A(t)、
    e^A(k) ＝ (a／w_max)·κ^(k−1−t0)·[ΔX_pre·post(k)·(w_max − w^A(k−1)) − ΔX_post·pre(k)·w^A(k−1)]（ΔX は t0 の痕跡の差 A − B）。
    w^A(k − 1) は本体の更新で A を進めた値を使う。"""
    problems = []
    partner, base = W.SOURCE[yoke], W.BASE[yoke]
    fired = W.fired_by_pulse(run["arms"]["spikes"][partner])
    want = set(check_at)
    fa, fb = run["fork"][base]["connections"], run["fork"][partner]["connections"]
    for cid in sorted(fa):
        src, dst = W.unit_of(cid)
        a0, b0 = fa[cid], fb[cid]
        d_omega = a0["weight"] - b0["weight"]
        dx_pre, dx_post = a0["pre_trace"] - b0["pre_trace"], a0["post_trace"] - b0["post_trace"]
        stA = W.PlasticState(weight=a0["weight"], pre_trace=a0["pre_trace"], post_trace=a0["post_trace"])
        xb, yb = b0["pre_trace"], b0["post_trace"]
        phi, T = 1.0, 0.0
        for p in range(start + 1, end + 1):
            f = fired.get(p, ())
            pre, post = src in f, dst in f
            sigma_b = 1.0 - RATIO * (xb * post + yb * pre)
            k = KAPPA ** (p - 1 - start)
            e = RATIO * k * (dx_pre * post * (SPEC.w_max - stA.weight) - dx_post * pre * stA.weight)
            phi, T = sigma_b * phi, sigma_b * T + e
            xb, yb = xb * KAPPA + pre, yb * KAPPA + post
            stA = W.balanced_pair_window(stA, pre_fired=pre, post_fired=post, delta_time=DT, spec=SPEC)
            if p in want:
                got = (_state_at(run, yoke, p, end)["connections"][cid]["weight"]
                       - _state_at(run, partner, p, end)["connections"][cid]["weight"])
                if not abs(got - (phi * d_omega + T)) < TOL["P_identity"]:
                    problems.append(f"{yoke} − {partner} {p}：{cid} で P（{got}）≠ Φ·δω ＋ T（{phi * d_omega + T}）")
    return problems


# ---- 観測（README §5。判定なし。本番の解析でだけ計算する） ---------------------------------------------------

def _describe(values: list) -> dict:
    """分布の記述。null の個体は分布に入れず、その個数を併記する（missing_values.null_is_not_zero）。"""
    got = [v for v in values if v is not None]
    return {"n": len(got), "null": len(values) - len(got),
            "median": statistics.median(got) if got else None,
            "min": min(got) if got else None, "max": max(got) if got else None}


def _by_role(conns: Mapping[str, Mapping], u: Mapping[str, str], f: str) -> dict[str, float]:
    return {name: conns[W.connection_id(u[a], u[b])][f] for name, (a, b) in CONNECTIONS.items()}


def weight_and_trace_differences(run: dict, start: int = END, end: int = TOTAL) -> tuple[dict, dict]:
    """接続ごとの符号付きの重みの差（#90 の定義のまま）と痕跡の差。t0・標本・T。接続ごと・時刻ごとに別々（まとめない）。"""
    u = run["roles"]["units"]
    times = sorted(set(sample_times(run)) | {end})
    wd, td = {}, {}
    for t in times:
        st = {arm: _state_at(run, arm, t, end)["connections"] for arm in ("O", "S", "Y_O_from_S", "Y_S_from_O")}
        w = {arm: _by_role(c, u, "weight") for arm, c in st.items()}
        wd[str(t)] = {name: {"D_nat": w["O"][name] - w["S"][name],
                             "F_O": w["O"][name] - w["Y_O_from_S"][name],
                             "P_O": w["Y_O_from_S"][name] - w["S"][name],
                             "F_S": w["Y_S_from_O"][name] - w["S"][name],
                             "P_S": w["Y_S_from_O"][name] - w["O"][name]} for name in CONNECTIONS}
        td[str(t)] = {}
        for name in CONNECTIONS:
            td[str(t)][name] = {}
            for f in TRACES:
                x = {arm: _by_role(c, u, f)[name] for arm, c in st.items()}
                td[str(t)][name][f] = {"natural": x["O"] - x["S"],
                                       "base_minus_yoke_O": x["O"] - x["Y_O_from_S"],
                                       "base_minus_yoke_S": x["S"] - x["Y_S_from_O"]}
    return wd, td


def record_run(run: dict, start: int = END, end: int = TOTAL) -> dict:
    u = run["roles"]["units"]
    role = {uid: r for r, uid in u.items()}
    sp = run["arms"]["spikes"]
    fd_os = first_difference(sp["O"], sp["S"])
    fds = {pair: first_difference(sp[b], sp[y]) for pair, (b, y) in W.PAIRS.items()}

    def detail(fd, a: str, b: str):
        if fd is None:
            return None
        t, units = fd
        fa = set(spikes_at(sp[a], t))
        return [{"unit": x, "role": role[x], "fired_in": a if x in fa else b} for x in units]

    t_os = fd_os[0] if fd_os else None
    t_yo = fds["YO"][0] if fds["YO"] else None
    t_ys = fds["YS"][0] if fds["YS"] else None
    pairs_n = {"O_vs_Y_O_from_S": ("O", "Y_O_from_S"), "S_vs_Y_S_from_O": ("S", "Y_S_from_O"), "O_vs_S": ("O", "S")}
    diffs = {k: differing(sp[a], sp[b]) for k, (a, b) in pairs_n.items()}
    k_contrib = {}
    for pair in W.PAIRS:
        k = first_difference_contributions(run, pair, fd_os, fds[pair], start, end)
        k_contrib[pair] = None if k is None else {role[j]: {"K": {role[s]: v for s, v in c["K"].items()}, "sum": c["sum"]}
                                                  for j, c in k.items()}
    wd, td = weight_and_trace_differences(run, start, end)
    return {
        # 主（README §5.1）
        "t_YO": t_yo, "U_YO": detail(fds["YO"], "O", "Y_O_from_S"),
        "t_YS": t_ys, "U_YS": detail(fds["YS"], "S", "Y_S_from_O"),
        # 副（README §5.2。別々に記録する。まとめない）
        "t_OS": t_os, "U_OS": detail(fd_os, "O", "S"),
        "t_YO_minus_t_OS": None if t_yo is None else t_yo - t_os,
        "t_YS_minus_t_OS": None if t_ys is None else t_ys - t_os,
        "detectable_pulses_after_t_OS": None if t_os is None else max(0, end - t_os - 1),
        "spike_counts_per_unit": {arm: {r: sum(1 for _, x in sp[arm] if x == u[r]) for r in W.ROLES}
                                  for arm in ("O", "S", "Y_O_from_S", "Y_S_from_O")},
        "differing_pulses": {k: len(v) for k, v in diffs.items()},
        "last_differing_pulse": {k: (v[-1] if v else None) for k, v in diffs.items()},
        "weight_differences_per_connection": {"t0": wd[str(start)], "T": wd[str(end)], "samples": SERIES},
        "trace_differences_per_connection": {"t0": td[str(start)], "T": td[str(end)], "samples": SERIES},
        "first_difference_contributions": k_contrib,
    }


def category(rec: dict) -> str:
    """構造上の区分（README §11 の 3。判定ではない）。"""
    if rec["t_OS"] is None:
        return "a_no_t_OS"
    if rec["t_YO"] is None and rec["t_YS"] is None:
        return "b_t_OS_without_t_YO_t_YS"
    if rec["t_YS"] is None:
        return "c_t_YO_only"
    if rec["t_YO"] is None:
        return "d_t_YS_only"
    return "e_t_YO_and_t_YS"


CATEGORIES = ("a_no_t_OS", "b_t_OS_without_t_YO_t_YS", "c_t_YO_only", "d_t_YS_only", "e_t_YO_and_t_YS")


def summarize(per: dict, individuals: dict, start: int = END) -> dict:
    """数え上げと分布の記述だけ（README §7.3）。集団の holds／fails・合格の基準・区間・比・まとめた得点は置かない。"""
    cats = {c: [int(s) for s, r in per.items() if category(r) == c] for c in CATEGORIES}

    def rel(key: str) -> list:
        return [None if r[key] is None else r[key] - start for r in per.values()]

    out = {
        "individuals": len(per),
        "invalid_individuals": sorted(int(s) for s, v in individuals.items() if not v["valid"]),
        "failed_checks": {k: sum(1 for v in individuals.values() if v["failed_checks"].get(k)) for k in CHECK_NAMES},
        "categories": {c: {"count": len(v), "seeds": v} for c, v in cats.items()},
        "t_YO_minus_t0": _describe(rel("t_YO")),
        "t_YS_minus_t0": _describe(rel("t_YS")),
        "t_OS_minus_t0": _describe(rel("t_OS")),
        "t_YO_minus_t_OS": _describe([r["t_YO_minus_t_OS"] for r in per.values()]),
        "t_YS_minus_t_OS": _describe([r["t_YS_minus_t_OS"] for r in per.values()]),
    }
    for key, arms in (("U_YO", ("O", "Y_O_from_S")), ("U_YS", ("S", "Y_S_from_O"))):
        units = [x for r in per.values() for x in (r[key] or [])]
        out[f"{key}_roles"] = {r: sum(1 for x in units if x["role"] == r) for r in W.ROLES}
        out[f"{key}_fired_in"] = {a: sum(1 for x in units if x["fired_in"] == a) for a in arms}
    return out


def analyze(data: dict, mode: str, records: dict | None,
            before_start: Mapping[str, Mapping[str, float]] | None = None) -> dict:
    """mode：formal（本番）か check（道具の通しの確認）。records：guard.read_records の値。"""
    problems = completeness(data, mode) + verify_records(records, data, mode)
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    individuals = {}
    for r in runs:
        seed = r.get("seed") if isinstance(r, dict) else "?"
        try:
            checks = check_run(r, before_start)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
            checks = {k: [] for k in CHECK_NAMES} | {"revalidate_from_raw": [f"記録の形が想定と違う（{e!r}）"]}
        failed = {k: v for k, v in checks.items() if v}
        individuals[str(seed)] = {"valid": not failed, "failed_checks": failed}
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    all_valid = not problems and all(v["valid"] for v in individuals.values())
    base = {"experiment": EXPERIMENT, "kind": KIND, "mode": mode, "git_commit": meta.get("git_commit"),
            "seeds": meta.get("seeds"), "valid": all_valid, "problems": problems, "individuals": individuals}
    if mode != "formal":
        return base | {"note": "道具の通しの確認（操作の確認だけ）。観測の量は計算・表示していない"}
    try:
        per = {str(r["seed"]): record_run(r) | {"valid": individuals[str(r["seed"])]["valid"]} for r in runs}
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        return base | {"note": f"記録の形が想定と違い、観測の量を計算できなかった（{e!r}）"}
    note = "事前登録した記述的な介入実験（判定なし）。全個体を記録し、invalid の個体も除かずに載せる（valid の欄）"
    if problems:
        note += "。データ全体の問題があるので、invalid のデータの記録である"
    return base | {"note": note, "summary": summarize(per, individuals), "per_seed": per}


def difference_series(data: dict) -> dict:
    """本番の記録の、接続ごとの重みの差・痕跡の差の標本ごとの値（README §5.2。t0・60 Pulse ごと・T）。seed → {weight, trace}。"""
    out = {}
    for r in data.get("runs") or []:
        wd, td = weight_and_trace_differences(r)
        out[str(r["seed"])] = {"weight": wd, "trace": td}
    return out


def analyze_folder(folder: Path, mode: str) -> dict:
    """解析だけ（読むだけで、どこにも書かない）。"""
    records = G.read_records(folder)
    if not (folder / G.RUNS).exists():
        return {"experiment": EXPERIMENT, "kind": KIND, "mode": mode, "valid": False,
                "problems": ["結果のファイル（runs.json.gz）がない"], "records": records}
    return analyze(read(folder / G.RUNS), mode, records)


# ---- 成果物の公開（一度限り。中断に備える。#92 のレビュー 5505249564）------------------------------------------
#
# 本番の解析は 2 つの成果物（差の系列 differences_series.json.gz と report.json）を出す。公開の手順と記録：
#   1. 書いてよい場所かを、何も読まず・書かずに確かめる（report_destination）
#   2. 解析の記録 analysis_log.jsonl を排他的に作り、「開始」と入力の sha256（raw・実行の記録・protocol・道具）を残す。
#      以後この記録には追記だけをする（書き換え・削除はしない）
#   3. 成果物を計算する（解析は決定論的。report に時刻を入れず、gzip の mtime は 0）。report には入力の sha256 と、
#      差の系列の sha256・バイト数を入れる（後から照合できる）
#   4. 差の系列 → report の順に公開する。公開は一時ファイル（試行ごとに別の名前）に書いて fsync し、os.link で本名に置く
#      （本名が既にあれば失敗する。上書きしない）。公開するたびに「書いた」と sha256 を記録に追記する
#   5. 最後に「完了」と成果物の sha256 を追記する
# 途中で例外・中断があれば「失敗」と、その時点にある成果物の sha256 を追記する（中断で追記できなかった場合も、記録には
# 「開始」と「書いた」が残る）。成果物を黙って消す・書き直すことはしない。seed は走らせ直さない。
#
# 中断の後は、明示的な --resume でだけ再開する（何もなければ、既にある成果物・記録を理由に止まる）。再開では：
#   - 入力の sha256 が「開始」のときと完全に同じであること、「書いた」と記録した成果物が消えていないこと
#   - 同じ raw から決定論的に計算し直した成果物と、既にある成果物のバイト列（sha256）が一致すること
# を確かめ、一致すれば既にあるものはそのまま残し、ないものだけを公開して「完了」を追記する。1 つでも合わなければ
# （破損・入力の変化・成果物の消失・記録の破損）、「復旧不能」と理由を追記して止まる。以後の再開は拒否し、手動の監査の判断に委ねる。
# 完了した解析は、--verify で、成果物・記録・入力の sha256 を照合できる（何も書かない）。

LOG = "analysis_log.jsonl"
TOOL_FILES = ("analyze.py", "world.py", "alignment.py", "guard.py")


def _artifact_names(mode: str) -> tuple[str, ...]:
    """公開の順序。差の系列（本番だけ）を先、report を後にする（report があれば、それが参照する系列もある）。"""
    return (SERIES, REPORT) if mode == "formal" else (REPORT,)


def _tmp_names(folder: Path) -> list[str]:
    names = (REPORT, SERIES, LOG)
    return sorted(p.name for p in folder.iterdir() if p.is_file() and any(p.name.startswith(n + ".tmp") for n in names)) \
        if folder.is_dir() else []


def report_destination(folder: Path, mode: str, resume: bool = False) -> Path:
    """report を書いてよい場所。だめなら GuardError（何も読まず・書かずに止まる）。

    - 本番（formal）：この実験の出力先（protocol の execution.output_dir）だけ。他の実験のフォルダには書かない
    - 通しの確認（check）：data/experiments の下（本番・他の実験のデータの場所）には書かない
    - 再開（resume）でなければ、report・差の系列・解析の記録・それらの一時ファイルのどれかが既にあれば止まる（上書きしない。
      解析は 1 回だけ）。中断の後の扱いは publish（--resume）
    """
    f, root, own = folder.resolve(), DATA_ROOT.resolve(), OWN_DIR.resolve()
    if mode == "formal":
        if f != own:
            raise G.GuardError(f"本番の解析の report は {DEFAULT_DIR} にだけ書く（{folder} には書かない）")
    elif mode == "check":
        if f == root or root in f.parents:
            raise G.GuardError(f"通しの確認の解析の report は data/experiments の下（{folder}）に書かない")
    else:
        raise G.GuardError(f"未知の mode（{mode}）")
    if not resume:
        found = [n for n in (REPORT, SERIES, LOG) if (f / n).exists()] + _tmp_names(f)
        if found:
            raise G.GuardError(f"{f} に {found} が既にある（上書きしない。解析は 1 回だけ。中断の後なら --resume で照合して完了する）")
    return f / REPORT


def analysis_context(folder: Path, mode: str) -> dict:
    """解析の入力の sha256（raw・実行の記録・protocol・道具）。開始のときと再開のときで完全に同じであることを確かめる。"""
    def sha(path: Path):
        return G.sha256_file(path) if path.exists() else None
    return {"experiment": EXPERIMENT, "kind": KIND, "mode": mode,
            "runs_sha256": sha(folder / G.RUNS), "run_started_sha256": sha(folder / G.START),
            "run_finished_sha256": sha(folder / G.FINISH), "protocol_sha256": G.sha256_file(REPO / PROTOCOL_PATH),
            "tool_sha256": {n: G.sha256_file(REPO / HERE / n) for n in TOOL_FILES}}


def build_outputs(folder: Path, mode: str) -> tuple[dict, dict[str, bytes]]:
    """解析（読むだけ）。report の中身と、差の系列のバイト列（本番で観測の量を計算したときだけ）。決定論的。"""
    report = analyze_folder(folder, mode)
    series: dict[str, bytes] = {}
    if mode == "formal" and "per_seed" in report:
        series[SERIES] = gzip.compress(json.dumps(difference_series(read(folder / G.RUNS))).encode("utf-8"), mtime=0)
    return report, series


def render(report: dict, series: Mapping[str, bytes], context: dict) -> dict[str, bytes]:
    """公開するバイト列。report には入力の sha256 と、差の系列の sha256・バイト数を入れる（後から照合できる）。"""
    artifacts = {name: {"sha256": G.sha256_bytes(b), "bytes": len(b)} for name, b in series.items()}
    full = report | {"inputs": context, "artifacts": artifacts}
    return dict(series) | {REPORT: json.dumps(full, ensure_ascii=False, indent=2).encode("utf-8")}


def read_log(folder: Path) -> list[dict]:
    """解析の記録を読む。読めない行があれば GuardError（記録の破損。手動の監査へ）。"""
    events = []
    for k, line in enumerate((folder / LOG).read_text(encoding="utf-8").splitlines(), 1):
        try:
            e = json.loads(line)
        except json.JSONDecodeError as err:
            raise G.GuardError(f"解析の記録の {k} 行目が読めない（記録の破損。手動の監査の判断に委ねる）") from err
        if not isinstance(e, dict) or "event" not in e or "attempt" not in e:
            raise G.GuardError(f"解析の記録の {k} 行目の形が想定と違う（手動の監査の判断に委ねる）")
        events.append(e)
    return events


def _append(folder: Path, event: dict, create: bool = False) -> None:
    """解析の記録に 1 行を追記する（create のときは排他的に作る）。追記だけで、書き換え・削除はしない。"""
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | (os.O_EXCL if create else 0)
    fd = os.open(folder / LOG, flags, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(event | {"time_unix": time.time()}, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    G._fsync_dir(folder)


def _publish_file(path: Path, data: bytes, attempt: int) -> None:
    """試行ごとに別の名前の一時ファイルに書いて fsync し、os.link で本名に置く（本名が既にあれば失敗する。上書きしない）。"""
    tmp = path.with_name(f"{path.name}.tmp-{attempt}")
    with open(tmp, "xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.link(tmp, path)
    os.unlink(tmp)
    G._fsync_dir(path.parent)


def _present(folder: Path, names: Iterable[str]) -> dict:
    return {n: (G.sha256_file(folder / n) if (folder / n).exists() else None) for n in names}


class Unrecoverable(G.GuardError):
    """再開しても安全に完了できない（入力の変化・成果物の破損・消失・記録の破損）。手動の監査の判断に委ねる。"""


def publish(folder: Path, mode: str, resume: bool = False) -> dict:
    """解析して成果物を公開する（README §7.2 の一度限りの解析。上の手順）。返す値：report の中身（入力・成果物の sha256 つき）。"""
    names = _artifact_names(mode)
    context = analysis_context(folder, mode)
    written: dict[str, str] = {}
    if not resume:
        report_destination(folder, mode)                  # 既に何かあれば止まる（ここでも確かめ直す）
        attempt = 1
        _append(folder, {"event": "started", "attempt": attempt, "context": context}, create=True)
    else:
        if not (folder / LOG).exists():
            raise Unrecoverable("再開できる解析の記録がない（成果物だけがあるなら、手動の監査の判断に委ねる）")
        events = read_log(folder)
        if events[0].get("event") != "started":
            raise Unrecoverable("解析の記録が「開始」で始まっていない（手動の監査の判断に委ねる）")
        if any(e["event"] == "completed" for e in events):
            raise G.GuardError("この解析は既に完了している（再開しない。--verify で照合できる）")
        if any(e["event"] == "unrecoverable" for e in events):
            raise Unrecoverable("この解析は復旧不能として記録済み（再開しない。手動の監査の判断を待つ）")
        attempt = max(int(e["attempt"]) for e in events) + 1
        written = {e["file"]: e["sha256"] for e in events if e["event"] == "written"}
        _append(folder, {"event": "resumed", "attempt": attempt, "context": context,
                         "present": _present(folder, names), "stale_tmp": _tmp_names(folder)})
        reasons = []
        if context != events[0]["context"]:
            reasons.append("入力（raw・実行の記録・protocol・道具）の sha256 が開始のときと違う")
        reasons += [f"{n} は書いた記録があるのに、ない" for n in written if not (folder / n).exists()]
        if reasons:
            _append(folder, {"event": "unrecoverable", "attempt": attempt, "reasons": reasons})
            raise Unrecoverable("；".join(reasons) + "（手動の監査の判断に委ねる）")
    try:
        report, series = build_outputs(folder, mode)
        files = render(report, series, context)
        reasons = [f"{n} があるのに、計算し直した成果物に含まれない" for n in names
                   if n not in files and (folder / n).exists()]
        for n in names:
            if n not in files:
                continue
            path, sha = folder / n, G.sha256_bytes(files[n])
            if path.exists():
                got = G.sha256_file(path)
                if got != sha or written.get(n, got) != got:
                    reasons.append(f"{n} の sha256（{got}）が、同じ入力から計算し直した成果物（{sha}）・書いた記録と一致しない（破損）")
                continue                                   # 同じバイト列が既にある：そのまま残す（書き直さない）
            if reasons:
                break
            _publish_file(path, files[n], attempt)
            _append(folder, {"event": "written", "attempt": attempt, "file": n, "sha256": sha, "bytes": len(files[n])})
        if reasons:
            _append(folder, {"event": "unrecoverable", "attempt": attempt, "reasons": reasons})
            raise Unrecoverable("；".join(reasons) + "（手動の監査の判断に委ねる）")
        _append(folder, {"event": "completed", "attempt": attempt, "resumed": resume,
                         "artifacts": {n: G.sha256_bytes(files[n]) for n in names if n in files}})
        return json.loads(files[REPORT])
    except G.GuardError:
        raise
    except BaseException as e:
        with contextlib.suppress(Exception):          # 失敗の記録が書けなくても、元の例外を投げ直す（記録には「開始」「書いた」が残る）
            _append(folder, {"event": "failed", "attempt": attempt, "reason": repr(e), "present": _present(folder, names)})
        raise


def verify_artifacts(folder: Path, mode: str) -> dict:
    """完了した解析の成果物・記録・入力の sha256 を照合する（何も書かない）。{problems, notes}。"""
    problems, notes = [], []
    if not (folder / LOG).exists():
        return {"problems": ["解析の記録がない"], "notes": notes}
    try:
        events = read_log(folder)
    except G.GuardError as e:
        return {"problems": [str(e)], "notes": notes}
    done = [e for e in events if e["event"] == "completed"]
    if len(done) != 1 or events[-1] is not done[-1]:
        problems.append("解析の記録が「完了」1 つで終わっていない")
    if any(e["event"] == "unrecoverable" for e in events):
        problems.append("復旧不能が記録されている")
    if not (folder / REPORT).exists():
        return {"problems": problems + ["report がない"], "notes": notes}
    report = json.loads((folder / REPORT).read_text(encoding="utf-8"))
    now = analysis_context(folder, mode)
    inputs = report.get("inputs") or {}
    for k in ("experiment", "kind", "mode", "runs_sha256", "run_started_sha256", "run_finished_sha256", "protocol_sha256"):
        if inputs.get(k) != now[k]:
            problems.append(f"report の入力 {k} が今のファイルと違う")
    if inputs != events[0].get("context"):
        problems.append("report の入力が、解析の記録の「開始」のものと違う")
    if inputs.get("tool_sha256") != now["tool_sha256"]:
        notes.append("道具の sha256 が今の道具と違う（後の commit で照合している。成果物の照合には影響しない）")
    for n, a in (report.get("artifacts") or {}).items():
        path = folder / n
        if not path.exists():
            problems.append(f"report が参照する {n} がない")
        elif G.sha256_file(path) != a.get("sha256") or path.stat().st_size != a.get("bytes"):
            problems.append(f"{n} の sha256・バイト数が report の記録と違う（破損・差し替え）")
    names = set(_artifact_names(mode)) if (report.get("artifacts") or mode == "check") else {REPORT}
    for n, sha in (done[-1].get("artifacts") or {}).items() if done else []:
        if not (folder / n).exists() or G.sha256_file(folder / n) != sha:
            problems.append(f"{n} が、解析の記録の「完了」の sha256 と違う")
    if done and set(done[-1].get("artifacts") or {}) != names:
        problems.append("解析の記録の「完了」の成果物の一覧が想定と違う")
    return {"problems": problems, "notes": notes}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "check" if "--check" in sys.argv else "formal"
    resume = "--resume" in sys.argv
    folder = Path(args[0]) if args else OWN_DIR
    if "--verify" in sys.argv:
        result = verify_artifacts(folder, mode)
        for n in result["notes"]:
            print(f"  （注）{n}")
        print("照合：問題なし" if not result["problems"] else "照合：問題あり\n" + "\n".join(f"  - {p}" for p in result["problems"]))
        raise SystemExit(0 if not result["problems"] else 1)
    try:
        report_destination(folder, mode, resume)    # 解析の前に、書いてよい場所かを確かめる（だめなら何も読まず・書かずに止まる）
    except G.GuardError as e:
        raise SystemExit(f"report を書かない：{e}") from e
    ALIGN.check(PROTOCOL)
    try:
        report = publish(folder, mode, resume)
    except G.GuardError as e:
        raise SystemExit(f"report を書かない：{e}") from e
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    bad = {s: v["failed_checks"] for s, v in report.get("individuals", {}).items() if not v["valid"]}
    for s, f in list(bad.items())[:20]:
        print(f"  - seed {s}: {sorted(f)}")
    if mode == "check":
        print("【道具の通しの確認。観測の量は計算していない】")
    else:
        print("観測の量は report.json・differences_series.json.gz に書いた（ここには表示しない）")
    print(f"saved {folder / REPORT}（解析の記録 {LOG}）")


if __name__ == "__main__":
    main()
