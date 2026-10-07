"""L0 の完成条件を確認するシナリオテスト。

- Pulse が入力の有無に関係なく回り続ける
- 複数の Unit が 1 つの llm_pool を共有し、同時に計算するのは容量の分だけ（残りは列で待つ）
- Kernel の結果が数 Pulse 後に返り、その間も Pulse は進む
- 出力から入力まで来歴を最後まで辿れる
- 権限違反が棄却され、記録される
- 入力がなくても内在的な駆動で自発的に活動する
- 同じ個体（seed）なら同じ結果になり、seed が違えば別の個体になる
- 1 Unit 1 Pulse 1 依頼の契約と、根拠なしの計算の印（v1.4）
"""

import asyncio
import copy
from dataclasses import asdict
from pathlib import Path

import pytest

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.effector.recording_effector import RecordingEffector
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
from anima_ll.adapter.persistence.json_snapshot_store import JsonSnapshotStore
from anima_ll.bootstrap import Application, ConfigurationMismatch, build_application
from anima_ll.domain.model.compute_request import ComputeRequest, KernelTaskDraft
from anima_ll.domain.model.delta import ProposedDelta
from anima_ll.domain.model.identifiers import is_receptor
from anima_ll.domain.model.runtime_event import RuntimeEventType as T
from anima_ll.domain.model.unit_step import UnitStepResult

BASE = {
    "neuro": {
        "version": 0,
        "delta_ttl_pulses": 10,
        "interfaces": {
            "resources": ["llm_pool"],
            "receptors": ["receptor.console"],
            "effectors": ["effector.console"],
        },
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
    },
    "env": {
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed", "delay_seconds": 3}},
        "receptors": {"receptor.console": {"kind": "scripted", "script": {5: "ただいま"}}},
        "effectors": {"effector.console": {"kind": "recording"}},
    },
    "birth": {"individual_id": "anima", "seed": 42},
}


def silent(cfg: dict) -> dict:
    """入力のない構成にする。"""
    cfg = copy.deepcopy(cfg)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {}
    return cfg


def run(cfg: dict, pulses: int, **overrides) -> tuple[Application, InMemoryEventLog]:
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(cfg["neuro"]),
        parse_environment(cfg["env"]),
        parse_birth_state(cfg["birth"]),
        clock=FixedStepClock(1.0),
        event_log=log,
        **overrides,
    )
    asyncio.run(app.lifecycle.run(max_pulses=pulses))
    return app, log


def test_pulse_keeps_running_without_input() -> None:
    _, log = run(silent(BASE), 30)
    assert [e.pulse for e in log.of_type(T.PULSE)] == list(range(1, 31))


def test_single_worker_runs_one_intent_at_a_time() -> None:
    _, log = run(BASE, 60)
    events = sorted(log.of_type(T.INTENT_STARTED) + log.of_type(T.INTENT_COMPLETED),
                    key=lambda e: (e.pulse, e.type != T.INTENT_COMPLETED))
    running = 0
    for e in events:
        running += 1 if e.type == T.INTENT_STARTED else -1
        assert running <= 1
    waits = [e.pulse - e.data["created_pulse"] for e in log.of_type(T.INTENT_STARTED)]
    assert any(w > 0 for w in waits), "容量 1 で列に待った意図がない"


def test_thinking_spans_pulses_while_world_moves_on() -> None:
    _, log = run(BASE, 60)
    completed = log.of_type(T.INTENT_COMPLETED)
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
    task_inputs = {e.data["task_id"]: e.data["input_delta_ids"] for e in log.of_type(T.INTENT_STARTED)}

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
                ComputeRequest("forbidden_pool", KernelTaskDraft({}, ())),
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
    assert not [e for e in log.of_type(T.INTENT_CREATED) if e.data["unit_id"] == "u1"]
    u1_deltas = [e.data for e in log.of_type(T.DELTA) if e.data["source_id"] == "u1"]
    assert u1_deltas and all(d["parent_delta_ids"] == () for d in u1_deltas)


def test_spontaneous_activity_without_input() -> None:
    _, log = run(silent(BASE), 80)
    assert log.of_type(T.INTENT_STARTED), "入力がないと何も考えない"


def test_drive_below_threshold_stays_silent_without_input() -> None:
    cfg = silent(BASE)
    cfg["neuro"]["defaults"]["dynamics"]["intrinsic_drive"] = 0.03  # 平衡値 ≒ 0.2 < 閾値
    _, log = run(cfg, 80)
    assert not log.of_type(T.INTENT_CREATED)


def test_same_seed_is_deterministic() -> None:
    _, first = run(BASE, 60)
    _, second = run(BASE, 60)
    assert [asdict(e) for e in first.events] == [asdict(e) for e in second.events]


def test_different_seed_is_a_different_individual() -> None:
    other = copy.deepcopy(BASE)
    other["birth"]["seed"] = 43
    _, first = run(BASE, 60)
    _, second = run(other, 60)
    assert [asdict(e) for e in first.events] != [asdict(e) for e in second.events]


class GreedyUnit(MisbehavingUnit):
    """1 Pulse に 2 件の計算依頼を出す Unit（テスト用）。"""

    def tick(self, view, context) -> UnitStepResult:
        request = ComputeRequest("llm_pool", KernelTaskDraft({"items": []}, ()))
        return UnitStepResult(compute_requests=(request, request))


def test_extra_compute_request_is_rejected_and_logged() -> None:
    _, log = run(silent(BASE), 3, unit_overrides={"u1": GreedyUnit()})
    extras = [e for e in log.of_type(T.VIOLATION)
              if e.data["source_id"] == "u1" and e.data["rule"] == "extra_compute_request"]
    assert len(extras) == 3  # 毎 Pulse 1 件ずつ
    created = [e for e in log.of_type(T.INTENT_CREATED) if e.data["unit_id"] == "u1"]
    assert len(created) == 3  # 毎 Pulse 1 件目だけが意図になる
    started = [e for e in log.of_type(T.INTENT_STARTED) if e.data["unit_id"] == "u1"]
    assert len(started) == 1  # 計算中なので 2 件目以降は列で待つ（消えない）


def test_calls_without_evidence_are_marked_not_blocked() -> None:
    _, log = run(silent(BASE), 80)
    started = log.of_type(T.INTENT_STARTED)
    assert started, "根拠なしでも計算は止めない"
    # 入力がないので、最初に始まる計算は必ず根拠なし。
    # （後の計算は他の Unit の出力を受け取るので「直接の根拠なし」ではなくなる。
    #   外からの根拠に辿り着くかどうかは、来歴を辿って集計する：実験 0002 の analyze.py）
    assert started[0].data["without_evidence"] is True
    for e in started:
        assert e.data["without_evidence"] == (len(e.data["input_delta_ids"]) == 0)
    completed = log.of_type(T.INTENT_COMPLETED)
    assert completed and all("without_evidence" in e.data for e in completed)


def test_calls_with_sensory_input_are_not_marked() -> None:
    _, log = run(BASE, 30)
    assert any(e.data["without_evidence"] is False for e in log.of_type(T.INTENT_STARTED))


def test_mismatched_environment_refuses_to_start() -> None:
    cfg = copy.deepcopy(BASE)
    cfg["env"]["receptors"] = {"receptor.mic": {"kind": "scripted"}}
    with pytest.raises(ConfigurationMismatch, match="receptor.console"):
        run(cfg, 1)


def test_run_metadata_is_logged_first() -> None:
    _, log = run(BASE, 3)
    first = log.events[0]
    assert first.type == T.RUN and first.pulse == 0
    assert first.data["seed"] == 42 and first.data["individual_id"] == "anima"
    assert first.data["environment"]["resources"][0]["kernel"] == "fake_delayed"


def test_adaptation_reduces_silent_activity() -> None:
    adapted = silent(BASE)
    adapted["neuro"]["defaults"]["dynamics"].update(adaptation_increment=0.01, adaptation_tau=300)
    _, plain_log = run(silent(BASE), 1200)
    _, adapted_log = run(adapted, 1200)
    assert 0 < len(adapted_log.of_type(T.INTENT_CREATED)) < len(plain_log.of_type(T.INTENT_CREATED))


def test_unit_state_is_sampled_only_when_asked() -> None:
    _, quiet = run(BASE, 20)
    assert not quiet.of_type(T.UNIT_STATE)
    _, sampled = run(BASE, 20, state_sample_interval=5)
    samples = sampled.of_type(T.UNIT_STATE)
    assert [e.pulse for e in samples] == [p for p in (5, 10, 15, 20) for _ in range(4)]
    assert {"activity", "adaptation", "fire_count"} <= set(samples[0].data["state"])


def test_individual_snapshot_roundtrip(tmp_path: Path) -> None:
    store = JsonSnapshotStore(tmp_path)
    app, _ = run(BASE, 20, snapshot_store=store)
    loaded = store.load_latest()
    assert loaded is not None and loaded.pulse == 20
    assert set(loaded.units) == {"u0", "u1", "u2", "u3"}
    assert "worker" not in str(loaded.units)  # 実行基盤の状態は個体に含めない


def test_old_snapshots_without_adaptation_still_load() -> None:
    app, _ = run(BASE, 1)
    unit = app.units.get("u1")
    unit.import_state({"activity": 0.2, "refractory_remaining": 0})
    assert unit.export_state()["adaptation"] == 0.0
