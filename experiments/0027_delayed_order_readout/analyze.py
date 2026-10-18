"""実験 0027 の記録の解析（確定した事前登録 v0.1 に従う）。正本は protocol.yaml・README。

0023〜0026 の解析の契約（PR #104・#108・#112・#115：記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、
解析の道具の HEAD ＝ 測定の commit）をそのまま引き継ぐ（ほかの実験の analyze.py は読み込まない）。0025 から変えたのは、
本体が O・W1〜W19（M なし）であること、試しの区間が二つ（早い時点：補助、遅い時点：主）になったこと（README §2）、
それに合わせた操作の確認（遅い時点はすべての試し・早い時点は最初と最後の試しで複製の確認、両方の区間の空の側、14101 までの
O の双子、12000 と 13500 の重みの再生）、主の判定が遅い時点の h_late だけになったこと、補助の記録（README §6）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる。
   違えば、何も読まず・書かず、判定の量を計算・表示せずに止まる（判定の量を計算する直前と、解析の終わりにも確かめ直す）
1. 実行の記録（seed ごとの開始・終了の記録、raw の SHA-256・バイト数。guard.py）を確かめる。
   - 未完了（まだ始めていない seed がある。失敗・中断・破損はない）：**解析しない**（何も読まず・書かずに止まる）
   - 失敗・中断・破損・範囲の外の seed・別の測定の commit：実験全体を invalid として、記録と操作の確認だけを報告する（判定しない）
2. 操作の確認（README §7、protocol の checks）を、保存した生の記録から seed ごとに再検証する。1 つでも成り立たなければその個体は
   invalid で、実験全体を invalid とする（judgment.on_any_invalid）。打ち切りの算術は、ほかのすべての確認がすべての個体で
   成り立ったときに最後に確かめる
3. 判定（README §5、protocol の quantities・judgment）：**本番（formal）で、20 個の seed がすべて completed、raw のハッシュが一致、
   すべての個体ですべての確認が成り立ったときだけ**、主・補助の量を計算して report に書く。smoke では判定の量も、現象に関する数値も
   計算・表示・保存しない（操作の確認だけ）
4. report は一度だけ書く（既にあれば上書きしない。解析の記録 analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0027_delayed_order_readout/analyze.py                         # 本番（protocol の execution.output_dir）
  python experiments/0027_delayed_order_readout/analyze.py <フォルダ> --smoke        # smoke（操作の確認だけ。data/experiments の下には書かない）
  （中断の後だけ）--resume：入力の SHA-256 が開始のときと同じで、report がまだないときだけ、計算し直して完了する
"""

import bisect
import gzip
import importlib.util
import itertools
import json
import math
import os
import sys
import time
from collections.abc import Iterable, Mapping
from fractions import Fraction
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
DEFAULT_DIR = Path(PROTOCOL["execution"]["output_dir"])
DATA_ROOT = REPO / "data" / "experiments"          # 本番・他の実験のデータの場所（smoke・合成の report は書かない）
OWN_DIR = REPO / DEFAULT_DIR                       # 本番の report を書いてよい唯一の場所
REPORT, LOG = "report.json", "analysis_log.jsonl"
MODES = ("formal", "smoke", "synthetic")           # synthetic は契約テストの関数呼び出しだけ
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
TOOL_FILES = ("analyze.py", "world.py", "alignment.py", "guard.py", "run.py")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIGN = load(f"alignment_{EXPERIMENT}", REPO / HERE / "alignment.py")
W = load(f"world_{EXPERIMENT}", REPO / HERE / "world.py")
G = load(f"guard_{EXPERIMENT}", REPO / HERE / "guard.py")
SPEC = W.plasticity(PROTOCOL)
W_MAX, W_MIN, AMP = SPEC.w_max, SPEC.w_min, SPEC.amplitude
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
KAPPA = math.exp(-DT / SPEC.trace_tau_seconds)      # 痕跡の 1 Pulse の減り方（本体の規則と同じ式）
TOL = PROTOCOL["checks"]["numeric"]
CENSOR_CHECK = "censor_arithmetic_recomputed"
CHECK_NAMES = list(PROTOCOL["checks"]["exact"]) + list(PROTOCOL["checks"]["numeric"]) + ["revalidate_from_raw"]
UNITS = tuple(PROTOCOL["brain"]["sensory_units"])
WINDOWS = W.WINDOWS                                # ("early", "late")
PRIMARY = "late"


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- 発火の列・状態 ------------------------------------------------------------------------------------

def spikes_of(sp: Mapping, unit: str) -> list[int]:
    return sp.get(unit, [])


def fired_at(sp: Mapping, unit: str, p: int) -> int:
    xs = spikes_of(sp, unit)
    i = bisect.bisect_left(xs, p)
    return int(i < len(xs) and xs[i] == p)


def in_range(sp: Mapping, unit: str, lo: int, hi: int) -> list[int]:
    xs = spikes_of(sp, unit)
    return xs[bisect.bisect_left(xs, lo):bisect.bisect_right(xs, hi)]


def well_formed(sp, lo: int, hi: int, what: str) -> list[str]:
    """Unit → Pulse の列：Unit は設計図の 3 つ、Pulse は整数で lo〜hi、狭義の増加。"""
    if not isinstance(sp, dict):
        return [f"{what}：発火の記録が辞書でない"]
    problems = []
    for u, xs in sp.items():
        if u not in UNITS:
            problems.append(f"{what}：知らない Unit {u!r} の発火")
        elif (not isinstance(xs, list) or any(not isinstance(p, int) or not lo <= p <= hi for p in xs)
              or any(b <= a for a, b in itertools.pairwise(xs))):
            problems.append(f"{what}：{u} の発火の列が {lo}〜{hi} の狭義に増加する整数の列でない")
    return problems


def state_at(body: Mapping, p: int) -> Mapping:
    """本体の Pulse p の終わりの全状態（早い時点・遅い時点のどちらかの範囲の各 Pulse の記録から）。"""
    for w in WINDOWS:
        part = body[w]
        k = p - part["states_from"]
        if 0 <= k < len(part["states"]):
            st = part["states"][k]
            if st["pulse"] != p:
                raise ValueError(f"{body['body']} の Pulse {p} の状態の Pulse が {st['pulse']}")
            return st
    raise ValueError(f"{body['body']} の Pulse {p} の全状態は記録の範囲の外")


# ---- 可塑性の再生（本体の実装を呼ばない、独立な計算。README §7 の重みの再生・切り詰めなし）-----------------------------

def replay(state0: list, src: str, dst: str, sp: Mapping, start: int, end: int, record: Iterable[int] = ()) -> dict:
    """1 本の接続を、start の終わりの状態 [重み, 送り手の痕跡, 受け手の痕跡] から end まで、記録した発火で進め直す。
    返す値：end の状態、record の Pulse の終わりの状態、切り詰め（[w_min, w_max] の外に出た）の Pulse の一覧。"""
    pre, post = set(spikes_of(sp, src)), set(spikes_of(sp, dst))
    w, x, y = state0
    want, at, clipped = set(record), {}, []
    if start in want:
        at[start] = [w, x, y]
    for p in range(start + 1, end + 1):
        pf, qf = p in pre, p in post
        raw = w + (AMP * x * (W_MAX - w) / W_MAX if qf else 0.0) - (AMP * y * w / W_MAX if pf else 0.0)
        if raw > W_MAX or raw < W_MIN:
            clipped.append(p)
        w = min(W_MAX, max(W_MIN, raw))
        x = x * KAPPA + (1.0 if pf else 0.0)
        y = y * KAPPA + (1.0 if qf else 0.0)
        if p in want:
            at[p] = [w, x, y]
    return {"end": [w, x, y], "at": at, "clipped": clipped}


def replay_all(conns0: Mapping[str, list], sp: Mapping, start: int, end: int, record: Iterable[int] = ()) -> dict:
    """6 本の接続をまとめて再生する。返す値：{end: {cid: 状態}, at: {Pulse: {cid: 状態}}, clipped: [(cid, Pulse)]}。"""
    record = tuple(dict.fromkeys(record))
    out = {"end": {}, "at": {p: {} for p in record}, "clipped": []}
    for cid, s0 in conns0.items():
        src, dst = W.unit_of(cid)
        r = replay(s0, src, dst, sp, start, end, record)
        out["end"][cid] = r["end"]
        for p in record:
            out["at"][p][cid] = r["at"][p]
        out["clipped"] += [(cid, p) for p in r["clipped"]]
    return out


def max_diff(a: Mapping[str, list], b: Mapping[str, list]) -> float:
    if set(a) != set(b):
        return math.inf
    return max((abs(u - v) for k in a for u, v in zip(a[k], b[k], strict=True)), default=0.0)


def pair_sum_problems(st: Mapping, what: str) -> list[str]:
    w = {cid: v[0] for cid, v in st["connections"].items()}
    problems = []
    for i, j in itertools.combinations(UNITS, 2):
        dev = abs(w[W.connection_id(i, j)] + w[W.connection_id(j, i)] - W_MAX)
        if not dev <= TOL["pair_sum"]:
            problems.append(f"{what}：組 {i}・{j} の和と w_max の差 {dev}")
    return problems


# ---- 実行の記録 ------------------------------------------------------------------------------------------

def verify_records(out: Path, mode: str, seeds: list[int]) -> dict:
    """seed ごとの開始・終了の記録の確認。state：complete（全 seed が completed）／incomplete（未着手の seed だけがある）／
    failed（失敗・中断・破損・範囲の外・食い違いがある）。"""
    found = G.scan(out)
    problems = list(found["anomalies"])
    statuses = {s: st for s, (st, _) in found["seeds"].items()}
    for s, (st, why) in found["seeds"].items():
        if s not in seeds:
            problems.append(f"範囲の外・余分な seed {s}（{st}）がある（穴埋め・混入をしない）")
        if st in ("failed", "started", "broken"):
            problems.append(f"seed {s} が {st}" + (f"（{'; '.join(why)}）" if why else ""))
    missing = [s for s in seeds if statuses.get(s, "absent") == "absent"]
    commits, shas = set(), set()
    for s in sorted(statuses):                        # 開始の記録があるすべての seed（completed 以外も）の測定の commit
        try:
            st = G.read_seed(out, s)["start"]
        except (OSError, ValueError):
            st = None
        if isinstance(st, dict):
            commits.add(st.get("measurement_commit"))
    for s in seeds:
        if statuses.get(s) != "completed":
            continue
        r = G.read_seed(out, s)
        st, fin = r["start"], r["finish"]
        if any(x.get(k) != v for x in (st, fin) for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode))):
            problems.append(f"seed {s} の開始・終了の記録の experiment・kind・mode が {EXPERIMENT}・{KIND}・{mode} ではない")
        if not G.SHA_RE.match(str(st.get("measurement_commit"))) or fin.get("measurement_commit_end") != st.get("measurement_commit"):
            problems.append(f"seed {s} の測定の commit が 40 桁でないか、開始と終了で違う")
        shas.add(st.get("protocol_sha256"))
    if len(commits) > 1:
        problems.append(f"seed によって測定の commit が違う（{sorted(map(str, commits))}）")
    if shas and shas != {G.sha256_file(REPO / PROTOCOL_PATH)}:
        problems.append("開始の記録の protocol.yaml の SHA-256 が今のものと違う")
    state = "failed" if problems else ("incomplete" if missing else "complete")
    commit = next(iter(commits)) if len(commits) == 1 else None
    return {"state": state, "problems": problems, "missing": missing,
            "statuses": {str(s): statuses.get(s, "absent") for s in sorted(set(seeds) | set(statuses))},
            "measurement_commit": commit if G.SHA_RE.match(str(commit)) else None}


def verify_analysis_commit(repo: Path, commit: str | None) -> str:
    """解析する道具の commit（このファイルがあるリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーが
    その commit と一致すること（変更・未追跡のファイルがない）。だめなら GuardError：判定の量を計算・表示せず、何も書かずに止まる。"""
    if commit is None:
        raise G.GuardError("測定の commit が 1 つに定まらない（開始の記録がないか、seed によって違うか、40 桁でない）。解析しない")
    try:
        return G.verify_clean_commit(repo, commit)
    except G.GuardError as e:
        raise G.GuardError(f"解析の道具が測定の commit {commit} のままではない。解析しない：{e}") from e


def preconditions(out: Path, mode: str, seeds: list[int], repo: Path) -> tuple[dict, str]:
    """解析の前提（何も読まず・書かずに止まる側の確認）：記録が未完了でないこと、HEAD ＝ 測定の commit、作業ツリーがきれいなこと。"""
    records = verify_records(out, mode, seeds)
    if records["state"] == "incomplete":
        raise G.GuardError(f"未完了（まだ始めていない seed：{records['missing']}）。20 個体の完了の前には集計しない")
    return records, verify_analysis_commit(repo, records["measurement_commit"])


# ---- 操作の確認（README §7）--------------------------------------------------------------------------------

def check_seed(data: dict, mode: str, seed: int, plan, start_record: Mapping | None = None) -> dict[str, list[str]]:
    """保存した生の記録から、1 個体の操作の確認（censor_arithmetic_recomputed を除く）。確認の名前 → 成り立たなかった理由。"""
    out = {k: [] for k in CHECK_NAMES if k != CENSOR_CHECK}
    try:
        _check_structure(data, mode, seed, plan, start_record, out)
        if out["revalidate_from_raw"]:
            return out
        run = data["run"]
        _check_labels(run, seed, plan, out)
        _check_inputs(run, seed, plan, out)
        _check_before_divergence(run, plan, out)
        _check_probes(run, seed, plan, out)
        _check_empty_side(run, plan, out)
        _check_twin(run, plan, out)
        _check_replay(run, plan, out)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        out["revalidate_from_raw"].append(f"記録の形が想定と違う（{e!r}）")
    return out


def _with_states(plan, w: str, t0: int) -> bool:
    """A の複製に 4 時点の全状態を残す試しか（遅い時点はすべて、早い時点は最初と最後だけ：protocol の records）。"""
    probes = plan.probes(w)
    return w == "late" or t0 in (probes[0], probes[-1])


def _check_structure(data, mode, seed, plan, start_record, out) -> None:
    bad = out["revalidate_from_raw"]
    meta, run = data.get("meta") or {}, data.get("run") or {}
    if (meta.get("experiment"), meta.get("kind"), meta.get("mode"), meta.get("seed")) != (EXPERIMENT, KIND, mode, seed):
        bad.append("raw の experiment・kind・mode・seed が想定と違う")
    if start_record is not None and (meta.get("measurement_commit"), meta.get("protocol_sha256")) != (
            start_record.get("measurement_commit"), start_record.get("protocol_sha256")):
        bad.append("raw の測定の commit・protocol の SHA-256 が開始の記録と違う")
    if meta.get("protocol") != PROTOCOL:
        bad.append("raw の protocol が今の protocol.yaml と違う")
    if meta.get("manifest") != W.manifest_raw(PROTOCOL):
        bad.append("raw の設計図が今の設計図と違う")
    if run.get("seed") != seed:
        bad.append("結果の seed がフォルダの seed と違う")
    if run.get("plan") != plan.as_dict():
        bad.append("raw の Plan（経験・遅れ・二つの試しの区間・窓・本体の終わり）が想定と違う")
    if run.get("roles") != {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)}:
        bad.append("役の割り当てが (seed − 1) mod 6 と違う")
    bodies = run.get("bodies") or {}
    if tuple(bodies) != W.BODIES or "O_twin" not in run:
        bad.append(f"本体が {W.BODIES} と O の双子ではない")
        return
    for b, rec in bodies.items():
        bad += well_formed(rec["spikes"], 1, plan.body_end, f"{b} の本体")
        for w in WINDOWS:
            part, (lo, hi), probes = rec[w], plan.state_range(w), plan.probes(w)
            if part["states_from"] != lo or len(part["states"]) != hi - lo + 1:
                bad.append(f"{b}（{w}）：各 Pulse の状態の範囲が {lo}〜{hi} ではない")
            elif any(st["pulse"] != lo + k for k, st in enumerate(part["states"])):
                bad.append(f"{b}（{w}）：各 Pulse の状態の Pulse の番号が並んでいない")
            if [c["t0"] for c in part["probes"]] != list(probes):
                bad.append(f"{b}（{w}）：試しの t0 が {probes[0]}〜{probes[-1]} の全件ではない")
            for c in part["probes"]:
                t0 = c["t0"]
                bad += well_formed(c["spikes"], t0, t0 + 1 + plan.window, f"{b}（{w}）の t0 {t0} の A の複製")
                if _with_states(plan, w, t0):
                    if {k: v["pulse"] for k, v in c.get("states", {}).items()} != {
                            "t0-1": t0 - 1, "t0": t0, "t0+1": t0 + 1, "end": t0 + 1 + plan.window}:
                        bad.append(f"{b}（{w}）の t0 {t0}：A の複製の 4 時点の全状態がない・時点が違う")
                elif "states" in c:
                    bad.append(f"{b}（{w}）の t0 {t0}：最初と最後以外の早い時点の試しに全状態がある（記録の項目と違う）")
            if [c["t0"] for c in part["empty_side"]] != [probes[0], probes[-1]]:
                bad.append(f"{b}（{w}）：空の側の複製が最初と最後の試しではない")
            for c in part["empty_side"]:
                bad += well_formed(c["spikes"], c["t0"], c["t0"] + 1 + plan.window, f"{b}（{w}）の空の側の複製 {c['t0']}")
    tw = run["O_twin"]
    bad += well_formed(tw["spikes"], 1, plan.body_end, "O の双子")
    if (tw["state_experience_end"]["pulse"], tw["state_late_start"]["pulse"], tw["state_end"]["pulse"]) != (
            plan.experience_end, plan.state_range("late")[0], plan.body_end):
        bad.append("O の双子の状態の時点が想定と違う")
    if any(k in tw for k in WINDOWS):
        bad.append("O の双子に試しの記録がある")


def _check_labels(run, seed, plan, out) -> None:
    bad = out["stimulus_labels"]
    s, bodies = PROTOCOL["stimulus"], run["bodies"]
    rec = {b: [tuple(x) for x in bodies[b]["labels"]] for b in W.BODIES}
    o_times = [t for t, _ in rec["O"]]
    to_role = {r: role for role, r in W.role_receptors(PROTOCOL, seed).items()}
    for b in W.BODIES:
        labels = rec[b]
        if labels != W.labels_of(PROTOCOL, plan, seed, b):
            bad.append(f"{b}：札の列が protocol の作り方と違う")
        if [t for t, _ in labels] != o_times or len(set(o_times)) != len(o_times):
            bad.append(f"{b}：刺激の時刻の集合が O と違うか、同じ Pulse に 2 つの刺激がある")
        for role in W.ROLES:
            if sum(1 for _, x in labels if x == role) != plan.trials:
                bad.append(f"{b}：{role} の数が {plan.trials} ではない")
        got = sorted((p, to_role[r]) for p, r in bodies[b]["sensory"] if p <= plan.experience_end)
        if got != sorted(labels):
            bad.append(f"{b}：本体が受けた感覚の出来事が札の列と違う")
        want_rng = W.rng_name(seed, W.shuffle_index(b)) if b in W.SHUFFLES else None
        if bodies[b]["rng"] != want_rng or (want_rng is not None and want_rng != PROTOCOL["conditions"]["within_trial_shuffles"]
                                            ["rng"].format(i=W.shuffle_index(b), seed=seed)):
            bad.append(f"{b}：試行の中の並べ替えの乱数の流れの名前が protocol と違う（{bodies[b]['rng']!r}）")
        at_b = dict(labels)
        for slots in W.trial_slots(PROTOCOL, plan):                   # 試行の中の釣り合い
            if sorted(at_b.get(t, "") for t in slots) != list(W.ROLES):
                bad.append(f"{b}：試行（{slots[0]} から）の 3 つの枠に A・B・C が 1 回ずつ来ていない")
                break
        if b != "O" and bodies[b]["first_divergence_from_O"] != W.first_label_divergence(rec["O"], labels):
            bad.append(f"{b}：札が O と最初に違う Pulse の記録が違う")
    at = dict(rec["O"])
    for t, x in rec["O"]:
        if x == "A" and (at.get(t + s["b_offset"]) != "B" or at.get(t + s["c_offset"]) != "C"):
            bad.append(f"O：A（{t}）の後の B・C の形が違う")
            break
    for b in W.SHUFFLES:
        if sorted(x for _, x in rec[b]) != sorted(x for _, x in rec["O"]):
            bad.append(f"{b}：札の多重集合が O と違う")
    if len(rec["O"]) != 3 * plan.trials:
        bad.append(f"O：刺激の数が 3 × 試行の数（{3 * plan.trials}）ではない")


def _check_inputs(run, seed, plan, out) -> None:
    bad = out["input_free_after_experience"]
    a_rec = W.role_receptors(PROTOCOL, seed)["A"]
    for b, rec in run["bodies"].items():
        if any(p > plan.experience_end for p, _ in rec["sensory"]):
            bad.append(f"{b}：経験の後に感覚の出来事がある")
        for w in WINDOWS:
            for c in rec[w]["probes"]:
                if c["sensory"] != [[c["t0"], a_rec]]:
                    bad.append(f"{b}（{w}）の t0 {c['t0']}：A の複製の感覚の出来事が t0 の A の 1 つだけではない")
            for c in rec[w]["empty_side"]:
                if c["sensory"]:
                    bad.append(f"{b}（{w}）の空の側の複製 {c['t0']} に感覚の出来事がある")
    tw = run["O_twin"]
    if any(p > plan.experience_end for p, _ in tw["sensory"]) or tw["sensory"] != run["bodies"]["O"]["sensory"]:
        bad.append("O の双子の感覚の出来事が O の本体と違うか、経験の後にある")


def _check_before_divergence(run, plan, out) -> None:
    bad = out["identical_before_label_divergence"]
    bodies = run["bodies"]
    o = bodies["O"]
    want_o = set()
    for b in W.BODIES[1:]:
        rec, d = bodies[b], bodies[b]["first_divergence_from_O"]
        if rec["birth"] != o["birth"] or rec["dynamics"] != o["dynamics"]:
            bad.append(f"{b}：出生時の状態が O と違う")
            continue
        if d is None:                                 # 札がすべて同じ：全体が同じはず
            if rec["spikes"] != o["spikes"] or any(rec[w]["states"] != o[w]["states"] for w in WINDOWS):
                bad.append(f"{b}：札が O と同じなのに軌道が違う")
            continue
        if d - 1 > 0:
            want_o.add(str(d - 1))
            if set(rec["before_divergence"]) != {str(d - 1)}:
                bad.append(f"{b}：札が分かれる前の状態の記録が {d - 1} だけではない")
            elif rec["before_divergence"][str(d - 1)] != o["before_divergence"].get(str(d - 1)):
                bad.append(f"{b}：札が分かれる前（{d - 1} の終わり）の全状態が O と違う")
        for u in UNITS:
            if in_range(rec["spikes"], u, 1, d - 1) != in_range(o["spikes"], u, 1, d - 1):
                bad.append(f"{b}：札が分かれる前（{d} より前）の {u} の発火が O と違う")
    if set(o["before_divergence"]) != want_o:
        bad.append("O の、札が分かれる前の状態の記録の時点が想定と違う")


def _check_probes(run, seed, plan, out) -> None:
    clone_bad, ident_bad, p3_bad = (out["probe_clone_equals_body_t0_minus_1"], out["identical_through_t0_plus_1"],
                                    out["proposition_3"])
    units = W.role_units(PROTOCOL, seed)
    a_rec = W.role_receptors(PROTOCOL, seed)["A"]
    m = parse_neuroarchitecture(W.manifest_raw(PROTOCOL))
    w_in = next(p.weight for p in m.projections if p.source_id == a_rec and p.target_id == units["A"])
    for b, rec in run["bodies"].items():
        for w in WINDOWS:
            for c in rec[w]["probes"]:
                t0, sp = c["t0"], c["spikes"]
                if _with_states(plan, w, t0):        # 遅い時点はすべての試し、早い時点は最初と最後の試し
                    st = c["states"]
                    if st["t0-1"] != state_at(rec, t0 - 1):
                        clone_bad.append(f"{b}（{w}）の t0 {t0}：A の複製の t0 − 1 の全状態が本体と違う")
                    for key, p in (("t0", t0), ("t0+1", t0 + 1)):
                        body = state_at(rec, p)
                        for role in ("B", "C"):
                            u = units[role]
                            if st[key]["units"][u] != body["units"][u]:
                                ident_bad.append(f"{b}（{w}）の t0 {t0}：{role} の Unit の状態が {key} の終わりで本体と違う")
                            if fired_at(sp, u, p) != fired_at(rec["spikes"], u, p):
                                ident_bad.append(f"{b}（{w}）の t0 {t0}：{role} の {key} の発火が本体と違う")
                    body_t0 = state_at(rec, t0)
                    if st["t0"]["connections"] != body_t0["connections"]:
                        ident_bad.append(f"{b}（{w}）の t0 {t0}：t0 の終わりの重み・痕跡が本体と違う")
                    if st["t0"]["drives"] != sorted(body_t0["drives"] + [[a_rec, units["A"], w_in, t0]]):
                        ident_bad.append(f"{b}（{w}）の t0 {t0}：t0 の終わりの駆動が、本体のものに A の入力の駆動を足したものと違う")
                for role in ("B", "C"):              # 命題 3：両方の区間のすべての試し
                    u = units[role]
                    if fired_at(sp, u, t0 + 2) < fired_at(rec["spikes"], u, t0 + 2):
                        p3_bad.append(f"{b}（{w}）の t0 {t0}：{role}^A(t0 + 2) ≥ {role}^∅(t0 + 2) が成り立たない")


def _check_empty_side(run, plan, out) -> None:
    bad = out["empty_side_identity"]
    for b, rec in run["bodies"].items():
        for w in WINDOWS:
            for c in rec[w]["empty_side"]:
                t0, end = c["t0"], c["t0"] + 1 + plan.window
                if any(in_range(c["spikes"], u, t0, end) != in_range(rec["spikes"], u, t0, end) for u in UNITS):
                    bad.append(f"{b}（{w}）の空の側の複製 {t0}：窓の終わりまでの発火が本体と違う")
                if c["states_from"] != t0 - 1 or len(c["states"]) != end - t0 + 2:
                    bad.append(f"{b}（{w}）の空の側の複製 {t0}：状態の範囲が t0 − 1〜窓の終わりではない")
                    continue
                for k, st in enumerate(c["states"]):
                    if st != state_at(rec, t0 - 1 + k):
                        bad.append(f"{b}（{w}）の空の側の複製 {t0}：Pulse {t0 - 1 + k} の終わりの全状態が本体と違う")
                        break


def _check_twin(run, plan, out) -> None:
    """命題 0（README §2.3）：試しの複製を一度も作らない O の双子が、O の本体と終わりまで一致する。"""
    bad = out["O_twin_identity"]
    o, tw = run["bodies"]["O"], run["O_twin"]
    if tw["birth"] != o["birth"] or tw["dynamics"] != o["dynamics"]:
        bad.append("O の双子の出生時の状態が O と違う")
    if {u: spikes_of(tw["spikes"], u) for u in UNITS} != {u: spikes_of(o["spikes"], u) for u in UNITS}:
        bad.append("O の双子の 1〜終わりの発火が O の本体と違う")
    for key, p in (("state_experience_end", plan.experience_end), ("state_late_start", plan.state_range("late")[0]),
                   ("state_end", plan.body_end)):
        if tw[key] != state_at(o, p):
            bad.append(f"O の双子の Pulse {p} の終わりの全状態が O の本体と違う")


def _check_replay(run, plan, out) -> None:
    """重みの再生（12000・遅い時点の始まり）・組の和・切り詰めなし。再生は本体の実装を呼ばない独立な計算（replay）。"""
    init = W.initial_connections(PROTOCOL)
    late_start = plan.state_range("late")[0]
    starts = [t0 - 1 for w in WINDOWS for t0 in plan.probes(w)]
    for b, rec in run["bodies"].items():
        if rec["birth"]["connections"] != init:
            out["replay_history_12000"].append(f"{b}：出生時の接続の状態が設計図の初期値（痕跡 0）と違う")
        r = replay_all(init, rec["spikes"], 0, plan.body_end, [plan.experience_end, late_start] + starts)
        if not max_diff(r["at"][plan.experience_end], state_at(rec, plan.experience_end)["connections"]) \
                <= TOL["replay_history_12000"]:
            out["replay_history_12000"].append(f"{b}：{plan.experience_end} の再生と記録の重み・痕跡が一致しない")
        if not max_diff(r["at"][late_start], state_at(rec, late_start)["connections"]) <= TOL["replay_history_late_start"]:
            out["replay_history_late_start"].append(f"{b}：{late_start} の再生と記録の重み・痕跡が一致しない")
        if not max_diff(r["end"], state_at(rec, plan.body_end)["connections"]) <= TOL["replay_history_12000"]:
            out["no_clipping"].append(f"{b}：切り詰めの監査に使う再生が、終わりの記録と一致しない")
        if r["clipped"]:
            out["no_clipping"].append(f"{b}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
        for t in (plan.experience_end, late_start, plan.body_end):
            out["pair_sum"] += pair_sum_problems(state_at(rec, t), f"{b}：Pulse {t}")
        for w in WINDOWS:
            for c in rec[w]["probes"]:               # すべての試しの A の複製：本体の再生の t0 − 1 から
                t0, end = c["t0"], c["t0"] + 1 + plan.window
                rc = replay_all(r["at"][t0 - 1], c["spikes"], t0 - 1, end)
                if rc["clipped"]:
                    out["no_clipping"].append(f"{b}（{w}）の t0 {t0}：A の複製の重みが [w_min, w_max] の外に出た")
                if "states" in c and not max_diff(rc["end"], c["states"]["end"]["connections"]) <= TOL["replay_history_12000"]:
                    out["no_clipping"].append(f"{b}（{w}）の t0 {t0}：A の複製の再生が窓の終わりの記録と一致しない")
        recorded = [s for w in WINDOWS for s in rec[w]["states"]] + [
            s for w in WINDOWS for c in rec[w]["probes"] for s in c.get("states", {}).values()]
        if any(not W_MIN <= v[0] <= W_MAX for s in recorded for v in s["connections"].values()):
            out["no_clipping"].append(f"{b}：記録した重みに [w_min, w_max] の外の値がある")


# ---- 打ち切りの算術（最後に確かめる）と、試しの材料 ---------------------------------------------------------------

def _first_route1(sp: Mapping, u: str, lo: int, hi: int, censor: int) -> tuple[int, int]:
    """経路 1：二分探索。窓の中の最初の発火（なければ censor）と、窓の中の発火の数。"""
    xs = in_range(sp, u, lo, hi)
    return (xs[0] if xs else censor), len(xs)


def _first_route2(fired: Mapping[int, set], u: str, lo: int, hi: int, censor: int) -> tuple[int, int]:
    """経路 2：窓の各 Pulse を順に見る（経路 1 と独立）。"""
    first, n = censor, 0
    for p in range(lo, hi + 1):
        if u in fired.get(p, ()):
            n += 1
            if first == censor:
                first = p
    return first, n


def _by_pulse(sp: Mapping) -> dict[int, set]:
    out: dict[int, set] = {}
    for u, xs in sp.items():
        for p in xs:
            out.setdefault(p, set()).add(u)
    return out


def _rows(name: str, rec: Mapping, probes: list, units: Mapping, plan, problems: list[str]) -> list[tuple]:
    body_fired = _by_pulse(rec["spikes"])
    rows = []
    for c in probes:
        t0 = c["t0"]
        lo, hi, censor = t0 + 2, t0 + 1 + plan.window, t0 + 2 + plan.window
        copy_fired = _by_pulse(c["spikes"])
        row_n, row_N = [], []
        for role in ("B", "C"):
            u = units[role]
            for side, sp, fired in (("A", c["spikes"], copy_fired), ("0", rec["spikes"], body_fired)):
                r1, r2 = _first_route1(sp, u, lo, hi, censor), _first_route2(fired, u, lo, hi, censor)
                if r1 != r2:
                    problems.append(f"{name} の t0 {t0}：{role}・{side} の側の最初の発火・数が 2 通りの計算で違う")
                n, cnt = r1
                if not (lo <= n <= hi or n == censor) or ((n == censor) != (cnt == 0)):
                    problems.append(f"{name} の t0 {t0}：{role}・{side} の側の打ち切りの不変条件が成り立たない")
                row_n.append(n)
                row_N.append(cnt)
        rows.append(tuple(row_n + row_N))
    return rows


def probe_table(run: dict, seed: int, plan) -> tuple[dict[str, dict[str, list[tuple]]], list[str]]:
    """試しの材料：{区間: {本体: 行}}。行は試しごとの (nA_B, n0_B, nA_C, n0_C, NA_B, N0_B, NA_C, N0_C)。n は窓 [t0 + 2, t0 + 1 + T_w]
    の中の最初の発火（なければ t0 + 2 + T_w）、N は窓の中の発火の数。2 通りの計算が一致し、打ち切りの不変条件が成り立つことを
    確かめる。値は返すが、呼び出し側は確認がすべて成り立ったときだけ使う。"""
    units = W.role_units(PROTOCOL, seed)
    problems: list[str] = []
    table = {w: {b: _rows(f"{b}（{w}）", rec, rec[w]["probes"], units, plan, problems) for b, rec in run["bodies"].items()}
             for w in WINDOWS}
    return table, problems


# ---- 判定の量（本番・合成で、すべての確認が成り立ったときだけ。README §4〜§6）----------------------------------------------

def frac(x: Fraction) -> dict:
    return {"exact": f"{x.numerator}/{x.denominator}", "value": float(x)}


def body_quantities(rows: list[tuple], probes: tuple, window: int) -> dict:
    """1 つの本体・1 つの区間の量（Fraction）。L ＝ mean(ℓ_B − ℓ_C)、ℓ_X ＝ n_X^∅ − n_X^A。"""
    P = len(rows)
    lB = [r[1] - r[0] for r in rows]
    lC = [r[3] - r[2] for r in rows]
    censor_counts = {"B_A": 0, "B_null": 0, "C_A": 0, "C_null": 0}
    for (t0, r) in zip(probes, rows):
        c = t0 + 2 + window
        for k, v in zip(("B_A", "B_null", "C_A", "C_null"), r[:4]):
            censor_counts[k] += v == c
    return {"L": Fraction(sum(b - c for b, c in zip(lB, lC)), P),
            "L_B": Fraction(sum(lB), P), "L_C": Fraction(sum(lC), P),
            "censor_counts": censor_counts}


def outside(x: Fraction, refs: list[Fraction]) -> bool:
    """README §5.1：x ＞ max または x ＜ min（厳密な不等号。等号は外にない）。"""
    return x > max(refs) or x < min(refs)


def silence_counts(per_body: Mapping[str, dict], n_probes: int) -> dict[str, int]:
    """README §6・protocol の silence_counts（補助の記録。判定に使わない・個体を除く理由にしない。0024・0025 と同じ定義）：
    20 本体のうち、B（C）が両方の側で、すべての試しで窓の中で発火しなかった本体の数。"""
    return {role: sum(q["censor_counts"][f"{role}_A"] == n_probes and q["censor_counts"][f"{role}_null"] == n_probes
                      for q in per_body.values())
            for role in ("B", "C")}


def window_eval(per_body: Mapping[str, dict], n_probes: int) -> dict:
    """1 つの区間の、O が W の外にあるか（README §5.1・§6）と補助。"""
    if tuple(per_body) != W.BODIES:
        raise ValueError(f"本体が {W.BODIES} ではない")
    o = per_body["O"]["L"]
    s = [per_body[b]["L"] for b in W.SHUFFLES]
    return {"outside": outside(o, s),
            "direction": "above_max" if o > max(s) else ("below_min" if o < min(s) else None),
            "rank_of_L_O_among_20": {"shuffles_below": sum(x < o for x in s), "shuffles_equal": sum(x == o for x in s),
                                     "shuffles_above": sum(x > o for x in s)},
            "frozen": len(set(s + [o])) == 1,
            "silence_counts": silence_counts(per_body, n_probes)}


def individual(per: Mapping[str, Mapping[str, dict]], n_probes: Mapping[str, int]) -> dict:
    """1 個体の評価：主は遅い時点（late）、早い時点（early）は記録だけ。"""
    return {w: window_eval(per[w], n_probes[w]) for w in WINDOWS}


def binom_tail(n: int, p: Fraction, k: int) -> Fraction:
    """P(Bin(n, p) ≥ k)（厳密）。"""
    return sum((math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)), Fraction(0))


def clopper_pearson(h: int, n: int, level: float = 0.95) -> list[float]:
    """h／n の Clopper–Pearson の区間（補助記録。独立・同じ確率の二項モデルの前提に依る参考値。判定に使わない）。"""
    a = (1 - level) / 2

    def cdf(k: int, p: float) -> float:
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k + 1))

    def solve(f, target: float) -> float:          # f は p に対して単調。二分法
        lo, hi = 0.0, 1.0
        inc = f(1.0) > f(0.0)
        for _ in range(200):
            mid = (lo + hi) / 2
            if (f(mid) < target) == inc:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if h == 0 else solve(lambda p: 1 - cdf(h - 1, p), a)
    upper = 1.0 if h == n else solve(lambda p: cdf(h, p), a)
    return [lower, upper]


def judgment(per_seed: Mapping[str, dict]) -> dict:
    """個体をまたぐ判定（README §5.2。遅い時点の h_late だけ）と補助の数え上げ（README §6。早い時点は記録だけで、比べない）。"""
    ind = {s: v["individual"] for s, v in per_seed.items()}
    n = len(ind)
    threshold = ALIGN.HOLDS_MIN_H
    h = {w: sum(v[w]["outside"] for v in ind.values()) for w in WINDOWS}
    table = {f"early_{'outside' if e else 'not_outside'}__late_{'outside' if l else 'not_outside'}":
             sum(v["early"]["outside"] == e and v["late"]["outside"] == l for v in ind.values())
             for e in (True, False) for l in (True, False)}
    j = PROTOCOL["judgment"]
    return {"h_late": h["late"], "n": n, "holds": h["late"] >= threshold, "holds_if": f"h >= {threshold}",
            "h_early": h["early"], "early_late_table": table,
            "direction_counts": {w: {"above_max": sum(v[w]["direction"] == "above_max" for v in ind.values()),
                                     "below_min": sum(v[w]["direction"] == "below_min" for v in ind.values())} for w in WINDOWS},
            "frozen_individuals": {w: sum(v[w]["frozen"] for v in ind.values()) for w in WINDOWS},
            "clopper_pearson_95_of_h_over_n": {w: clopper_pearson(h[w], n) for w in ("late", "early")},
            "scope": j["scope"], "not_judged": j["not_judged"],
            "note": ("主の判定は遅い時点（経験の終わりから 5τ_a 後に始まる 300 回の試し）の h_late だけ。成立は、全個体での交換可能性"
                     "（試行の中の並べ替え W に対して）という帰無仮説を、個体間の独立性という統計モデル上の前提のもとで水準 0.05 で棄却すること"
                     "（交換可能性の破れの証明ではない）。持続の機構・二つの区間のあいだの減衰・記憶の成立は判定しない。h_early・"
                     "early_late_table・Clopper–Pearson の区間・silence_counts は補助の記録で、判定に使わず、h_late と比べない")}


def quantities_for_seed(table: Mapping[str, Mapping[str, list[tuple]]], plan) -> dict:
    per = {w: {b: body_quantities(rows, plan.probes(w), plan.window) for b, rows in table[w].items()} for w in WINDOWS}
    out_bodies = {w: {b: {k: (frac(x) if isinstance(x, Fraction) else x) for k, x in q.items()} for b, q in v.items()}
                  for w, v in per.items()}
    return {"bodies": out_bodies, "individual": individual(per, {w: len(plan.probes(w)) for w in WINDOWS})}


# ---- 解析の本体 --------------------------------------------------------------------------------------------

def analyze(out: Path, mode: str, plan=None, seeds: list[int] | None = None, repo: Path = REPO) -> dict:
    """読むだけ（どこにも書かない）。mode：formal・smoke・synthetic（synthetic は契約テストだけ。plan・seeds を渡す）。

    記録が未完了（未着手の seed だけがある）、または解析する道具の HEAD が測定の commit と違う・作業ツリーがきれいでないなら
    GuardError（解析しない）。HEAD・作業ツリーは、判定の量を計算する直前と、解析の終わりにも確かめ直す。"""
    if mode not in MODES:
        raise G.GuardError(f"未知の mode（{mode}）")
    if mode == "synthetic":
        if plan is None or not seeds or any(s not in expected_seeds("synthetic") for s in seeds):
            raise G.GuardError("synthetic は契約テストだけ（合成の範囲の seed と Plan を渡す）")
    else:
        if plan is not None or seeds is not None:
            raise G.GuardError("本番・smoke は protocol の Plan と seed の範囲だけを使う")
        plan, seeds = W.plan_from(PROTOCOL), expected_seeds(mode)
    records, head = preconditions(out, mode, seeds, repo)
    base = {"experiment": EXPERIMENT, "kind": KIND, "mode": mode, "seeds": seeds, "plan": plan.as_dict(),
            "records": records, "analysis_commit": head}
    checks, invalid = {}, []
    for s in seeds:
        if records["statuses"].get(str(s)) != "completed":
            continue
        start = G.read_seed(out, s)["start"]
        data = read_raw(G.seed_dir(out, s) / G.RAW)
        checks[str(s)] = check_seed(data, mode, s, plan, start)
        if any(checks[str(s)].values()):
            invalid.append(s)
        del data
    censor = "not_evaluated"
    tables = {}
    if records["state"] == "complete" and not invalid:
        censor = "evaluated"
        for s in seeds:
            data = read_raw(G.seed_dir(out, s) / G.RAW)
            tables[str(s)], problems = probe_table(data["run"], s, plan)
            checks[str(s)][CENSOR_CHECK] = problems
            if problems:
                invalid.append(s)
            del data
    verify_analysis_commit(repo, records["measurement_commit"])     # 確認の途中で道具が変わっていない
    valid = records["state"] == "complete" and not invalid and censor == "evaluated"
    report = base | {"valid": valid, "invalid_seeds": sorted(set(invalid)), "censor_arithmetic": censor,
                     "checks": {s: {k: v for k, v in c.items() if v} for s, c in checks.items()},
                     "checks_evaluated": {s: sorted(c) for s, c in checks.items()}}
    if not valid:
        tables.clear()
        return report | {"judgment": None, "note": (
            "invalid か記録の問題があるので、判定の量（L・外にあるか・h・補助の量）は計算も表示もしない"
            "（judgment.on_any_invalid）。invalid を「外にない」に数えない")}
    if mode == "smoke":
        tables.clear()
        return report | {"judgment": None, "note": "smoke（操作の確認だけ）。判定の量も現象に関する数値も計算・表示・保存していない"}
    per_seed = {s: quantities_for_seed(tables[s], plan) for s in tables}
    result = report | {"judgment": judgment(per_seed), "per_seed": per_seed,
                       "note": "事前登録した検証。主の判定は遅い時点の h_late だけ。補助は記録で、主の不成立を救わない"}
    verify_analysis_commit(repo, records["measurement_commit"])     # 終わりに確かめ直す（変わっていれば捨てて止まる）
    return result


# ---- report の公開（一度だけ）---------------------------------------------------------------------------------

def report_destination(folder: Path, mode: str, resume: bool = False) -> Path:
    """report を書いてよい場所。だめなら GuardError（何も読まず・書かずに止まる）。"""
    f, root, own = folder.resolve(), DATA_ROOT.resolve(), OWN_DIR.resolve()
    if mode == "formal":
        if f != own:
            raise G.GuardError(f"本番の解析の report は {DEFAULT_DIR} にだけ書く（{folder} には書かない）")
    elif mode in ("smoke", "synthetic"):
        if f == root or root in f.parents:
            raise G.GuardError(f"{mode} の解析の report は data/experiments の下（{folder}）に書かない")
    else:
        raise G.GuardError(f"未知の mode（{mode}）")
    if (f / REPORT).exists():
        raise G.GuardError(f"{f / REPORT} が既にある（上書きしない。集計は一度だけ）")
    if (f / LOG).exists() and not resume:
        raise G.GuardError(f"{f / LOG} が既にある（解析は一度だけ。report のない中断の後なら --resume）")
    return f / REPORT


def analysis_context(folder: Path, mode: str) -> dict:
    """解析の入力の SHA-256（seed ごとの記録と raw、protocol、道具）。"""
    seeds = {}
    for s, _ in G.scan(folder)["seeds"].items():
        d = G.seed_dir(folder, s)
        seeds[str(s)] = {n: (G.sha256_file(d / n) if (d / n).exists() else None) for n in (G.START, G.FINISH, G.RAW)}
    return {"experiment": EXPERIMENT, "kind": KIND, "mode": mode, "seeds": seeds,
            "protocol_sha256": G.sha256_file(REPO / PROTOCOL_PATH),
            "tool_sha256": {n: G.sha256_file(REPO / HERE / n) for n in TOOL_FILES}}


def _append(folder: Path, event: dict, create: bool = False) -> None:
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | (os.O_EXCL if create else 0)
    fd = os.open(folder / LOG, flags, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(event | {"time_unix": time.time()}, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def publish(folder: Path, mode: str, resume: bool = False, plan=None, seeds: list[int] | None = None,
            repo: Path = REPO) -> dict:
    """解析して report を一度だけ書く。返す値：report の中身。
    記録が未完了・解析の道具が測定の commit のままでないなら、解析の記録も report も書かずに止まる。"""
    report_destination(folder, mode, resume)
    want = seeds if mode == "synthetic" else expected_seeds(mode)
    preconditions(folder, mode, want, repo)          # 読むだけ（だめなら run.lock も作らずに止まる）
    with G.session_lock(folder):                     # 実行中なら解析しない
        preconditions(folder, mode, want, repo)      # 鍵を取ったあとで確かめ直す
        context = analysis_context(folder, mode)
        if resume:
            events = [json.loads(x) for x in (folder / LOG).read_text(encoding="utf-8").splitlines()]
            if not events or events[0].get("event") != "started" or any(e.get("event") == "completed" for e in events):
                raise G.GuardError("再開できる解析の記録ではない（手動の監査の判断に委ねる）")
            if events[0].get("context") != context:
                raise G.GuardError("入力の SHA-256 が開始のときと違う（再開しない。手動の監査の判断に委ねる）")
            _append(folder, {"event": "resumed"})
        else:
            _append(folder, {"event": "started", "context": context}, create=True)
        try:
            report = analyze(folder, mode, plan, seeds, repo) | {"inputs": context}
            data = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
            G.write_once(folder / REPORT, data)
            _append(folder, {"event": "completed", "report_sha256": G.sha256_bytes(data)})
        except BaseException as e:
            _append(folder, {"event": "failed", "reason": repr(e)})
            raise
    return report


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "smoke" if "--smoke" in sys.argv else "formal"
    folder = Path(args[0]) if args else OWN_DIR
    try:
        report_destination(folder, mode, "--resume" in sys.argv)
        ALIGN.check(PROTOCOL)
        report = publish(folder, mode, "--resume" in sys.argv)
    except G.GuardError as e:
        raise SystemExit(f"report を書かない：{e}") from e
    print(f"記録：{report['records']['state']}　valid：{report['valid']}　測定・解析の commit：{report['analysis_commit']}")
    for p in report["records"]["problems"][:30]:
        print(f"  - {p}")
    for s, c in report["checks"].items():
        if c:
            print(f"  - seed {s}：{sorted(c)}")
    if report.get("judgment"):
        j = report["judgment"]
        print(f"h_late ＝ {j['h_late']}／{j['n']}　判定：{'holds' if j['holds'] else 'fails'}（{j['holds_if']}）")
    else:
        print(report["note"])
    print(f"saved {folder / REPORT}（解析の記録 {LOG}）")


if __name__ == "__main__":
    main()
