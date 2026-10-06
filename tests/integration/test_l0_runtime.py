"""L0 の完成条件を確認するシナリオテスト。

- Pulse が入力の有無に関係なく回り続ける
- 複数の Unit が 1 つの llm_pool を取り合い、容量分だけ採択される
- Kernel の結果が数 Pulse 後に返り、その間も Pulse は進む
- 出力から入力まで来歴を最後まで辿れる
- 権限違反が棄却され、記録される
- 入力がなくても内在的な駆動で自発的に活動する
- 同じ seed なら同じ結果になる
"""

import asyncio
import copy
from dataclasses import asdict
from pathlib import Path

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.effector.recording_effector import RecordingEffector
from anima_ll.adapter.manifest.yaml_manifest_source import parse_manifest
from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
from anima_ll.adapter.persistence.json_snapshot_store import JsonSnapshotStore
from anima_ll.bootstrap import Application, build_application
from anima_ll.domain.model.claim import ComputeClaim, ComputeRequest, KernelTaskDraft
from anima_ll.domain.model.delta import ProposedDelta
from anima_ll.domain.model.identifiers import is_receptor
from anima_ll.domain.model.runtime_event import RuntimeEventType as T
from anima_ll.domain.model.unit_step import UnitStepResult

BASE = {
    "version": 0,
    "seed": 42,
    "delta_ttl_pulses": 10,
    "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed", "delay_seconds": 3}},
    "receptors": [{"id": "receptor.console", "kind": "scripted", "script": {5: "ただいま"}}],
    "effectors": [{"id": "effector.console", "kind": "recording"}],
    "defaults": {"dynamics": {"kind": "simple_activity", "decay": 0.85, "threshold": 0.5,
                              "refractory_pulses": 3, "intrinsic_drive": 0.08, "jitter": 0.1}},
    "units": [
        {"id": "u0", "output": "relay"},
        {"id": "u1", "output": {"kind": "kernel_request", "resource": "llm_pool"}},
        {"id": "u2", "output": {"kind": "kernel_request", "resource": "llm_pool"}},
        {"id": "u3", "output": {"kind": "kernel_request", "resource": "llm_pool"}},
    ],
    "projections": [
        {"from": "receptor.console.main", "to": "u0"},
        {"from": "u0.main", "to": "u1"},
        {"from": "u0.main", "to": "u2"},
        {"from": "u1.main", "to": "u2", "weight": 0.4},
        {"from": "u2.main", "to": "u1", "weight": 0.4},
        {"from": "u1.main", "to": "u3", "weight": 0.6},
        {"from": "u2.main", "to": "u3", "weight": 0.6},
        {"from": "u3.main", "to": "effector.console"},
    ],
}


def run(raw: dict, pulses: int, **overrides) -> tuple[Application, InMemoryEventLog]:
    log = InMemoryEventLog()
    app = build_application(parse_manifest(raw), clock=FixedStepClock(1.0), event_log=log, **overrides)
    asyncio.run(app.lifecycle.run(max_pulses=pulses))
    return app, log


def test_pulse_keeps_running_without_input() -> None:
    raw = copy.deepcopy(BASE)
    raw["receptors"][0]["script"] = {}
    _, log = run(raw, 30)
    assert [e.pulse for e in log.of_type(T.PULSE)] == list(range(1, 31))


def test_units_compete_for_single_worker() -> None:
    _, log = run(BASE, 60)
    contested = [e for e in log.of_type(T.SCHEDULE) if e.data["accepted"] and e.data["rejected"]]
    assert contested, "llm_pool を取り合った Pulse がない"
    assert all(len(e.data["accepted"]) == 1 for e in contested)


def test_thinking_spans_pulses_while_world_moves_on() -> None:
    _, log = run(BASE, 60)
    completed = log.of_type(T.TASK_COMPLETED)
    assert completed
    for event in completed:
        started = event.data["started_pulse"]
        assert event.pulse - started >= 3
        between = [p.pulse for p in log.of_type(T.PULSE) if started < p.pulse < event.pulse]
        assert between, "思考中に Pulse が進んでいない"


def test_output_traces_back_to_sensory_input() -> None:
    app, log = run(BASE, 60)
    effector = app.effectors["effector.console"]
    assert isinstance(effector, RecordingEffector) and effector.received

    deltas = {e.data["delta_id"]: e.data for e in log.of_type(T.DELTA)}
    task_inputs = {e.data["task_id"]: e.data["input_delta_ids"] for e in log.of_type(T.TASK_STARTED)}

    def reaches_receptor(delta_id: str) -> bool:
        stack, seen = [delta_id], set()
        while stack:
            current = deltas[stack.pop()]
            if current["delta_id"] in seen:
                continue
            seen.add(current["delta_id"])
            if is_receptor(current["source_id"]):
                return True
            stack += list(current["parent_delta_ids"])
            if current["origin_task_id"]:
                stack += task_inputs[current["origin_task_id"]]
        return False

    assert any(reaches_receptor(d.delta_id) for d in effector.received)


class MisbehavingUnit:
    """権限外の資源を要求し、見ていない Delta を根拠に挙げる Unit（テスト用）。"""

    unit_id = "u1"

    def tick(self, view, context) -> UnitStepResult:
        return UnitStepResult(
            proposed_deltas=(ProposedDelta(kind="content", payload="x", cited_delta_ids=("d-fake",)),),
            compute_requests=(
                ComputeRequest(ComputeClaim("forbidden_pool", 1.0), KernelTaskDraft({}, ())),
            ),
        )

    def handle_kernel_result(self, task, result, context) -> UnitStepResult:
        return UnitStepResult.empty()

    def export_state(self):
        return {}

    def import_state(self, state) -> None:
        pass


def test_violations_are_rejected_and_logged() -> None:
    _, log = run(BASE, 5, unit_overrides={"u1": MisbehavingUnit()})
    rules = {e.data["rule"] for e in log.of_type(T.VIOLATION) if e.data["source_id"] == "u1"}
    assert {"resource_not_allowed", "uncited_reference"} <= rules
    assert not [e for e in log.of_type(T.TASK_STARTED) if e.data["unit_id"] == "u1"]
    u1_deltas = [e.data for e in log.of_type(T.DELTA) if e.data["source_id"] == "u1"]
    assert u1_deltas and all(d["parent_delta_ids"] == () for d in u1_deltas)


def test_spontaneous_activity_without_input() -> None:
    raw = copy.deepcopy(BASE)
    raw["receptors"][0]["script"] = {}
    _, log = run(raw, 80)
    assert log.of_type(T.TASK_STARTED), "入力がないと何も考えない"


def test_drive_below_threshold_stays_silent_without_input() -> None:
    raw = copy.deepcopy(BASE)
    raw["receptors"][0]["script"] = {}
    raw["defaults"]["dynamics"]["intrinsic_drive"] = 0.03  # 平衡値 ≒ 0.2 < 閾値
    _, log = run(raw, 80)
    assert not log.of_type(T.TASK_STARTED)


def test_same_seed_is_deterministic() -> None:
    _, first = run(BASE, 60)
    _, second = run(BASE, 60)
    assert [asdict(e) for e in first.events] == [asdict(e) for e in second.events]


def test_individual_snapshot_roundtrip(tmp_path: Path) -> None:
    store = JsonSnapshotStore(tmp_path)
    app, _ = run(BASE, 20, snapshot_store=store)
    loaded = store.load_latest()
    assert loaded is not None and loaded.pulse == 20
    assert set(loaded.units) == {"u0", "u1", "u2", "u3"}
    assert "worker" not in str(loaded.units)  # 実行基盤の状態は個体に含めない
