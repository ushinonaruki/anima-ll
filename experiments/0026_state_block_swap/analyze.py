"""実験 0026 の記録の解析（確定した事前登録 v0.2 に従う）。正本は protocol.yaml・README。

0023〜0025 の解析の契約（PR #104・#108・#112：記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、
解析の道具の HEAD ＝ 測定の commit）をそのまま引き継ぐ（ほかの実験の analyze.py は読み込まない）。0025 から変えたのは、
自然な本体が O・W1〜W20（M なし）であること、入れ替えた本体 40・確認の本体 2 の操作の確認（README §7 の T の規則・入れ替えの
組み立て・不変の関係・全部の入れ替え・入れ替えなし、入れ替えた本体の試し・再生）と、主の判定が 2 つ（重み・Unit の状態。
それぞれ h ≥ 6：README §5）になったこと、補助の記録（README §6）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる。
   違えば、何も読まず・書かず、判定の量を計算・表示せずに止まる（判定の量を計算する直前と、解析の終わりにも確かめ直す）
1. 実行の記録（seed ごとの開始・終了の記録、raw の SHA-256・バイト数。guard.py）を確かめる。
   - 未完了（まだ始めていない seed がある。失敗・中断・破損はない）：**解析しない**（何も読まず・書かずに止まる。
     途中の seed だけで判定の量を計算・表示しない）
   - 失敗・中断・破損・範囲の外の seed・別の測定の commit：実験全体を invalid として、記録と操作の確認だけを報告する（判定しない）
2. 操作の確認（README §7、protocol の checks）を、保存した生の記録から seed ごとに再検証する。確認の名前ごとに、成り立たなかった
   理由を残す。1 つでも成り立たなければその個体は invalid で、実験全体を invalid とする（judgment.on_any_invalid）。
   打ち切りの算術（censor_arithmetic_recomputed）だけは、ほかのすべての確認がすべての個体で成り立ったときに最後に確かめる
3. 判定（README §5、protocol の quantities・judgment）：**本番（formal）で、20 個の seed がすべて completed、raw のハッシュが一致、
   すべての個体ですべての確認が成り立ったときだけ**、主・補助の量を計算して report に書く。smoke では判定の量（ℓ・L・外にあるか・
   h・補助の量）も、現象に関する数値（T の値など）も、計算・表示・保存しない（操作の確認だけ）
4. report は一度だけ書く（既にあれば上書きしない。解析の記録 analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

入れ替えの確認（README §7）は、world.py の入れ替えの関数を呼ばずに、protocol の intervention.blocks の欄の一覧から
期待する状態を組み立て直して比べる（独立な計算）。T も、記録した発火の列から規則どおりに数え直す。

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0026_state_block_swap/analyze.py                         # 本番（protocol の execution.output_dir）
  python experiments/0026_state_block_swap/analyze.py <フォルダ> --smoke        # smoke（操作の確認だけ。data/experiments の下には書かない）
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
IV = PROTOCOL["intervention"]
FAMILIES = tuple(IV["blocks"])                     # ("weights", "units")：主の判定の 2 つの家族
DONORS = tuple(IV["donors"])                       # O と W2〜W20
RECIPIENT = IV["recipient"]
# 全状態の欄の並び（world.full_state と同じ形。生の記録の欄の位置）
UNIT_IDX = {"activity": 0, "adaptation": 1, "refractory_remaining": 2, "fire_count": 3}
CONN_IDX = {"weight": 0, "pre_trace": 1, "post_trace": 2}


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
    """自然な本体の Pulse p の終わりの全状態（各 Pulse の記録から）。"""
    st = body["states"][p - body["states_from"]]
    if st["pulse"] != p:
        raise ValueError(f"{body['body']} の Pulse {p} の状態の Pulse が {st['pulse']}")
    return st


def selected_at(rec: Mapping, p: int) -> Mapping:
    """入れ替えた本体の Pulse p の終わりの全状態（selected_pulses の記録から）。"""
    st = rec["states"][str(p)]
    if st["pulse"] != p:
        raise ValueError(f"入れ替えた本体の Pulse {p} の状態の Pulse が {st['pulse']}")
    return st


def swapped_bodies(run: Mapping) -> list[tuple[str, str, str, Mapping]]:
    """入れ替えた本体の一覧 [(名前, 塊, ドナー, 記録)]。名前は Y(塊<-ドナー)。T がなければ空。"""
    return [(f"Y({c}<-{d})", c, d, rec) for c in FAMILIES for d, rec in run["swapped"][c].items()]


def without_fire_count(st: Mapping) -> dict:
    """全状態から発火の回数（観察用の数で、力学に使わない）を除いたもの。"""
    return {k: ({u: [x for i, x in enumerate(v) if i != UNIT_IDX["fire_count"]] for u, v in st["units"].items()}
                if k == "units" else v) for k, v in st.items()}


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
    record = tuple(record)
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
    w = {cid: v[CONN_IDX["weight"]] for cid, v in st["connections"].items()}
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
        _check_before_divergence(run, out)
        _check_probes(run, seed, plan, out)
        _check_empty_side(run, plan, out)
        _check_twin(run, plan, out)
        _check_swap_time(run, plan, out)
        _check_swap(run, plan, out)
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
    if meta.get("manifest") != W.manifest_raw(PROTOCOL):
        bad.append("raw の設計図が今の設計図と違う")
    if run.get("seed") != seed:
        bad.append("結果の seed がフォルダの seed と違う")
    if run.get("plan") != plan.as_dict():
        bad.append("raw の Plan（経験・試し・窓・本体の終わり）が想定と違う")
    if run.get("roles") != {"receptors": W.role_receptors(PROTOCOL, seed), "units": W.role_units(PROTOCOL, seed)}:
        bad.append("役の割り当てが (seed − 1) mod 6 と違う")
    lo, hi = W.swap_window(PROTOCOL, plan)
    if run.get("swap_window") != [lo, hi]:
        bad.append("raw の T の窓が protocol の式と違う")
    T = run.get("swap_time")
    if T is not None and not (isinstance(T, int) and lo <= T <= hi):
        bad.append("raw の T が窓の中の整数でも None でもない")
    bodies = run.get("bodies") or {}
    if tuple(bodies) != W.BODIES or "O_twin" not in run:
        bad.append(f"自然な本体が {W.BODIES} と O の双子ではない")
        return
    for b, rec in bodies.items():
        bad += well_formed(rec["spikes"], 1, plan.body_end, f"{b} の本体")
        if rec["states_from"] != plan.states_from or len(rec["states"]) != plan.body_end - plan.states_from + 1:
            bad.append(f"{b}：各 Pulse の状態の範囲が {plan.states_from}〜{plan.body_end} ではない")
        elif any(st["pulse"] != plan.states_from + k for k, st in enumerate(rec["states"])):
            bad.append(f"{b}：各 Pulse の状態の Pulse の番号が並んでいない")
        if (rec["state_T"] is None) != (T is None) or (T is not None and rec["state_T"]["pulse"] != T):
            bad.append(f"{b}：T の終わりの全状態の記録が T と合わない")
        if [c["t0"] for c in rec["probes"]] != list(plan.probes):
            bad.append(f"{b}：試しの t0 が {plan.probes[0]}〜{plan.probes[-1]} の全件ではない")
        for c in rec["probes"]:
            t0 = c["t0"]
            bad += well_formed(c["spikes"], t0, t0 + 1 + plan.window, f"{b} の t0 {t0} の A の複製")
            if {k: v["pulse"] for k, v in c["states"].items()} != {"t0-1": t0 - 1, "t0": t0, "t0+1": t0 + 1,
                                                                  "end": t0 + 1 + plan.window}:
                bad.append(f"{b} の t0 {t0}：A の複製の状態の時点が想定と違う")
        if [c["t0"] for c in rec["empty_side"]] != [plan.probes[0], plan.probes[-1]]:
            bad.append(f"{b}：空の側の複製が最初と最後の試しではない")
        for c in rec["empty_side"]:
            bad += well_formed(c["spikes"], c["t0"], c["t0"] + 1 + plan.window, f"{b} の空の側の複製 {c['t0']}")
    tw = run["O_twin"]
    bad += well_formed(tw["spikes"], 1, plan.body_end, "O の双子")
    if (tw["state_experience_end"]["pulse"], tw["state_end"]["pulse"]) != (plan.experience_end, plan.body_end):
        bad.append("O の双子の状態の時点が想定と違う")
    swapped, controls = run.get("swapped"), run.get("controls")
    if not isinstance(swapped, dict) or tuple(swapped) != FAMILIES:
        bad.append(f"入れ替えた本体の家族が {FAMILIES} ではない")
        return
    if T is None:
        if any(swapped[c] for c in FAMILIES) or controls is not None:
            bad.append("T がないのに、入れ替えた本体・確認の本体がある")
        return
    if any(tuple(swapped[c]) != DONORS for c in FAMILIES):
        bad.append(f"各家族のドナーが {DONORS} の順ではない")
        return
    if not isinstance(controls, dict) or tuple(controls) != W.CONTROLS:
        bad.append(f"確認の本体が {W.CONTROLS} ではない")
        return
    keep = {str(p) for p in W.selected_pulses(plan)}
    edges = (plan.probes[0], plan.probes[-1])
    for name, _, _, rec in swapped_bodies(run):
        bad += well_formed(rec["spikes"], T + 1, plan.body_end, name)
        if rec["state_T"]["pulse"] != T:
            bad.append(f"{name}：入れ替えた直後の全状態の Pulse が T ではない")
        if set(rec["states"]) != keep or any(v["pulse"] != int(k) for k, v in rec["states"].items()):
            bad.append(f"{name}：全状態を残した Pulse が selected_pulses ではない")
        if [c["t0"] for c in rec["probes"]] != list(plan.probes):
            bad.append(f"{name}：試しの t0 が全件ではない")
        for c in rec["probes"]:
            t0 = c["t0"]
            bad += well_formed(c["spikes"], t0, t0 + 1 + plan.window, f"{name} の t0 {t0} の A の複製")
            if t0 in edges:
                if {k: v["pulse"] for k, v in c.get("states", {}).items()} != {
                        "t0-1": t0 - 1, "t0": t0, "t0+1": t0 + 1, "end": t0 + 1 + plan.window}:
                    bad.append(f"{name} の t0 {t0}：A の複製の 4 時点の全状態がない・時点が違う")
            elif "states" in c:
                bad.append(f"{name} の t0 {t0}：最初と最後以外の試しに全状態がある（記録の項目と違う）")
    for name, rec in controls.items():
        bad += well_formed(rec["spikes"], T + 1, plan.body_end, name)
        if (rec["state_T"]["pulse"], rec["state_experience_end"]["pulse"], rec["state_end"]["pulse"]) != (
                T, plan.experience_end, plan.body_end):
            bad.append(f"{name}：全状態の時点が想定と違う")


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
        for slots in W.trial_slots(PROTOCOL, plan):                   # 試行の中の釣り合い（README §2.1・§7）
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
        for c in rec["probes"]:
            if c["sensory"] != [[c["t0"], a_rec]]:
                bad.append(f"{b} の t0 {c['t0']}：A の複製の感覚の出来事が t0 の A の 1 つだけではない")
        for c in rec["empty_side"]:
            if c["sensory"]:
                bad.append(f"{b} の空の側の複製 {c['t0']} に感覚の出来事がある")
    tw = run["O_twin"]
    if any(p > plan.experience_end for p, _ in tw["sensory"]) or tw["sensory"] != run["bodies"]["O"]["sensory"]:
        bad.append("O の双子の感覚の出来事が O の本体と違うか、経験の後にある")
    for name, _, _, rec in swapped_bodies(run):                       # T より後には Receptor の出来事がない
        if rec["sensory"]:
            bad.append(f"{name}：T より後に感覚の出来事がある")
        for c in rec["probes"]:
            if c["sensory"] != [[c["t0"], a_rec]]:
                bad.append(f"{name} の t0 {c['t0']}：A の複製の感覚の出来事が t0 の A の 1 つだけではない")
    for name, rec in (run["controls"] or {}).items():
        if rec["sensory"]:
            bad.append(f"{name}：T より後に感覚の出来事がある")


def _check_before_divergence(run, out) -> None:
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
            if rec["spikes"] != o["spikes"] or rec["states"] != o["states"]:
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


def _probe_identity(name, c, body_state, body_spikes, units, a_rec, w_in, clone_bad, ident_bad) -> None:
    """A の複製の t0 − 1 の全状態が本体と同じで、t0・t0 ＋ 1 の終わりまで B・C の Unit の状態・発火、t0 の重み・痕跡が本体と同じ、
    t0 の駆動が本体のものに A の入力の駆動を足したもの（0025 と同じ確認）。body_state(p) は本体の Pulse p の終わりの全状態。"""
    t0, st, sp = c["t0"], c["states"], c["spikes"]
    if st["t0-1"] != body_state(t0 - 1):
        clone_bad.append(f"{name} の t0 {t0}：A の複製の t0 − 1 の全状態が本体と違う")
    for key, p in (("t0", t0), ("t0+1", t0 + 1)):
        body = body_state(p)
        for role in ("B", "C"):
            u = units[role]
            if st[key]["units"][u] != body["units"][u]:
                ident_bad.append(f"{name} の t0 {t0}：{role} の Unit の状態が {key} の終わりで本体と違う")
            if fired_at(sp, u, p) != fired_at(body_spikes, u, p):
                ident_bad.append(f"{name} の t0 {t0}：{role} の {key} の発火が本体と違う")
    body_t0 = body_state(t0)
    if st["t0"]["connections"] != body_t0["connections"]:
        ident_bad.append(f"{name} の t0 {t0}：t0 の終わりの重み・痕跡が本体と違う")
    if st["t0"]["drives"] != sorted(body_t0["drives"] + [[a_rec, units["A"], w_in, t0]]):
        ident_bad.append(f"{name} の t0 {t0}：t0 の終わりの次の Pulse に届く駆動が、本体のものに A の入力の駆動を足したものと違う")


def _check_probes(run, seed, plan, out) -> None:
    clone_bad, ident_bad, p3_bad = (out["probe_clone_equals_body_t0_minus_1"], out["identical_through_t0_plus_1"],
                                    out["proposition_3"])
    units = W.role_units(PROTOCOL, seed)
    a_rec = W.role_receptors(PROTOCOL, seed)["A"]
    m = parse_neuroarchitecture(W.manifest_raw(PROTOCOL))
    w_in = next(p.weight for p in m.projections if p.source_id == a_rec and p.target_id == units["A"])
    edges = (plan.probes[0], plan.probes[-1])
    targets = [(b, rec, (lambda p, rec=rec: state_at(rec, p)), True) for b, rec in run["bodies"].items()]
    targets += [(name, rec, (lambda p, rec=rec: selected_at(rec, p)), False) for name, _, _, rec in swapped_bodies(run)]
    for name, rec, body_state, every_probe in targets:
        for c in rec["probes"]:
            t0 = c["t0"]
            if every_probe or t0 in edges:            # 自然な本体はすべての試し、入れ替えた本体は最初と最後の試し
                _probe_identity(name, c, body_state, rec["spikes"], units, a_rec, w_in, clone_bad, ident_bad)
            for role in ("B", "C"):                   # 命題 3：すべての本体・すべての試し
                u = units[role]
                if fired_at(c["spikes"], u, t0 + 2) < fired_at(rec["spikes"], u, t0 + 2):
                    p3_bad.append(f"{name} の t0 {t0}：{role}^A(t0 + 2) ≥ {role}^∅(t0 + 2) が成り立たない")


def _check_empty_side(run, plan, out) -> None:
    bad = out["empty_side_identity"]
    for b, rec in run["bodies"].items():
        for c in rec["empty_side"]:
            t0, end = c["t0"], c["t0"] + 1 + plan.window
            if any(in_range(c["spikes"], u, t0, end) != in_range(rec["spikes"], u, t0, end) for u in UNITS):
                bad.append(f"{b} の空の側の複製 {t0}：窓の終わりまでの発火が本体と違う")
            if c["states_from"] != t0 - 1 or len(c["states"]) != end - t0 + 2:
                bad.append(f"{b} の空の側の複製 {t0}：状態の範囲が t0 − 1〜窓の終わりではない")
                continue
            for k, st in enumerate(c["states"]):
                if st != state_at(rec, t0 - 1 + k):
                    bad.append(f"{b} の空の側の複製 {t0}：Pulse {t0 - 1 + k} の終わりの全状態が本体と違う")
                    break


def _check_twin(run, plan, out) -> None:
    bad = out["O_twin_identity"]
    o, tw = run["bodies"]["O"], run["O_twin"]
    if tw["birth"] != o["birth"] or tw["dynamics"] != o["dynamics"]:
        bad.append("O の双子の出生時の状態が O と違う")
    if {u: spikes_of(tw["spikes"], u) for u in UNITS} != {u: spikes_of(o["spikes"], u) for u in UNITS}:
        bad.append("O の双子の 1〜終わりの発火が O の本体と違う")
    if tw["state_experience_end"] != state_at(o, plan.experience_end):
        bad.append("O の双子の経験の終わりの全状態が O の本体と違う")
    if tw["state_end"] != state_at(o, plan.body_end):
        bad.append("O の双子の終わりの全状態が O の本体と違う")


# ---- 入れ替えの確認（README §2.2・§7。world.py の入れ替えの関数を呼ばない独立な組み立て）------------------------------------

def _check_swap_time(run, plan, out) -> None:
    """T の規則（README §2.2）：記録した自然な 21 本体の発火の列から、窓の各 Pulse に発火があるかを数え直す。"""
    bad = out["swap_time_rule"]
    lo, hi = W.swap_window(PROTOCOL, plan)
    T = run["swap_time"]
    bodies = run["bodies"]
    fired = {t for rec in bodies.values() for u in UNITS for t in in_range(rec["spikes"], u, lo, hi)}
    quiet = [t for t in range(hi, lo - 1, -1) if t not in fired]       # 窓の終わりから数える（world と別の書き方）
    if T is None:
        if quiet:
            bad.append("T がないと記録されているが、窓の中に、どの自然な本体も発火していない Pulse がある")
    else:
        if not lo <= T <= hi:
            bad.append("T が窓の外にある")
        if T in fired:
            bad.append("T に、どれかの自然な本体で発火がある")
        if any(t not in fired for t in range(T + 1, hi + 1)):
            bad.append("T より後の窓に、どの自然な本体も発火していない Pulse がある（T が最後ではない）")
        if not quiet or quiet[0] != T:
            bad.append("記録した T が、発火の列から数え直した T と違う")
        for b, rec in bodies.items():
            st = rec["state_T"]
            if st["drives"] != [] or st["deltas"] != 0:
                bad.append(f"{b}：T の終わりに、次の Pulse に届く駆動か Delta がある")
    for b, rec in bodies.items():
        if any(lo <= p <= hi for p, _ in rec["sensory"]):
            bad.append(f"{b}：T の窓の中に感覚の出来事がある")


def _block_fields() -> dict[str, tuple[list[str], list[str]]]:
    """protocol の intervention.blocks の replace（"units.activity" など）から、塊 → (Unit の欄, 接続の欄)。"""
    out = {}
    for c, spec in IV["blocks"].items():
        unit_f = [x.split(".", 1)[1] for x in spec["replace"] if x.startswith("units.")]
        conn_f = [x.split(".", 1)[1] for x in spec["replace"] if x.startswith("connections.")]
        if len(unit_f) + len(conn_f) != len(spec["replace"]):
            raise ValueError(f"塊 {c} の欄の名前が units.・connections. で始まらない")
        out[c] = (unit_f, conn_f)
    return out


def composed_state(recipient: Mapping, donor: Mapping, blocks: Iterable[str]) -> dict:
    """README §2.3：受け手の全状態のうち、塊 blocks の欄だけをドナーの値にした全状態（期待する入れ替えた状態）。"""
    fields = _block_fields()
    st = copy.deepcopy(dict(recipient))
    for c in blocks:
        unit_f, conn_f = fields[c]
        for u in st["units"]:
            for f in unit_f:
                st["units"][u][UNIT_IDX[f]] = donor["units"][u][UNIT_IDX[f]]
        for cid in st["connections"]:
            for f in conn_f:
                st["connections"][cid][CONN_IDX[f]] = donor["connections"][cid][CONN_IDX[f]]
    return st


def invariant_problems(st: Mapping, what: str) -> list[str]:
    """入れ替えた状態の I1〜I4（README §3、protocol の invariants_checked_on_swapped_state）。"""
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
    T = run["swap_time"]
    if T is None:
        return
    bodies, controls = run["bodies"], run["controls"]
    w1 = bodies[RECIPIENT]["state_T"]
    comp_bad, inv_bad = out["swap_composition"], out["swap_invariants"]
    states = []
    for name, c, d, rec in swapped_bodies(run):
        if rec["swap"] != {"T": T, "recipient": RECIPIENT, "blocks": [c], "donor": d}:
            comp_bad.append(f"{name}：入れ替えの記録（T・受け手・塊・ドナー）が想定と違う")
        if rec["state_T"] != composed_state(w1, bodies[d]["state_T"], [c]):
            comp_bad.append(f"{name}：入れ替えた状態が、W1 の T の状態の {c} の欄だけをドナーの値にしたものと違う")
        states.append((name, rec["state_T"]))
    for name, donor in (("full_swap", "O"), ("null_swap", RECIPIENT)):
        rec = controls[name]
        if rec["swap"] != {"T": T, "recipient": RECIPIENT, "blocks": list(FAMILIES), "donor": donor}:
            comp_bad.append(f"{name}：入れ替えの記録が想定と違う")
        if rec["state_T"] != composed_state(w1, bodies[donor]["state_T"], FAMILIES):
            comp_bad.append(f"{name}：入れ替えた状態が、W1 の T の状態の両方の塊を {donor} の値にしたものと違う")
        states.append((name, rec["state_T"]))
    for name, st in states:
        inv_bad += invariant_problems(st, name)
        out["pair_sum"] += pair_sum_problems(st, f"{name} の T の入れ替えた状態")
    # 全部の入れ替え：O の自然な軌道（T より後の発火、12000・終わりの全状態。発火の回数を除く）と一致
    fs, o = controls["full_swap"], bodies["O"]
    bad = out["full_swap_reproduces_donor"]
    if any(spikes_of(fs["spikes"], u) != in_range(o["spikes"], u, T + 1, plan.body_end) for u in UNITS):
        bad.append("full_swap の T より後の発火が O の自然な本体と違う")
    for key, p in (("state_experience_end", plan.experience_end), ("state_end", plan.body_end)):
        if without_fire_count(fs[key]) != without_fire_count(state_at(o, p)):
            bad.append(f"full_swap の Pulse {p} の終わりの全状態（発火の回数を除く）が O の自然な本体と違う")
    # 入れ替えなし：W1 の自然な軌道と全く同じ
    ns, w = controls["null_swap"], bodies[RECIPIENT]
    bad = out["null_swap_identity"]
    if any(spikes_of(ns["spikes"], u) != in_range(w["spikes"], u, T + 1, plan.body_end) for u in UNITS):
        bad.append("null_swap の T より後の発火が W1 の自然な本体と違う")
    for key, p in (("state_experience_end", plan.experience_end), ("state_end", plan.body_end)):
        if ns[key] != state_at(w, p):
            bad.append(f"null_swap の Pulse {p} の終わりの全状態が W1 の自然な本体と違う")


def _check_replay(run, plan, out) -> None:
    """重みの再生（12000）・組の和・切り詰めなし。再生は本体の実装を呼ばない独立な計算（replay）。
    自然な本体は出生から、入れ替えた本体・確認の本体は T の入れ替えた状態から（README §7）。"""
    init = W.initial_connections(PROTOCOL)
    T = run["swap_time"]
    rp, clip_bad = out["replay_history_12000"], out["no_clipping"]
    for b, rec in run["bodies"].items():
        if rec["birth"]["connections"] != init:
            rp.append(f"{b}：出生時の接続の状態が設計図の初期値（痕跡 0）と違う")
        marks = (plan.experience_end,) + ((T,) if T is not None else ())
        r = replay_all(init, rec["spikes"], 0, plan.body_end, marks)
        if not max_diff(r["at"][plan.experience_end], state_at(rec, plan.experience_end)["connections"]) <= TOL["replay_history_12000"]:
            rp.append(f"{b}：{plan.experience_end} の再生と記録の重み・痕跡が一致しない")
        if T is not None and not max_diff(r["at"][T], rec["state_T"]["connections"]) <= TOL["replay_history_12000"]:
            rp.append(f"{b}：T の再生と、T の終わりの全状態の記録の重み・痕跡が一致しない")
        if not max_diff(r["end"], state_at(rec, plan.body_end)["connections"]) <= TOL["replay_history_12000"]:
            clip_bad.append(f"{b}：切り詰めの監査に使う再生が、終わりの記録と一致しない")
        if r["clipped"]:
            clip_bad.append(f"{b}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
        for t in (plan.experience_end, plan.body_end):
            out["pair_sum"] += pair_sum_problems(state_at(rec, t), f"{b}：Pulse {t}")
        for c in rec["probes"]:
            t0, end = c["t0"], c["t0"] + 1 + plan.window
            rc = replay_all(c["states"]["t0-1"]["connections"], c["spikes"], t0 - 1, end)
            if not max_diff(rc["end"], c["states"]["end"]["connections"]) <= TOL["replay_history_12000"]:
                clip_bad.append(f"{b} の t0 {t0}：A の複製の再生が窓の終わりの記録と一致しない")
            if rc["clipped"]:
                clip_bad.append(f"{b} の t0 {t0}：A の複製の重みが [w_min, w_max] の外に出た")
        states = rec["states"] + [s for c in rec["probes"] for s in c["states"].values()]
        if any(not W_MIN <= v[0] <= W_MAX for s in states for v in s["connections"].values()):
            clip_bad.append(f"{b}：記録した重みに [w_min, w_max] の外の値がある")
    if T is None:
        return
    edges = (plan.probes[0], plan.probes[-1])
    for name, _, _, rec in swapped_bodies(run):
        starts = tuple(t0 - 1 for t0 in plan.probes)
        marks = tuple(dict.fromkeys((plan.experience_end,) + starts))
        r = replay_all(rec["state_T"]["connections"], rec["spikes"], T, plan.body_end, marks)
        if not max_diff(r["at"][plan.experience_end], selected_at(rec, plan.experience_end)["connections"]) <= TOL["replay_history_12000"]:
            rp.append(f"{name}：{plan.experience_end} の再生（T の入れ替えた状態から）と記録が一致しない")
        if not max_diff(r["end"], selected_at(rec, plan.body_end)["connections"]) <= TOL["replay_history_12000"]:
            rp.append(f"{name}：{plan.body_end} の再生（T の入れ替えた状態から）と記録が一致しない")
        if r["clipped"]:
            clip_bad.append(f"{name}：重みが [w_min, w_max] の外に出た（{r['clipped'][:3]}…）")
        for t in (plan.experience_end, plan.body_end):
            out["pair_sum"] += pair_sum_problems(selected_at(rec, t), f"{name}：Pulse {t}")
        for c in rec["probes"]:                       # すべての試しの A の複製：本体の再生の t0 − 1 から
            t0, end = c["t0"], c["t0"] + 1 + plan.window
            rc = replay_all(r["at"][t0 - 1], c["spikes"], t0 - 1, end)
            if rc["clipped"]:
                clip_bad.append(f"{name} の t0 {t0}：A の複製の重みが [w_min, w_max] の外に出た")
            if t0 in edges and not max_diff(rc["end"], c["states"]["end"]["connections"]) <= TOL["replay_history_12000"]:
                clip_bad.append(f"{name} の t0 {t0}：A の複製の再生が窓の終わりの記録と一致しない")
        recorded = list(rec["states"].values()) + [rec["state_T"]] + [s for c in rec["probes"]
                                                                       for s in c.get("states", {}).values()]
        if any(not W_MIN <= v[0] <= W_MAX for s in recorded for v in s["connections"].values()):
            clip_bad.append(f"{name}：記録した重みに [w_min, w_max] の外の値がある")
    for name, rec in run["controls"].items():
        r = replay_all(rec["state_T"]["connections"], rec["spikes"], T, plan.body_end, (plan.experience_end,))
        if not max_diff(r["at"][plan.experience_end], rec["state_experience_end"]["connections"]) <= TOL["replay_history_12000"]:
            rp.append(f"{name}：{plan.experience_end} の再生（T の入れ替えた状態から）と記録が一致しない")
        if not max_diff(r["end"], rec["state_end"]["connections"]) <= TOL["replay_history_12000"]:
            rp.append(f"{name}：{plan.body_end} の再生（T の入れ替えた状態から）と記録が一致しない")
        if r["clipped"]:
            clip_bad.append(f"{name}：重みが [w_min, w_max] の外に出た")
        for key in ("state_experience_end", "state_end"):
            out["pair_sum"] += pair_sum_problems(rec[key], f"{name}：{key}")


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


def _rows(name: str, rec: Mapping, units: Mapping, plan, problems: list[str]) -> list[tuple]:
    body_fired = _by_pulse(rec["spikes"])
    rows = []
    for c in rec["probes"]:
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
    """試しの材料：{"natural": {本体: 行}, "weights": {ドナー: 行}, "units": {ドナー: 行}}。行は試しごとの
    (nA_B, n0_B, nA_C, n0_C, NA_B, N0_B, NA_C, N0_C)。n は窓 [t0 + 2, t0 + 1 + T_w] の中の最初の発火（なければ t0 + 2 + T_w）、
    N は窓の中の発火の数。2 通りの計算が一致し、打ち切りの不変条件が成り立つことを確かめる。
    値は返すが、呼び出し側は確認がすべて成り立ったときだけ使う。"""
    units = W.role_units(PROTOCOL, seed)
    problems: list[str] = []
    table = {"natural": {b: _rows(b, rec, units, plan, problems) for b, rec in run["bodies"].items()}}
    for c in FAMILIES:
        table[c] = {d: _rows(f"Y({c}<-{d})", rec, units, plan, problems) for d, rec in run["swapped"][c].items()}
    return table, problems


# ---- 判定の量（本番・合成で、すべての確認が成り立ったときだけ。README §4〜§6）----------------------------------------------

def frac(x: Fraction) -> dict:
    return {"exact": f"{x.numerator}/{x.denominator}", "value": float(x)}


def body_quantities(rows: list[tuple], plan) -> dict:
    """1 つの本体の量（Fraction）。L ＝ mean(ℓ_B − ℓ_C)、ℓ_X ＝ n_X^∅ − n_X^A。"""
    P = len(rows)
    lB = [r[1] - r[0] for r in rows]
    lC = [r[3] - r[2] for r in rows]
    censor_counts = {"B_A": 0, "B_null": 0, "C_A": 0, "C_null": 0}
    for (t0, r) in zip(plan.probes, rows):
        c = t0 + 2 + plan.window
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
    本体のうち、B（C）が両方の側で、すべての試しで窓の中で発火しなかった本体の数。"""
    return {role: sum(q["censor_counts"][f"{role}_A"] == n_probes and q["censor_counts"][f"{role}_null"] == n_probes
                      for q in per_body.values())
            for role in ("B", "C")}


def family(fam: Mapping[str, dict]) -> dict:
    """1 つの家族（塊 c）の評価（README §5.1）：ドナー O の L が、参照のドナー W2〜W20 の L の外にあるか。"""
    if tuple(fam) != DONORS:
        raise ValueError(f"家族のドナーが {DONORS} ではない")
    x = fam["O"]["L"]
    refs = [fam[d]["L"] for d in DONORS[1:]]
    return {"outside": outside(x, refs),
            "direction": "above_max" if x > max(refs) else ("below_min" if x < min(refs) else None),
            "rank_of_donor_O_among_20": {"donors_below": sum(r < x for r in refs), "donors_equal": sum(r == x for r in refs),
                                         "donors_above": sum(r > x for r in refs)},
            "frozen": len(set(refs + [x])) == 1}


def individual(per: Mapping[str, Mapping[str, dict]], n_probes: int, swap_time: int | None) -> dict:
    """1 個体の評価（README §5.1・§6）。T がなければ、両方の家族で「外にない」（除外しない）。"""
    nat = per["natural"]
    if tuple(nat) != W.BODIES:
        raise ValueError(f"自然な本体が {W.BODIES} ではない")
    o = nat["O"]["L"]
    refs = [nat[b]["L"] for b in W.SHUFFLES]
    out = {"swap_time": swap_time, "no_swap_time": swap_time is None,
           "natural_outside": outside(o, refs),                          # 補助の記録だけ（判定を置かない）
           "silence_counts": {"natural": silence_counts(nat, n_probes)}}
    for c in FAMILIES:
        if swap_time is None:
            if per[c]:
                raise ValueError("T がないのに入れ替えた本体の量がある")
            out[c] = {"outside": False, "direction": None, "rank_of_donor_O_among_20": None, "frozen": None,
                      "not_outside_because": "no_swap_time"}
            out["silence_counts"][c] = None
        else:
            out[c] = family(per[c])
            out["silence_counts"][c] = silence_counts(per[c], n_probes)
    return out


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
    """個体をまたぐ 2 つの判定（README §5.2）と補助の数え上げ。2 つの h を比べたり足したりしない。"""
    ind = {s: v["individual"] for s, v in per_seed.items()}
    n = len(ind)
    threshold = ALIGN.HOLDS_MIN_H
    j = PROTOCOL["judgment"]
    out = {"n": n, "holds_if": f"h >= {threshold}", "alpha_each": j["alpha_each"], "alpha_family": j["alpha_family"]}
    for c in FAMILIES:
        h = sum(v[c]["outside"] for v in ind.values())
        out[f"h_{c}"] = h
        out[f"holds_{c}"] = h >= threshold
    out |= {
        "direction_counts": {c: {"above_max": sum(v[c]["direction"] == "above_max" for v in ind.values()),
                                 "below_min": sum(v[c]["direction"] == "below_min" for v in ind.values())} for c in FAMILIES},
        "frozen_individuals": {c: sum(bool(v[c]["frozen"]) for v in ind.values()) for c in FAMILIES},
        "no_swap_time_individuals": sorted(int(s) for s, v in ind.items() if v["no_swap_time"]),
        "natural_outside_count": sum(v["natural_outside"] for v in ind.values()),
        "clopper_pearson_95_of_h_over_n": {c: clopper_pearson(out[f"h_{c}"], n) for c in FAMILIES},
        "scope": j["scope"], "not_judged": j["not_judged"],
        "note": ("2 つの判定は、それぞれ、全個体での交換可能性（W1 への塊のドナーとして、O は W2〜W20 と交換可能）という帰無仮説を、"
                 "個体間の独立性という統計モデル上の前提のもとで水準 0.025 で棄却すること（家族全体で 0.05。交換可能性の破れの証明ではない）。"
                 "判定の範囲は、W1 の残りの塊と T を背景に固定した、ドナーのあいだの条件付きの効果（C-I）とその介入の参照との比較まで。"
                 "C-II（自然な差の再現・消去）・C-III（自然な差の原因）は判定しない。2 つの h を比べない・足さない・寄与の割合に分けない。"
                 "natural_outside_count・Clopper–Pearson の区間・silence_counts は補助の記録で、判定に使わない")}
    return out


def quantities_for_seed(table: Mapping[str, Mapping[str, list[tuple]]], plan, swap_time: int | None) -> dict:
    per = {k: {b: body_quantities(rows, plan) for b, rows in v.items()} for k, v in table.items()}
    out_bodies = {k: {b: {n: (frac(x) if isinstance(x, Fraction) else x) for n, x in q.items()} for b, q in v.items()}
                  for k, v in per.items()}
    return {"bodies": out_bodies, "individual": individual(per, len(plan.probes), swap_time)}


# ---- 解析の本体 --------------------------------------------------------------------------------------------

def analyze(out: Path, mode: str, plan=None, seeds: list[int] | None = None, repo: Path = REPO) -> dict:
    """読むだけ（どこにも書かない）。mode：formal・smoke・synthetic（synthetic は契約テストだけ。plan・seeds を渡す）。

    記録が未完了（未着手の seed だけがある）、または解析する道具の HEAD が測定の commit と違う・作業ツリーがきれいでないなら
    GuardError（解析しない）。HEAD・作業ツリーは、判定の量を計算する直前と、解析の終わりにも確かめ直す。
    repo は契約テストで使い捨てのリポジトリを渡すためにある（本番・smoke は既定のこのリポジトリ）。"""
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
    tables, swap_times = {}, {}
    if records["state"] == "complete" and not invalid:
        censor = "evaluated"
        for s in seeds:
            data = read_raw(G.seed_dir(out, s) / G.RAW)
            tables[str(s)], problems = probe_table(data["run"], s, plan)
            swap_times[str(s)] = data["run"]["swap_time"]
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
        swap_times.clear()
        return report | {"judgment": None, "note": (
            "invalid か記録の問題があるので、判定の量（L・外にあるか・h・補助の量）は計算も表示もしない"
            "（judgment.on_any_invalid）。invalid を「外にない」に数えない")}
    if mode == "smoke":
        tables.clear()
        swap_times.clear()
        return report | {"judgment": None, "note": "smoke（操作の確認だけ）。判定の量も T の値も計算・表示・保存していない"}
    per_seed = {s: quantities_for_seed(tables[s], plan, swap_times[s]) for s in tables}
    result = report | {"judgment": judgment(per_seed), "per_seed": per_seed,
                       "note": "事前登録した検証。主の判定は h_weights・h_units の 2 つだけ。補助は記録で、主の不成立を救わない"}
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
        for c in FAMILIES:
            print(f"h_{c} ＝ {j[f'h_{c}']}／{j['n']}　判定：{'holds' if j[f'holds_{c}'] else 'fails'}（{j['holds_if']}）")
    else:
        print(report["note"])
    print(f"saved {folder / REPORT}（解析の記録 {LOG}）")


if __name__ == "__main__":
    main()
