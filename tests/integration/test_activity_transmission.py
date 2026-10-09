"""活動の伝達・感覚の駆動・中身の運搬の契約テスト（仕様 §9 の T1〜T8）。

仕様：docs/activity-transmission-spec.md v0.2
"""

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
from anima_ll.domain.model.activity import Drive
from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.runtime_event import RuntimeEventType as T
from anima_ll.runtime.projection_router import ProjectionRouter
from anima_ll.unit.dynamics.activity_dynamics import ActivityState
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics
from anima_ll.unit.generic_cognitive_unit import GenericCognitiveUnit
from anima_ll.unit.output.kernel_request_output import KernelRequestOutput
from anima_ll.unit.output.relay_output import RelayOutput
from anima_test_support import BASE, silent

PULSES = 300


def run(cfg: dict, pulses: int = PULSES) -> InMemoryEventLog:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(cfg["neuro"]),
        parse_environment(cfg["env"]),
        parse_birth_state(cfg["birth"]),
        clock=FixedStepClock(1.0),
        event_log=log,
    )
    asyncio.run(app.lifecycle.run(max_pulses=pulses))
    return log


def activities(log: InMemoryEventLog) -> list[tuple[int, str]]:
    return [(e.pulse, e.data["unit_id"]) for e in log.events if e.type == T.ACTIVITY]


def views(log: InMemoryEventLog) -> dict[tuple[int, str], dict]:
    return {(e.pulse, e.data["unit_id"]): e.data for e in log.events if e.type == T.VIEW}


def with_kernel(cfg: dict, **params) -> dict:
    cfg = copy.deepcopy(cfg)
    cfg["env"]["resources"]["llm_pool"].update(params)
    return cfg


def make_unit(output=None) -> GenericCognitiveUnit:
    dynamics = SimpleActivityDynamics(
        decay_per_second=0.85, threshold=0.5, refractory_pulses=0,
        intrinsic_drive_per_second=0.08, adaptation_increment=0.0, adaptation_tau_seconds=0.0,
    )
    return GenericCognitiveUnit("u1", dynamics, output or RelayOutput(), ActivityState(activity=0.1))


def delta(i: int, pulse: int) -> StateDelta:
    return StateDelta(
        delta_id=f"d{i}", source_id="u0", output_port="main", target_id="u1", created_pulse=pulse,
        kind="content", payload="x", parent_delta_ids=(), origin_snapshot_id=None,
        origin_task_id=None, expires_after_pulse=pulse + 10,
    )


# ---- T1：Delta は駆動しない ---------------------------------------------------------

def test_t1_deltas_do_not_drive() -> None:
    context = PulseContext(pulse=11, now=11.0, delta_time=1.0)
    empty = ReceptiveView("u1", "s", 11, deltas=())
    crowded = ReceptiveView("u1", "s", 11, deltas=tuple(delta(i, 10) for i in range(20)))
    a, b = make_unit(), make_unit()
    a.tick(empty, context)
    b.tick(crowded, context)
    assert a.state == b.state


def test_t1_drives_do() -> None:
    context = PulseContext(pulse=11, now=11.0, delta_time=1.0)
    unit = make_unit()
    step = unit.tick(ReceptiveView("u1", "s", 11, deltas=(), drives=(Drive("u0", "u1", 1.0, 10),)),
                     context)
    assert step.activity is not None and step.activity.unit_id == "u1" and step.activity.pulse == 11


# ---- T2：1 回の発火で、接続ごとにちょうど 1 つの駆動（relay が何も出さなくても） -------------

def test_t2_each_firing_reaches_every_connection_once() -> None:
    cfg = silent(BASE)
    cfg["birth"]["seed"] = 1   # 出生時のばらつきで u0 が自力で発火できる個体（seed 42 の u0 は発火しない）
    log = run(cfg)
    v = views(log)
    u0_fires = [p for p, u in activities(log) if u == "u0" and p < PULSES]
    assert u0_fires, "u0 が自発的に発火していない（入力なし）"
    for p in u0_fires:
        for target in ("u1", "u2"):
            from_u0 = [d for d in v[(p + 1, target)]["drives"] if d[0] == "u0"]
            assert from_u0 == [["u0", 1.0]], (p, target)
    # 入力なしなので、u0 の relay は中身を出していない
    assert not [e for e in log.events if e.type == T.DELTA and e.data["source_id"] == "u0"]


def test_t2_drive_count_matches_firing_count() -> None:
    log = run(silent(BASE))
    v = views(log)
    fires = activities(log)
    for unit, targets in {"u1": ("u2", "u3"), "u2": ("u1", "u3")}.items():
        sent = [p for p, u in fires if u == unit and p < PULSES]
        for target in targets:
            received = [p - 1 for (p, t), data in v.items() if t == target
                        for d in data["drives"] if d[0] == unit]
            assert sorted(received) == sorted(sent), (unit, target)


# ---- T3：送り手が Unit でも Receptor でも、運び方の意味が同じ ---------------------------

def test_t3_same_transport_semantics_for_units_and_receptors() -> None:
    cfg = copy.deepcopy(BASE)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {5: "ただいま"}
    log = run(cfg, 30)
    v = views(log)
    sensory = [e.pulse for e in log.events if e.type == T.SENSORY]
    assert sensory == [5]
    assert ["receptor.console", 1.0] in v[(6, "u0")]["drives"]       # 1 Pulse の遅れ・重みの凍結
    assert all(d[0] != "receptor.console" for p in range(1, 31) if p != 6
               for d in v[(p, "u0")]["drives"])
    for p, u in activities(log):
        if u == "u0" and p < 30:
            assert ["u0", 1.0] in v[(p + 1, "u1")]["drives"]           # 同じ 1 Pulse の遅れ・重み


# ---- T4・T6：感覚の出来事は Receptor から。中身の有無は Receptor が決める --------------------

def test_t4_t6_sensory_event_without_material_drives_but_carries_no_content() -> None:
    cfg = copy.deepcopy(BASE)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {5: None}
    log = run(cfg, 20)
    assert [(e.pulse, e.data["with_material"]) for e in log.events if e.type == T.SENSORY] == [(5, False)]
    assert ["receptor.console", 1.0] in views(log)[(6, "u0")]["drives"]
    assert not [e for e in log.events if e.type == T.DELTA and e.data["source_id"] == "receptor.console"]


def test_t6_sensory_event_with_material_also_delivers_content() -> None:
    cfg = copy.deepcopy(BASE)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {5: "ただいま"}
    log = run(cfg, 20)
    contents = [e for e in log.events if e.type == T.DELTA and e.data["source_id"] == "receptor.console"]
    assert [(e.pulse, e.data["payload"], e.data["target_id"]) for e in contents] == [(5, "ただいま", "u0")]
    assert contents[0].data["delta_id"] in views(log)[(6, "u0")]["delta_ids"]


def test_t4_silent_run_has_no_sensory_events() -> None:
    log = run(silent(BASE), 50)
    assert not [e for e in log.events if e.type == T.SENSORY]


# ---- T5：Kernel の結果は駆動しない ----------------------------------------------------

def test_t5_kernel_result_never_creates_activity() -> None:
    output = KernelRequestOutput(resource_class="llm_pool", io_template=None, max_inputs=8)
    unit = make_unit(output)
    task = KernelTask(task_id="t1", unit_id="u1", resource_class="llm_pool", snapshot_id="s",
                      input_delta_ids=(), started_pulse=1, inputs={})
    context = PulseContext(pulse=5, now=5.0, delta_time=1.0)
    for result in (KernelResult("t1", KernelStatus.OK, output="x"),
                   KernelResult("t1", KernelStatus.OK, output=""),
                   KernelResult("t1", KernelStatus.ERROR, error="boom")):
        assert unit.handle_kernel_result(task, result, context).activity is None


def test_t5_firing_record_is_independent_of_kernel_timing_and_result() -> None:
    cfg = copy.deepcopy(BASE)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {5: "ただいま", 40: "おはよう"}
    records = [
        activities(run(with_kernel(cfg, **params), 200))
        for params in (
            {"delay_seconds": 0},
            {"delay_seconds": 3},
            {"delay_seconds": 30},
            {"delay_seconds": 3, "delay_jitter_seconds": 3},
            {"delay_seconds": 3, "result": "empty"},
            {"delay_seconds": 3, "result": "failure"},
        )
    ]
    assert records[0], "発火がない"
    assert all(r == records[0] for r in records[1:])


# ---- T7：重みは伝達の成立時点で凍結される --------------------------------------------------

def test_t7_drive_carries_the_weight_frozen_at_transmission() -> None:
    manifest = parse_neuroarchitecture(BASE["neuro"])
    weights = {(p.source_id, p.target_id): p.weight for p in manifest.projections}
    log = run(silent(BASE), 100)
    checked = 0
    for (_pulse, target), data in views(log).items():
        for source, weight in data["drives"]:
            assert weight == weights[(source, target)]
            checked += 1
    assert checked
    # 可塑性はまだないので、凍結された値は設計図の重みと同じ。可塑性を入れたら、境界で重みが
    # 変わっても前の Pulse に成立した駆動の値が変わらないことを確かめる（接続の状態 仕様 T7）


# ---- T8：駆動は Effector に届かない ---------------------------------------------------

def test_t8_activity_routes_never_include_effectors() -> None:
    manifest = parse_neuroarchitecture(BASE["neuro"])
    router = ProjectionRouter(manifest)
    assert [p.target_id for p in router.route("u3", "main")] == ["effector.console"]   # 中身は届く
    assert router.route_activity("u3") == ()                                          # 駆動は届かない


def test_t8_no_drive_reaches_an_effector_in_a_run() -> None:
    cfg = copy.deepcopy(BASE)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {5: "ただいま"}
    log = run(cfg, 100)
    assert [p for p, u in activities(log) if u == "u3"], "u3 が発火していない"
    for e in log.events:
        if e.type == T.VIEW:
            assert all(not str(d[0]).startswith("effector.") for d in e.data["drives"])
            assert not str(e.data["unit_id"]).startswith("effector.")
