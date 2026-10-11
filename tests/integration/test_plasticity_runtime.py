"""接続の状態・可塑性 v1 と Runtime の契約テスト（接続の状態 仕様 §7、可塑性 v1 の設計案 §6）。"""

import asyncio
import copy

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
from anima_ll.bootstrap import build_application
from anima_ll.domain.model.activity import ActivityEvent
from anima_ll.domain.model.runtime_event import RuntimeEventType as T
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_test_support import BASE, silent

BRAIN = {
    "version": 0, "delta_ttl_pulses": 10,
    "interfaces": {"resources": [], "receptors": [], "effectors": []},
    "defaults": {"dynamics": {"kind": "simple_activity", "decay": 0.85, "threshold": 0.5,
                              "refractory_pulses": 0, "intrinsic_drive": 0.08, "jitter": 0.1,
                              "initial_activity_max_ratio": 0.5}},
    "units": [{"id": "s1", "output": "relay"}, {"id": "s2", "output": "relay"}],
    "projections": [
        {"from": "s1.main", "to": "s2", "weight": 0.25, "plastic": True},
        {"from": "s2.main", "to": "s1", "weight": 0.25, "plastic": True},
    ],
    "plasticity": {"rule": "balanced_pair_window", "trace": "additive", "bounds": "soft",
                   "trace_tau": "activity_time_constant", "w_min": 0.0, "w_max": "threshold",
                   "amplitude_ratio": 0.01},
}
ENV = {"resources": {}, "receptors": {}, "effectors": {}}


class ScriptedFiringUnit:
    """決めた Pulse にだけ発火する Unit（テスト用）。力学は持たない。"""

    def __init__(self, unit_id: str, pulses: set[int]) -> None:
        self.unit_id = unit_id
        self._pulses = pulses

    def tick(self, view, context) -> UnitStepResult:
        if context.pulse in self._pulses:
            return UnitStepResult(activity=ActivityEvent(self.unit_id, context.pulse))
        return UnitStepResult.empty()

    def handle_kernel_result(self, task, result, context) -> UnitStepResult:
        return UnitStepResult.empty()

    def export_state(self):
        return {}

    def import_state(self, state) -> None:
        pass


def build(brain: dict, env: dict, log: InMemoryEventLog, seed: int = 1, units=None):
    return build_application(
        parse_neuroarchitecture(brain), parse_environment(env),
        parse_birth_state({"individual_id": "anima", "seed": seed}),
        clock=FixedStepClock(1.0), event_log=log, unit_overrides=units, state_sample_interval=1,
    )


def views(log: InMemoryEventLog) -> dict[tuple[int, str], dict]:
    return {(e.pulse, e.data["unit_id"]): e.data for e in log.events if e.type == T.VIEW}


def connection_states(log: InMemoryEventLog) -> dict[int, dict]:
    return {e.pulse: e.data["connections"] for e in log.events if e.type == T.CONNECTION_STATE}


# ---- 本来の T7：学習は、その原因になった伝達に遡らない --------------------------------------

def test_t7_transmission_keeps_the_weight_frozen_at_its_pulse() -> None:
    log = InMemoryEventLog()
    # s1 が 5・6・7 に、s2 が 6 に発火する。6 の境界で s1 → s2 が強まる（s1 は 5 に先に発火していた）
    units = {"s1": ScriptedFiringUnit("s1", {5, 6, 7}), "s2": ScriptedFiringUnit("s2", {6})}
    app = build(copy.deepcopy(BRAIN), ENV, log, units=units)
    asyncio.run(app.lifecycle.run(max_pulses=9))
    v, c = views(log), connection_states(log)
    key = "s1.main->s2"
    w6_after = c[6][key]["weight"]                # 6 の境界で更新された重み（W_7）
    assert c[5][key]["weight"] == 0.25 and w6_after > 0.25
    # s1 の 6 の発火で成立した伝達（7 に届く）は、6 の冒頭の重み（0.25）のまま
    assert v[(7, "s2")]["drives"] == [["s1", 0.25]]
    # 更新された重みは、7 以降に成立した伝達から使われる（s1 の 7 の発火 → 8 に届く）
    assert v[(8, "s2")]["drives"] == [["s1", w6_after]]


# ---- 可塑性の対象がなければ、今までと同じ ------------------------------------------------

def run_activity(brain: dict, env: dict, pulses: int, seed: int) -> list:
    log = InMemoryEventLog()
    asyncio.run(build(brain, env, log, seed).lifecycle.run(max_pulses=pulses))
    return [(e.pulse, e.data["unit_id"]) for e in log.events if e.type == T.ACTIVITY]


def test_plasticity_block_without_plastic_connections_changes_nothing() -> None:
    cfg = silent(BASE)
    with_block = copy.deepcopy(cfg["neuro"])
    with_block["plasticity"] = copy.deepcopy(BRAIN["plasticity"])
    for seed in (1, 9):
        assert run_activity(cfg["neuro"], cfg["env"], 400, seed) == run_activity(with_block, cfg["env"], 400, seed)


def test_plastic_connections_change_weights_and_are_saved_in_the_snapshot() -> None:
    log = InMemoryEventLog()
    app = build(copy.deepcopy(BRAIN), ENV, log)
    asyncio.run(app.lifecycle.run(max_pulses=600))
    snapshot = app.lifecycle.save_snapshot()
    assert set(snapshot.connections) == {"s1.main->s2", "s2.main->s1"}
    assert any(v["weight"] != 0.25 for v in snapshot.connections.values())
    assert snapshot.connections == app.connections.export_state()
