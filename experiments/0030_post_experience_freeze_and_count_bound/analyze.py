"""実験 0030 の記録の解析（確定した事前登録 v0.1 に従う）。正本は protocol.yaml・README。

0023〜0029 の解析の契約（PR #104・#108・#112・#115・#119・#124・#128：記録の確認、生の記録からの操作の確認、invalid なら判定しない、
一度だけの report、解析の道具の HEAD ＝ 測定の commit、確認の結果の pass・fail・not_applicable）をそのまま引き継ぐ（ほかの実験の
analyze.py は読み込まない）。0029 から変えたのは、自然な本体 21（O・M・W1〜W19）、T_0 から可塑性を止めた F 本体と組み立ての確認の
本体 R(O)（README §2）、T_0 がない個体の扱い（README §2.6）、主の判定が F の家族と N^cnt の家族（どちらも一方向）にそれぞれ 4 つ
であること（README §4・§5）、それに合わせた操作の確認（README §7）と補助の記録（README §6）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる。
   違えば、何も読まず・書かず、判定の量を計算・表示せずに止まる（判定の量を計算する直前と、解析の終わりにも確かめ直す）
1. 実行の記録（seed ごとの開始・終了の記録、raw の SHA-256・バイト数。guard.py）を確かめる。
   - 未完了（まだ始めていない seed がある。失敗・中断・破損はない）：**解析しない**（何も読まず・書かずに止まる）
   - 失敗・中断・破損・範囲の外の seed・別の測定の commit：実験全体を invalid として、記録と操作の確認だけを報告する（判定しない）
2. 操作の確認（README §7・§2.6、protocol の checks）を、保存した生の記録から seed ごとに再検証する。確認ごとの結果は pass・fail・
   not_applicable。**T_0 がない個体**では、F に固有の 4 つ（checks.no_t0.not_applicable）は not_applicable（失敗ではなく、invalid の
   理由にならない）、ほかの確認は自然な本体だけで行い、T_0 の規則の確認は T_0 がないことの証明（window_witness の再検証）になる。
   fail が 1 つでもあればその個体は invalid で、実験全体を invalid とする（judgment.on_any_invalid）。raw の freeze の欄と本体の並びが
   §2.6 の対応から外れていれば invalid。時間差 1 の組の数え方の 2 通りの算術（lag1_counts_two_ways）は、ほかのすべての確認がすべての
   個体で成り立ったときに最後に確かめる
3. 判定（README §4、protocol の quantities・judgment）：**本番（formal）で、20 個の seed がすべて completed、raw のハッシュが一致、
   すべての個体で fail がないときだけ**、主・補助の量を計算して report に書く（raw には判定の量を書かない：protocol の
   records.no_judgment_quantities_in_raw）。家族（F・Ncnt）ごとに 4 つの主の判定 J_Ca・J_O・J_M・J_OM。T_0 がない個体は 20 個体の
   分母に残り、F の 4 つの事象を「外にない」に数える（凍結とは別に記録）。N^cnt の事象は T_0 に依らずに計算する。smoke では判定の量も、
   現象に関する数値（T_0 の値・T_0 の有無を含む）も計算・表示・保存しない（操作の確認だけ。確認の結果は fail か ok〔pass と
   not_applicable を区別しない〕だけを書く）
4. report は一度だけ書く（既にあれば上書きしない。解析の記録 analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0030_post_experience_freeze_and_count_bound/analyze.py                   # 本番（protocol の execution.output_dir）
  python experiments/0030_post_experience_freeze_and_count_bound/analyze.py <フォルダ> --smoke  # smoke（操作の確認だけ。data/experiments の下には書かない）
  （中断の後だけ）--resume：入力の SHA-256 が開始のときと同じで、report がまだないときだけ、計算し直して完了する
"""

import bisect
import copy
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
SPEC = W.plasticity(PROTOCOL)                      # C0 の可塑性の規則
W_MAX, W_MIN, AMP = SPEC.w_max, SPEC.w_min, SPEC.amplitude
DT = PROTOCOL["timeline"]["pulse_interval_seconds"]
KAPPA = math.exp(-DT / SPEC.trace_tau_seconds)      # 痕跡の 1 Pulse の減り方（本体の規則と同じ式）
TOL = {k: v["tolerance"] for k, v in PROTOCOL["checks"]["numeric"].items()}
COUNT_CHECK = "lag1_counts_two_ways"
CHECK_NAMES = list(PROTOCOL["checks"]["exact"]) + list(PROTOCOL["checks"]["numeric"]) + ["revalidate_from_raw"]
NOT_APPLICABLE_WITHOUT_T0 = tuple(PROTOCOL["checks"]["no_t0"]["not_applicable"])
PASS, FAIL, NA = PROTOCOL["checks"]["result_values"]   # "pass"・"fail"・"not_applicable"
SMOKE_VALUES = tuple(PROTOCOL["checks"]["smoke_report_check_values"])   # ("fail", "ok")
UNITS = tuple(PROTOCOL["brain"]["sensory_units"])
RECEPTOR_UNIT = dict(PROTOCOL["brain"]["receptors"])
BODIES, SHUFFLES, ROLES = W.BODIES, W.SHUFFLES, W.ROLES
REFERENCE = tuple(PROTOCOL["freeze"]["reference_bodies"])
CONTROL = PROTOCOL["f_variant"]["rebuild_control"]["body"]
FAMILIES = ALIGN.FAMILIES
UNIT_IDX = {f: i for i, f in enumerate(W.UNIT_FIELDS)}
PAIRS = (("A", "B"), ("B", "A"), ("A", "C"), ("C", "A"), ("B", "C"), ("C", "B"))
PAIR_KEYS = tuple(f"{x}->{y}" for x, y in PAIRS)
JUDGMENTS, STATISTIC, EVENT = ALIGN.JUDGMENTS, ALIGN.STATISTIC, ALIGN.EVENT
EVENTS = {f: tuple(PROTOCOL["quantities"]["primary"]["per_individual"][f]) for f in FAMILIES}
NATURAL_EVENTS = tuple(PROTOCOL["quantities"]["auxiliary"]["per_individual"]["natural_0028_form_events"])
NULL_WITHOUT_T0 = tuple(PROTOCOL["quantities"]["auxiliary"]["when_no_t0"]["null_with_reason_no_t0"])
NO_T0_REASON = ALIGN.NO_T0_REASON


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
        elif (not isinstance(xs, list) or any(not isinstance(p, int) or isinstance(p, bool) or not lo <= p <= hi for p in xs)
              or any(b <= a for a, b in itertools.pairwise(xs))):
            problems.append(f"{what}：{u} の発火の列が {lo}〜{hi} の狭義に増加する整数の列でない")
    return problems


def t0_of(run: Mapping) -> int | None:
    """raw の T_0（T_0 がない個体では None）。形の確認は _check_structure。"""
    return run["freeze"]["t0"] if run["freeze"]["t0_exists"] is True else None


def natural_recorded_states(bodies: Mapping) -> Iterator[tuple[str, object]]:
    """自然な本体の、raw に記録したすべての全状態（場所の名前と値）。T_0 の全状態は T_0 があるときだけ。"""
    for b, rec in bodies.items():
        yield f"{b} の出生時", rec["birth"]
        for part, name in (("first_stimulus", "最初の刺激"), ("before_divergence", "札が分かれる前"), ("states", "記録の時点")):
            for k, st in rec[part].items():
                yield f"{b} の{name}（{k}）", st
        if rec["state_t0"] is not None:
            yield f"{b} の T_0", rec["state_t0"]


def rebuilt_recorded_states(rec: Mapping, name: str) -> Iterator[tuple[str, object]]:
    """F 本体・R(O) の、raw に記録したすべての全状態（始まりと記録の時点）。"""
    yield f"{name} の始まり", rec["start"]
    for k, st in rec["states"].items():
        yield f"{name}（{k}）", st


def f_entries(run: Mapping) -> list[tuple[str, str, Mapping]]:
    """F 本体の一覧 [(名前, もとの本体, 記録)]。T_0 がなければ空。"""
    return [(f"F({rec['original_body']})", rec["original_body"], rec) for rec in run["f_bodies"]]


def control_entry(run: Mapping) -> Mapping | None:
    return run["control_bodies"][0] if run["control_bodies"] else None


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


# ---- 操作の確認（README §7・§2.6）--------------------------------------------------------------------------------

def check_seed(data: dict, mode: str, seed: int, plan, start_record: Mapping | None = None) -> dict[str, list[str]]:
    """保存した生の記録から、1 個体の操作の確認（lag1_counts_two_ways を除く）。確認の名前 → 成り立たなかった理由。
    T_0 がない個体では、F に固有の確認は理由を作らない（not_applicable は check_statuses が付ける）。"""
    out = {k: [] for k in CHECK_NAMES if k != COUNT_CHECK}
    try:
        _check_structure(data, mode, seed, plan, start_record, out)
        if out["revalidate_from_raw"]:
            return out
        run = data["run"]
        _check_labels(run, seed, plan, out)
        _check_birth(run, out)
        _check_inputs(run, plan, out)
        _check_before_divergence(run, plan, out)
        _check_freeze_time(run, plan, out)
        if t0_of(run) is not None:
            _check_f(run, data["meta"]["manifest"], out)
            _check_rebuild(run, plan, out)
        _check_replay(run, plan, out)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        out["revalidate_from_raw"].append(f"記録の形が想定と違う（{e!r}）")
    return out


def raw_t0_exists(data: Mapping) -> bool | None:
    """raw の freeze.t0_exists（真偽でなければ None）。"""
    try:
        v = data["run"]["freeze"]["t0_exists"]
    except (KeyError, TypeError):
        return None
    return v if isinstance(v, bool) else None


def check_statuses(reasons: Mapping[str, list], t0_exists: bool | None) -> dict[str, str]:
    """確認ごとの結果（protocol の checks.result_values）：理由があれば fail。T_0 がない個体（t0_exists が False）の F に固有の
    確認は not_applicable（失敗ではない：README §2.6）。ほかは pass。"""
    out = {}
    for k, why in reasons.items():
        if why:
            out[k] = FAIL
        elif t0_exists is False and k in NOT_APPLICABLE_WITHOUT_T0:
            out[k] = NA
        else:
            out[k] = PASS
    return out


def _drive_shape_problem(drive) -> str | None:
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


def _state_shape(st, what: str) -> list[str]:
    if not isinstance(st, dict) or tuple(st) != W.FULL_STATE_FIELDS:
        return [f"{what}：全状態の欄が {W.FULL_STATE_FIELDS} ではない"]
    for drive in st["drives"]:
        why = _drive_shape_problem(drive)
        if why is not None:
            return [f"{what}：{why}"]
    return []


def _check_structure(data, mode, seed, plan, start_record, out) -> None:
    """raw の形（README §2.6・§8）。freeze の欄と本体の並びが §2.6 の対応から外れていれば、ここで成り立たない（invalid）。"""
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
    if set(run) != {"seed", "plan", "roles", "freeze_window", "freeze", "natural_bodies", "f_bodies", "control_bodies"}:
        bad.append("raw の run の欄が想定と違う（判定の量を raw に書かない：records.no_judgment_quantities_in_raw）")
        return
    if run.get("seed") != seed:
        bad.append("結果の seed がフォルダの seed と違う")
    if run.get("plan") != plan.as_dict():
        bad.append("raw の Plan（経験・最後の刺激・遅れ・T_0 の窓・主の区間・本体の終わり・最初の刺激）が想定と違う")
    if run.get("roles") != {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)}:
        bad.append("役の割り当てが (seed − 1) mod 6 と違う")
    lo, hi = plan.freeze_window
    if run.get("freeze_window") != [lo, hi]:
        bad.append("raw の T_0 の窓が Plan と違う")
    # freeze の欄（README §2.6 の表。どちらの場合も同じ鍵）
    fr = run.get("freeze")
    if not isinstance(fr, dict) or set(fr) != {"t0_exists", "t0", "window_witness"}:
        bad.append("raw の freeze の欄が t0_exists・t0・window_witness ではない")
        return
    exists, t0 = fr["t0_exists"], fr["t0"]
    fb, cb = run.get("f_bodies"), run.get("control_bodies")
    if exists is True:
        if not (isinstance(t0, int) and not isinstance(t0, bool) and lo <= t0 <= hi):
            bad.append("T_0 があるのに、T_0 が窓の中の整数ではない")
        if fr["window_witness"] is not None:
            bad.append("T_0 があるのに、window_witness が null ではない")
        if not isinstance(fb, list) or len(fb) != len(BODIES):
            bad.append(f"T_0 があるのに、F 本体が {len(BODIES)} の配列ではない")
        if not isinstance(cb, list) or len(cb) != 1:
            bad.append("T_0 があるのに、確認の本体が 1 の配列ではない")
    elif exists is False:
        if t0 is not None:
            bad.append("T_0 がないのに、T_0 が null ではない")
        if not isinstance(fr["window_witness"], list):
            bad.append("T_0 がないのに、window_witness が配列ではない")
        if fb != [] or cb != []:
            bad.append("T_0 がないのに、F 本体・確認の本体が空の配列ではない")
    else:
        bad.append("freeze.t0_exists が真偽ではない")
    if bad:
        return
    t0 = t0_of(run)
    # 自然な本体
    bodies = run.get("natural_bodies") or {}
    if tuple(bodies) != BODIES:
        bad.append(f"自然な本体が {BODIES} ではない")
        return
    want_states = [str(p) for p in plan.snapshots]
    want_first = [str(p) for p in plan.first_stimulus]
    for b, rec in bodies.items():
        if rec.get("body") != b:
            bad.append(f"{b}：本体の記録の名前が違う")
        bad += well_formed(rec["spikes"], 1, plan.body_end, f"{b} の本体")
        if list(rec["states"]) != want_states or any(rec["states"][k]["pulse"] != int(k) for k in want_states):
            bad.append(f"{b}：全状態の時点が {want_states} ではない")
        if list(rec["first_stimulus"]) != want_first or any(rec["first_stimulus"][k]["pulse"] != int(k) for k in want_first):
            bad.append(f"{b}：最初の刺激の全状態の時点が {want_first} ではない")
        if any(st["pulse"] != int(k) for k, st in rec["before_divergence"].items()):
            bad.append(f"{b}：札が分かれる前の全状態の Pulse の番号が違う")
        if t0 is None:
            if rec["state_t0"] is not None:
                bad.append(f"{b}：T_0 がないのに、T_0 の全状態が null ではない")
        elif not isinstance(rec["state_t0"], dict) or rec["state_t0"].get("pulse") != t0:
            bad.append(f"{b}：T_0 の終わりの全状態の記録が T_0 と合わない")
    for where, st in natural_recorded_states(bodies):
        bad += _state_shape(st, where)
    if t0 is None or bad:
        return
    # F 本体・確認の本体（T_0 があるとき）
    if [rec.get("original_body") for rec in fb] != list(BODIES):
        bad.append(f"F 本体の並び（もとの本体）が {BODIES} ではない")
        return
    if cb[0].get("name") != CONTROL:
        bad.append(f"確認の本体が {CONTROL} ではない")
        return
    want_sw = [str(p) for p in plan.rebuilt_snapshots]
    named = [(n, r, {"original_body", "dynamics", "start", "states", "sensory", "spikes", "frozen_weights"}) for n, _, r in f_entries(run)]
    named.append((CONTROL, cb[0], {"name", "dynamics", "start", "states", "sensory", "spikes"}))
    for name, rec, keys in named:
        if set(rec) != keys:
            bad.append(f"{name}：記録の欄が想定と違う")
            continue
        bad += well_formed(rec["spikes"], t0 + 1, plan.body_end, name)
        if not isinstance(rec["start"], dict) or rec["start"].get("pulse") != t0:
            bad.append(f"{name}：始まりの全状態の Pulse が T_0 ではない")
        if list(rec["states"]) != want_sw or any(rec["states"][k]["pulse"] != int(k) for k in want_sw):
            bad.append(f"{name}：全状態の時点が {want_sw} ではない")
        for where, st in rebuilt_recorded_states(rec, name):
            bad += _state_shape(st, where)


def _check_labels(run, seed, plan, out) -> None:
    bad = out["stimulus_labels"]
    s = PROTOCOL["stimulus"]
    to_role = {r: role for role, r in W.role_receptors(PROTOCOL, seed).items()}
    bodies = run["natural_bodies"]
    rec = {b: [tuple(x) for x in bodies[b]["labels"]] for b in BODIES}
    o_times = [t for t, _ in rec["O"]]
    for b in BODIES:
        labels = rec[b]
        if labels != W.labels_of(PROTOCOL, plan, seed, b):
            bad.append(f"{b}：札の列が protocol の作り方と違う")
        if [t for t, _ in labels] != o_times or len(set(o_times)) != len(o_times):
            bad.append(f"{b}：刺激の時刻の集合が O と違うか、同じ Pulse に 2 つの刺激がある")
        for role in ROLES:
            if sum(1 for _, x in labels if x == role) != plan.trials:
                bad.append(f"{b}：{role} の数が {plan.trials} ではない")
        got = sorted((p, to_role[r]) for p, r in bodies[b]["sensory"] if p <= plan.experience_end)
        if got != sorted(labels):
            bad.append(f"{b}：本体が受けた感覚の出来事が札の列と違う")
        want_rng = W.rng_name(seed, W.shuffle_index(b)) if b in SHUFFLES else None
        if bodies[b]["rng"] != want_rng or (want_rng is not None and want_rng != PROTOCOL["conditions"]["within_trial_shuffles"]
                                            ["rng"].format(i=W.shuffle_index(b), seed=seed)):
            bad.append(f"{b}：試行の中の並べ替えの乱数の流れの名前が protocol と違う（{bodies[b]['rng']!r}）")
        at_b = dict(labels)
        for slots in W.trial_slots(PROTOCOL, plan):                   # 試行の中の釣り合い
            if sorted(at_b.get(t, "") for t in slots) != list(ROLES):
                bad.append(f"{b}：試行（{slots[0]} から）の 3 つの枠に A・B・C が 1 回ずつ来ていない")
                break
        if b != "O" and bodies[b]["first_divergence_from_O"] != W.first_label_divergence(rec["O"], labels):
            bad.append(f"{b}：札が O と最初に違う Pulse の記録が違う")
        elif b == "O" and bodies[b]["first_divergence_from_O"] is not None:
            bad.append("O：札が O と最初に違う Pulse の記録が空でない")
    at = dict(rec["O"])
    for t, x in rec["O"]:
        if x == "A" and (at.get(t + s["b_offset"]) != "B" or at.get(t + s["c_offset"]) != "C"):
            bad.append(f"O：A（{t}）の後の B・C の形が違う")
            break
    if rec["M"] != [(t, W.MIRROR[x]) for t, x in rec["O"]]:
        bad.append("M が O の B と C の入れ替えではない")
    for b in SHUFFLES:
        if sorted(x for _, x in rec[b]) != sorted(x for _, x in rec["O"]):
            bad.append(f"{b}：札の多重集合が O と違う")
    if len(rec["O"]) != 3 * plan.trials or max(o_times) != plan.last_stimulus:
        bad.append(f"O：刺激の数が 3 × 試行の数（{3 * plan.trials}）ではないか、最後の刺激が {plan.last_stimulus} ではない")


def _check_birth(run, out) -> None:
    """自然な 21 本体の出生時の全状態・Unit の力学が同じで、接続の状態が設計図の初期値（README §7）。"""
    bad = out["identical_birth_state_natural_bodies"]
    bodies = run["natural_bodies"]
    o = bodies["O"]
    init = W.initial_connections(PROTOCOL)
    for b, rec in bodies.items():
        if rec["dynamics"] != o["dynamics"]:
            bad.append(f"{b}：Unit の力学が O と違う")
        if rec["birth"] != o["birth"]:
            bad.append(f"{b}：出生時の全状態が O と違う")
        if rec["birth"]["connections"] != init:
            bad.append(f"{b}：出生時の接続の状態が設計図の初期値と違う")


def _check_inputs(run, plan, out) -> None:
    """12001 以後、自然な本体に Receptor の出来事がない。F 本体・R(O) には T_0 より後に Receptor の出来事・Receptor の駆動がない。"""
    bad = out["input_free_after_experience"]
    for b, rec in run["natural_bodies"].items():
        if any(p > plan.experience_end for p, _ in rec["sensory"]):
            bad.append(f"{b}：経験の後に感覚の出来事がある")
    rebuilt = [(n, r) for n, _, r in f_entries(run)] + ([(CONTROL, control_entry(run))] if control_entry(run) else [])
    for name, rec in rebuilt:
        if rec["sensory"]:
            bad.append(f"{name}：T_0 より後に感覚の出来事がある")
        if any(src in RECEPTOR_UNIT for _, st in rebuilt_recorded_states(rec, name) for src, *_ in st["drives"]):
            bad.append(f"{name}：記録した全状態に Receptor の駆動がある")


def _check_before_divergence(run, plan, out) -> None:
    """札が O と最初に違う Pulse の前まで、発火と全状態が O と同じ（README §7）。"""
    bad = out["identical_before_label_divergence"]
    bodies = run["natural_bodies"]
    o = bodies["O"]
    want_o = set()
    for b in BODIES[1:]:
        rec, dv = bodies[b], bodies[b]["first_divergence_from_O"]
        if dv is None:                                # 札がすべて同じ：全体が同じはず
            if rec["spikes"] != o["spikes"] or rec["states"] != o["states"]:
                bad.append(f"{b}：札が O と同じなのに軌道が違う")
            continue
        if dv - 1 > 0:
            want_o.add(str(dv - 1))
            if set(rec["before_divergence"]) != {str(dv - 1)}:
                bad.append(f"{b}：札が分かれる前の状態の記録が {dv - 1} だけではない")
            elif rec["before_divergence"][str(dv - 1)] != o["before_divergence"].get(str(dv - 1)):
                bad.append(f"{b}：札が分かれる前（{dv - 1} の終わり）の全状態が O と違う")
        elif rec["before_divergence"]:
            bad.append(f"{b}：札が最初の Pulse から違うのに、札が分かれる前の状態の記録がある")
        for u in UNITS:
            if in_range(rec["spikes"], u, 1, dv - 1) != in_range(o["spikes"], u, 1, dv - 1):
                bad.append(f"{b}：札が分かれる前（{dv} より前）の {u} の発火が O と違う")
        for p in plan.first_stimulus:                 # 札が分かれる前の、最初の刺激とその次の全状態
            if p < dv and rec["first_stimulus"][str(p)] != o["first_stimulus"][str(p)]:
                bad.append(f"{b}：札が分かれる前（{p} の終わり）の全状態が O と違う")
    if set(o["before_divergence"]) != want_o:
        bad.append("O：札が分かれる前の状態の記録の時点が想定と違う")


# ---- T_0 の規則・F の確認・組み立ての確認（README §2.2・§2.6・§7。world.py の組み立ての関数を呼ばない）---------------------

def _first_firing_at(bodies: Mapping, t: int) -> tuple[str, str] | None:
    """Pulse t に発火した自然な本体と Unit のうち、本体を O・M・W1〜W19、Unit を s1・s2・s3 の順に見て最初のもの（二分探索）。"""
    for b in BODIES:
        for u in UNITS:
            xs = spikes_of(bodies[b]["spikes"], u)
            i = bisect.bisect_left(xs, t)
            if i < len(xs) and xs[i] == t:
                return b, u
    return None


def _check_freeze_time(run, plan, out) -> None:
    """T_0 の規則（README §2.2）。T_0 がある個体：記録した自然な 21 本体の発火の列から、窓の各 Pulse に発火があるかを数え直し、
    T_0 の全状態に駆動・Delta がないことを確かめる。T_0 がない個体：T_0 がないことの証明（README §2.6）。"""
    bad = out["freeze_time_rule"]
    lo, hi = plan.freeze_window
    bodies = run["natural_bodies"]
    fired = {t for rec in bodies.values() for u in UNITS for t in in_range(rec["spikes"], u, lo, hi)}
    quiet = [t for t in range(hi, lo - 1, -1) if t not in fired]       # 窓の終わりから数える（world と別の書き方）
    t0 = t0_of(run)
    if t0 is None:
        if quiet:
            bad.append(f"T_0 がないと記録されているが、窓の中に、どの自然な本体も発火していない Pulse がある（{len(quiet)} 個）")
        witness = run["freeze"]["window_witness"]
        if [w.get("pulse") if isinstance(w, dict) else None for w in witness] != list(range(lo, hi + 1)):
            bad.append("window_witness の Pulse が、窓の各 Pulse の昇順ではない")
        for w in witness:
            if not isinstance(w, dict) or set(w) != {"pulse", "body", "unit"}:
                bad.append(f"window_witness の要素の形が {{pulse, body, unit}} ではない（{w!r}）")
                continue
            t = w["pulse"]
            if w["body"] not in bodies or w["unit"] not in UNITS or t not in spikes_of(bodies[w["body"]]["spikes"], w["unit"]):
                bad.append(f"window_witness（Pulse {t}）の本体・Unit が、記録した発火の列にない")
            elif _first_firing_at(bodies, t) != (w["body"], w["unit"]):
                bad.append(f"window_witness（Pulse {t}）が、決めた順に見て最初の発火ではない")
        return
    if t0 in fired:
        bad.append("T_0 に、どれかの自然な本体で発火がある")
    if any(t not in fired for t in range(t0 + 1, hi + 1)):
        bad.append("T_0 より後の窓に、どの自然な本体も発火していない Pulse がある（T_0 が最後ではない）")
    if not quiet or quiet[0] != t0:
        bad.append("記録した T_0 が、発火の列から数え直した T_0 と違う")
    for b, rec in bodies.items():
        st = rec["state_t0"]
        if st["drives"] != [] or st["deltas"] != 0:
            bad.append(f"{b}：T_0 の終わりに、次の Pulse に届く駆動か Delta がある")


def expected_variant(manifest: Mapping, weights: Mapping[str, float]) -> dict:
    """README §2.4 の F の変種を、world.py の関数を使わずに作る（確認のための独立な組み立て）。"""
    v = copy.deepcopy(dict(manifest))
    for p in v["projections"]:
        src, dst = p["from"].split(".")[0], p["to"]
        if src in UNITS and dst in UNITS:
            p.pop("plastic", None)
            p["weight"] = weights[f"{src}.main->{dst}"]
    return v


def _check_f(run, manifest, out) -> None:
    """T_0 がある個体だけ：F の組み立て・F の重みの一定・F の最初の発火までの一致（README §7）。"""
    t0 = t0_of(run)
    bodies = run["natural_bodies"]
    cons, const, first = out["f_construction"], out["f_weights_constant"], out["f_matches_natural_until_first_spike"]
    for name, b, rec in f_entries(run):
        nat = bodies[b]
        want_w = {cid: v[0] for cid, v in nat["state_t0"]["connections"].items()}
        if rec["frozen_weights"] != want_w or set(want_w) != set(W.initial_connections(PROTOCOL)):
            cons.append(f"{name}：固定した重みが {b} の T_0 の重みとちょうど同じではない")
        variant = parse_neuroarchitecture(expected_variant(manifest, rec["frozen_weights"]))
        if any(p.plastic for p in variant.projections):
            cons.append(f"{name}：F の変種に可塑性の対象の接続が残る")
        if rec["dynamics"] != nat["dynamics"]:
            cons.append(f"{name}：Unit の力学が自然な本体 {b} と違う")
        if rec["start"] != {"pulse": t0, "units": nat["state_t0"]["units"], "connections": {}, "drives": [], "deltas": 0}:
            cons.append(f"{name}：始まりの全状態が、{b} の T_0 の Unit の状態・接続の状態なし・駆動なし・Delta なしではない")
        for where, st in rebuilt_recorded_states(rec, name):
            if st["connections"] != {}:
                const.append(f"{where}：接続の状態の欄 connections が空の辞書ではない")
            for src, dst, w, _ in st["drives"]:
                if src in UNITS and w != rec["frozen_weights"][f"{src}.main->{dst}"]:
                    const.append(f"{where}：Unit → Unit の駆動 {src} → {dst} の重みが固定した重みちょうどではない（{w!r}）")
        after = sorted(p for u in UNITS for p in spikes_of(nat["spikes"], u) if p > t0)
        p1 = after[0] if after else None
        for u in UNITS:
            nat_u = [p for p in spikes_of(nat["spikes"], u) if p > t0 and (p1 is None or p <= p1)]
            f_u = [p for p in spikes_of(rec["spikes"], u) if p1 is None or p <= p1]
            if nat_u != f_u:
                first.append(f"{name}：{u} の発火が、T_0 より後の {b} の最初の発火（{p1}）まで {b} と一致しない")


def _check_rebuild(run, plan, out) -> None:
    """T_0 がある個体だけ：組み立ての確認 R(O) が自然な O を再現する（README §2.4・§7）。"""
    bad = out["rebuild_identity"]
    t0 = t0_of(run)
    o, r = run["natural_bodies"]["O"], control_entry(run)
    if r["start"] != o["state_t0"]:
        bad.append("R(O) の始まりの全状態が、O の T_0 の終わりの全状態と違う")
    if r["dynamics"] != o["dynamics"]:
        bad.append("R(O) の Unit の力学が O と違う")
    if any(spikes_of(r["spikes"], u) != in_range(o["spikes"], u, t0 + 1, plan.body_end) for u in UNITS):
        bad.append("R(O) の T_0 より後の発火が O と違う")
    for p in plan.rebuilt_snapshots:
        if r["states"][str(p)] != o["states"][str(p)]:
            bad.append(f"R(O) の Pulse {p} の終わりの全状態が O と違う")


def _check_replay(run, plan, out) -> None:
    """重みの再生・組の和・切り詰めなし。再生は本体の実装を呼ばない独立な計算（replay）。自然な本体は出生から（12000・T_0・
    13500・25500。T_0 がない個体は T_0 を除く）、R(O) は T_0 の写した状態から（13500・25500）。F 本体は可塑性がないので再生しない
    （重みの一定は f_weights_constant）。"""
    init = W.initial_connections(PROTOCOL)
    t0 = t0_of(run)
    rp, clip_bad = out["replay_weights_and_traces"], out["no_clipping"]
    for b, rec in run["natural_bodies"].items():
        marks = plan.snapshots + ((t0,) if t0 is not None else ())
        r = replay_all(init, rec["spikes"], 0, plan.body_end, marks)
        for p in plan.snapshots:
            st = rec["states"][str(p)]
            if not max_diff(r["at"][p], st["connections"]) <= TOL["replay_weights_and_traces"]:
                rp.append(f"{b}：{p} の再生と記録の重み・痕跡が一致しない")
            out["pair_sum"] += pair_sum_problems(st, f"{b}：Pulse {p}")
        if t0 is not None:
            if not max_diff(r["at"][t0], rec["state_t0"]["connections"]) <= TOL["replay_weights_and_traces"]:
                rp.append(f"{b}：T_0 の再生と、T_0 の終わりの全状態の記録の重み・痕跡が一致しない")
            out["pair_sum"] += pair_sum_problems(rec["state_t0"], f"{b}：T_0")
        if r["clipped"]:
            clip_bad.append(f"{b}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
    for where, st in natural_recorded_states(run["natural_bodies"]):
        if any(not W_MIN <= v[0] <= W_MAX for v in st["connections"].values()):
            clip_bad.append(f"{where}：記録した重みに [w_min, w_max] の外の値がある")
        if any(src in UNITS and not W_MIN <= w <= W_MAX for src, _, w, _ in st["drives"]):
            clip_bad.append(f"{where}：記録した Unit → Unit の駆動の重みに [w_min, w_max] の外の値がある")
    rec = control_entry(run)
    if t0 is None or rec is None:
        return
    r = replay_all(rec["start"]["connections"], rec["spikes"], t0, plan.body_end, plan.rebuilt_snapshots)
    for p in plan.rebuilt_snapshots:
        st = rec["states"][str(p)]
        if not max_diff(r["at"][p], st["connections"]) <= TOL["replay_weights_and_traces"]:
            rp.append(f"{CONTROL}：{p} の再生（T_0 の写した状態から）と記録が一致しない")
        out["pair_sum"] += pair_sum_problems(st, f"{CONTROL}：Pulse {p}")
    out["pair_sum"] += pair_sum_problems(rec["start"], f"{CONTROL} の始まり")
    if r["clipped"]:
        clip_bad.append(f"{CONTROL}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
    for where, st in rebuilt_recorded_states(rec, CONTROL):
        if any(not W_MIN <= v[0] <= W_MAX for v in st["connections"].values()):
            clip_bad.append(f"{where}：記録した重みに [w_min, w_max] の外の値がある")


# ---- 時間差 1 の発火の組の数（2 通りの算術。最後に確かめる）---------------------------------------------------------

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
    """主の区間の時間差 1 の組の数と各役の発火の数：{natural: {本体: 量}, F: {もとの本体: 量}}（T_0 がない個体の F は空）。
    2 通りの計算が一致し、0 ≤ N_{X→Y} ≤ min(X の [S, E − 1] の発火の数, Y の [S ＋ 1, E] の発火の数) が成り立つことを確かめる。
    値は返すが、呼び出し側は確認がすべて成り立ったときだけ使う（smoke では捨てる）。"""
    units = W.role_units(PROTOCOL, seed)
    lo, hi = plan.main
    problems: list[str] = []

    def one(name: str, sp: Mapping) -> dict:
        r1, r2 = _counts_route1(sp, units, lo, hi), _counts_route2(sp, units, lo, hi)
        if r1 != r2:
            problems.append(f"{name}：時間差 1 の組の数・発火の数が 2 通りの計算で違う")
        for x, y in PAIRS:
            cap = min(len(in_range(sp, units[x], lo, hi - 1)), len(in_range(sp, units[y], lo + 1, hi)))
            if not 0 <= r1["N"][f"{x}->{y}"] <= cap:
                problems.append(f"{name}：N_{{{x}→{y}}} が 0 以上・発火の数以下ではない")
        return r1

    table = {"natural": {b: one(b, rec["spikes"]) for b, rec in run["natural_bodies"].items()},
             "F": {b: one(name, rec["spikes"]) for name, b, rec in f_entries(run)}}
    return table, problems


# ---- 判定の量（本番・合成で、すべての確認が成り立ったときだけ。README §4・§6）----------------------------------------------

def body_quantities(entry: Mapping) -> dict:
    """1 つの本体の主の区間の量（整数）。Δ_AB ＝ N_{A→B} − N_{B→A}、Δ_AC ＝ N_{A→C} − N_{C→A}、D ＝ Δ_AB − Δ_AC、N_X は役の発火の数。"""
    n = entry["N"]
    dab, dac, dbc = n["A->B"] - n["B->A"], n["A->C"] - n["C->A"], n["B->C"] - n["C->B"]
    return {"N": dict(n), "spike_counts": dict(entry["spikes"]), "Delta_AB": dab, "Delta_AC": dac, "Delta_BC": dbc,
            "D": dab - dac, "silent_roles": [r for r in ROLES if entry["spikes"][r] == 0]}


def rank(x, refs: list) -> dict[str, int]:
    """x の、参照の 19 本の中での順位（下・同じ・上の本数）。"""
    return {"reference_below": sum(r < x for r in refs), "reference_equal": sum(r == x for r in refs),
            "reference_above": sum(r > x for r in refs)}


def _ref(q: Mapping, key: str) -> list:
    return [q[d][key] for d in REFERENCE]


def order_events(q: Mapping[str, Mapping]) -> dict[str, bool]:
    """0028 の形の一方向の 4 つの事象（厳密な不等号。等号・逆の向きは「外にない」）。q：{本体: 量}（O・M・W1〜W19）。
    F の家族の事象（F 本体の量に当てる）と、自然な本体の 0028 の形の事象（補助）に使う。"""
    if tuple(q) != BODIES:
        raise ValueError(f"本体が {BODIES} ではない")
    ab, d = _ref(q, "Delta_AB"), _ref(q, "D")
    ev = {"O_Delta_AB_above": q["O"]["Delta_AB"] > max(ab), "O_above": q["O"]["D"] > max(d), "M_below": q["M"]["D"] < min(d)}
    ev["O_and_M_split"] = ev["O_above"] and ev["M_below"]
    return ev


def _cnt_terms(q: Mapping[str, Mapping]) -> dict[str, list[tuple[int, int]]]:
    """README §3.3 の N^cnt の各 W_i の (左辺, 右辺)。Ca：Δ_AB(O) − Δ_AB(W_i) と |ΔN_A| ＋ |ΔN_B|。O：D(O) − D(W_i) と
    2|ΔN_A| ＋ |ΔN_B| ＋ |ΔN_C|（O と W_i の差）。M：D(W_i) − D(M) と 2|ΔN_A| ＋ |ΔN_B| ＋ |ΔN_C|（M と W_i の差）。"""
    n = {b: q[b]["spike_counts"] for b in q}

    def dn(x, y, r):
        return abs(n[x][r] - n[y][r])
    return {"E_Ca_cnt": [(q["O"]["Delta_AB"] - q[w]["Delta_AB"], dn("O", w, "A") + dn("O", w, "B")) for w in REFERENCE],
            "E_O_cnt": [(q["O"]["D"] - q[w]["D"], 2 * dn("O", w, "A") + dn("O", w, "B") + dn("O", w, "C")) for w in REFERENCE],
            "E_M_cnt": [(q[w]["D"] - q["M"]["D"], 2 * dn("M", w, "A") + dn("M", w, "B") + dn("M", w, "C")) for w in REFERENCE]}


def cnt_events(q: Mapping[str, Mapping]) -> dict[str, bool]:
    """README §3.3 の N^cnt の 4 つの事象（参照の 19 本すべてで厳密な ＞。E_OM は積）。q：自然な本体の量。"""
    if tuple(q) != BODIES:
        raise ValueError(f"本体が {BODIES} ではない")
    terms = _cnt_terms(q)
    ev = {e: all(lhs > rhs for lhs, rhs in terms[e]) for e in ("E_Ca_cnt", "E_O_cnt", "E_M_cnt")}
    ev["E_OM_cnt"] = ev["E_O_cnt"] and ev["E_M_cnt"]
    if tuple(ev) != EVENTS["Ncnt"]:
        raise ValueError("N^cnt の事象の名前が protocol と違う")
    return ev


def cnt_margins(q: Mapping[str, Mapping]) -> dict:
    """補助（README §6）：各事象で、不等式が成り立った W_i の数と、成り立たなかった W_i の「左辺 − 右辺」の最大（届かなかった
    うちで最も近いもの。すべて成り立てば None）。E_OM は、O と M の両方の不等式が成り立った W_i の数と、成り立たなかった W_i の
    min(O の左辺 − 右辺, M の左辺 − 右辺) の最大。記述だけ。"""
    terms = _cnt_terms(q)
    out = {}
    for e, t in terms.items():
        miss = [lhs - rhs for lhs, rhs in t if not lhs > rhs]
        out[e] = {"satisfied": len(t) - len(miss), "largest_shortfall_margin": max(miss) if miss else None}
    both = [min(a[0] - a[1], b[0] - b[1]) for a, b in zip(terms["E_O_cnt"], terms["E_M_cnt"])]
    miss = [m for m in both if not m > 0]
    out["E_OM_cnt"] = {"satisfied": len(both) - len(miss), "largest_shortfall_margin": max(miss) if miss else None}
    return out


def frozen(q: Mapping[str, Mapping]) -> dict[str, bool]:
    """判定に使う値がすべて等しい（凍結。README §4.1。0028 の形）：J_Ca は O と参照の Δ_AB の 20 本、J_O は O と参照の D、J_M は
    M と参照の D、J_OM は O・M・参照の D の 21 本。"""
    ab, d = _ref(q, "Delta_AB"), _ref(q, "D")
    return {"J_Ca": len(set(ab + [q["O"]["Delta_AB"]])) == 1, "J_O": len(set(d + [q["O"]["D"]])) == 1,
            "J_M": len(set(d + [q["M"]["D"]])) == 1, "J_OM": len(set(d + [q["O"]["D"], q["M"]["D"]])) == 1}


def birth_margins(dynamics: Mapping[str, Mapping], units: Mapping[str, str]) -> dict:
    """README §6：役 A・B・C の余裕 g ＝ c／(1 − λ) − θ（出生時の Unit の力学の値。c ＝ intrinsic_drive_per_second × Δt、
    λ ＝ decay_per_second^Δt）と層（構造的 g ＜ −0.03、条件付き −0.03 ≤ g ＜ 0、活動的 g ≥ 0）。"""
    out = {}
    for role in ROLES:
        dyn = dynamics[units[role]]
        lam = dyn["decay_per_second"] ** DT
        g = dyn["intrinsic_drive_per_second"] * DT / (1 - lam) - dyn["threshold"]
        stratum = ALIGN.STRATA[0] if g < ALIGN.STRUCTURAL_BOUND else (ALIGN.STRATA[1] if g < 0 else ALIGN.STRATA[2])
        out[role] = {"g": g, "stratum": stratum}
    return out


def individual(table: Mapping, natural_dynamics: Mapping, units: Mapping[str, str], t0: int | None) -> dict:
    """1 個体の評価：F の 4 つの事象（T_0 がない個体はすべて false）、N^cnt の 4 つの事象（T_0 に依らない）、補助
    （README §4.1・§6・§2.6）。"""
    natural = {b: body_quantities(table["natural"][b]) for b in BODIES}
    events = {"Ncnt": cnt_events(natural)}
    aux: dict = {"freeze_time": t0, "t0_exists": t0 is not None,
                 "natural_body_components": natural,
                 "natural_0028_form_events": order_events(natural),
                 "ncnt_margins": cnt_margins(natural),
                 "Ncnt_frozen": frozen(natural),
                 "birth_margin_strata": birth_margins(natural_dynamics, units)}
    if t0 is None:
        events["F"] = {e: False for e in EVENTS["F"]}
        for key in NULL_WITHOUT_T0:
            aux[key] = None
        aux["null_reason"] = NO_T0_REASON
        return {"events": {f: events[f] for f in FAMILIES}, "not_outside_reason": {"F": NO_T0_REASON, "Ncnt": None},
                "auxiliary": aux}
    fq = {b: body_quantities(table["F"][b]) for b in BODIES}
    events["F"] = order_events(fq)
    ab, d = _ref(fq, "Delta_AB"), _ref(fq, "D")
    aux |= {"F_body_components": fq,
            "F_ranks": {"rank_of_Delta_AB_FO_among_reference": rank(fq["O"]["Delta_AB"], ab),
                        "rank_of_D_FO_among_reference": rank(fq["O"]["D"], d),
                        "rank_of_D_FM_among_reference": rank(fq["M"]["D"], d)},
            "F_opposite_direction": {"Delta_AB_FO_below_min": fq["O"]["Delta_AB"] < min(ab), "D_FO_below_min": fq["O"]["D"] < min(d),
                                     "D_FM_above_max": fq["M"]["D"] > max(d)},
            "F_frozen": frozen(fq),
            "F_body_silence": {b: fq[b]["silent_roles"] for b in BODIES},
            "null_reason": None}
    return {"events": {f: events[f] for f in FAMILIES}, "not_outside_reason": {"F": None, "Ncnt": None}, "auxiliary": aux}


def quantities_for_seed(table: Mapping, natural_dynamics: Mapping, units: Mapping[str, str], t0: int | None) -> dict:
    return {"individual": individual(table, natural_dynamics, units, t0)}


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


def family_judgment(ind: Mapping[str, dict], family: str) -> dict:
    """1 つの家族の 4 つの主の判定（README §4.2・§5）と、補助の数え上げ（README §6）。T_0 がない個体は分母に残り、F の事象は false。
    家族の中・家族のあいだで、判定の成立を足し合わせたり h を比べたりしない。"""
    n = len(ind)
    k = len(REFERENCE)
    j = PROTOCOL["judgment"]
    split = j["per_family"]["alpha_split"]
    out = {"family": family, "bodies": j["families"][family]["bodies"], "direction": j["families"][family]["direction"],
           "alpha": j["families"][family]["alpha"], "n": n, "main_judgments": list(JUDGMENTS)}
    for J in JUDGMENTS:
        h = sum(v["events"][family][EVENT[family][J]] for v in ind.values())
        threshold = ALIGN.HOLDS_MIN[family][J]
        p0 = ALIGN.per_individual_null(J, k)
        out[J] = {"statistic": STATISTIC[J], STATISTIC[J]: h, "event": EVENT[family][J], "holds_if": f"{STATISTIC[J]} >= {threshold}",
                  "holds": h >= threshold, "alpha": split[J],
                  "per_individual_null_probability_at_most": f"{p0.numerator}/{p0.denominator}",
                  "binomial_upper_tail_at_threshold": float(binom_tail(n, p0, threshold)),
                  "clopper_pearson_95_of_h_over_n": clopper_pearson(h, n)}
    auxs = [v["auxiliary"] for v in ind.values()]
    if family == "F":
        with_t0 = [a for a in auxs if a["t0_exists"]]
        aux = {"no_t0_individuals": sum(not a["t0_exists"] for a in auxs),
               "frozen_among_individuals_with_t0": {J: sum(a["F_frozen"][J] for a in with_t0) for J in JUDGMENTS},
               "individuals_with_a_silent_role_in_some_F_body": sum(any(a["F_body_silence"].values()) for a in with_t0),
               "F_opposite_direction": {k2: sum(a["F_opposite_direction"][k2] for a in with_t0)
                                        for k2 in ("Delta_AB_FO_below_min", "D_FO_below_min", "D_FM_above_max")}}
    else:
        aux = {"frozen": {J: sum(a["Ncnt_frozen"][J] for a in auxs) for J in JUDGMENTS},
               "individuals_with_a_silent_role_in_some_natural_body": sum(
                   any(b["silent_roles"] for b in a["natural_body_components"].values()) for a in auxs),
               "natural_0028_form_event_counts": {e: sum(a["natural_0028_form_events"][e] for a in auxs) for e in NATURAL_EVENTS}}
    out["auxiliary"] = aux
    return out


def strata_counts(ind: Mapping[str, dict]) -> dict:
    """README §6・§2.6：役ごと・層ごとに、個体の数、T_0 がない個体の数、8 つの事象の個体の数（T_0 がない個体の F は「外にない」）。
    層ごとの判定は置かない。"""
    out = {}
    for role in ROLES:
        out[role] = {}
        for stratum in ALIGN.STRATA:
            members = [v for v in ind.values() if v["auxiliary"]["birth_margin_strata"][role]["stratum"] == stratum]
            out[role][stratum] = {"individuals": len(members),
                                  "no_t0": sum(not v["auxiliary"]["t0_exists"] for v in members),
                                  "events": {f: {e: sum(v["events"][f][e] for v in members) for e in EVENTS[f]}
                                             for f in FAMILIES}}
    return out


def judgment(per_seed: Mapping[str, dict]) -> dict:
    """家族（F・Ncnt）ごとの 4 つの主の判定。二つの家族を組み合わせた量は作らない（README §5.2）。"""
    j = PROTOCOL["judgment"]
    ind = {s: v["individual"] for s, v in per_seed.items()}
    fams = {f: family_judgment(ind, f) for f in FAMILIES}
    return {"families": fams, "experiment_wide_error_rate_claimed": j["experiment_wide_error_rate_claimed"],
            "scope": j["scope"], "not_judged": j["not_judged"],
            "no_t0_individuals": sorted(int(s) for s, v in ind.items() if not v["auxiliary"]["t0_exists"]),
            "birth_margin_strata_counts": strata_counts(ind),
            "note": ("家族（F・Ncnt）ごとに 4 つの主の判定 J_Ca・J_O・J_M・J_OM（どちらも一方向、閾値 4・4・4・2）。各家族の水準は 0.05"
                     "（J_Ca・J_O・J_M に 0.016 ずつ、J_OM に 0.002 の重みつきの Bonferroni）。成立は、交換可能性という帰無仮説を、個体間の"
                     "独立性という統計モデル上の前提のもとで、その判定の水準で棄却すること（交換可能性の破れの証明ではない）。実験全体"
                     "（8 判定）で誤りの水準 0.05 とは主張しない（単純な和の上界は 0.10）。二つの家族の結果を組み合わせた主張・h の比較は"
                     "しない。F の成立は「T_0 から可塑性を止めた変種でも現れた」まで、N^cnt の成立は「(a)・(b) の意味の数だけの違いでは"
                     "作れない」まで。0029 の Wt の効果の分解ではない。T_0 がない個体は 20 個体の分母に残り、F の 4 つの事象を「外にない」に"
                     "数える（凍結とは別に記録）。auxiliary・Clopper–Pearson の区間・自然な本体の 0028 の形の事象・N^cnt の余裕・出生時の"
                     "値の層は補助の記録で、主の不成立を救わない")}


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
    checks, t0_exists, invalid = {}, {}, []
    for s in seeds:
        if records["statuses"].get(str(s)) != "completed":
            continue
        start = G.read_seed(out, s)["start"]
        data = read_raw(G.seed_dir(out, s) / G.RAW)
        checks[str(s)] = check_seed(data, mode, s, plan, start)
        t0_exists[str(s)] = raw_t0_exists(data) if not checks[str(s)]["revalidate_from_raw"] else None
        if any(checks[str(s)].values()):
            invalid.append(s)
        del data
    counted = "not_evaluated"
    tables, extra = {}, {}
    if records["state"] == "complete" and not invalid:
        counted = "evaluated"
        for s in seeds:
            data = read_raw(G.seed_dir(out, s) / G.RAW)
            run = data["run"]
            tables[str(s)], problems = count_table(run, s, plan)
            checks[str(s)][COUNT_CHECK] = problems
            if problems:
                invalid.append(s)
            elif mode != "smoke":
                extra[str(s)] = {"dynamics": run["natural_bodies"]["O"]["dynamics"], "units": run["roles"]["units"],
                                 "t0": t0_of(run)}
            del data, run
    verify_analysis_commit(repo, records["measurement_commit"])     # 確認の途中で道具が変わっていない
    valid = records["state"] == "complete" and not invalid and counted == "evaluated"
    statuses = {s: check_statuses(c, t0_exists.get(s)) for s, c in checks.items()}
    if mode == "smoke":                              # smoke では T_0 の有無を表に出さない（pass と not_applicable を区別しない）
        statuses = {s: {k: (SMOKE_VALUES[0] if v == FAIL else SMOKE_VALUES[1]) for k, v in st.items()} for s, st in statuses.items()}
    report = base | {"valid": valid, "invalid_seeds": sorted(set(invalid)), "count_arithmetic": counted,
                     "checks": {s: {k: v for k, v in c.items() if v} for s, c in checks.items()},
                     "checks_evaluated": {s: sorted(c) for s, c in checks.items()},
                     "check_results": statuses}
    if not valid:
        tables.clear()
        extra.clear()
        return report | {"judgment": None, "note": (
            "invalid か記録の問題があるので、判定の量（N・Δ・D・事象・h・補助の量）は計算も表示もしない"
            "（judgment.on_any_invalid）。invalid を「外にない」に数えない。not_applicable（T_0 がない個体の F に固有の確認）"
            "は失敗ではない")}
    if mode == "smoke":
        tables.clear()
        extra.clear()
        return report | {"judgment": None, "note": ("smoke（操作の確認だけ）。判定の量も現象に関する数値（T_0 の値・T_0 の有無を"
                                                     "含む）も計算・表示・保存していない")}
    per_seed = {s: quantities_for_seed(tables[s], extra[s]["dynamics"], extra[s]["units"], extra[s]["t0"]) for s in tables}
    result = report | {"judgment": judgment(per_seed), "per_seed": per_seed,
                       "note": ("事前登録した検証。主の判定は家族（F・Ncnt）ごとに J_Ca・J_O・J_M・J_OM の 4 つ。"
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
