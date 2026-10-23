"""実験 0031 の記録の解析（確定した事前登録 v0.1 に従う）。正本は protocol.yaml・README。

0023〜0030 の解析の契約（PR #104・#108・#112・#115・#119・#124・#128・#131：記録の確認、生の記録からの操作の確認、invalid なら判定しない、
一度だけの report、解析の道具の HEAD ＝ 測定の commit）をそのまま引き継ぐ（ほかの実験の analyze.py は読み込まない）。0029 から
変えたのは、自然な本体 26（O・M・W1〜W24）、5 つの受け手 W20〜W24 への重みだけの入れ替え（入れ替えた本体 105・確認の本体 10）、
受け手ごとの順位の点とその合計（README §3.2）、主の判定が Agg の家族と All の家族（どちらも一方向）にそれぞれ 4 つであること
（README §4・§5）、それに合わせた操作の確認（README §7）と補助の記録（README §6）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる。
   違えば、何も読まず・書かず、判定の量を計算・表示せずに止まる（判定の量を計算する直前と、解析の終わりにも確かめ直す）
1. 実行の記録（seed ごとの開始・終了の記録、raw の SHA-256・バイト数。guard.py）を確かめる。
   - 未完了（まだ始めていない seed がある。失敗・中断・破損はない）：**解析しない**（何も読まず・書かずに止まる）
   - 失敗・中断・破損・範囲の外の seed・別の測定の commit：実験全体を invalid として、記録と操作の確認だけを報告する（判定しない）
2. 操作の確認（README §7・§2.6、protocol の checks）を、保存した生の記録から seed ごとに再検証する。確認ごとの結果は pass・fail・
   not_applicable（protocol の checks.result_values）。**τ がない個体**では、入れ替えに固有の 4 つ（checks.no_tau.not_applicable）は
   not_applicable（失敗ではなく、invalid の理由にならない）、ほかの確認は自然な本体だけで行い、τ の規則の確認は τ がないことの証明
   （window_witness の再検証）になる。fail が 1 つでもあればその個体は invalid で、実験全体を invalid とする（judgment.on_any_invalid）。
   raw の swap の欄と本体の並びが §2.6 の対応から外れていれば、また raw に判定の量の欄があれば（records.
   no_judgment_quantities_in_raw。raw の最上位・meta・run・各本体の欄の集合を固定し、余分な欄があれば）invalid。時間差 1 の組の数え方の 2 通りの算術（lag1_counts_two_ways）は、ほかのすべての確認が
   すべての個体で成り立ったときに最後に確かめる
3. 判定（README §4、protocol の quantities・judgment）：**本番（formal）・合成で、20 個の seed がすべて completed、raw のハッシュが一致、
   すべての個体で fail がないときだけ**、主・補助の量を計算して report に書く。家族（Agg・All）ごとに 4 つの主の判定 J_Ca・J_O・J_M・
   J_OM。τ がない個体は 20 個体の分母に残り、8 つの事象をすべて「外にない」に数える（凍結とは別に記録）。All の事象が Agg の事象の
   部分集合であること（README §4.3 の命題 1 の帰結 2）を、個体ごと・判定ごとに機械的に確かめる（破れていれば解析の誤りとして止まる）。
   smoke では判定の量も、現象に関する数値（τ の値・τ の有無を含む）も計算・表示・保存しない（操作の確認だけ。確認の結果は fail か ok
   〔pass と not_applicable を区別しない：checks.smoke_report_check_values〕だけを書き、成り立たなかった確認は名前だけを書く。
   理由の文〔τ の有無・時刻に触れうる〕は smoke の report に出さない）
4. report は一度だけ書く（既にあれば上書きしない。解析の記録 analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0031_multi_recipient_weight_swap/analyze.py                         # 本番（protocol の execution.output_dir）
  python experiments/0031_multi_recipient_weight_swap/analyze.py <フォルダ> --smoke        # smoke（操作の確認だけ。data/experiments の下には書かない）
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
NOT_APPLICABLE_WITHOUT_TAU = tuple(PROTOCOL["checks"]["no_tau"]["not_applicable"])
PASS, FAIL, NA = PROTOCOL["checks"]["result_values"]   # "pass"・"fail"・"not_applicable"
SMOKE_VALUES = tuple(PROTOCOL["checks"]["smoke_report_check_values"])   # ("fail", "ok")
UNITS = tuple(PROTOCOL["brain"]["sensory_units"])
RECEPTOR_UNIT = dict(PROTOCOL["brain"]["receptors"])
IV = PROTOCOL["intervention"]
RECIPIENTS, DONORS, REFERENCE = tuple(IV["recipients"]), tuple(IV["donors"]), tuple(IV["reference_donors"])
CONTROLS = tuple(IV["control_bodies"])             # ("full_swap", "null_swap")
FAMILIES = ALIGN.FAMILIES                          # ("Agg", "All")
BODIES, SHUFFLES, ROLES = W.BODIES, W.SHUFFLES, W.ROLES
UNIT_IDX = {f: i for i, f in enumerate(W.UNIT_FIELDS)}
CONN_IDX = {f: i for i, f in enumerate(W.CONNECTION_FIELDS)}
PAIRS = (("A", "B"), ("B", "A"), ("A", "C"), ("C", "A"), ("B", "C"), ("C", "B"))
PAIR_KEYS = tuple(f"{x}->{y}" for x, y in PAIRS)
JUDGMENTS, STATISTIC, EVENT, EVENTS = ALIGN.JUDGMENTS, ALIGN.STATISTIC, ALIGN.EVENT, ALIGN.EVENTS
QUANTITY_OF = {"J_Ca": "Delta_AB", "J_O": "D", "J_M": "D", "J_OM": "D"}
TARGET_OF = {"J_Ca": ("O",), "J_O": ("O",), "J_M": ("M",), "J_OM": ("O", "M")}   # 的の本体だけの沈黙を見る的（README §6）
NATURAL_EVENTS = tuple(PROTOCOL["quantities"]["auxiliary"]["per_individual"]["natural_comparison"]["events"])
NATURAL_REFERENCE = tuple(PROTOCOL["quantities"]["auxiliary"]["per_individual"]["natural_comparison"]["reference"])
NULL_WITHOUT_TAU = tuple(PROTOCOL["quantities"]["auxiliary"]["when_no_tau"]["null_with_reason_no_tau"])
NO_TAU_REASON = ALIGN.NO_TAU_REASON
RAW_KEYS = {"meta", "run"}                         # raw の最上位（run.py の compute_and_write が書く欄）
META_KEYS = {"experiment", "kind", "mode", "seed", "measurement_commit", "protocol_sha256", "protocol", "manifest"}
RUN_KEYS = {"seed", "plan", "roles", "swap_window", "swap", "natural_bodies", "swapped_bodies", "control_bodies"}
NATURAL_KEYS = {"body", "birth", "dynamics", "first_stimulus", "before_divergence", "states", "sensory", "spikes", "labels", "rng",
                "first_divergence_from_O", "state_tau"}
SWAPPED_KEYS = {"recipient", "donor", "swap", "state_tau", "states", "sensory", "spikes"}
CONTROL_KEYS = {"name", "recipient", "swap", "state_tau", "states", "sensory", "spikes"}


def _fields(names: Iterable[str]) -> tuple[list[str], list[str]]:
    """protocol の欄の名前（"units.activity" など）から (Unit の欄, 接続の欄)。world.py の定数を使わない（独立な組み立て）。"""
    names = list(names)
    unit_f = [x.split(".", 1)[1] for x in names if x.startswith("units.")]
    conn_f = [x.split(".", 1)[1] for x in names if x.startswith("connections.")]
    if len(unit_f) + len(conn_f) != len(names):
        raise ValueError("欄の名前が units.・connections. で始まらない")
    return unit_f, conn_f


WT_FIELDS = _fields(IV["block"]["replace"])                       # 入れ替えた本体：重みだけ
_keep_u, _keep_c = _fields(IV["block"]["keep_from_recipient"])
ALL_FIELDS = ([f for f in _keep_u if f != "fire_count"], WT_FIELDS[1] + _keep_c)   # 確認の本体：発火の回数を除くすべて


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


def tau_of(run: Mapping) -> int | None:
    """raw の τ（τ がない個体では None）。形の確認は _check_structure。"""
    return run["swap"]["tau"] if run["swap"]["tau_exists"] is True else None


def without_fire_count(st: Mapping) -> dict:
    """全状態から発火の回数（観察用の数で、力学に使わない）を除いたもの。"""
    return {k: ({u: [x for i, x in enumerate(v) if i != UNIT_IDX["fire_count"]] for u, v in st["units"].items()}
                if k == "units" else v) for k, v in st.items()}


def swapped_entries(run: Mapping) -> list[tuple[str, str, str, Mapping]]:
    """入れ替えた本体の一覧 [(名前, 受け手, ドナー, 記録)]。名前は Y_<受け手>(<ドナー>)。τ がなければ空。"""
    return [(f"Y_{rec['recipient']}({rec['donor']})", rec["recipient"], rec["donor"], rec) for rec in run["swapped_bodies"]]


def control_entries(run: Mapping) -> list[tuple[str, str, str, Mapping]]:
    """確認の本体の一覧 [(名前, 受け手, 種類, 記録)]。名前は <種類>(<受け手>)。"""
    return [(f"{rec['name']}({rec['recipient']})", rec["recipient"], rec["name"], rec) for rec in run["control_bodies"]]


def natural_recorded_states(bodies: Mapping) -> Iterator[tuple[str, object]]:
    """自然な本体の、raw に記録したすべての全状態（場所の名前と値）。τ の全状態は τ があるときだけ。"""
    for b, rec in bodies.items():
        yield f"{b} の出生時", rec["birth"]
        for part, name in (("first_stimulus", "最初の刺激"), ("before_divergence", "札が分かれる前"), ("states", "記録の時点")):
            for k, st in rec[part].items():
                yield f"{b} の{name}（{k}）", st
        if rec["state_tau"] is not None:
            yield f"{b} の τ", rec["state_tau"]


def swapped_recorded_states(run: Mapping) -> Iterator[tuple[str, object]]:
    """入れ替えた本体・確認の本体の、raw に記録したすべての全状態（入れ替えた直後と、記録の時点）。"""
    for name, _, _, rec in swapped_entries(run) + control_entries(run):
        yield f"{name} の入れ替えた直後", rec["state_tau"]
        for k, st in rec["states"].items():
            yield f"{name}（{k}）", st


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
    τ がない個体では、入れ替えに固有の確認は理由を作らない（not_applicable は check_statuses が付ける）。"""
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
        _check_swap_time(run, plan, out)
        if tau_of(run) is not None:
            _check_swap(run, plan, out)
        _check_replay(run, plan, out)
    except (KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        out["revalidate_from_raw"].append(f"記録の形が想定と違う（{e!r}）")
    return out


def raw_tau_exists(data: Mapping) -> bool | None:
    """raw の swap.tau_exists（真偽でなければ None）。"""
    try:
        v = data["run"]["swap"]["tau_exists"]
    except (KeyError, TypeError):
        return None
    return v if isinstance(v, bool) else None


def check_statuses(reasons: Mapping[str, list], tau_exists: bool | None) -> dict[str, str]:
    """確認ごとの結果（protocol の checks.result_values）：理由があれば fail。τ がない個体（tau_exists が False）の
    入れ替えに固有の確認は not_applicable（失敗ではない：README §2.6）。ほかは pass。"""
    out = {}
    for k, why in reasons.items():
        if why:
            out[k] = FAIL
        elif tau_exists is False and k in NOT_APPLICABLE_WITHOUT_TAU:
            out[k] = NA
        else:
            out[k] = PASS
    return out


def smoke_statuses(statuses: Mapping[str, str]) -> dict[str, str]:
    """smoke の report の確認の結果（protocol の checks.smoke_report_check_values）：fail か ok だけ（τ の有無を表に出さない）。"""
    fail, ok = SMOKE_VALUES
    return {k: (fail if v == FAIL else ok) for k, v in statuses.items()}


def _state_shape(st, what: str) -> list[str]:
    if not isinstance(st, dict) or tuple(st) != W.FULL_STATE_FIELDS:
        return [f"{what}：全状態の欄が {W.FULL_STATE_FIELDS} ではない"]
    for drive in st["drives"]:
        why = _drive_shape_problem(drive)
        if why is not None:
            return [f"{what}：{why}"]
    return []


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


def _check_structure(data, mode, seed, plan, start_record, out) -> None:
    """raw の形（README §2.6・§8）。swap の欄と本体の並びが §2.6 の対応から外れていれば、また raw に判定の量の欄があれば
    （records.no_judgment_quantities_in_raw）、ここで成り立たない（invalid）。"""
    bad = out["revalidate_from_raw"]
    if not isinstance(data, dict) or set(data) != RAW_KEYS:
        bad.append(f"raw の最上位の欄が {sorted(RAW_KEYS)} ではない（判定の量などの欄を書かない）")
        return
    meta, run = data["meta"], data["run"]
    if not isinstance(meta, dict) or set(meta) != META_KEYS:
        bad.append(f"raw の meta の欄が {sorted(META_KEYS)} ではない（判定の量などの欄を書かない）")
        return
    if not isinstance(run, dict):
        bad.append("raw の run が辞書ではない")
        return
    if (meta.get("experiment"), meta.get("kind"), meta.get("mode"), meta.get("seed")) != (EXPERIMENT, KIND, mode, seed):
        bad.append("raw の experiment・kind・mode・seed が想定と違う")
    if start_record is not None and (meta.get("measurement_commit"), meta.get("protocol_sha256")) != (
            start_record.get("measurement_commit"), start_record.get("protocol_sha256")):
        bad.append("raw の測定の commit・protocol の SHA-256 が開始の記録と違う")
    if meta.get("protocol") != PROTOCOL:
        bad.append("raw の protocol が今の protocol.yaml と違う")
    if meta.get("manifest") != W.manifest_raw(PROTOCOL):
        bad.append("raw の設計図が今の設計図と違う")
    if set(run) != RUN_KEYS:
        bad.append(f"raw の run の欄が {sorted(RUN_KEYS)} ではない（判定の量などの欄を書かない）")
        return
    if run.get("seed") != seed:
        bad.append("結果の seed がフォルダの seed と違う")
    if run.get("plan") != plan.as_dict():
        bad.append("raw の Plan（経験・遅れ・τ の窓・主の区間・本体の終わり・最初の刺激）が想定と違う")
    if run.get("roles") != {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)}:
        bad.append("役の割り当てが (seed − 1) mod 6 と違う")
    lo, hi = plan.swap_window
    if run.get("swap_window") != [lo, hi]:
        bad.append("raw の τ の窓が Plan と違う")
    # swap の欄（README §2.6 の表。どちらの場合も同じ鍵）
    swap = run.get("swap")
    if not isinstance(swap, dict) or set(swap) != {"tau_exists", "tau", "window_witness"}:
        bad.append("raw の swap の欄が tau_exists・tau・window_witness ではない")
        return
    exists, tau = swap["tau_exists"], swap["tau"]
    swapped, controls = run.get("swapped_bodies"), run.get("control_bodies")
    n_sw, n_ct = len(RECIPIENTS) * len(DONORS), len(RECIPIENTS) * len(CONTROLS)
    if exists is True:
        if not (isinstance(tau, int) and not isinstance(tau, bool) and lo <= tau <= hi):
            bad.append("τ があるのに、τ が窓の中の整数ではない")
        if swap["window_witness"] is not None:
            bad.append("τ があるのに、window_witness が null ではない")
        if not isinstance(swapped, list) or len(swapped) != n_sw:
            bad.append(f"τ があるのに、入れ替えた本体が {n_sw} の配列ではない")
        if not isinstance(controls, list) or len(controls) != n_ct:
            bad.append(f"τ があるのに、確認の本体が {n_ct} の配列ではない")
    elif exists is False:
        if tau is not None:
            bad.append("τ がないのに、τ が null ではない")
        if not isinstance(swap["window_witness"], list):
            bad.append("τ がないのに、window_witness が配列ではない")
        if swapped != [] or controls != []:
            bad.append("τ がないのに、入れ替えた本体・確認の本体が空の配列ではない")
    else:
        bad.append("swap.tau_exists が真偽ではない")
    if bad:
        return
    tau = tau_of(run)
    # 自然な本体
    bodies = run.get("natural_bodies") or {}
    if tuple(bodies) != BODIES:
        bad.append(f"自然な本体が {BODIES} ではない")
        return
    want_states = [str(p) for p in plan.snapshots]
    want_first = [str(p) for p in plan.first_stimulus]
    for b, rec in bodies.items():
        if not isinstance(rec, dict) or set(rec) != NATURAL_KEYS:
            bad.append(f"{b}：自然な本体の記録の欄が想定と違う")
            return
        if rec.get("body") != b:
            bad.append(f"{b}：本体の記録の名前が違う")
        bad += well_formed(rec["spikes"], 1, plan.body_end, f"{b} の本体")
        if list(rec["states"]) != want_states or any(rec["states"][k]["pulse"] != int(k) for k in want_states):
            bad.append(f"{b}：全状態の時点が {want_states} ではない")
        if list(rec["first_stimulus"]) != want_first or any(rec["first_stimulus"][k]["pulse"] != int(k) for k in want_first):
            bad.append(f"{b}：最初の刺激の全状態の時点が {want_first} ではない")
        if any(st["pulse"] != int(k) for k, st in rec["before_divergence"].items()):
            bad.append(f"{b}：札が分かれる前の全状態の Pulse の番号が違う")
        if tau is None:
            if rec["state_tau"] is not None:
                bad.append(f"{b}：τ がないのに、τ の全状態が null ではない")
        elif not isinstance(rec["state_tau"], dict) or rec["state_tau"].get("pulse") != tau:
            bad.append(f"{b}：τ の終わりの全状態の記録が τ と合わない")
    for where, st in natural_recorded_states(bodies):
        bad += _state_shape(st, where)
    if tau is None or bad:
        return
    # 入れ替えた本体・確認の本体（τ があるとき）。受け手の順、その中でドナーの順・確認の種類の順
    if any(not isinstance(rec, dict) or set(rec) != SWAPPED_KEYS for rec in swapped):
        bad.append("入れ替えた本体の記録の欄が想定と違う")
        return
    if any(not isinstance(rec, dict) or set(rec) != CONTROL_KEYS for rec in controls):
        bad.append("確認の本体の記録の欄が想定と違う")
        return
    if [(rec["recipient"], rec["donor"]) for rec in swapped] != [(r, d) for r in RECIPIENTS for d in DONORS]:
        bad.append("入れ替えた本体の並び（受け手・ドナー）が想定と違う")
        return
    if [(rec["recipient"], rec["name"]) for rec in controls] != [(r, c) for r in RECIPIENTS for c in CONTROLS]:
        bad.append("確認の本体の並び（受け手・種類）が想定と違う")
        return
    want_sw = [str(p) for p in plan.swapped_snapshots]
    for name, _, _, rec in swapped_entries(run) + control_entries(run):
        bad += well_formed(rec["spikes"], tau + 1, plan.body_end, name)
        if not isinstance(rec["state_tau"], dict) or rec["state_tau"].get("pulse") != tau:
            bad.append(f"{name}：入れ替えた直後の全状態の Pulse が τ ではない")
        if list(rec["states"]) != want_sw or any(rec["states"][k]["pulse"] != int(k) for k in want_sw):
            bad.append(f"{name}：全状態の時点が {want_sw} ではない")
        elif tau == plan.pre_main and rec["states"][str(tau)] != rec["state_tau"]:
            bad.append(f"{name}：τ が主の区間の始まりの 1 つ前なのに、その時点の全状態が入れ替えた直後の全状態と違う")
    for where, st in swapped_recorded_states(run):
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
    if len(rec["O"]) != 3 * plan.trials:
        bad.append(f"O：刺激の数が 3 × 試行の数（{3 * plan.trials}）ではない")


def _check_birth(run, out) -> None:
    """自然な 26 本体の出生時の全状態・Unit の力学が同じで、接続の状態が設計図の初期値（README §7）。"""
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
    bad = out["input_free_after_experience"]
    for b, rec in run["natural_bodies"].items():
        if any(p > plan.experience_end for p, _ in rec["sensory"]):
            bad.append(f"{b}：経験の後に感覚の出来事がある")
    for name, _, _, rec in swapped_entries(run) + control_entries(run):   # τ より後には Receptor の出来事がない
        if rec["sensory"]:
            bad.append(f"{name}：τ より後に感覚の出来事がある")


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


# ---- τ の規則・入れ替えの確認（README §2.2・§2.6・§7。world.py の関数を呼ばない独立な組み立て）------------------------------

def _first_firing_at(bodies: Mapping, t: int) -> tuple[str, str] | None:
    """Pulse t に発火した自然な本体と Unit のうち、本体を O・M・W1〜W24、Unit を s1・s2・s3 の順に見て最初のもの（二分探索）。"""
    for b in BODIES:
        for u in UNITS:
            xs = spikes_of(bodies[b]["spikes"], u)
            i = bisect.bisect_left(xs, t)
            if i < len(xs) and xs[i] == t:
                return b, u
    return None


def _check_swap_time(run, plan, out) -> None:
    """τ の規則（README §2.2）。τ がある個体：記録した自然な 26 本体の発火の列から、窓の各 Pulse に発火があるかを数え直し、
    自然な本体の τ の全状態に駆動・Delta がないことを確かめる。τ がない個体：τ がないことの証明（README §2.6）。"""
    bad = out["swap_time_rule"]
    lo, hi = plan.swap_window
    bodies = run["natural_bodies"]
    fired = {t for rec in bodies.values() for u in UNITS for t in in_range(rec["spikes"], u, lo, hi)}
    quiet = [t for t in range(hi, lo - 1, -1) if t not in fired]       # 窓の終わりから数える（world と別の書き方）
    tau = tau_of(run)
    if tau is None:
        if quiet:
            bad.append(f"τ がないと記録されているが、窓の中に、どの自然な本体も発火していない Pulse がある（{len(quiet)} 個）")
        witness = run["swap"]["window_witness"]
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
    if tau in fired:
        bad.append("τ に、どれかの自然な本体で発火がある")
    if any(t not in fired for t in range(tau + 1, hi + 1)):
        bad.append("τ より後の窓に、どの自然な本体も発火していない Pulse がある（τ が最後ではない）")
    if not quiet or quiet[0] != tau:
        bad.append("記録した τ が、発火の列から数え直した τ と違う")
    for b, rec in bodies.items():
        st = rec["state_tau"]
        if st["drives"] != [] or st["deltas"] != 0:
            bad.append(f"{b}：τ の終わりに、次の Pulse に届く駆動か Delta がある")


def composed_state(recipient: Mapping, donor: Mapping, fields: tuple[list[str], list[str]]) -> dict:
    """README §2.3・§2.4：受け手の全状態のうち、fields（(Unit の欄, 接続の欄)）だけをドナーの値にした全状態（期待する入れ替えた状態）。"""
    unit_f, conn_f = fields
    st = copy.deepcopy(dict(recipient))
    for u in st["units"]:
        for f in unit_f:
            st["units"][u][UNIT_IDX[f]] = donor["units"][u][UNIT_IDX[f]]
    for cid in st["connections"]:
        for f in conn_f:
            st["connections"][cid][CONN_IDX[f]] = donor["connections"][cid][CONN_IDX[f]]
    return st


def invariant_problems(st: Mapping, what: str) -> list[str]:
    """入れ替えた状態の I1〜I4（protocol の invariants_checked_on_swapped_state）。"""
    problems = pair_sum_problems(st, f"{what}（I1）")
    conns = st["connections"]
    for u in UNITS:                                   # I2：痕跡が Unit ごとに一つの値
        vals = [v[CONN_IDX["pre_trace"]] for cid, v in conns.items() if W.unit_of(cid)[0] == u]
        vals += [v[CONN_IDX["post_trace"]] for cid, v in conns.items() if W.unit_of(cid)[1] == u]
        if len(set(vals)) != 1:
            problems.append(f"{what}（I2）：{u} の痕跡が接続によって違う")
    if any(not v[UNIT_IDX["activity"]] > 0 for v in st["units"].values()):
        problems.append(f"{what}（I3）：activity が正でない Unit がある")
    if st["drives"] != [] or st["deltas"] != 0:
        problems.append(f"{what}（I4）：次の Pulse に届く駆動か Delta がある")
    return problems


def _check_swap(run, plan, out) -> None:
    """τ がある個体だけ：受け手ごとの入れ替えの組み立て・不変の関係・全部の入れ替え・入れ替えなし（README §7）。"""
    tau = tau_of(run)
    bodies = run["natural_bodies"]
    comp_bad, inv_bad = out["swap_composition"], out["swap_invariants"]
    for name, r, d, rec in swapped_entries(run):
        if rec["swap"] != {"tau": tau, "block": "weights", "recipient": r, "donor": d}:
            comp_bad.append(f"{name}：入れ替えの記録（τ・塊・受け手・ドナー）が想定と違う")
        if rec["state_tau"] != composed_state(bodies[r]["state_tau"], bodies[d]["state_tau"], WT_FIELDS):
            comp_bad.append(f"{name}：入れ替えた状態が、{r} の τ の状態の重みだけを {d} の値にしたものと違う")
        inv_bad += invariant_problems(rec["state_tau"], name)
    o = bodies["O"]
    for name, r, kind, rec in control_entries(run):
        donor = "O" if kind == "full_swap" else r
        if rec["swap"] != {"tau": tau, "recipient": r, "kind": kind}:
            comp_bad.append(f"{name}：入れ替えの記録（τ・受け手・種類）が想定と違う")
        if rec["state_tau"] != composed_state(bodies[r]["state_tau"], bodies[donor]["state_tau"], ALL_FIELDS):
            comp_bad.append(f"{name}：入れ替えた状態が、{r} の τ の状態の発火の回数を除くすべてを {donor} の値にしたものと違う")
        inv_bad += invariant_problems(rec["state_tau"], name)
        if kind == "full_swap":                       # O の自然な軌道（τ より後の発火、13500〔τ ＜ 13500 のとき〕・25500。発火の回数を除く）
            bad = out["full_swap_reproduces_donor"]
            if any(spikes_of(rec["spikes"], u) != in_range(o["spikes"], u, tau + 1, plan.body_end) for u in UNITS):
                bad.append(f"{name} の τ より後の発火が O の自然な本体と違う")
            for p in plan.swapped_snapshots:
                if p == plan.pre_main and tau >= plan.pre_main:
                    continue
                if without_fire_count(rec["states"][str(p)]) != without_fire_count(o["states"][str(p)]):
                    bad.append(f"{name} の Pulse {p} の終わりの全状態（発火の回数を除く）が O の自然な本体と違う")
        else:                                         # 入れ替えなし：受け手 r の自然な軌道と全く同じ
            bad = out["null_swap_identity"]
            w = bodies[r]
            if any(spikes_of(rec["spikes"], u) != in_range(w["spikes"], u, tau + 1, plan.body_end) for u in UNITS):
                bad.append(f"{name} の τ より後の発火が {r} の自然な本体と違う")
            for p in plan.swapped_snapshots:
                if rec["states"][str(p)] != w["states"][str(p)]:
                    bad.append(f"{name} の Pulse {p} の終わりの全状態が {r} の自然な本体と違う")


def _check_replay(run, plan, out) -> None:
    """重みの再生・組の和・切り詰めなし。再生は本体の実装を呼ばない独立な計算（replay）。自然な本体は出生から（12000・τ・13500・
    25500。τ がない個体は τ を除く）、入れ替えた本体・確認の本体は τ の入れ替えた状態から（13500・25500）。"""
    init = W.initial_connections(PROTOCOL)
    tau = tau_of(run)
    rp, clip_bad = out["replay_weights_and_traces"], out["no_clipping"]
    for b, rec in run["natural_bodies"].items():
        marks = plan.snapshots + ((tau,) if tau is not None else ())
        r = replay_all(init, rec["spikes"], 0, plan.body_end, marks)
        for p in plan.snapshots:
            st = rec["states"][str(p)]
            if not max_diff(r["at"][p], st["connections"]) <= TOL["replay_weights_and_traces"]:
                rp.append(f"{b}：{p} の再生と記録の重み・痕跡が一致しない")
            out["pair_sum"] += pair_sum_problems(st, f"{b}：Pulse {p}")
        if tau is not None:
            if not max_diff(r["at"][tau], rec["state_tau"]["connections"]) <= TOL["replay_weights_and_traces"]:
                rp.append(f"{b}：τ の再生と、τ の終わりの全状態の記録の重み・痕跡が一致しない")
            out["pair_sum"] += pair_sum_problems(rec["state_tau"], f"{b}：τ")
        if r["clipped"]:
            clip_bad.append(f"{b}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
    for where, st in natural_recorded_states(run["natural_bodies"]):
        if any(not W_MIN <= v[0] <= W_MAX for v in st["connections"].values()):
            clip_bad.append(f"{where}：記録した重みに [w_min, w_max] の外の値がある")
        if any(src in UNITS and not W_MIN <= w <= W_MAX for src, _, w, _ in st["drives"]):
            clip_bad.append(f"{where}：記録した Unit → Unit の駆動の重みに [w_min, w_max] の外の値がある")
    if tau is None:
        return
    for name, _, _, rec in swapped_entries(run) + control_entries(run):
        r = replay_all(rec["state_tau"]["connections"], rec["spikes"], tau, plan.body_end, plan.swapped_snapshots)
        for p in plan.swapped_snapshots:
            st = rec["states"][str(p)]
            if not max_diff(r["at"][p], st["connections"]) <= TOL["replay_weights_and_traces"]:
                rp.append(f"{name}：{p} の再生（τ の入れ替えた状態から）と記録が一致しない")
            out["pair_sum"] += pair_sum_problems(st, f"{name}：Pulse {p}")
        out["pair_sum"] += pair_sum_problems(rec["state_tau"], f"{name} の τ の入れ替えた状態")
        if r["clipped"]:
            clip_bad.append(f"{name}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
    for where, st in swapped_recorded_states(run):
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
    """主の区間の時間差 1 の組の数の材料：{natural: {本体: 量}, swapped: {受け手: {ドナー: 量}}, controls: {名前: 量}}
    （τ がない個体の swapped・controls は空）。2 通りの計算が一致し、0 ≤ N_{X→Y} ≤ min(X の [S, E − 1] の発火の数,
    Y の [S ＋ 1, E] の発火の数) が成り立つことを確かめる。値は返すが、呼び出し側は確認がすべて成り立ったときだけ使う
    （smoke では捨てる）。"""
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
             "swapped": {r: {} for r in RECIPIENTS} if run["swapped_bodies"] else {}, "controls": {}}
    for name, r, d, rec in swapped_entries(run):
        table["swapped"][r][d] = one(name, rec["spikes"])
    for name, _, _, rec in control_entries(run):
        table["controls"][name] = one(name, rec["spikes"])
    return table, problems


# ---- 判定の量（本番・合成で、すべての確認が成り立ったときだけ。README §3.2・§4・§6）----------------------------------------

def body_quantities(entry: Mapping) -> dict:
    """1 つの本体の主の区間の量（整数）。Δ_AB ＝ N_{A→B} − N_{B→A}、Δ_AC ＝ N_{A→C} − N_{C→A}、D ＝ Δ_AB − Δ_AC、N_X は役の発火の数。"""
    n = entry["N"]
    dab, dac, dbc = n["A->B"] - n["B->A"], n["A->C"] - n["C->A"], n["B->C"] - n["C->B"]
    return {"N": dict(n), "spike_counts": dict(entry["spikes"]), "Delta_AB": dab, "Delta_AC": dac, "Delta_BC": dbc,
            "D": dab - dac, "silent_roles": [r for r in ROLES if entry["spikes"][r] == 0]}


def rank_scores(values: Mapping[str, int]) -> dict[str, int]:
    """README §3.2：受け手の中の順位の点 s(d) ＝ Σ_{e ∈ 𝒟, e ≠ d} sgn(x(d) − x(e))（21 のドナーの中で。同じ値は 0。−20〜20）。
    values：{ドナー: 量}（ドナーの順）。e ＝ d の項は sgn(0) ＝ 0 なので、すべての e で足してよい。"""
    if tuple(values) != DONORS:
        raise ValueError(f"ドナーが {DONORS} ではない")
    xs = list(values.values())
    return {d: sum((x > y) - (x < y) for y in xs) for d, x in values.items()}


def outside_events(ab: Mapping[str, int], d: Mapping[str, int], reference: Iterable[str] = REFERENCE) -> dict[str, bool]:
    """0029 の Wt の形の一方向の 4 つの事象（厳密な不等号。等号・逆の向きは「外にない」）。ab・d：{本体: 値}（O・M・参照を含む）。
    Agg は合計の点に、All は受け手ごとの値に、自然な本体の比較（補助）は自然な本体の値に当てる。"""
    reference = tuple(reference)
    ref_ab, ref_d = [ab[x] for x in reference], [d[x] for x in reference]
    ev = {"O_Delta_AB_above": ab["O"] > max(ref_ab), "O_above": d["O"] > max(ref_d), "M_below": d["M"] < min(ref_d)}
    ev["O_and_M_split"] = ev["O_above"] and ev["M_below"]
    if tuple(ev) != EVENTS:
        raise ValueError("事象の名前が protocol と違う")
    return ev


def frozen(ab: Mapping[str, int], d: Mapping[str, int]) -> dict[str, bool]:
    """判定に使う値がすべて等しい（凍結。README §4.1）。J_Ca：O と参照の 20 個、J_O：O と参照の D、J_M：M と参照の D、J_OM：21 個。"""
    ref_ab, ref_d = [ab[x] for x in REFERENCE], [d[x] for x in REFERENCE]
    return {"J_Ca": len(set(ref_ab + [ab["O"]])) == 1, "J_O": len(set(ref_d + [d["O"]])) == 1,
            "J_M": len(set(ref_d + [d["M"]])) == 1, "J_OM": len(set(ref_d + [d["O"], d["M"]])) == 1}


def rank(x, refs: list) -> dict[str, int]:
    """x の、参照の 19 本の中での順位（下・同じ・上の本数）。"""
    return {"reference_below": sum(r < x for r in refs), "reference_equal": sum(r == x for r in refs),
            "reference_above": sum(r > x for r in refs)}


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


def scores_of(sw: Mapping[str, Mapping[str, Mapping]]) -> dict:
    """README §3.2：受け手ごとの値 x_r(d)、順位の点 s^x_r(d)、合計の点 S^x(d)（x ＝ Delta_AB・D）。sw：{受け手: {ドナー: 量}}。"""
    values = {x: {r: {d: sw[r][d][x] for d in DONORS} for r in RECIPIENTS} for x in ("Delta_AB", "D")}
    per = {x: {r: rank_scores(values[x][r]) for r in RECIPIENTS} for x in values}
    total = {x: {d: sum(per[x][r][d] for r in RECIPIENTS) for d in DONORS} for x in values}
    return {"values": values, "rank_scores": per, "total_scores": total}


def nesting_violations(agg: Mapping[str, bool], all_: Mapping[str, bool]) -> list[str]:
    """README §4.3 の命題 1 の帰結 2（All ⊆ Agg）が破れた事象（All が成り立ち Agg が成り立たない）。成り立つなら空。"""
    return [e for e in EVENTS if all_[e] and not agg[e]]


def target_only_silence(sw: Mapping[str, Mapping[str, Mapping]]) -> dict:
    """README §6：受け手ごとに、Y_r(O)・Y_r(M) の沈黙した役の集合が、Y_r(W1)〜Y_r(W19) のどれとも違うか。"""
    out = {}
    for t in ("O", "M"):
        hit = [r for r in RECIPIENTS
               if all(set(sw[r][t]["silent_roles"]) != set(sw[r][w]["silent_roles"]) for w in REFERENCE)]
        out[t] = {"recipients": hit, "count": len(hit)}
    return out


def individual(table: Mapping, natural_dynamics: Mapping, units: Mapping[str, str], tau: int | None) -> dict:
    """1 個体の評価：8 つの主の事象（τ がない個体はすべて false）と補助（README §4.1・§6・§2.6）。All ⊆ Agg を確かめる。"""
    natural = {b: body_quantities(table["natural"][b]) for b in BODIES}
    aux: dict = {"swap_time": tau, "tau_exists": tau is not None,
                 "natural_body_components": natural,
                 "natural_comparison": outside_events({b: natural[b]["Delta_AB"] for b in BODIES},
                                                      {b: natural[b]["D"] for b in BODIES}, NATURAL_REFERENCE),
                 "birth_margin_strata": birth_margins(natural_dynamics, units)}
    if tau is None:
        for key in NULL_WITHOUT_TAU:
            aux[key] = None
        aux["null_reason"] = NO_TAU_REASON
        return {"events": {f: dict.fromkeys(EVENTS, False) for f in FAMILIES}, "not_outside_reason": NO_TAU_REASON,
                "auxiliary": aux}
    sw = {r: {d: body_quantities(table["swapped"][r][d]) for d in DONORS} for r in RECIPIENTS}
    controls = {n: body_quantities(e) for n, e in table["controls"].items()}
    sc = scores_of(sw)
    per_r = {r: outside_events(sc["values"]["Delta_AB"][r], sc["values"]["D"][r]) for r in RECIPIENTS}
    agg = outside_events(sc["total_scores"]["Delta_AB"], sc["total_scores"]["D"])
    all_ = {e: all(per_r[r][e] for r in RECIPIENTS) for e in EVENTS}
    broken = nesting_violations(agg, all_)
    if broken:
        raise ValueError(f"All ⊆ Agg（README §4.3 の命題 1 の帰結 2）が破れた：{broken}（解析の誤り）")
    tot_ab, tot_d = sc["total_scores"]["Delta_AB"], sc["total_scores"]["D"]
    ref_ab, ref_d = [tot_ab[x] for x in REFERENCE], [tot_d[x] for x in REFERENCE]
    frozen_r = {r: frozen(sc["values"]["Delta_AB"][r], sc["values"]["D"][r]) for r in RECIPIENTS}
    aux |= {
        "swapped_body_components": {"swapped": sw, "controls": controls},
        "scores": {"rank_scores": sc["rank_scores"], "total_scores": sc["total_scores"]},
        "per_recipient_0029_form_events": {"events": per_r, "k": {e: sum(per_r[r][e] for r in RECIPIENTS) for e in EVENTS}},
        "ranks": {"rank_of_total_Delta_AB_O_among_reference": rank(tot_ab["O"], ref_ab),
                  "rank_of_total_D_O_among_reference": rank(tot_d["O"], ref_d),
                  "rank_of_total_D_M_among_reference": rank(tot_d["M"], ref_d)},
        "Agg_opposite_direction": {"total_Delta_AB_O_below_min": tot_ab["O"] < min(ref_ab), "total_D_O_below_min": tot_d["O"] < min(ref_d),
                                   "total_D_M_above_max": tot_d["M"] > max(ref_d)},
        "frozen_per_judgment": {"Agg": frozen(tot_ab, tot_d),
                                "All": {J: sum(frozen_r[r][J] for r in RECIPIENTS) for J in JUDGMENTS}},
        "target_only_silence": target_only_silence(sw),
        "swapped_body_silence": {r: {d: sw[r][d]["silent_roles"] for d in DONORS} for r in RECIPIENTS},
        "null_reason": None}
    return {"events": {"Agg": agg, "All": all_}, "not_outside_reason": None, "auxiliary": aux}


def quantities_for_seed(table: Mapping, natural_dynamics: Mapping, units: Mapping[str, str], tau: int | None) -> dict:
    return {"individual": individual(table, natural_dynamics, units, tau)}


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


def _target_silent(a: Mapping, J: str) -> bool:
    return any(a["target_only_silence"][t]["count"] > 0 for t in TARGET_OF[J])


def family_judgment(ind: Mapping[str, dict], family: str) -> dict:
    """1 つの家族の 4 つの主の判定（README §4.2・§5）と、補助の数え上げ（README §6）。τ がない個体は分母に残り、事象は false。
    家族の中・家族のあいだで、判定の成立を足し合わせたり h を比べたりしない。"""
    n = len(ind)
    k = len(REFERENCE)
    j = PROTOCOL["judgment"]
    split = j["per_family"]["alpha_split"]
    out = {"family": family, "events_from": j["families"][family]["events"], "direction": j["families"][family]["direction"],
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
    with_tau = [v for v in ind.values() if v["auxiliary"]["tau_exists"]]
    aux: dict = {"no_tau_individuals": n - len(with_tau),
                 "event_with_target_only_silence": {
                     J: sum(v["events"][family][EVENT[family][J]] and _target_silent(v["auxiliary"], J) for v in with_tau)
                     for J in JUDGMENTS}}
    if family == "Agg":
        aux["frozen_among_individuals_with_tau"] = {J: sum(v["auxiliary"]["frozen_per_judgment"]["Agg"][J] for v in with_tau)
                                                    for J in JUDGMENTS}
        aux["Agg_opposite_direction"] = {k2: sum(v["auxiliary"]["Agg_opposite_direction"][k2] for v in with_tau)
                                         for k2 in ("total_Delta_AB_O_below_min", "total_D_O_below_min", "total_D_M_above_max")}
    else:
        aux["frozen_recipients_distribution"] = {
            J: {str(c): sum(v["auxiliary"]["frozen_per_judgment"]["All"][J] == c for v in with_tau) for c in range(len(RECIPIENTS) + 1)}
            for J in JUDGMENTS}
    out["auxiliary"] = aux
    return out


def strata_counts(ind: Mapping[str, dict]) -> dict:
    """README §6・§2.6：役ごと・層ごとに、個体の数、τ がない個体の数、8 つの事象の個体の数（τ がない個体は「外にない」）。
    層ごとの判定は置かない。"""
    out = {}
    for role in ROLES:
        out[role] = {}
        for stratum in ALIGN.STRATA:
            members = [v for v in ind.values() if v["auxiliary"]["birth_margin_strata"][role]["stratum"] == stratum]
            out[role][stratum] = {"individuals": len(members),
                                  "no_tau": sum(not v["auxiliary"]["tau_exists"] for v in members),
                                  "events": {f: {e: sum(v["events"][f][e] for v in members) for e in EVENTS} for f in FAMILIES}}
    return out


def judgment(per_seed: Mapping[str, dict]) -> dict:
    """家族（Agg・All）ごとの 4 つの主の判定と、8 判定をまとめた水準（入れ子による。README §5.2）。h^All ≤ h^Agg を確かめる。"""
    j = PROTOCOL["judgment"]
    ind = {s: v["individual"] for s, v in per_seed.items()}
    fams = {f: family_judgment(ind, f) for f in FAMILIES}
    for J in JUDGMENTS:                               # 命題 1 の帰結 2 の、個体をまたいだ形
        if fams["All"][J][STATISTIC[J]] > fams["Agg"][J][STATISTIC[J]]:
            raise ValueError(f"{J}：h^All ＞ h^Agg（README §4.3 の命題 1 の帰結 2 が破れた。解析の誤り）")
    with_tau = [v for v in ind.values() if v["auxiliary"]["tau_exists"]]
    k_dist = {e: {str(c): sum(v["auxiliary"]["per_recipient_0029_form_events"]["k"][e] == c for v in with_tau)
                  for c in range(len(RECIPIENTS) + 1)} for e in EVENTS}
    silent = sum(any(any(x for x in by_d.values()) for by_d in v["auxiliary"]["swapped_body_silence"].values()) for v in with_tau)
    natural = {e: sum(v["auxiliary"]["natural_comparison"][e] for v in ind.values()) for e in NATURAL_EVENTS}
    return {"families": fams, "nesting": j["nesting"],
            "nesting_verified": {"per_individual_all_implies_agg": True, "per_judgment_h_all_le_h_agg": True},
            "experiment_wide_error_rate_claimed": j["experiment_wide_error_rate_claimed"],
            "scope": j["scope"], "not_judged": j["not_judged"],
            "no_tau_individuals": sorted(int(s) for s, v in ind.items() if not v["auxiliary"]["tau_exists"]),
            "distribution_of_k_per_event": k_dist,
            "individuals_with_a_silent_role_in_some_swapped_body": silent,
            "natural_comparison_counts": natural, "birth_margin_strata_counts": strata_counts(ind),
            "note": ("家族（Agg・All）ごとに 4 つの主の判定 J_Ca・J_O・J_M・J_OM（どちらも一方向、閾値 4・4・4・2）。各家族の中は"
                     "J_Ca・J_O・J_M に 0.016 ずつ、J_OM に 0.002 の重みつきの Bonferroni。All の事象は Agg の事象の部分集合で、"
                     "帰無仮説・閾値も同じなので、8 判定のどれかの誤った棄却は Agg の 4 判定のどれかの誤った棄却に含まれ、8 判定を"
                     "まとめた誤りの水準は 0.05（README §5.2。0031 の 8 判定に限る）。成立は、ドナーの交換可能性という帰無仮説を、"
                     "個体間の独立性・受け手とドナーの独立という統計モデル上の前提のもとで棄却すること（交換可能性の破れの証明では"
                     "ない）。主張の水準は C-I の一般化まで（背景の異質性・任意の背景は言わない）。h^All と h^Agg の比・差、受け手ごとの"
                     "事象の数 k を、背景への依存の量として読まない。τ がない個体は 20 個体の分母に残り、8 つの事象を「外にない」に"
                     "数える（凍結とは別に記録）。補助は記録で、主の不成立を救わない")}


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
    checks, tau_exists, invalid = {}, {}, []
    for s in seeds:
        if records["statuses"].get(str(s)) != "completed":
            continue
        start = G.read_seed(out, s)["start"]
        data = read_raw(G.seed_dir(out, s) / G.RAW)
        checks[str(s)] = check_seed(data, mode, s, plan, start)
        tau_exists[str(s)] = raw_tau_exists(data) if not checks[str(s)]["revalidate_from_raw"] else None
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
                                 "tau": tau_of(run)}
            del data, run
    verify_analysis_commit(repo, records["measurement_commit"])     # 確認の途中で道具が変わっていない
    valid = records["state"] == "complete" and not invalid and counted == "evaluated"
    statuses = {s: check_statuses(c, tau_exists.get(s)) for s, c in checks.items()}
    if mode == "smoke":                              # smoke では τ の有無を表に出さない（pass と not_applicable を区別しない）
        statuses = {s: smoke_statuses(st) for s, st in statuses.items()}
    if mode == "smoke":                              # smoke では成り立たなかった確認の名前だけ（理由の文は τ に触れうるので出さない）
        failed = {s: sorted(k for k, v in c.items() if v) for s, c in checks.items()}
    else:
        failed = {s: {k: v for k, v in c.items() if v} for s, c in checks.items()}
    report = base | {"valid": valid, "invalid_seeds": sorted(set(invalid)), "count_arithmetic": counted,
                     "checks": failed,
                     "checks_evaluated": {s: sorted(c) for s, c in checks.items()},
                     "check_results": statuses}
    if not valid and mode == "smoke":
        tables.clear()
        extra.clear()
        return report | {"judgment": None, "note": ("smoke（操作の確認だけ）。invalid か記録の問題がある。確認の結果は fail・ok と、"
                                                     "成り立たなかった確認の名前だけを書く（理由の文は書かない）。判定の量も現象に"
                                                     "関する数値も計算・表示・保存していない")}
    if not valid:
        tables.clear()
        extra.clear()
        return report | {"judgment": None, "note": (
            "invalid か記録の問題があるので、判定の量（N・Δ・D・点・事象・h・補助の量）は計算も表示もしない"
            "（judgment.on_any_invalid）。invalid を「外にない」に数えない。not_applicable（τ がない個体の入れ替えに固有の確認）"
            "は失敗ではない")}
    if mode == "smoke":
        tables.clear()
        extra.clear()
        return report | {"judgment": None, "note": ("smoke（操作の確認だけ）。判定の量も現象に関する数値（τ の値・τ の有無を"
                                                     "含む）も計算・表示・保存していない")}
    per_seed = {s: quantities_for_seed(tables[s], extra[s]["dynamics"], extra[s]["units"], extra[s]["tau"]) for s in tables}
    result = report | {"judgment": judgment(per_seed), "per_seed": per_seed,
                       "note": ("事前登録した検証。主の判定は家族（Agg・All）ごとに J_Ca・J_O・J_M・J_OM の 4 つ。"
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
