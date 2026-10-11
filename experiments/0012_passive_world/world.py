"""実験 0012 の人工世界と試しの道具（事前登録の一部。測定の前にコミットする）。

ここにあるのは実験の道具（Environment と実験者の側）で、脳の側ではない。値はすべて protocol.yaml から受け取る。

- 役の割り当て：A・B・C → receptor.x1〜x3。protocol の role_orders の (seed − 1) mod 6 番目（乱数ではない）
- 刺激の列：
  - ordered：試行 k の A を trials.first ＋ k × trials.every に、その delta_pulses 後に B か C。
    B・C の数は p_b × count で固定（160・40）。どの試行が B かは、B 160 個・C 40 個の札の列を
    random.Random(seed × 1000 ＋ 12) の shuffle で並べ替えて決める
  - shuffled：ordered で作った 400 個の刺激の時刻はそのままで、札（A 200・B 160・C 40）を
    random.Random(seed × 1000 ＋ 13) の shuffle で時刻のあいだで並べ替える
  - silent：刺激なし
  どちらの乱数も Birth State の乱数（random.Random(seed)。bootstrap が Unit の初期値に使う）とは別の流れ
- 感覚の出来事は中身なし（material なし）。Receptor は、決めた Pulse の番号のときに出来事を成立させる
- 試し：個体を丸ごと複製し（Unit の状態・接続の状態・BrainState・Receptor の予定・Pulse・時計）、
  複製のほうの A の Receptor にだけ t0 の出来事を足して、t0 から clone_pulses 進めて記録し、捨てる。
  複製でも可塑性は止めない（「試しの間は学ばない」という切り替えを脳の側に作らない）
"""

import asyncio
import copy
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
from anima_ll.domain.model.runtime_event import RuntimeEvent, RuntimeEventType
from anima_ll.domain.model.sensory_event import SensoryEvent

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "neuroarchitecture.yaml"
ROLES = ("A", "B", "C")

# protocol.yaml の式の文字列。ここに書いた式を実装している（alignment.py が protocol と同じか確かめる）
ROLE_ASSIGNMENT = "(seed - 1) mod 6"
RNG_ORDERED = "seed * 1000 + 12"
RNG_SHUFFLE = "seed * 1000 + 13"


# ---- 役の割り当てと刺激 ------------------------------------------------------------

def role_receptors(protocol: dict, seed: int) -> dict[str, ComponentId]:
    """{A, B, C} → Receptor。(seed − 1) mod 6 番目の並べ方。"""
    order = protocol["stimulus"]["role_orders"][(seed - 1) % 6]
    return dict(zip(ROLES, order))


def role_units(protocol: dict, seed: int) -> dict[str, ComponentId]:
    """{A, B, C} → その Receptor が 1 対 1 でつながる s（protocol の brain.receptors）。"""
    to_unit = protocol["brain"]["receptors"]
    return {role: to_unit[r] for role, r in role_receptors(protocol, seed).items()}


def trial_starts(protocol: dict) -> list[PulseNumber]:
    t = protocol["timeline"]["trials"]
    return [t["first"] + k * t["every"] for k in range(t["count"])]


def probe_times(protocol: dict, phase: str) -> list[PulseNumber]:
    p = protocol["timeline"][f"{phase}_probes"]
    return [p["first"] + k * p["every"] for k in range(p["count"])]


def _b_count(protocol: dict) -> int:
    count = protocol["timeline"]["trials"]["count"]
    exact = protocol["stimulus"]["p_b"] * count
    n = round(exact)
    if abs(exact - n) > 1e-9:
        raise ValueError(f"p_b × 試行数 が整数でない（{exact}）。B の数を固定できない")
    return n


def ordered_stimuli(protocol: dict, seed: int) -> list[tuple[PulseNumber, str]]:
    """順序あり：[(Pulse, 札)]（時刻の順）。"""
    starts = trial_starts(protocol)
    n_b = _b_count(protocol)
    labels = ["B"] * n_b + ["C"] * (len(starts) - n_b)
    random.Random(seed * 1000 + 12).shuffle(labels)
    delta = protocol["stimulus"]["delta_pulses"]
    stimuli = []
    for start, follower in zip(starts, labels):
        stimuli += [(start, "A"), (start + delta, follower)]
    return sorted(stimuli)


def shuffled_stimuli(protocol: dict, seed: int) -> list[tuple[PulseNumber, str]]:
    """順序を崩した刺激：順序ありの 400 個の時刻はそのまま、札だけを時刻のあいだで並べ替える。"""
    ordered = ordered_stimuli(protocol, seed)
    labels = [label for _, label in ordered]
    random.Random(seed * 1000 + 13).shuffle(labels)
    return [(t, label) for (t, _), label in zip(ordered, labels)]


def stimuli(protocol: dict, condition: str, seed: int) -> list[tuple[PulseNumber, str]]:
    if condition == "ordered":
        return ordered_stimuli(protocol, seed)
    if condition == "shuffled":
        return shuffled_stimuli(protocol, seed)
    if condition == "silent":
        return []
    raise ValueError(f"未知の条件: {condition}")


def stimulus_counts(stim: Iterable[tuple[PulseNumber, str]], delta: int) -> dict[str, int]:
    """札ごとの数と、A の delta 後に B・C が来た組の数（操作の確認用）。"""
    stim = list(stim)
    at = {t: label for t, label in stim}
    if len(at) != len(stim):
        raise ValueError("同じ Pulse に 2 つの刺激がある")
    counts = {r: sum(label == r for _, label in stim) for r in ROLES}
    counts["a_then_b"] = sum(label == "A" and at.get(t + delta) == "B" for t, label in stim)
    counts["a_then_c"] = sum(label == "A" and at.get(t + delta) == "C" for t, label in stim)
    return counts


# ---- Receptor（実行環境の側） -------------------------------------------------------

class ScheduledReceptor:
    """決めた Pulse の番号のときに、中身なしの感覚の出来事を成立させる Receptor（実験の道具）。

    予定は Pulse の番号で持つ（呼ばれた回数ではない）。試しでは、複製のほうにだけ inject で予定を足す。
    """

    def __init__(self, receptor_id: ComponentId, pulses: Iterable[PulseNumber]) -> None:
        self._receptor_id = receptor_id
        self._pulses = set(pulses)
        self._last_drained: PulseNumber = 0

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self, pulse: PulseNumber) -> tuple[SensoryEvent, ...]:
        self._last_drained = pulse
        return (SensoryEvent(self._receptor_id, pulse, None),) if pulse in self._pulses else ()

    def inject(self, pulse: PulseNumber) -> None:
        """これから来る Pulse に出来事を足す（過去・今の Pulse には足せない）。"""
        if pulse <= self._last_drained:
            raise ValueError(f"{self._receptor_id}: Pulse {pulse} はもう過ぎている（{self._last_drained} まで drain 済み）")
        self._pulses.add(pulse)


def receptors_for(protocol: dict, condition: str, seed: int) -> dict[ComponentId, ScheduledReceptor]:
    roles = role_receptors(protocol, seed)
    schedule: dict[ComponentId, list[PulseNumber]] = {r: [] for r in protocol["brain"]["receptors"]}
    for t, label in stimuli(protocol, condition, seed):
        schedule[roles[label]].append(t)
    return {r: ScheduledReceptor(r, pulses) for r, pulses in schedule.items()}


# ---- 個体の組み立て -----------------------------------------------------------------

class ExperimentLog:
    """来歴ログのうち、この実験が使う出来事（run・感覚・発火）だけを持つ（メモリを抑えるため）。"""

    KEEP = frozenset({RuntimeEventType.RUN, RuntimeEventType.SENSORY, RuntimeEventType.ACTIVITY})

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def append(self, event: RuntimeEvent) -> None:
        if event.type in self.KEEP:
            self.events.append(event)

    def activity(self) -> list[list]:
        return [[e.pulse, e.data["unit_id"]] for e in self.events if e.type == RuntimeEventType.ACTIVITY]

    def sensory(self) -> list[list]:
        return [[e.pulse, e.data["receptor_id"]] for e in self.events if e.type == RuntimeEventType.SENSORY]


def manifest_raw() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def environment_raw(protocol: dict) -> dict:
    """実行環境の設定。Receptor の口だけを宣言し、中身は ScheduledReceptor で差し替える。"""
    return {
        "receptors": {r: {"kind": "scripted", "script": {}} for r in protocol["brain"]["receptors"]},
        "runtime": {"pulse_interval_seconds": protocol["timeline"]["pulse_interval_seconds"]},
    }


def build(protocol: dict, condition: str, seed: int, log: ExperimentLog) -> Application:
    env = parse_environment(environment_raw(protocol))
    return build_application(
        parse_neuroarchitecture(manifest_raw()),
        env,
        parse_birth_state({"individual_id": f"anima-0012-{seed}", "seed": seed}),
        clock=FixedStepClock(env.pulse_interval_seconds),
        event_log=log,
        receptor_overrides=receptors_for(protocol, condition, seed),
        run_metadata={"experiment": "0012", "condition": condition,
                      "receptors": "ScheduledReceptor（experiments/0012_passive_world/world.py）"},
    )


def advance_to(app: Application, pulse: PulseNumber) -> None:
    """個体を、Pulse `pulse` の処理が終わったところまで進める（すでにそこなら何もしない）。"""
    if app.lifecycle.pulse > pulse:
        raise ValueError(f"Pulse {app.lifecycle.pulse} からは {pulse} へ戻れない")
    if app.lifecycle.pulse < pulse:
        asyncio.run(app.lifecycle.run(max_pulses=pulse))


# ---- 複製と試し ---------------------------------------------------------------------

def clone(app: Application, app_log: ExperimentLog) -> tuple[Application, ExperimentLog]:
    """個体を丸ごと複製する。複製は本体と何も共有しない。

    来歴ログだけは複製せず、新しい空のログに差し替える（本体のログを汚さない・大きなログを写さない）。
    """
    clone_log = ExperimentLog()
    copied = copy.deepcopy(app, {id(app_log): clone_log})
    return copied, clone_log


def weights_of(app: Application) -> dict[str, float]:
    """可塑性の対象の接続の今の重み {connection_id: w}。"""
    return {cid: v["weight"] for cid, v in app.connections.export_state().items()}


def probe(protocol: dict, app: Application, app_log: ExperimentLog, a_receptor: ComponentId,
          t0: PulseNumber) -> list[list]:
    """本体は t0 − 1 まで進んでいること。複製にだけ t0 の A を与え、clone_pulses 進めた発火を返す。

    返す値：[[t0 からの相対 Pulse, Unit], ...]。複製は捨てる。
    """
    if app.lifecycle.pulse != t0 - 1:
        raise ValueError(f"試しは Pulse {t0 - 1} まで進んだ個体から作る（今 {app.lifecycle.pulse}）")
    copied, log = clone(app, app_log)
    copied.receptors[a_receptor].inject(t0)
    advance_to(copied, t0 - 1 + protocol["probe"]["clone_pulses"])
    return [[p - t0, u] for p, u in log.activity()]


def fired_in(fires: Iterable[list], unit: ComponentId, window: Iterable[int]) -> bool:
    lo, hi = window
    return any(u == unit and lo <= offset <= hi for offset, u in fires)


def connection_id(source: ComponentId, target: ComponentId) -> str:
    return f"{source}.main->{target}"


def w_difference(weights: Mapping[str, float], units: Mapping[str, ComponentId]) -> float:
    """W ＝ w(s_A → s_B) − w(s_A → s_C)。"""
    return (weights[connection_id(units["A"], units["B"])]
            - weights[connection_id(units["A"], units["C"])])
