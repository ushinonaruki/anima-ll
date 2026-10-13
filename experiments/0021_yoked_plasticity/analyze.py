"""実験 0021 の記録の解析（事前登録 v0.1 に従う。判定なし）。正本は protocol.yaml・README。

1. 実行の記録（開始・終了の記録、結果の sha256。guard.py）と、データの完全性（experiment・kind・mode・seed・commit）を確かめる
2. 操作の確認（README §6、protocol の checks）を、保存した生の記録から個体ごとに再検証する。確認の名前ごとに、
   成り立たなかった理由を個体ごとに残す。1 つでも成り立たなければその個体は invalid。結果の都合で個体を除かない
3. 観測（README §5、protocol の observations）を、生の記録から個体ごとに全件計算する。t1・t2・U1・U2 は保存した
   分岐の記録ではなく全発火の列から計算し直す。欠測は null、実際の 0 は 0（observations.missing_values）
4. 要約は数え上げと分布の記述だけ。集団の holds／fails・0.8・方向の予想・区間は置かない

分岐の Pulse の activity の再構成（numeric.divergence_activity_reconstruction）：t の判定の直前の activity は記録しない
（README §4 の記録は t − 2・t − 1 の状態）。そこで同じ再構成の式を t − 1 で、t − 2 の状態・t − 3 の重み・t − 2 の発火から
計算し、保存した t − 1 の activity と照合する（発火した Unit は 0 に戻っていること）。t の判定は t − 1 の状態から再構成して
実際の発火と照合する（exact.divergence_decisions_reconstructed）。t − 3 ＝ t0 − 1 のときの重みは、介入の前の重みで、
ordered の記録した発火から出生時の状態を本体の更新で進めて求める（腕によらず同じ）。

使い方:
  python experiments/0021_yoked_plasticity/analyze.py [出力先]             # 本番（既定の出力先は protocol の execution.output_dir）
  python experiments/0021_yoked_plasticity/analyze.py <フォルダ> --check   # 道具の通しの確認（操作の確認だけ。観測の量は出さない）
"""

import gzip
import importlib.util
import json
import math
import statistics
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
DEFAULT_DIR = Path(PROTOCOL["execution"]["output_dir"])
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
EVERY = W.sample_every(PROTOCOL)
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
SPEC = W.plasticity(PROTOCOL)
TOL = PROTOCOL["checks"]["numeric"]
FIELDS = ("weight", "pre_trace", "post_trace")
CHECK_NAMES = (list(PROTOCOL["checks"]["inherited_from_0020"]) + list(PROTOCOL["checks"]["exact"])
               + list(PROTOCOL["checks"]["numeric"]) + ["revalidate_from_raw"])
PAIRS = {"AB": ("A", "B"), "AC": ("A", "C"), "BA": ("B", "A"), "CA": ("C", "A"), "BC": ("B", "C"), "CB": ("C", "B")}


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
    if any(b[0] < a[0] for a, b in zip(spikes, spikes[1:])):
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


def differing_pulses(a: list, b: list) -> int:
    fa, fb = W.fired_by_pulse(a), W.fired_by_pulse(b)
    return sum(1 for p in set(fa) | set(fb) if fa.get(p, set()) != fb.get(p, set()))


def plasticity_spikes(run: dict, arm: str) -> list:
    """可塑性の更新に使った発火の列（C・I・twin は自分、Y・Y0 は C。README §2）。"""
    return run["arms"]["spikes"][W.SOURCE if arm in W.YOKED else arm]


def replay_arm(run: dict, arm: str, record: Iterable[int] = (), start: int = END, end: int = TOTAL) -> dict:
    """腕の接続の状態を、t0（start）の状態から、可塑性の更新に使った列で end まで再生する（README §2）。"""
    fired = W.fired_by_pulse(plasticity_spikes(run, arm))
    record = list(record)
    return {cid: W.replay(st, cid, fired, start, end, SPEC, DT, record)
            for cid, st in run["fork"][arm]["connections"].items()}


def sample_times(run: dict) -> list[int]:
    return sorted(int(t) for t in run["arms"]["samples"][W.SOURCE])


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

def _weights(conns: Mapping[str, Mapping]) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in conns.items()}


def check_divergence(run: dict, key: str, arms: tuple[str, ...], fd, before_start: Mapping[str, float],
                     start: int = END, end: int = TOTAL) -> dict[str, list]:
    """t1（key ＝ "t1"、腕 C・I・Y）か t2（"t2"、I・Y）の記録を、全発火の列から独立に再検証し、判定・activity を再構成する。"""
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
    before = rec.get("before") or {}
    for arm in arms:
        for k, p in (("t-1", t - 1), ("t", t)):
            copy_ = rec["spikes"][k][arm]
            if any(q != p for q, _ in copy_) or sorted(u for _, u in copy_) != spikes_at(sp[arm], p):
                out["revalidate_from_raw"].append(f"{key} {arm}：分岐の記録の発火のコピー（{k}）が全発火の列と違う")
    if t - 2 < start or before.get("t-2") is None:
        out["revalidate_from_raw"].append(f"{key}：分岐の直前 2 Pulse の状態がない（分岐 {t}）")
        return out
    tol = TOL["affine_reconstruction_T"]
    for arm in arms:
        rep = replay_arm(run, arm, [t - 3, t - 2, t - 1] if t - 3 >= start else [t - 2, t - 1], start, end)
        for k, p in (("t-2", t - 2), ("t-1", t - 1)):
            stored = before[k][arm]["connections"]
            if set(stored) != set(rep) or any(abs(rep[c]["at"][p][f] - stored[c][f]) > tol for c in rep for f in FIELDS):
                out["revalidate_from_raw"].append(f"{key} {arm}：分岐の直前（{k}）の接続の状態が、介入の直後の状態と可塑性の列からの再構成と違う")
            for uid, st in before[k][arm]["units"].items():
                expected = run["fork"][arm]["units"][uid]["fire_count"] + sum(1 for q, x in sp[arm] if x == uid and q <= p)
                if st["fire_count"] != expected:
                    out["revalidate_from_raw"].append(f"{key} {arm}：分岐の直前（{k}）の {uid} の fire_count が全発火の列と合わない")
        # t の判定：t − 1 の状態・t − 2 の重み・t − 1 の発火から
        dec = W.reconstruct_firing(before["t-1"][arm]["units"], _weights(before["t-2"][arm]["connections"]),
                                   [[t - 1, x] for x in spikes_at(sp[arm], t - 1)], DT)
        if sorted(x for x, r in dec.items() if r["fires"]) != spikes_at(sp[arm], t):
            out["divergence_decisions_reconstructed"].append(f"{key} {arm}：Pulse {t} の発火の判定の再構成が実際の発火と合わない")
        # t − 1 の activity：t − 2 の状態・t − 3 の重み・t − 2 の発火から再構成し、保存した t − 1 と照合する
        w3 = (dict(before_start) if t - 3 == start - 1
              else {c: rep[c]["at"][t - 3]["weight"] for c in rep})
        prev = W.reconstruct_firing(before["t-2"][arm]["units"], w3, [[t - 2, x] for x in spikes_at(sp[arm], t - 2)], DT)
        fired_tm1 = set(spikes_at(sp[arm], t - 1))
        for uid, r in prev.items():
            got = before["t-1"][arm]["units"][uid]["activity"]
            if r["fires"] != (uid in fired_tm1):
                out["divergence_decisions_reconstructed"].append(f"{key} {arm}：Pulse {t - 1} の {uid} の発火の判定の再構成が実際と合わない")
            elif uid in fired_tm1 and got != 0.0:
                out["divergence_activity_reconstruction"].append(f"{key} {arm}：Pulse {t - 1} に発火した {uid} の activity が 0 に戻っていない")
            elif uid not in fired_tm1 and not abs(r["activity_pre"] - got) < TOL["divergence_activity_reconstruction"]:
                out["divergence_activity_reconstruction"].append(
                    f"{key} {arm}：Pulse {t - 1} の {uid} の activity の再構成（{r['activity_pre']}）が保存した値（{got}）と合わない")
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
    """Pulse lo〜hi の終わりの、腕 a と腕 b の重みの差（a − b）。可塑性の列で介入の直後から再生する。"""
    times = list(range(max(lo, start), hi + 1))
    ra, rb = replay_arm(run, a, times, start, end), replay_arm(run, b, times, start, end)
    table = {m: {cid: ra[cid]["at"][m]["weight"] - rb[cid]["at"][m]["weight"] for cid in ra} for m in times}
    return lambda m: table[m]


def t2_contributions(run: dict, fd1, fd2, start: int = END, end: int = TOTAL) -> dict | None:
    """t2 の差の接続ごとの寄与（j ∈ U2）と、t2 の activity の差の再構成（ã^I − ã^Y）。t2 がなければ None。"""
    if fd2 is None or fd1 is None:
        return None
    (t1, _), (t2, u2) = fd1, fd2
    rec = run["arms"]["t2"]
    diff = _diff_series(run, "I", "Y", t1, t2 - 2, start, end)
    act = {arm: W.reconstruct_firing(rec["before"]["t-1"][arm]["units"], _weights(rec["before"]["t-2"][arm]["connections"]),
                                     [[t2 - 1, x] for x in spikes_at(run["arms"]["spikes"][arm], t2 - 1)], DT)
           for arm in ("I", "Y")}
    out = {}
    for j in u2:
        decay = run["fork"]["I"]["units"][j]["dynamics"]["decay_per_second"] ** DT
        k = contributions(j, t2, t1 + 2, run["arms"]["spikes"]["I"], diff, decay, start)
        out[j] = {"K": k, "sum": sum(k.values()),
                  "activity_difference": act["I"][j]["activity_pre"] - act["Y"][j]["activity_pre"]}
    return out


def t1_contributions(run: dict, fd1, start: int = END, end: int = TOTAL) -> dict | None:
    """t1 の差の接続ごとの寄与（数式のメモ F3c。j ∈ U1、C と I の共通の列、Δw ＝ w^I − w^C）。t1 がなければ None。"""
    if fd1 is None:
        return None
    t1, u1 = fd1
    diff = _diff_series(run, "I", "C", start, t1 - 2, start, end)
    out = {}
    for j in u1:
        decay = run["fork"]["C"]["units"][j]["dynamics"]["decay_per_second"] ** DT
        k = contributions(j, t1, start + 2, run["arms"]["spikes"]["C"], diff, decay, start)
        out[j] = {"K": k, "sum": sum(k.values())}
    return out


# ---- 操作の確認（生の記録から。README §6） ------------------------------------------------------------

def _states_equal(a: Mapping, b: Mapping) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def check_run(run: dict, before_start: Mapping[str, float] | None = None) -> dict[str, list[str]]:
    """個体の操作の確認。{確認の名前: 成り立たなかった理由の一覧}。before_start：介入の前の重み（省略すると記録から求める）。"""
    out: dict[str, list[str]] = {k: [] for k in CHECK_NAMES}
    if before_start is None:
        before_start = W.birth_replay_weights(PROTOCOL, run["conditions"]["ordered"]["activity"], END - 1)
    check_conditions(run, out)
    check_arms(run, out, END, TOTAL, before_start)
    return out


def check_conditions(run: dict, out: dict[str, list[str]]) -> None:
    """経験の 2 条件と、t0 の分け方の確認（0020 から継承した確認）。"""
    seed, conds = run["seed"], run["conditions"]
    u = run["roles"]["units"]
    ids = W.four_ids(u)
    target_ids = {ids[k] for k in W.TARGETS}
    sp, fork = run["arms"]["spikes"], run["fork"]
    # ---- 0020 から継承 ----
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
    fc, fi = fork["C"], fork["I"]
    if not _states_equal(fc["connections"], o["connections_12000"]) or not _states_equal(fc["units"], o["units_12000"]):
        out["transplant"].append("C の t0 の状態が ordered の 12000 と違う")
    if not _states_equal(fi["units"], fc["units"]):
        out["transplant"].append("I の t0 の Unit の状態が C と違う")
    for cid, v in fc["connections"].items():
        e = fi["connections"][cid]
        if e["pre_trace"] != v["pre_trace"] or e["post_trace"] != v["post_trace"]:
            out["transplant"].append(f"{cid} の痕跡が移植で変わった")
        if cid not in target_ids and e["weight"] != v["weight"]:
            out["transplant"].append(f"移植の対象外の {cid} の重みが変わった")
    if any(fi["connections"][ids[k]]["weight"] != s["connections_12000"][ids[k]]["weight"] for k in W.TARGETS):
        out["transplant"].append("I の 4 本が shuffled の 12000 の値と違う")
    if not _states_equal(fork["Y"], fi):
        out["transplant"].append("Y の t0 の状態が I と違う")
    for arm in ("twin", "Y0"):
        if not _states_equal(fork[arm], fc):
            out["transplant"].append(f"{arm} の t0 の状態が C と違う")



def check_arms(run: dict, out: dict[str, list[str]], start: int, end: int, before_start: Mapping[str, float]) -> None:
    """5 つの腕の確認（README §6）。start ＝ t0、end ＝ T。契約テストは合成の短い窓でも同じ関数を呼ぶ。"""
    u = run["roles"]["units"]
    ids = W.four_ids(u)
    target_ids = {ids[k] for k in W.TARGETS}
    sp, samples, fork, ends = run["arms"]["spikes"], run["arms"]["samples"], run["fork"], run["endpoints"]
    for arm in W.ARMS:
        out["revalidate_from_raw"] += [f"{arm}：{p}" for p in well_formed(sp[arm], start, end)]
    if sorted(samples) != sorted(W.ARMS) or any(sorted(samples[a]) != sorted(samples[W.SOURCE]) for a in W.ARMS):
        out["revalidate_from_raw"].append("標本の腕・時刻がそろっていない")
    if any(run["arms"]["sensory"][a] for a in W.ARMS):
        out["input_free_after_experience"].append("W の間に感覚の出来事がある腕がある")
    first = start + 1
    if len({tuple(spikes_at(sp[a], first)) for a in W.ARMS}) != 1:
        out["first_pulse_identical"].append(f"{first} の発火が腕によって違う")

    # ---- 厳密に一致すべきもの ----
    times = sample_times(run)
    for arm, name in (("twin", "twin_equals_C"), ("Y0", "Y0_equals_C")):
        if sp[arm] != sp["C"]:
            out[name].append(f"{arm} の発火が C と違う")
        if any(not _states_equal(samples[arm][str(t)], samples["C"][str(t)]) for t in times):
            out[name].append(f"{arm} の標本の状態が C と違う")
        if not _states_equal(ends[arm], ends["C"]):
            out[name].append(f"{arm} の T の状態が C と違う")
    fd1 = first_difference(sp["C"], sp["I"])
    fd2 = first_difference(sp["I"], sp["Y"])
    t1 = fd1[0] if fd1 else None
    limit = end if t1 is None else t1
    if [x for x in sp["I"] if x[0] <= limit] != [x for x in sp["Y"] if x[0] <= limit]:
        out["I_equals_Y_until_t1"].append(f"I と Y の発火が {limit} までに違う")
    conn_limit = end if t1 is None else t1 - 1
    for t in times:
        if t <= conn_limit and not _states_equal(samples["I"][str(t)]["connections"], samples["Y"][str(t)]["connections"]):
            out["I_equals_Y_until_t1"].append(f"I と Y の接続の状態が標本 {t} で違う")
    if t1 is None and not _states_equal(ends["I"]["connections"], ends["Y"]["connections"]):
        out["I_equals_Y_until_t1"].append("t1 がないのに、I と Y の T の接続の状態が違う")
    rec1 = run["arms"]["t1"]
    if t1 is not None and rec1 is not None and rec1.get("pulse") == t1:
        tm1 = rec1["before"]["t-1"]
        if not _states_equal(tm1["I"]["connections"], tm1["Y"]["connections"]):
            out["I_equals_Y_until_t1"].append(f"I と Y の接続の状態が {t1 - 1} で違う")
    for t, state_y, state_c in [(t, samples["Y"][str(t)], samples["C"][str(t)]) for t in times] + [(end, ends["Y"], ends["C"])]:
        for cid, v in state_c["connections"].items():
            e = state_y["connections"][cid]
            if e["pre_trace"] != v["pre_trace"] or e["post_trace"] != v["post_trace"]:
                out["Y_traces_equal_C_traces"].append(f"{t}：{cid} の Y の痕跡が C と違う")
            if cid not in target_ids and e["weight"] != v["weight"]:
                out["P_zero_on_untransplanted_pairs"].append(f"{t}：移植していない {cid} で w_Y ≠ w_C")
    if first_difference(sp["C"], sp["Y"]) != fd1:
        out["t1_C_Y_equals_t1_C_I"].append("C と Y の最初の違い（Pulse・Unit）が C と I のものと違う")
    if fd2 is not None and (fd1 is None or fd2[0] < fd1[0] + 2):
        out["t2_at_least_t1_plus_2"].append(f"t2（{fd2[0]}）が t1（{t1}）＋ 2 より前、または t1 がない")

    # ---- 再構成・数値 ----
    for arm in W.ARMS:
        rep = replay_arm(run, arm, (), start, end)
        for cid, r in rep.items():
            if r["clipped"]:
                out["no_clipping"].append(f"{arm}：{cid} の更新で切り詰めが働いた（Pulse {r['clipped'][:3]}…）")
            stored = ends[arm]["connections"][cid]
            w0 = fork[arm]["connections"][cid]["weight"]
            if (any(not abs(r["end"][f] - stored[f]) < TOL["affine_reconstruction_T"] for f in FIELDS)
                    or not abs(r["S"] * w0 + r["B"] - stored["weight"]) < TOL["affine_reconstruction_T"]):
                out["affine_reconstruction_T"].append(f"{arm}：{cid} の T の状態が可塑性の列からの再構成と合わない")
    for arm in W.ARMS:
        for t, state in [(t, samples[arm][str(t)]) for t in times] + [(end, ends[arm])]:
            for cid, v in state["connections"].items():
                if not 0.0 <= v["weight"] <= SPEC.w_max:
                    out["no_clipping"].append(f"{arm} {t}：{cid} の重みが [0, w_max] の外")
                src, dst = W.unit_of(cid)
                back = state["connections"][W.connection_id(dst, src)]["weight"]
                if not abs(v["weight"] + back - SPEC.w_max) < TOL["pair_sum"]:
                    out["pair_sum"].append(f"{arm} {t}：{cid} の組の和が w_max と違う")
    # P の恒等式：w_Y − w_C ＝ Φ_C·δω（移植した 4 本、標本と T）
    fired_c = W.fired_by_pulse(sp["C"])
    check_at = set(times) | {end}
    for cid in sorted(target_ids):
        dw0 = fork["Y"]["connections"][cid]["weight"] - fork["C"]["connections"][cid]["weight"]
        src, dst = W.unit_of(cid)
        x, y = fork["C"]["connections"][cid]["pre_trace"], fork["C"]["connections"][cid]["post_trace"]
        phi, ratio, kappa = 1.0, SPEC.amplitude / SPEC.w_max, math.exp(-DT / SPEC.trace_tau_seconds)
        for p in range(start, end + 1):
            if p > start:
                f = fired_c.get(p, ())
                pre, post = src in f, dst in f
                phi *= 1.0 - ratio * (x * post + y * pre)
                x, y = x * kappa + pre, y * kappa + post
            if p in check_at:
                sy = (ends if p == end else {a: samples[a][str(p)] for a in ("Y", "C")})
                got = sy["Y"]["connections"][cid]["weight"] - sy["C"]["connections"][cid]["weight"]
                if not abs(got - phi * dw0) < TOL["P_identity"]:
                    out["P_identity"].append(f"{p}：{cid} で w_Y − w_C（{got}）≠ Φ_C·δω（{phi * dw0}）")
    # 分岐の記録の再検証・判定と activity の再構成
    for key, arms_, fd in (("t1", ("C", "I", "Y"), fd1), ("t2", ("I", "Y"), fd2)):
        for name, problems in check_divergence(run, key, arms_, fd, before_start, start, end).items():
            out[name] += problems
    # t2 の分解の恒等式
    if fd2 is not None and fd1 is not None and run["arms"]["t2"] is not None and not out["revalidate_from_raw"]:
        for j, c in (t2_contributions(run, fd1, fd2, start, end) or {}).items():
            if not abs(c["sum"] - c["activity_difference"]) < TOL["t2_decomposition_identity"]:
                out["t2_decomposition_identity"].append(f"{j}：Σ K（{c['sum']}）≠ ã^I − ã^Y（{c['activity_difference']}）")


# ---- 観測（README §5。判定なし） -------------------------------------------------------------------

def relation(a: float, b: float, opposite: str) -> str:
    """向きの関係。0 を向きの一致に数えない（README §5.2）。"""
    if a == 0 and b == 0:
        return "both_zero"
    if a == 0 or b == 0:
        return "one_zero"
    return "same" if (a > 0) == (b > 0) else opposite


def _describe(values: list) -> dict:
    """分布の記述。null の個体は分布に入れず、その個数を併記する（missing_values.null_is_not_zero）。"""
    got = [v for v in values if v is not None]
    return {"n": len(got), "null": len(values) - len(got),
            "median": statistics.median(got) if got else None,
            "min": min(got) if got else None, "max": max(got) if got else None}


def record_run(run: dict, start: int = END, end: int = TOTAL) -> dict:
    u = run["roles"]["units"]
    role = {uid: r for r, uid in u.items()}
    sp = run["arms"]["spikes"]
    fd1 = first_difference(sp["C"], sp["I"])
    fd2 = first_difference(sp["I"], sp["Y"])

    def detail(fd, a: str, b: str):
        if fd is None:
            return None
        t, units = fd
        fa = set(spikes_at(sp[a], t))
        return [{"unit": x, "role": role[x], "fired_in": a if x in fa else b} for x in units]

    t1 = fd1[0] if fd1 else None
    t2 = fd2[0] if fd2 else None
    counts = {arm: {r: sum(1 for _, x in sp[arm] if x == u[r]) for r in W.ROLES} for arm in ("C", "I", "Y")}
    from_t2 = None if t2 is None else {arm: {r: sum(1 for p, x in sp[arm] if x == u[r] and p >= t2) for r in W.ROLES}
                                       for arm in ("I", "Y")}
    k2 = t2_contributions(run, fd1, fd2, start, end)
    k1 = t1_contributions(run, fd1, start, end)
    wT = {arm: _weights(run["endpoints"][arm]["connections"]) for arm in ("C", "I", "Y")}
    pfd = {}
    for name, (a, b) in PAIRS.items():
        cid = W.connection_id(u[a], u[b])
        P, F, D = wT["Y"][cid] - wT["C"][cid], wT["I"][cid] - wT["Y"][cid], wT["I"][cid] - wT["C"][cid]
        pfd[name] = {"P": P, "F": F, "D": D, "P_F": relation(P, F, "opposite"), "D_P": relation(D, P, "reversed")}
    PW, FW, DW = (pfd["AB"][k] - pfd["AC"][k] for k in ("P", "F", "D"))
    return {
        "t1": t1, "U1": detail(fd1, "C", "I"),
        "t2": t2, "U2": detail(fd2, "I", "Y"),
        "t2_minus_t1": None if t2 is None else t2 - t1,
        "remaining_after_t1": None if t1 is None else end - t1,
        "t2_detectable_pulses": None if t1 is None else max(0, end - t1 - 1),
        "spike_counts_per_unit": counts,
        "spike_counts_per_unit_from_t2": from_t2,
        "differing_pulses": {"I_Y": differing_pulses(sp["I"], sp["Y"]), "C_I": differing_pulses(sp["C"], sp["I"]),
                             "C_Y": differing_pulses(sp["C"], sp["Y"])},
        "t2_contributions": None if k2 is None else {role[j]: {"K": {role[s]: v for s, v in c["K"].items()}, "sum": c["sum"]}
                                                     for j, c in k2.items()},
        "t1_contributions": None if k1 is None else {role[j]: {"K": {role[s]: v for s, v in c["K"].items()}, "sum": c["sum"]}
                                                     for j, c in k1.items()},
        "P_F_D": pfd,
        "W_contrast": {"P": PW, "F": FW, "D": DW, "P_F": relation(PW, FW, "opposite"), "D_P": relation(DW, PW, "reversed")},
    }


def category(rec: dict) -> str:
    if rec["t1"] is None:
        return "a_no_t1"
    return "b_t1_no_t2" if rec["t2"] is None else "c_t1_t2"


def summarize(per: dict, individuals: dict) -> dict:
    """数え上げと分布の記述だけ。集団の holds／fails・0.8・区間は置かない。"""
    cats = {c: [int(s) for s, r in per.items() if category(r) == c] for c in ("a_no_t1", "b_t1_no_t2", "c_t1_t2")}
    u2 = [x for r in per.values() for x in (r["U2"] or [])]
    return {
        "individuals": len(per),
        "invalid_individuals": sorted(int(s) for s, v in individuals.items() if not v["valid"]),
        "failed_checks": {k: sum(1 for v in individuals.values() if v["failed_checks"].get(k)) for k in CHECK_NAMES},
        "categories": {c: {"count": len(v), "seeds": v} for c, v in cats.items()},
        "t1": _describe([r["t1"] for r in per.values()]),
        "t2_minus_t1": _describe([r["t2_minus_t1"] for r in per.values()]),
        "U2_roles": {r: sum(1 for x in u2 if x["role"] == r) for r in W.ROLES},
        "U2_fired_in": {a: sum(1 for x in u2 if x["fired_in"] == a) for a in ("I", "Y")},
    }


def analyze(data: dict, mode: str, records: dict | None, before_start: Mapping[str, float] | None = None) -> dict:
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


def analyze_folder(folder: Path, mode: str) -> dict:
    records = G.read_records(folder)
    if not (folder / G.RUNS).exists():
        return {"experiment": EXPERIMENT, "kind": KIND, "mode": mode, "valid": False,
                "problems": ["結果のファイル（runs.json.gz）がない"], "records": records}
    return analyze(read(folder / G.RUNS), mode, records)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "check" if "--check" in sys.argv else "formal"
    folder = Path(args[0]) if args else DEFAULT_DIR
    ALIGN.check(PROTOCOL)
    report = analyze_folder(folder, mode)
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"valid: {report['valid']}")
    for p in report["problems"][:50]:
        print(f"  - {p}")
    bad = {s: v["failed_checks"] for s, v in report.get("individuals", {}).items() if not v["valid"]}
    for s, f in list(bad.items())[:20]:
        print(f"  - seed {s}: {sorted(f)}")
    if mode == "check":
        print("【道具の通しの確認。観測の量は計算していない】")
    elif "summary" in report:
        print("summary:", json.dumps(report["summary"], ensure_ascii=False))
    print(f"saved {folder / 'report.json'}")


if __name__ == "__main__":
    main()
