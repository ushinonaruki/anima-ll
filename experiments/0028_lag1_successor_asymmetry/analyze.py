"""実験 0028 の記録の解析（確定した事前登録 v0.2 に従う）。正本は protocol.yaml・README。

0023〜0027 の解析の契約（PR #104・#108・#112・#115・#119：記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの
report、解析の道具の HEAD ＝ 測定の commit）をそのまま引き継ぐ（ほかの実験の analyze.py は読み込まない）。0027 から変えたのは、
二つの設計（C0・V1）でそれぞれ 21 の本体（O・M・W1〜W19）を走らせること、試しを置かないこと、主の量が時間差 1 の発火の組の数
（README §3）であること、主の判定が家族ごとに 4 つ（J_Ca・J_O・J_M・J_OM）であること（README §4）、それに合わせた操作の確認
（README §7）と補助の記録（README §5）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる。
   違えば、何も読まず・書かず、判定の量を計算・表示せずに止まる（判定の量を計算する直前と、解析の終わりにも確かめ直す）
1. 実行の記録（seed ごとの開始・終了の記録、raw の SHA-256・バイト数。guard.py）を確かめる。
   - 未完了（まだ始めていない seed がある。失敗・中断・破損はない）：**解析しない**（何も読まず・書かずに止まる）
   - 失敗・中断・破損・範囲の外の seed・別の測定の commit：実験全体を invalid として、記録と操作の確認だけを報告する（判定しない）
2. 操作の確認（README §7、protocol の checks）を、保存した生の記録から seed ごとに再検証する。1 つでも成り立たなければその個体は
   invalid で、実験全体を invalid とする（judgment.on_any_invalid）。時間差 1 の組の数え方の 2 通りの算術（lag1_counts_two_ways）は、
   ほかのすべての確認がすべての個体で成り立ったときに最後に確かめる
3. 判定（README §4、protocol の quantities・judgment）：**本番（formal）で、20 個の seed がすべて completed、raw のハッシュが一致、
   すべての個体ですべての確認が成り立ったときだけ**、主・補助の量を計算して report に書く。家族（C0・V1）ごとに 4 つの主の判定
   J_Ca・J_O・J_M・J_OM（J_Ca は C-a の正式な主の判定で、補助ではない）。smoke では判定の量も、現象に関する数値も
   計算・表示・保存しない（操作の確認だけ）
4. report は一度だけ書く（既にあれば上書きしない。解析の記録 analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0028_lag1_successor_asymmetry/analyze.py                         # 本番（protocol の execution.output_dir）
  python experiments/0028_lag1_successor_asymmetry/analyze.py <フォルダ> --smoke        # smoke（操作の確認だけ。data/experiments の下には書かない）
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
from collections.abc import Iterable, Iterator, Mapping
from fractions import Fraction
from pathlib import Path

import yaml

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
SPEC = W.plasticity(PROTOCOL)                      # C0 の可塑性の規則
W_MAX, W_MIN, AMP = SPEC.w_max, SPEC.w_min, SPEC.amplitude
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
KAPPA = math.exp(-DT / SPEC.trace_tau_seconds)      # 痕跡の 1 Pulse の減り方（本体の規則と同じ式）
TOL = {k: v["tolerance"] for k, v in PROTOCOL["checks"]["numeric"].items()}
COUNT_CHECK = "lag1_counts_two_ways"
CHECK_NAMES = list(PROTOCOL["checks"]["exact"]) + list(PROTOCOL["checks"]["numeric"]) + ["revalidate_from_raw"]
UNITS = tuple(PROTOCOL["brains"]["common"]["sensory_units"])
RECEPTOR_UNIT = dict(PROTOCOL["brains"]["common"]["receptors"])
S_TO_S = PROTOCOL["brains"]["V1"]["fixed_weights"]["s_to_s"]        # V1：Unit のあいだの 6 本の伝達の重み（一生この値。0.005）
RECEPTOR_WEIGHT = {r: W.projection_weights(PROTOCOL, "V1")[(r, u)] for r, u in RECEPTOR_UNIT.items()}   # 1.0（alignment が確かめる）
DESIGNS, BODIES, SHUFFLES, ROLES, WINDOWS = W.DESIGNS, W.BODIES, W.SHUFFLES, W.ROLES, W.WINDOWS
PAIRS = (("A", "B"), ("B", "A"), ("A", "C"), ("C", "A"), ("B", "C"), ("C", "B"))
PAIR_KEYS = tuple(f"{x}->{y}" for x, y in PAIRS)
WEIGHT_RANK_PAIRS = ("A->B", "A->C", "B->C")       # protocol の C0_weight_ranks
JUDGMENTS, STATISTIC, EVENT = ALIGN.JUDGMENTS, ALIGN.STATISTIC, ALIGN.EVENT


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- 発火の列・状態 ------------------------------------------------------------------------------------

def spikes_of(sp: Mapping, unit: str) -> list[int]:
    return sp.get(unit, [])


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


def recorded_states(design: str, bodies: Mapping) -> Iterator[tuple[str, object]]:
    """1 つの設計の、raw に記録したすべての全状態（場所の名前と値）：各本体の出生時、最初の刺激とその次、札が分かれる前、
    経験の終わり・早い区間の終わり・本体の終わり。形が想定と違う場所も、そのまま値として返す（呼び出し側が確かめる）。"""
    for b, rec in bodies.items():
        yield f"{design}・{b} の出生時", rec["birth"]
        for part, name in (("first_stimulus", "最初の刺激"), ("before_divergence", "札が分かれる前"), ("states", "記録の時点")):
            for k, st in rec[part].items():
                yield f"{design}・{b} の{name}（{k}）", st


# ---- 可塑性の再生（本体の実装を呼ばない、独立な計算。README §7 の重みの再生・切り詰めなし。C0 だけ）--------------------------

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
        if not dev <= TOL["C0_pair_sum"]:
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
    """保存した生の記録から、1 個体の操作の確認（lag1_counts_two_ways を除く）。確認の名前 → 成り立たなかった理由。"""
    out = {k: [] for k in CHECK_NAMES if k != COUNT_CHECK}
    try:
        _check_structure(data, mode, seed, plan, start_record, out)
        if out["revalidate_from_raw"]:
            return out
        run = data["run"]
        _check_connections_and_drives(run, out)      # V1 の確認と Receptor の駆動を先に（ほかの確認の途中の例外に左右されない）
        _check_labels(run, seed, plan, out)
        _check_birth(run, out)
        _check_inputs(run, plan, out)
        _check_before_divergence(run, plan, out)
        _check_replay(run, plan, out)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        out["revalidate_from_raw"].append(f"記録の形が想定と違う（{e!r}）")
    return out


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
    if meta.get("manifests") != {d: W.manifest_raw(PROTOCOL, d) for d in DESIGNS}:
        bad.append("raw の二つの設計図が今の設計図と違う")
    if run.get("seed") != seed:
        bad.append("結果の seed がフォルダの seed と違う")
    if run.get("plan") != plan.as_dict():
        bad.append("raw の Plan（経験・遅れ・二つの区間・本体の終わり・最初の刺激）が想定と違う")
    if run.get("roles") != {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)}:
        bad.append("役の割り当てが (seed − 1) mod 6 と違う")
    designs = run.get("designs")
    if not isinstance(designs, dict) or tuple(designs) != DESIGNS or any(
            not isinstance(designs[d], dict) or tuple(designs[d]) != BODIES for d in DESIGNS):
        bad.append(f"設計が {DESIGNS}、本体が各設計で {BODIES} ではない")
        return
    want_states = [str(p) for p in plan.snapshots]
    want_first = [str(p) for p in plan.first_stimulus]
    for d in DESIGNS:
        for b, rec in designs[d].items():
            what = f"{d}・{b}"
            if rec.get("design") != d or rec.get("body") != b:
                bad.append(f"{what}：本体の記録の設計・名前が違う")
            bad += well_formed(rec["spikes"], 1, plan.body_end, f"{what} の本体")
            if list(rec["states"]) != want_states or any(rec["states"][k]["pulse"] != int(k) for k in want_states):
                bad.append(f"{what}：全状態の時点が {want_states} ではない")
            if list(rec["first_stimulus"]) != want_first or any(rec["first_stimulus"][k]["pulse"] != int(k) for k in want_first):
                bad.append(f"{what}：最初の刺激の全状態の時点が {want_first} ではない")
            if any(st["pulse"] != int(k) for k, st in rec["before_divergence"].items()):
                bad.append(f"{what}：札が分かれる前の全状態の Pulse の番号が違う")
        for where, st in recorded_states(d, designs[d]):
            if not isinstance(st, dict) or tuple(st) != W.FULL_STATE_FIELDS:
                bad.append(f"{where}：全状態の欄が {W.FULL_STATE_FIELDS} ではない")
                continue
            for drive in st["drives"]:
                why = _drive_shape_problem(d, drive)
                if why is not None:
                    bad.append(f"{where}：{why}")
                    break


def _drive_shape_problem(design: str, drive) -> str | None:
    """1 つの駆動 [送り手, 受け手, 重み, 成立の Pulse] の形と配線（重みの値は別の確認）。"""
    if not isinstance(drive, list) or len(drive) != 4:
        return f"駆動の形が [送り手, 受け手, 重み, 成立の Pulse] ではない（{drive!r}）"
    src, dst, w, created = drive
    if not isinstance(w, float) or not isinstance(created, int):
        return f"駆動の重み・成立の Pulse の型が違う（{drive!r}）"
    if src in RECEPTOR_UNIT:
        return None if dst == RECEPTOR_UNIT[src] else f"Receptor の駆動 {src} → {dst} が設計図の Receptor → s ではない"
    if src in UNITS:
        return None if dst in UNITS and dst != src else f"Unit → Unit の駆動 {src} → {dst} が設計図の 6 本のどれでもない"
    return f"設計図にない送り手 {src!r} の駆動"


def _check_connections_and_drives(run, out) -> None:
    """README §7 の V1 の重みの一定と、Receptor の駆動の重み。記録したすべての全状態について：
    V1_connections_empty_all_recorded_states ＝ V1 の接続の状態の欄 connections が空の辞書。
    V1_s_to_s_drive_weights_all_0_005 ＝ V1 の Unit → Unit の駆動の重みが brains.V1.fixed_weights.s_to_s（0.005）ちょうど。
    receptor_drive_weights_all_1_0 ＝ 両方の設計で、Receptor → s の駆動の重みが設計図の値（1.0）ちょうど（浮動小数として等しい）。
    C0 の Unit → Unit の駆動の重みは可塑的なので、ここでは確かめない（範囲は C0_no_clipping）。"""
    conn_bad, ss_bad, rec_bad = (out["V1_connections_empty_all_recorded_states"], out["V1_s_to_s_drive_weights_all_0_005"],
                                 out["receptor_drive_weights_all_1_0"])
    for d in DESIGNS:
        for where, st in recorded_states(d, run["designs"][d]):
            if d == "V1" and not (isinstance(st["connections"], dict) and st["connections"] == {}):
                conn_bad.append(f"{where}：接続の状態の欄 connections が空の辞書ではない")
            for src, dst, w, _ in st["drives"]:
                if src in RECEPTOR_UNIT and w != RECEPTOR_WEIGHT[src]:
                    rec_bad.append(f"{where}：Receptor の駆動 {src} → {dst} の重みが {RECEPTOR_WEIGHT[src]!r} ちょうどではない（{w!r}）")
                elif d == "V1" and src in UNITS and w != S_TO_S:
                    ss_bad.append(f"{where}：Unit → Unit の駆動 {src} → {dst} の重みが {S_TO_S!r} ちょうどではない（{w!r}）")


def _check_labels(run, seed, plan, out) -> None:
    bad = out["stimulus_labels"]
    s = PROTOCOL["stimulus"]
    to_role = {r: role for role, r in W.role_receptors(PROTOCOL, seed).items()}
    recs = {}
    for d in DESIGNS:
        bodies = run["designs"][d]
        rec = {b: [tuple(x) for x in bodies[b]["labels"]] for b in BODIES}
        recs[d] = rec
        o_times = [t for t, _ in rec["O"]]
        for b in BODIES:
            labels = rec[b]
            if labels != W.labels_of(PROTOCOL, plan, seed, b):
                bad.append(f"{d}・{b}：札の列が protocol の作り方と違う")
            if [t for t, _ in labels] != o_times or len(set(o_times)) != len(o_times):
                bad.append(f"{d}・{b}：刺激の時刻の集合が O と違うか、同じ Pulse に 2 つの刺激がある")
            for role in ROLES:
                if sum(1 for _, x in labels if x == role) != plan.trials:
                    bad.append(f"{d}・{b}：{role} の数が {plan.trials} ではない")
            got = sorted((p, to_role[r]) for p, r in bodies[b]["sensory"] if p <= plan.experience_end)
            if got != sorted(labels):
                bad.append(f"{d}・{b}：本体が受けた感覚の出来事が札の列と違う")
            want_rng = W.rng_name(seed, W.shuffle_index(b)) if b in SHUFFLES else None
            if bodies[b]["rng"] != want_rng or (want_rng is not None and want_rng != PROTOCOL["conditions"]["within_trial_shuffles"]
                                                ["rng"].format(i=W.shuffle_index(b), seed=seed)):
                bad.append(f"{d}・{b}：試行の中の並べ替えの乱数の流れの名前が protocol と違う（{bodies[b]['rng']!r}）")
            at_b = dict(labels)
            for slots in W.trial_slots(PROTOCOL, plan):               # 試行の中の釣り合い
                if sorted(at_b.get(t, "") for t in slots) != list(ROLES):
                    bad.append(f"{d}・{b}：試行（{slots[0]} から）の 3 つの枠に A・B・C が 1 回ずつ来ていない")
                    break
            if b != "O" and bodies[b]["first_divergence_from_O"] != W.first_label_divergence(rec["O"], labels):
                bad.append(f"{d}・{b}：札が O と最初に違う Pulse の記録が違う")
            elif b == "O" and bodies[b]["first_divergence_from_O"] is not None:
                bad.append(f"{d}・O：札が O と最初に違う Pulse の記録が空でない")
        at = dict(rec["O"])
        for t, x in rec["O"]:
            if x == "A" and (at.get(t + s["b_offset"]) != "B" or at.get(t + s["c_offset"]) != "C"):
                bad.append(f"{d}・O：A（{t}）の後の B・C の形が違う")
                break
        if rec["M"] != [(t, W.MIRROR[x]) for t, x in rec["O"]]:
            bad.append(f"{d}・M が O の B と C の入れ替えではない")
        for b in SHUFFLES:
            if sorted(x for _, x in rec[b]) != sorted(x for _, x in rec["O"]):
                bad.append(f"{d}・{b}：札の多重集合が O と違う")
        if len(rec["O"]) != 3 * plan.trials:
            bad.append(f"{d}・O：刺激の数が 3 × 試行の数（{3 * plan.trials}）ではない")
    for b in BODIES:                                                  # V1 の札の列は C0 の同じ名前の本体と同じ
        if recs["V1"][b] != recs["C0"][b] or run["designs"]["V1"][b]["rng"] != run["designs"]["C0"][b]["rng"]:
            bad.append(f"V1・{b}：札の列・乱数の流れの名前が C0 の {b} と違う")


def _check_birth(run, out) -> None:
    """42 の本体の出生時の状態が同じ（README §7）。比べるのは、Unit の状態・Unit の力学・駆動・Delta・Pulse（出生時の乱数で決まる部分）。
    接続の状態の欄だけは設計で決まる違い（C0：可塑性の対象の 6 本の [0.005, 0, 0]、V1：空）で、各設計の設計図の初期値と同じことを
    確かめる。同じ設計の 21 本体どうしは全状態がそのまま同じ。"""
    bad = out["identical_birth_state_all_42_bodies"]
    ref = run["designs"][DESIGNS[0]]["O"]
    keys = ("pulse", "units", "drives", "deltas")
    for d in DESIGNS:
        init = W.initial_connections(PROTOCOL, d)
        o = run["designs"][d]["O"]
        for b, rec in run["designs"][d].items():
            if rec["dynamics"] != ref["dynamics"]:
                bad.append(f"{d}・{b}：Unit の力学が {DESIGNS[0]}・O と違う")
            if {k: rec["birth"][k] for k in keys} != {k: ref["birth"][k] for k in keys}:
                bad.append(f"{d}・{b}：出生時の Unit の状態・駆動・Delta・Pulse が {DESIGNS[0]}・O と違う")
            if rec["birth"] != o["birth"]:
                bad.append(f"{d}・{b}：出生時の全状態が同じ設計の O と違う")
            if rec["birth"]["connections"] != init:
                bad.append(f"{d}・{b}：出生時の接続の状態が {d} の設計図の初期値と違う")


def _check_inputs(run, plan, out) -> None:
    bad = out["input_free_after_experience"]
    for d in DESIGNS:
        for b, rec in run["designs"][d].items():
            if any(p > plan.experience_end for p, _ in rec["sensory"]):
                bad.append(f"{d}・{b}：経験の後に感覚の出来事がある")


def _check_before_divergence(run, plan, out) -> None:
    """各設計の中で、札が O と最初に違う Pulse の前まで、発火と全状態が O と同じ（README §7）。"""
    bad = out["identical_before_label_divergence_within_each_design"]
    for d in DESIGNS:
        bodies = run["designs"][d]
        o = bodies["O"]
        want_o = set()
        for b in BODIES[1:]:
            rec, dv = bodies[b], bodies[b]["first_divergence_from_O"]
            if dv is None:                            # 札がすべて同じ：全体が同じはず
                if rec["spikes"] != o["spikes"] or rec["states"] != o["states"]:
                    bad.append(f"{d}・{b}：札が O と同じなのに軌道が違う")
                continue
            if dv - 1 > 0:
                want_o.add(str(dv - 1))
                if set(rec["before_divergence"]) != {str(dv - 1)}:
                    bad.append(f"{d}・{b}：札が分かれる前の状態の記録が {dv - 1} だけではない")
                elif rec["before_divergence"][str(dv - 1)] != o["before_divergence"].get(str(dv - 1)):
                    bad.append(f"{d}・{b}：札が分かれる前（{dv - 1} の終わり）の全状態が O と違う")
            elif rec["before_divergence"]:
                bad.append(f"{d}・{b}：札が最初の Pulse から違うのに、札が分かれる前の状態の記録がある")
            for u in UNITS:
                if in_range(rec["spikes"], u, 1, dv - 1) != in_range(o["spikes"], u, 1, dv - 1):
                    bad.append(f"{d}・{b}：札が分かれる前（{dv} より前）の {u} の発火が O と違う")
            for p in plan.first_stimulus:             # 札が分かれる前の、最初の刺激とその次の全状態
                if p < dv and rec["first_stimulus"][str(p)] != o["first_stimulus"][str(p)]:
                    bad.append(f"{d}・{b}：札が分かれる前（{p} の終わり）の全状態が O と違う")
        if set(o["before_divergence"]) != want_o:
            bad.append(f"{d}・O：札が分かれる前の状態の記録の時点が想定と違う")


def _check_replay(run, plan, out) -> None:
    """C0：重みの再生（12000・13500・25500）・組の和・切り詰めなし。再生は本体の実装を呼ばない独立な計算（replay）。"""
    init = W.initial_connections(PROTOCOL, "C0")
    for b, rec in run["designs"]["C0"].items():
        r = replay_all(init, rec["spikes"], 0, plan.body_end, plan.snapshots)
        for p in plan.snapshots:
            st = rec["states"][str(p)]
            if not max_diff(r["at"][p], st["connections"]) <= TOL["C0_replay_weights_and_traces"]:
                out["C0_replay_weights_and_traces"].append(f"C0・{b}：{p} の再生と記録の重み・痕跡が一致しない")
            out["C0_pair_sum"] += pair_sum_problems(st, f"C0・{b}：Pulse {p}")
        if r["clipped"]:
            out["C0_no_clipping"].append(f"C0・{b}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
        for where, st in recorded_states("C0", {b: rec}):
            if any(not W_MIN <= v[0] <= W_MAX for v in st["connections"].values()):
                out["C0_no_clipping"].append(f"{where}：記録した重みに [w_min, w_max] の外の値がある")
            if any(src in UNITS and not W_MIN <= w <= W_MAX for src, _, w, _ in st["drives"]):
                out["C0_no_clipping"].append(f"{where}：記録した Unit → Unit の駆動の重みに [w_min, w_max] の外の値がある")


# ---- 時間差 1 の発火の組の数（2 通りの算術。最後に確かめる）と、重みの材料 ---------------------------------------------

def _counts_route1(sp: Mapping, units: Mapping[str, str], lo: int, hi: int) -> dict:
    """経路 1：区間 [lo, hi] の各 Pulse を順に見る。t と t ＋ 1 にそれぞれ発火した役の組を数える（t ≤ hi − 1）。"""
    fired: dict[int, set] = {}
    for role, u in units.items():
        for p in spikes_of(sp, u):
            if lo <= p <= hi:
                fired.setdefault(p, set()).add(role)
    n_pairs = {k: 0 for k in PAIR_KEYS}
    n_spikes = {r: 0 for r in ROLES}
    for t in range(lo, hi + 1):
        now = fired.get(t, ())
        for x in now:
            n_spikes[x] += 1
        if t <= hi - 1:
            nxt = fired.get(t + 1, ())
            for x in now:
                for y in nxt:
                    if x != y:
                        n_pairs[f"{x}->{y}"] += 1
    return {"N": n_pairs, "spikes": n_spikes}


def _counts_route2(sp: Mapping, units: Mapping[str, str], lo: int, hi: int) -> dict:
    """経路 2：発火の時刻の集合を 1 ずらして交わりを取る（経路 1 と独立）。N_{X→Y} ＝ |{t ∈ [lo, hi − 1] : X が t に発火}
    ∩ {t : Y が t ＋ 1 ∈ [lo ＋ 1, hi] に発火}|。"""
    src = {r: set(in_range(sp, units[r], lo, hi - 1)) for r in ROLES}
    dst = {r: {p - 1 for p in in_range(sp, units[r], lo + 1, hi)} for r in ROLES}
    return {"N": {f"{x}->{y}": len(src[x] & dst[y]) for x, y in PAIRS},
            "spikes": {r: len(in_range(sp, units[r], lo, hi)) for r in ROLES}}


def count_table(run: dict, seed: int, plan) -> tuple[dict, list[str]]:
    """時間差 1 の組の数の材料：{設計: {本体: {区間: {N: {"A->B": …}, spikes: {役: 発火の数}}}}}。2 通りの計算が一致し、
    0 ≤ N_{X→Y} ≤ min(X の [S, E − 1] の発火の数, Y の [S ＋ 1, E] の発火の数) が成り立つことを確かめる。
    値は返すが、呼び出し側は確認がすべて成り立ったときだけ使う（smoke では捨てる）。"""
    units = W.role_units(PROTOCOL, seed)
    problems: list[str] = []
    table: dict = {}
    for d in DESIGNS:
        table[d] = {}
        for b, rec in run["designs"][d].items():
            table[d][b] = {}
            for w in WINDOWS:
                lo, hi = plan.window(w)
                r1, r2 = _counts_route1(rec["spikes"], units, lo, hi), _counts_route2(rec["spikes"], units, lo, hi)
                if r1 != r2:
                    problems.append(f"{d}・{b}（{w}）：時間差 1 の組の数・発火の数が 2 通りの計算で違う")
                for x, y in PAIRS:
                    cap = min(len(in_range(rec["spikes"], units[x], lo, hi - 1)), len(in_range(rec["spikes"], units[y], lo + 1, hi)))
                    if not 0 <= r1["N"][f"{x}->{y}"] <= cap:
                        problems.append(f"{d}・{b}（{w}）：N_{{{x}→{y}}} が 0 以上・発火の数以下ではない")
                table[d][b][w] = r1
    return table, problems


def weight_table(run: dict, seed: int, plan) -> dict:
    """C0 の各本体の、12000・13500・25500 の 6 本の重み（役の組で）。補助の記録（判定に使わない）。確認がすべて成り立ったときだけ呼ぶ。"""
    units = W.role_units(PROTOCOL, seed)
    out = {}
    for b, rec in run["designs"]["C0"].items():
        out[b] = {str(p): {f"{x}->{y}": rec["states"][str(p)]["connections"][W.connection_id(units[x], units[y])][0]
                           for x, y in PAIRS} for p in plan.snapshots}
    return out


# ---- 判定の量（本番・合成で、すべての確認が成り立ったときだけ。README §4・§5）----------------------------------------------

def body_quantities(entry: Mapping) -> dict:
    """1 つの本体・1 つの区間の量（整数）。Δ_AB ＝ N_{A→B} − N_{B→A}、Δ_AC ＝ N_{A→C} − N_{C→A}、D ＝ Δ_AB − Δ_AC。"""
    n = entry["N"]
    dab, dac, dbc = n["A->B"] - n["B->A"], n["A->C"] - n["C->A"], n["B->C"] - n["C->B"]
    return {"N": dict(n), "spike_counts": dict(entry["spikes"]), "Delta_AB": dab, "Delta_AC": dac, "Delta_BC": dbc, "D": dab - dac}


def rank(x, refs: list) -> dict[str, int]:
    """x の、W の 19 本の中での順位（下・同じ・上の本数）。"""
    return {"W_below": sum(r < x for r in refs), "W_equal": sum(r == x for r in refs), "W_above": sum(r > x for r in refs)}


def four_events(q: Mapping[str, Mapping]) -> dict[str, bool]:
    """README §4.1：厳密な不等号の、一方向の 4 つの事象（等号・逆の向きは「外にない」）。q：{本体: 量}（1 つの区間）。"""
    if tuple(q) != BODIES:
        raise ValueError(f"本体が {BODIES} ではない")
    w_ab = [q[b]["Delta_AB"] for b in SHUFFLES]
    w_d = [q[b]["D"] for b in SHUFFLES]
    ev = {"O_Delta_AB_above": q["O"]["Delta_AB"] > max(w_ab),
          "O_above": q["O"]["D"] > max(w_d),
          "M_below": q["M"]["D"] < min(w_d)}
    ev["O_and_M_split"] = ev["O_above"] and ev["M_below"]
    return ev


def design_eval(per_body: Mapping[str, Mapping[str, dict]]) -> dict:
    """1 個体・1 つの設計の評価。主の区間の 4 つの事象（主の判定の材料）と補助、早い区間の 4 つの事象（補助）。"""
    main = {b: per_body[b]["main"] for b in per_body}
    early = {b: per_body[b]["early"] for b in per_body}
    ev = four_events(main)
    ab, ac, dd = ({b: main[b][k] for b in BODIES} for k in ("Delta_AB", "Delta_AC", "D"))
    w_ab, w_ac, w_d = ([x[b] for b in SHUFFLES] for x in (ab, ac, dd))
    return {"main": ev,
            "auxiliary": {
                "C_a_form_for_M": ac["M"] > max(w_ac),
                "opposite_direction": {"Delta_AB_O_below_min": ab["O"] < min(w_ab), "D_O_below_min": dd["O"] < min(w_d),
                                       "D_M_above_max": dd["M"] > max(w_d)},
                "ranks": {"rank_of_Delta_AB_O_among_W": rank(ab["O"], w_ab), "rank_of_D_O_among_W": rank(dd["O"], w_d),
                          "rank_of_D_M_among_W": rank(dd["M"], w_d)},
                "frozen": {"J_Ca": len(set(w_ab + [ab["O"]])) == 1, "J_O": len(set(w_d + [dd["O"]])) == 1,
                           "J_M": len(set(w_d + [dd["M"]])) == 1, "J_OM": len(set(w_d + [dd["O"], dd["M"]])) == 1},
                "silent_units_main_window": {b: [r for r in ROLES if main[b]["spike_counts"][r] == 0] for b in BODIES},
                "early_window_events": four_events(early)}}


def weight_ranks(weights: Mapping[str, Mapping[str, Mapping[str, float]]]) -> dict:
    """C0 の w(A→B)・w(A→C)・w(B→C) の、O・M の値の W の中での順位（記述だけ。判定にも主張にも使わない）。"""
    times = list(weights["O"])
    return {t: {b: {k: rank(weights[b][t][k], [weights[s][t][k] for s in SHUFFLES]) for k in WEIGHT_RANK_PAIRS}
                for b in ("O", "M")} for t in times}


def quantities_for_seed(table: Mapping, weights: Mapping) -> dict:
    per = {d: {b: {w: body_quantities(table[d][b][w]) for w in WINDOWS} for b in table[d]} for d in DESIGNS}
    return {"designs": {d: {"bodies": per[d], "individual": design_eval(per[d])} for d in DESIGNS},
            "C0_weights": dict(weights), "C0_weight_ranks": weight_ranks(weights)}


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


def family_judgment(ind: Mapping[str, dict], design: str, alpha: float) -> dict:
    """1 つの家族（設計）の 4 つの主の判定（README §4.1・§4.3）と、補助の数え上げ（README §5）。
    J_Ca・J_O・J_M・J_OM はどれも正式な主の判定で、成立を足し合わせたり h を比べたりしない。"""
    n = len(ind)
    k = PROTOCOL["conditions"]["within_trial_shuffles"]["count"]
    split = PROTOCOL["judgment"]["per_family"]["alpha_split"]
    out = {"design": design, "alpha": alpha, "n": n, "main_judgments": list(JUDGMENTS)}
    for J in JUDGMENTS:
        h = sum(v["main"][EVENT[J]] for v in ind.values())
        threshold = ALIGN.HOLDS_MIN[J]
        p0 = ALIGN.per_individual_null(J, k)
        out[J] = {"statistic": STATISTIC[J], STATISTIC[J]: h, "holds_if": f"{STATISTIC[J]} >= {threshold}",
                  "holds": h >= threshold, "alpha": split[J],
                  "per_individual_null_probability_at_most": f"{p0.numerator}/{p0.denominator}",
                  "binomial_upper_tail_at_threshold": float(binom_tail(n, p0, threshold)),
                  "clopper_pearson_95_of_h_over_n": clopper_pearson(h, n)}
    aux = [v["auxiliary"] for v in ind.values()]
    out["auxiliary"] = {
        "C_a_form_for_M": sum(a["C_a_form_for_M"] for a in aux),
        "opposite_direction": {k2: sum(a["opposite_direction"][k2] for a in aux) for k2 in aux[0]["opposite_direction"]},
        "frozen": {J: sum(a["frozen"][J] for a in aux) for J in JUDGMENTS},
        "early_window_events": {e: sum(a["early_window_events"][e] for a in aux) for e in EVENT.values()},
        "individuals_with_a_silent_unit_in_some_body": sum(any(a["silent_units_main_window"].values()) for a in aux)}
    return out


def judgment(per_seed: Mapping[str, dict]) -> dict:
    """家族（C0・V1）ごとの 4 つの主の判定。二つの家族を組み合わせた量は作らない（README §4.4）。"""
    j = PROTOCOL["judgment"]
    fams = {}
    for name, fam in j["families"].items():
        ind = {s: v["designs"][fam["design"]]["individual"] for s, v in per_seed.items()}
        fams[name] = family_judgment(ind, fam["design"], fam["alpha"])
    return {"families": fams, "experiment_wide_error_rate_claimed": j["experiment_wide_error_rate_claimed"],
            "scope": j["scope"], "content_claimed": j["content_claimed"], "not_judged": j["not_judged"],
            "note": ("家族（C0・V1）ごとに 4 つの主の判定 J_Ca・J_O・J_M・J_OM（J_Ca は C-a の正式な主の判定。scope の要約の文字列は D だけを"
                     "書いているが、主の判定は per_family の 4 つ）。各家族の水準は 0.05（J_Ca・J_O・J_M に 0.016 ずつ、J_OM に 0.002 の"
                     "重みつきの Bonferroni）。成立は、交換可能性という帰無仮説を、個体間の独立性という統計モデル上の前提のもとで、その判定の"
                     "水準で棄却すること（交換可能性の破れの証明ではない）。実験全体（8 判定）で誤りの水準 0.05 とは主張しない（単純な和の"
                     "上界は 0.10）。二つの家族の結果を組み合わせた主張はしない。auxiliary・Clopper–Pearson の区間・早い区間・重みの順位は"
                     "補助の記録で、主の不成立を救わない")}


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
    counted = "not_evaluated"
    tables, weights = {}, {}
    if records["state"] == "complete" and not invalid:
        counted = "evaluated"
        for s in seeds:
            data = read_raw(G.seed_dir(out, s) / G.RAW)
            tables[str(s)], problems = count_table(data["run"], s, plan)
            checks[str(s)][COUNT_CHECK] = problems
            if problems:
                invalid.append(s)
            elif mode != "smoke":
                weights[str(s)] = weight_table(data["run"], s, plan)
            del data
    verify_analysis_commit(repo, records["measurement_commit"])     # 確認の途中で道具が変わっていない
    valid = records["state"] == "complete" and not invalid and counted == "evaluated"
    report = base | {"valid": valid, "invalid_seeds": sorted(set(invalid)), "count_arithmetic": counted,
                     "checks": {s: {k: v for k, v in c.items() if v} for s, c in checks.items()},
                     "checks_evaluated": {s: sorted(c) for s, c in checks.items()}}
    if not valid:
        tables.clear()
        weights.clear()
        return report | {"judgment": None, "note": (
            "invalid か記録の問題があるので、判定の量（N・Δ・D・外にあるか・h・補助の量）は計算も表示もしない"
            "（judgment.on_any_invalid）。invalid を「外にない」に数えない")}
    if mode == "smoke":
        tables.clear()
        weights.clear()
        return report | {"judgment": None, "note": "smoke（操作の確認だけ）。判定の量も現象に関する数値も計算・表示・保存していない"}
    per_seed = {s: quantities_for_seed(tables[s], weights[s]) for s in tables}
    result = report | {"judgment": judgment(per_seed), "per_seed": per_seed,
                       "note": ("事前登録した検証。主の判定は家族（C0・V1）ごとに J_Ca・J_O・J_M・J_OM の 4 つ。"
                                "補助は記録で、主の不成立を救わない")}
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
        for name, fam in report["judgment"]["families"].items():
            line = "　".join(f"{J}：{fam[J][fam[J]['statistic']]}／{fam['n']}（{fam[J]['holds_if']}）"
                            f"{'holds' if fam[J]['holds'] else 'fails'}" for J in JUDGMENTS)
            print(f"{name} の家族：{line}")
    else:
        print(report["note"])
    print(f"saved {folder / REPORT}（解析の記録 {LOG}）")


if __name__ == "__main__":
    main()
