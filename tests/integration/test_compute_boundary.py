"""計算資源境界の契約テスト（実験 0007 の A1〜A5。条件を意図的に作って確かめる）。

仕様：docs/compute-boundary-spec.md v0.3.1
事前登録：experiments/0007_compute_boundary/README.md

Unit は台本どおりに計算を要求する ScriptedUnit に、Kernel はテストが完了のタイミングを
決める ManualKernel に置き換え、Pulse を 1 つずつ進める。
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
from anima_ll.domain.model.compute_request import ComputeRequest, KernelTaskDraft
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.runtime_event import RuntimeEventType as T
from anima_ll.domain.model.unit_step import UnitStepResult

from tests.integration.test_l0_runtime import BASE, silent


class ManualKernel:
    """テストが release するまで結果を返さない Kernel。"""

    def __init__(self) -> None:
        self.started: list[KernelTask] = []
        self._gates: dict[str, asyncio.Event] = {}
        self._status: dict[str, str] = {}

    async def execute(self, task: KernelTask) -> KernelResult:
        self.started.append(task)
        gate = self._gates.setdefault(task.task_id, asyncio.Event())
        await gate.wait()
        status = self._status.get(task.task_id, KernelStatus.OK)
        if status == KernelStatus.ERROR:
            return KernelResult(task_id=task.task_id, status=status, error="boom")
        return KernelResult(task_id=task.task_id, status=status, output=f"out:{task.inputs['tag']}")

    def release(self, tag: str, status: str = KernelStatus.OK) -> None:
        task = next(t for t in self.started if t.inputs["tag"] == tag)
        self._status[task.task_id] = status
        self._gates.setdefault(task.task_id, asyncio.Event()).set()

    def running_tags(self) -> list[str]:
        return [t.inputs["tag"] for t in self.started
                if not self._gates.get(t.task_id, asyncio.Event()).is_set()]


class ScriptedUnit:
    """決めた Pulse に計算を要求し、受け取った結果を記録する Unit（テスト用）。"""

    def __init__(self, unit_id: str, script: dict[int, str]) -> None:
        self.unit_id = unit_id
        self._script = script
        self.received: list[str] = []

    def tick(self, view, context) -> UnitStepResult:
        tag = self._script.get(context.pulse)
        if tag is None:
            return UnitStepResult.empty()
        draft = KernelTaskDraft({"tag": tag}, tuple(sorted(view.delta_ids())))
        return UnitStepResult(compute_requests=(ComputeRequest("llm_pool", draft),))

    def handle_kernel_result(self, task, result, context) -> UnitStepResult:
        self.received.append(result.output if result.status == KernelStatus.OK else f"error:{task.inputs['tag']}")
        return UnitStepResult.empty()

    def export_state(self):
        return {}

    def import_state(self, state) -> None:
        pass


class Harness:
    def __init__(self, scripts: dict[str, dict[int, str]], workers: int,
                 queue_capacity: int | None = None) -> None:
        cfg = copy.deepcopy(silent(BASE))
        pool = cfg["env"]["resources"]["llm_pool"]
        pool["capacity"] = workers
        if queue_capacity is not None:
            pool["queue_capacity"] = queue_capacity
        self.kernel = ManualKernel()
        self.units = {uid: ScriptedUnit(uid, script) for uid, script in scripts.items()}
        self.log = InMemoryEventLog()
        self.app = build_application(
            parse_neuroarchitecture(cfg["neuro"]),
            parse_environment(cfg["env"]),
            parse_birth_state(cfg["birth"]),
            clock=FixedStepClock(1.0),
            event_log=self.log,
            kernel_overrides={"llm_pool": self.kernel},
            unit_overrides=self.units,
        )
        self.pulse = 0

    async def step(self, n: int = 1) -> None:
        for _ in range(n):
            for _ in range(8):
                await asyncio.sleep(0)  # 解放された Kernel の結果を確定させる
            self.pulse += 1
            await self.app.pulse_runtime.run_pulse(PulseContext(self.pulse, float(self.pulse), 1.0))
        for _ in range(8):
            await asyncio.sleep(0)

    def tags(self, event_type: str) -> list[str]:
        tag_of = self._tag_of_intent()
        return [tag_of[e.data["intent_id"]] for e in self.log.of_type(event_type)]

    def _tag_of_intent(self) -> dict[str, str]:
        tags: dict[str, str] = {}
        for e in self.log.of_type(T.INTENT_CREATED):
            unit = self.units[e.data["unit_id"]]
            tags[e.data["intent_id"]] = unit._script[e.pulse]
        return tags

    def no_silent_drop(self) -> None:
        """容量負け・busy による捨ての痕跡がないこと（旧来の schedule・claim のログ自体がない）。"""
        types = {e.type for e in self.log.events}
        assert "schedule" not in types and "claim" not in types


def drive(coro_factory) -> None:
    asyncio.run(coro_factory())


# ---- A1 silent drop がない ----------------------------------------------------

def test_a1_intent_waits_when_workers_are_full() -> None:
    async def scenario() -> None:
        h = Harness({"u1": {1: "A"}, "u2": {1: "C"}}, workers=1)
        await h.step()
        assert h.tags(T.INTENT_CREATED) == ["A", "C"]
        assert h.tags(T.INTENT_ADMITTED) == ["A", "C"]
        assert h.tags(T.INTENT_STARTED) == ["A"]          # C は列で待つ（消えない）
        h.kernel.release("A")
        await h.step(2)
        assert h.tags(T.INTENT_STARTED) == ["A", "C"]
        h.kernel.release("C")
        await h.step(2)
        assert h.tags(T.INTENT_COMPLETED) == ["A", "C"]
        assert h.units["u2"].received == ["out:C"]
        h.no_silent_drop()

    drive(scenario)


def test_a1_intent_from_busy_unit_is_kept() -> None:
    async def scenario() -> None:
        h = Harness({"u1": {1: "A", 2: "B"}}, workers=4)
        await h.step(2)
        assert h.tags(T.INTENT_ADMITTED) == ["A", "B"]
        assert h.tags(T.INTENT_STARTED) == ["A"]          # 計算中の u1 が出した B は列に残る
        assert h.kernel.running_tags() == ["A"]
        h.kernel.release("A")
        await h.step(2)
        h.kernel.release("B")
        await h.step(2)
        assert h.tags(T.INTENT_COMPLETED) == ["A", "B"]
        assert h.units["u1"].received == ["out:A", "out:B"]
        h.no_silent_drop()

    drive(scenario)


# ---- A2 Worker の数で、成立済みの意図が変わらない ---------------------------------

def test_a2_intents_are_identical_for_0_1_4_free_workers() -> None:
    def created(workers: int) -> list[dict]:
        async def scenario() -> list[dict]:
            h = Harness({"u1": {1: "A", 3: "B"}, "u2": {1: "C", 2: "D"}, "u3": {2: "E"}},
                        workers=workers)
            await h.step(5)
            return [dict(e.data, pulse=e.pulse) for e in h.log.of_type(T.INTENT_CREATED)]

        return asyncio.run(scenario())

    zero, one, four = created(0), created(1), created(4)
    assert zero and zero == one == four


# ---- A3 Unit ごとの FIFO と 1 in-flight --------------------------------------------

def test_a3_same_unit_runs_one_at_a_time_in_order() -> None:
    async def scenario() -> None:
        h = Harness({"u1": {1: "A", 2: "B", 3: "C"}}, workers=4)
        await h.step(3)
        assert h.kernel.running_tags() == ["A"]           # Worker が空いていても同時に 1 件だけ
        h.kernel.release("A")
        await h.step(2)
        assert h.kernel.running_tags() == ["B"]
        h.kernel.release("B")
        await h.step(2)
        assert h.kernel.running_tags() == ["C"]
        h.kernel.release("C")
        await h.step(2)
        assert h.tags(T.INTENT_STARTED) == ["A", "B", "C"]
        assert h.units["u1"].received == ["out:A", "out:B", "out:C"]

    drive(scenario)


# ---- A4 Worker を遊ばせない（work-conserving dispatch） -----------------------------

def test_a4_skips_unrunnable_intent_and_keeps_its_place() -> None:
    async def scenario() -> None:
        # Pulse 2 の列：u1:B（intent_seq が先）、u2:C。Worker 2、u1:A は実行中
        h = Harness({"u1": {1: "A", 2: "B"}, "u2": {2: "C"}}, workers=2)
        await h.step(2)
        assert h.tags(T.INTENT_CREATED) == ["A", "B", "C"]
        assert sorted(h.kernel.running_tags()) == ["A", "C"]   # B は飛ばし、C を開始
        assert [i.unit_id for i in h.app.pulse_runtime._queue.waiting()] == ["u1"]
        h.kernel.release("A")
        await h.step(2)
        assert h.tags(T.INTENT_STARTED) == ["A", "C", "B"]

    drive(scenario)


# ---- A5 あふれは明示的な劣化 ------------------------------------------------------

def test_a5_overflow_rejects_new_intent_and_marks_degraded() -> None:
    async def scenario() -> None:
        # Worker 1、列の上限 2。Pulse 1：A を実行。Pulse 2：C・E が待ち（2 件）。Pulse 3：B は受け付けない
        h = Harness({"u1": {1: "A", 3: "B"}, "u2": {2: "C"}, "u3": {2: "E"}},
                    workers=1, queue_capacity=2)
        await h.step(2)
        assert not h.app.pulse_runtime.degraded
        await h.step()
        assert h.tags(T.INTENT_CREATED) == ["A", "C", "E", "B"]   # B も認知の出来事としては存在した
        assert h.tags(T.INTENT_REJECTED_OVERFLOW) == ["B"]
        assert h.app.pulse_runtime.degraded
        assert len(h.log.of_type(T.RUNTIME_DEGRADED)) == 1
        h.kernel.release("A")
        await h.step(2)
        h.kernel.release("C")
        await h.step(2)
        h.kernel.release("E")
        await h.step(2)
        assert h.tags(T.INTENT_COMPLETED) == ["A", "C", "E"]     # 受理済みの意図は捨てない

    drive(scenario)


def test_a5_kernel_error_is_distinct_from_overflow() -> None:
    async def scenario() -> None:
        h = Harness({"u1": {1: "A"}}, workers=1)
        await h.step()
        h.kernel.release("A", status=KernelStatus.ERROR)
        await h.step(2)
        assert h.tags(T.INTENT_KERNEL_ERROR) == ["A"]
        assert not h.log.of_type(T.INTENT_REJECTED_OVERFLOW)
        assert not h.app.pulse_runtime.degraded
        assert h.units["u1"].received == ["error:A"]

    drive(scenario)


def test_outstanding_intents_are_recorded_at_end() -> None:
    async def scenario() -> None:
        h = Harness({"u1": {1: "A", 2: "B"}}, workers=1)
        await h.step(2)
        h.app.pulse_runtime.record_outstanding(h.pulse)
        states = {e.data["intent_id"]: e.data["state"] for e in h.log.of_type(T.INTENT_OUTSTANDING)}
        assert sorted(states.values()) == ["running", "waiting"]
        await h.app.lifecycle._coordinator.shutdown()

    drive(scenario)
