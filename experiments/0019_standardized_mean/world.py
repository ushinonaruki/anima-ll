"""実験 0019 の道具（事前登録 v0.2 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 経験・無入力の区間・時刻・試しの元の作り方・runtime の境界：0017 v0.3・0018 v0.2 と同じ。順序を崩す乱数の流れの名前だけ "0019-shuffle:<seed>"
- 介入（README §3.1）：受け手（ordered）の試しの元の t0 の終わりの m_o と、提供側（shuffled）の試しの元の t0 の終わりの m_s を読み、
    受け手の試しの元を 2 腕（ordered_m・shuffled_m）に複製して、どちらも A–B／A–C の 4 本だけを
    x ＝ y ＝ m、w(B→A) ＝ w(C→A) ＝ w_max − m（W ＝ 0）
    に置き直す（m は ordered_m で m_o、shuffled_m で m_s）。痕跡・Unit の状態・B–C の 2 本・対象外は受け手のまま
- 指標の材料：E(t0) ＝ |B_ordered_m − B_shuffled_m| ＋ |C_ordered_m − C_shuffled_m|（t0 ＋ read_at の発火）

複製・時間の進め方・来歴のログ・Receptor は 0012 の道具、刺激の列・再生の確認は 0015 の道具、
接続の id・発火の読み方は 0014 の道具を使う（0017・0018 の道具と同じ組み立て）。
"""

import importlib.util
from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.bootstrap import Application, build_application
from anima_ll.domain.model.identifiers import ComponentId, PulseNumber

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# protocol.yaml の式・名前の文字列。ここに書いたものを実装している（alignment.py が protocol と同じか確かめる）
RNG_SHUFFLE = "0019-shuffle:{seed}"
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
ENDPOINT = "2 * experience_end"
PROBES_FIRST = "endpoint + 1"
PROBE_COUNT = "adaptation_tau / pulse_interval_seconds"
TOTAL_PULSES = "endpoint + probes.count"
CLONE_END = "t0 + probe.read_at"
INTERVENTION_RULE = "symmetric_contrast_background_with_history_mean"
BACKGROUND_CONTRAST = "0"
BOUNDARY = "after_pulse_t0_plasticity_before_t0_plus_1_weight_freeze"
ARMS = ("ordered_m", "shuffled_m")
CONDITIONS = ("ordered", "shuffled")
TARGETS = ("AB", "AC", "BA", "CA")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W14 = _load("world_0014_for_0019", ROOT / "experiments/0014_order_to_activity/world.py")
# 0015 の道具はこの実験専用に読み込み、乱数の流れの名前だけを 0019 のものに替える
# （0015 の刺激の関数は、呼ばれたときにこのモジュールの RNG_SHUFFLE を読む）
W15 = _load("world_0015_for_0019", ROOT / "experiments/0015_history_difference_persistence/world.py")
W15.RNG_SHUFFLE = RNG_SHUFFLE

ExperimentLog = W14.ExperimentLog
clone = W14.clone
advance_to = W14.advance_to
fired_at = W14.fired_at
four_ids = W14.four_ids
w_max = W14.w_max
role_units = W15.role_units
role_receptors = W15.role_receptors
stimuli = W15.stimuli
first_divergence = W15.first_divergence
check_stimulus_counts = W15.check_stimulus_counts
replay_error = W15.replay_error
weights = W15.weights
w_contrast = W15.w_contrast
snapshot = W15.snapshot
unit_states = W15.unit_states


def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


# ---- 時間の流れ（protocol の式から） ---------------------------------------------------------

def _expect(protocol_value, expected: str, name: str) -> None:
    if protocol_value != expected:
        raise ValueError(f"{name} の式が道具と違う")


def experience_end(protocol: dict) -> PulseNumber:
    tl = protocol["timeline"]
    _expect(tl["experience_end"], EXPERIENCE_END, "experience_end")
    t = tl["trials"]
    return t["first"] - 1 + t["count"] * t["every"]


def endpoint(protocol: dict) -> PulseNumber:
    _expect(protocol["timeline"]["endpoint"], ENDPOINT, "endpoint")
    return 2 * experience_end(protocol)


def probe_count(protocol: dict) -> int:
    tl = protocol["timeline"]
    _expect(tl["probes"]["count"], PROBE_COUNT, "probes.count")
    exact = manifest_raw(protocol)["defaults"]["dynamics"]["adaptation_tau"] / tl["pulse_interval_seconds"]
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"adaptation_tau ÷ pulse_interval_seconds が整数でない（{exact}）")
    return n


def probe_times(protocol: dict) -> list[PulseNumber]:
    p = protocol["timeline"]["probes"]
    _expect(p["first"], PROBES_FIRST, "probes.first")
    first = endpoint(protocol) + 1
    return [first + k * p["every"] for k in range(probe_count(protocol))]


def total_pulses(protocol: dict) -> PulseNumber:
    _expect(protocol["timeline"]["total_pulses"], TOTAL_PULSES, "total_pulses")
    _expect(protocol["timeline"]["clone_end"], CLONE_END, "clone_end")
    return endpoint(protocol) + probe_count(protocol)


# ---- 個体の組み立て ------------------------------------------------------------------------------

def build(protocol: dict, condition: str, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-0019-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=W15.receptors_for(protocol, condition, seed),
        run_metadata={"experiment": "0019", "condition": condition,
                      "receptors": "ScheduledReceptor（experiments/0012_passive_world/world.py）"},
    )


# ---- 介入 ----------------------------------------------------------------------------------------

def target_weights(connections: Mapping[str, Mapping], units: Mapping[str, ComponentId]) -> dict[str, float]:
    """4 本の weight {AB, AC, BA, CA: w}。"""
    ids = four_ids(units)
    return {k: connections[ids[k]]["weight"] for k in TARGETS}


def contrast(w: Mapping[str, float]) -> float:
    """W ＝ x − y（x ＝ w(A→B)、y ＝ w(A→C)）。"""
    return w["AB"] - w["AC"]


def forward_mean(w: Mapping[str, float]) -> float:
    """m ＝ (x ＋ y)／2。4 本全体の平均ではない（README §1）。"""
    return (w["AB"] + w["AC"]) / 2


def background_contrast(protocol: dict) -> float:
    """対称 contrast 背景の W（README §3.2）。"""
    if protocol["intervention"]["background_contrast"] != BACKGROUND_CONTRAST:
        raise ValueError("background_contrast の式が道具と違う")
    return 0.0


def standardized_weights(W: float, m: float, w_max_: float) -> dict[str, float]:
    """4 本（README §3.1）：x ＝ m ＋ W／2、y ＝ m − W／2、逆向きは組の和から。0019 では W ＝ 0 なので x ＝ y ＝ m。"""
    x, y = m + W / 2, m - W / 2
    return {"AB": x, "AC": y, "BA": w_max_ - x, "CA": w_max_ - y}


def set_targets(app: Application, units: Mapping[str, ComponentId], w: Mapping[str, float]) -> None:
    """複製の上でだけ使う：4 本の weight だけを置き直す。痕跡・他の接続・Unit の状態はそのまま。"""
    ids = four_ids(units)
    state = app.connections.export_state()
    for k in TARGETS:
        state[ids[k]]["weight"] = w[k]
    app.connections.import_state(state)


# ---- 試し ----------------------------------------------------------------------------------------

def _probe_base(protocol: dict, app: Application, log: ExperimentLog, seed: int, t0: PulseNumber, deliver: bool):
    """本体の t0 − 1 の終わりから複製し、t0 に A を入れて t0 の処理（可塑性の更新まで）を終えた試しの元。"""
    if app.lifecycle.pulse != t0 - 1:
        raise ValueError(f"試しは Pulse {t0 - 1} まで進んだ個体から作る（今 {app.lifecycle.pulse}）")
    base, base_log = clone(app, log)
    if deliver:
        base.receptors[role_receptors(protocol, seed)["A"]].inject(t0)
    advance_to(base, t0 + protocol["probe"]["fork_after"])
    return base, base_log


def probe(protocol: dict, recipient: Application, recipient_log: ExperimentLog,
          donor: Application, donor_log: ExperimentLog, seed: int, t0: PulseNumber, deliver: bool = True) -> dict:
    """両方の本体は t0 − 1 まで進んでいること。本体には触らない（README §3.1）。

    deliver は契約テストのためだけにある（False：A の刺激を入れない。本番の run.py は常に True）。
    返す値：
      base_sensory   受け手の試しの元が t0 に受けた感覚の出来事 [[Pulse, Receptor]]
      donor_sensory  提供側の試しの元が t0 に受けた感覚の出来事
      base           受け手の試しの元の t0 の終わりの状態（介入の前）{units, connections}
      donor          提供側の試しの元の t0 の終わりの 4 本の weight {AB, AC, BA, CA}
      fork           2 腕の置き直した直後の状態 {ordered_m, shuffled_m: {units, connections}}
      activity       2 腕の発火 {ordered_m, shuffled_m: [[Pulse, Unit]]}（t0 ＋ 1〜t0 ＋ read_at）
    """
    units = role_units(protocol, seed)
    wm, W0 = w_max(protocol), background_contrast(protocol)
    base, base_log = _probe_base(protocol, recipient, recipient_log, seed, t0, deliver)
    dbase, dbase_log = _probe_base(protocol, donor, donor_log, seed, t0, deliver)
    base_state = snapshot(base)
    donor_w = target_weights(dbase.connections.export_state(), units)
    m_o = forward_mean(target_weights(base_state["connections"], units))
    arms, logs = {}, {}
    for arm, m in (("ordered_m", m_o), ("shuffled_m", forward_mean(donor_w))):
        arms[arm], logs[arm] = clone(base, base_log)
        set_targets(arms[arm], units, standardized_weights(W0, m, wm))
    fork = {arm: snapshot(arms[arm]) for arm in ARMS}
    end = t0 + protocol["probe"]["read_at"]
    for arm in ARMS:
        advance_to(arms[arm], end)
    return {"t0": t0, "base_sensory": base_log.sensory(), "donor_sensory": dbase_log.sensory(),
            "base": base_state, "donor": donor_w, "fork": fork,
            "activity": {arm: logs[arm].activity() for arm in ARMS}}


def probe_series(protocol: dict, recipient: Application, recipient_log: ExperimentLog,
                 donor: Application, donor_log: ExperimentLog, seed: int, times: Iterable[PulseNumber],
                 deliver: bool = True) -> list[dict]:
    """各 t0 で両方の本体を t0 − 1 まで進めて試しを行い、そのあと両方の本体を t0 まで進めて
    t0 の終わりの重みを記録する（README §6「指す境界」の材料）。本番と契約テストが同じ関数を使う。"""
    out = []
    for t0 in times:
        advance_to(recipient, t0 - 1)
        advance_to(donor, t0 - 1)
        rec = probe(protocol, recipient, recipient_log, donor, donor_log, seed, t0, deliver)
        advance_to(recipient, t0)
        advance_to(donor, t0)
        rec["bodies"] = {"ordered": weights(recipient.connections.export_state()),
                         "shuffled": weights(donor.connections.export_state())}
        out.append(rec)
    return out


# ---- 指標 ----------------------------------------------------------------------------------------

def readout(record: Mapping, units: Mapping[str, ComponentId], read_at: int) -> int:
    """E(t0) ＝ |B_ordered_m − B_shuffled_m| ＋ |C_ordered_m − C_shuffled_m|（t0 ＋ read_at の発火）。"""
    t = record["t0"] + read_at
    act = record["activity"]
    return sum(abs(fired_at(act["ordered_m"], units[r], t) - fired_at(act["shuffled_m"], units[r], t))
               for r in ("B", "C"))


def fork_differences(record: Mapping, units: Mapping[str, ComponentId], w_max_: float) -> dict:
    """記録だけ（README §5）：2 腕の 4 本それぞれの差（ordered_m − shuffled_m）、dm_fork（＝ m_o − m_s）、
    違った本数、recipient_contrast_displacement（W_o ＝ 旧値 − 新値＝標準化で取り除いた量。加えた差分は −W_o）、
    donor_contrast_offset（W_s。介入の量ではない）。w_max_ は 0018 の道具と同じ呼び方のために受け取る。"""
    o = target_weights(record["fork"]["ordered_m"]["connections"], units)
    s = target_weights(record["fork"]["shuffled_m"]["connections"], units)
    d = {k: o[k] - s[k] for k in TARGETS}
    base = target_weights(record["base"]["connections"], units)
    return {"per_weight": d, "dm": forward_mean(base) - forward_mean(record["donor"]),
            "changed": sum(1 for k in TARGETS if o[k] != s[k]),
            "recipient_contrast_displacement": contrast(base) - 0.0,
            "donor_contrast_offset": contrast(record["donor"])}


# ---- 操作の確認（run.py の実行時と analyze.py の再検証が同じ関数を使う） ----------------------

def check_probe(protocol: dict, seed: int, record: Mapping, w_max_: float, tol: float = 1e-12) -> list[str]:
    """1 回の試しの操作の確認：試しの入力（両方）・標準化の腕・指す境界・2 腕の t0 ＋ 1 の一致（README §6）。"""
    problems = []
    t0 = record["t0"]
    units = role_units(protocol, seed)
    a_rec = role_receptors(protocol, seed)["A"]
    W0 = background_contrast(protocol)
    for key, who in (("base_sensory", "受け手"), ("donor_sensory", "提供側")):
        if [list(x) for x in record[key]] != [[t0, a_rec]]:
            problems.append(f"t0 {t0}: {who}の試しの元の感覚の出来事が A の 1 つだけではない")
    base = record["base"]
    ids = four_ids(units)
    target_ids = {ids[k] for k in TARGETS}
    w_base = target_weights(base["connections"], units)
    expected_m = {"ordered_m": forward_mean(w_base), "shuffled_m": forward_mean(record["donor"])}
    for arm in ARMS:
        f = record["fork"][arm]
        if f["units"] != base["units"]:
            problems.append(f"t0 {t0}: {arm} の Unit の状態が受け手の試しの元と違う")
        if set(f["connections"]) != set(base["connections"]):
            problems.append(f"t0 {t0}: {arm} の接続の集合が違う")
        for cid, v in base["connections"].items():
            e = f["connections"][cid]
            if e["pre_trace"] != v["pre_trace"] or e["post_trace"] != v["post_trace"]:
                problems.append(f"t0 {t0}: {arm} の {cid} の痕跡が変わった")
            if cid not in target_ids and e["weight"] != v["weight"]:
                problems.append(f"t0 {t0}: {arm} の対象外の {cid} の重みが変わった")
        w = target_weights(f["connections"], units)
        exp = standardized_weights(W0, expected_m[arm], w_max_)
        if any(abs(w[k] - exp[k]) > tol for k in TARGETS):
            problems.append(f"t0 {t0}: {arm} の 4 本が式どおりでない")
        if abs(forward_mean(w) - expected_m[arm]) > tol:
            problems.append(f"t0 {t0}: {arm} の m がその履歴の m と違う")
        if abs(contrast(w) - W0) > tol:
            problems.append(f"t0 {t0}: {arm} の W が 0 でない")
        for x, y in (("AB", "BA"), ("AC", "CA")):
            if abs(w[x] + w[y] - w_max_) > tol:
                problems.append(f"t0 {t0}: {arm} の組 {x} の和が w_max でない")
    # 指す境界（0017 §3.3）：受け手の試しの元の重み ＝ ordered の本体の t0 の終わり、
    # 提供側の 4 本 ＝ shuffled の本体の t0 の終わり
    if weights(base["connections"]) != record["bodies"]["ordered"]:
        problems.append(f"t0 {t0}: 受け手の試しの元の重みが ordered の本体の t0 の終わりと違う")
    body_s = record["bodies"]["shuffled"]
    if any(record["donor"][k] != body_s[ids[k]] for k in TARGETS):
        problems.append(f"t0 {t0}: 提供側の 4 本が shuffled の本体の t0 の終わりと違う")
    t1 = t0 + 1
    if ([x for x in record["activity"]["ordered_m"] if x[0] == t1]
            != [x for x in record["activity"]["shuffled_m"] if x[0] == t1]):
        problems.append(f"t0 {t0}: 2 腕の t0 ＋ 1 の発火が違う")
    return problems
