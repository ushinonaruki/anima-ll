"""実験 0015 の道具（事前登録 v0.2 に従う。脳の側ではなく、実験者の側）。値はすべて protocol.yaml から受け取る。

- 経験の区間は 0014 v0.3 と同じ設計（設計図・刺激・時刻）。順序を崩す乱数の流れの名前だけ "0015-shuffle:<seed>"
- 経験の終わり（experience_end）の後、総 Pulse まで外からの入力なしで本体を進める（Receptor の予定が空になるだけ）
- 試し（複製での読み出し）はない
- 指標の材料：W(t) ＝ w(A→B) − w(A→C)、D(t) ＝ W_ordered(t) − W_shuffled(t)

複製・時間の進め方・来歴のログ・Receptor は、0012 の道具（experiments/0012_passive_world/world.py）をそのまま使う。
"""

import importlib.util
import itertools
import random
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
ROLES = ("A", "B", "C")

# protocol.yaml の式の文字列。ここに書いた式を実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
RNG_SHUFFLE = "0015-shuffle:{seed}"
EXPERIENCE_END = "trials.first - 1 + trials.count * trials.every"
TOTAL_PULSES = "2 * experience_end"
SAMPLE_EVERY = "trials.every"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W12 = _load("world_0012_for_0015", ROOT / "experiments/0012_passive_world/world.py")
REPLAY = _load("replay_0012_post_for_0015", ROOT / "experiments/0012_passive_world/post/replay.py")
ExperimentLog = W12.ExperimentLog
ScheduledReceptor = W12.ScheduledReceptor
clone = W12.clone
advance_to = W12.advance_to
connection_id = W12.connection_id


# ---- 設計図と時間の流れ ----------------------------------------------------------------

def manifest_raw(protocol: dict) -> dict:
    return yaml.safe_load((ROOT / protocol["brain"]["manifest"]).read_text(encoding="utf-8"))


def plasticity(protocol: dict):
    return parse_neuroarchitecture(manifest_raw(protocol)).plasticity


def experience_end(protocol: dict) -> PulseNumber:
    tl = protocol["timeline"]
    if tl["experience_end"] != EXPERIENCE_END:
        raise ValueError("experience_end の式が道具と違う")
    t = tl["trials"]
    return t["first"] - 1 + t["count"] * t["every"]


def total_pulses(protocol: dict) -> PulseNumber:
    if protocol["timeline"]["total_pulses"] != TOTAL_PULSES:
        raise ValueError("total_pulses の式が道具と違う")
    return 2 * experience_end(protocol)


def sample_every(protocol: dict) -> int:
    if protocol["timeline"]["sample_every"] != SAMPLE_EVERY:
        raise ValueError("sample_every の式が道具と違う")
    return protocol["timeline"]["trials"]["every"]


def sample_times(protocol: dict) -> list[PulseNumber]:
    """記録の標本の時刻（0 から総 Pulse まで sample_every ごと）。経験の終わり・総 Pulse を含む。"""
    every, total = sample_every(protocol), total_pulses(protocol)
    times = list(range(0, total + 1, every))
    for t in (experience_end(protocol), total):
        if t not in times:
            raise ValueError(f"標本の時刻に {t} が含まれない")
    return times


def trial_starts(protocol: dict) -> list[PulseNumber]:
    t = protocol["timeline"]["trials"]
    return [t["first"] + k * t["every"] for k in range(t["count"])]


# ---- 役の割り当てと刺激（0014 と同じ設計） ---------------------------------------------------

def role_receptors(protocol: dict, seed: int) -> dict[str, ComponentId]:
    order = protocol["stimulus"]["role_orders"][(seed - 1) % 6]
    return dict(zip(ROLES, order))


def role_units(protocol: dict, seed: int) -> dict[str, ComponentId]:
    to_unit = protocol["brain"]["receptors"]
    return {role: to_unit[r] for role, r in role_receptors(protocol, seed).items()}


def ordered_stimuli(protocol: dict) -> list[tuple[PulseNumber, str]]:
    s = protocol["stimulus"]
    out = []
    for start in trial_starts(protocol):
        out += [(start, "A"), (start + s["b_offset"], "B"), (start + s["c_offset"], "C")]
    return sorted(out)


def shuffled_stimuli(protocol: dict, seed: int) -> list[tuple[PulseNumber, str]]:
    ordered = ordered_stimuli(protocol)
    labels = [label for _, label in ordered]
    random.Random(RNG_SHUFFLE.format(seed=seed)).shuffle(labels)
    return [(t, label) for (t, _), label in zip(ordered, labels)]


def stimuli(protocol: dict, condition: str, seed: int) -> list[tuple[PulseNumber, str]]:
    if condition == "ordered":
        return ordered_stimuli(protocol)
    if condition == "shuffled":
        return shuffled_stimuli(protocol, seed)
    raise ValueError(f"未知の条件: {condition}")


def first_divergence(protocol: dict, seed: int) -> PulseNumber | None:
    for (t, a), (_, b) in zip(stimuli(protocol, "ordered", seed), stimuli(protocol, "shuffled", seed)):
        if a != b:
            return t
    return None


def receptors_for(protocol: dict, condition: str, seed: int) -> dict[ComponentId, ScheduledReceptor]:
    roles = role_receptors(protocol, seed)
    schedule: dict[ComponentId, list[PulseNumber]] = {r: [] for r in protocol["brain"]["receptors"]}
    for t, label in stimuli(protocol, condition, seed):
        schedule[roles[label]].append(t)
    return {r: ScheduledReceptor(r, pulses) for r, pulses in schedule.items()}


# ---- 個体の組み立て ----------------------------------------------------------------------

def build(protocol: dict, condition: str, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment({
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    })
    return build_application(
        parse_neuroarchitecture(manifest_raw(protocol)),
        env,
        parse_birth_state({"individual_id": f"anima-0015-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=receptors_for(protocol, condition, seed),
        run_metadata={"experiment": "0015", "condition": condition,
                      "receptors": "ScheduledReceptor（experiments/0012_passive_world/world.py）"},
    )


def unit_states(app: Application) -> dict:
    return {u.unit_id: u.export_state() for u in app.units.all()}


def snapshot(app: Application) -> dict:
    return {"units": unit_states(app), "connections": app.connections.export_state()}


# ---- 指標 --------------------------------------------------------------------------------

def weights(connections: Mapping[str, Mapping]) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in connections.items()}


def w_contrast(w: Mapping[str, float], units: Mapping[str, ComponentId]) -> float:
    """W ＝ w(A→B) − w(A→C)。"""
    return w[connection_id(units["A"], units["B"])] - w[connection_id(units["A"], units["C"])]


def a_pair(w: Mapping[str, float], i: ComponentId, j: ComponentId) -> float:
    """a_ij ＝ w(i→j) − w(j→i)。"""
    return w[connection_id(i, j)] - w[connection_id(j, i)]


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


# ---- 操作の確認（run.py の実行時と analyze.py の再検証が同じ関数を使う） ----------------------

def check_stimulus_counts(protocol: dict, seed: int, sensory: Mapping[str, list]) -> list[str]:
    """刺激の列と、本体が受けた感覚の出来事の両方で、A・B・C が各 counts、時刻の集合が 2 条件で同じ、順序ありの形。"""
    problems = []
    s = protocol["stimulus"]
    to_role = {r: role for role, r in role_receptors(protocol, seed).items()}
    times = {}
    for cond in s["conditions"]:
        planned = stimuli(protocol, cond, seed)
        got = sorted((p, to_role[r]) for p, r in sensory[cond])
        if got != sorted(planned):
            problems.append(f"{cond}: 本体が受けた感覚の出来事が刺激の列と違う")
        for role in ROLES:
            if sum(1 for _, x in got if x == role) != s["counts"][role]:
                problems.append(f"{cond}: {role} の数が {s['counts'][role]} ではない")
        times[cond] = sorted(p for p, _ in got)
        if len(set(times[cond])) != len(times[cond]):
            problems.append(f"{cond}: 同じ Pulse に 2 つの刺激がある")
    if len(set(map(tuple, times.values()))) != 1:
        problems.append("刺激の時刻の集合が 2 条件で違う")
    at = {p: to_role[r] for p, r in sensory["ordered"]}
    for p, x in at.items():
        if x == "A" and (at.get(p + s["b_offset"]) != "B" or at.get(p + s["c_offset"]) != "C"):
            problems.append(f"ordered: A({p}) の後の B・C の形が違う")
            break
    return problems


def initial_weights(protocol: dict) -> dict[str, float]:
    """設計図の、可塑性の対象の接続の初期の重み {connection_id: w}。"""
    m = parse_neuroarchitecture(manifest_raw(protocol))
    return {connection_id(p.source_id, p.target_id): p.weight for p in m.projections if p.plastic}


def replay_error(protocol: dict, activity: Iterable[list], recorded: Mapping[str, float], end: PulseNumber) -> float:
    """発火の記録から可塑性の規則を再生した 6 本の重み（Pulse end の終わり）と、記録の重みの差の最大。"""
    spec = plasticity(protocol)
    w0 = initial_weights(protocol)
    units = protocol["brain"]["sensory_units"]
    spikes = {u: [p for p, v in activity if v == u and p <= end] for u in units}
    err = 0.0
    for a, b in itertools.permutations(units, 2):
        cid = connection_id(a, b)
        w, _ = REPLAY.replay(spikes[a], spikes[b], w0=w0[cid], w_max=spec.w_max, amplitude=spec.amplitude,
                             tau=spec.trace_tau_seconds, dt=protocol["timeline"]["pulse_interval_seconds"], end=end)
        err = max(err, abs(w - recorded[cid]))
    return err
