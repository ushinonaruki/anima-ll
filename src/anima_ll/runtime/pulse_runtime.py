from dataclasses import asdict

from anima_ll.domain.model.brain_state import BrainState, BrainStateSnapshot
from anima_ll.domain.model.claim import ComputeRequest
from anima_ll.domain.model.delta import ProposedDelta, StateDelta
from anima_ll.domain.model.identifiers import (
    ComponentId,
    DeltaId,
    ResourceClass,
    SnapshotId,
    TaskId,
    UnitId,
    is_effector,
)
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.runtime_event import RuntimeEvent, RuntimeEventType
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_ll.domain.port.event_log import EventLog
from anima_ll.runtime.brain_state_integrator import BrainStateIntegrator
from anima_ll.runtime.delta_canonicalizer import DeltaCanonicalizer
from anima_ll.runtime.effector_dispatcher import EffectorDispatcher
from anima_ll.runtime.external_event_intake import ExternalEventIntake
from anima_ll.runtime.identifier_issuer import IdentifierIssuer
from anima_ll.runtime.kernel_task_coordinator import KernelTaskCoordinator
from anima_ll.runtime.projection_router import ProjectionRouter
from anima_ll.runtime.receptive_view_builder import ReceptiveViewBuilder
from anima_ll.runtime.resource_scheduler import ClaimEntry, ResourceScheduler
from anima_ll.runtime.unit_registry import UnitRegistry

_PendingRequest = tuple[UnitId, ComputeRequest, SnapshotId]


def _without_evidence(input_delta_ids: tuple[DeltaId, ...]) -> bool:
    """受容野から 1 つも Delta を受け取らずに始まった計算か（中身は読まず、数だけを見る）。

    L1 では「何も起きなかった」を情報として表す手段がまだないため、
    このような計算は禁止せずに印をつけて観察する（v1.4 §6）。
    """
    return len(input_delta_ids) == 0


class PulseRuntime:
    """1 Pulse の手順を順に呼ぶだけの調整役。自分では意味の判断をしない。"""

    def __init__(
        self,
        *,
        units: UnitRegistry,
        claim_permissions: dict[UnitId, frozenset[ResourceClass]],
        intake: ExternalEventIntake,
        view_builder: ReceptiveViewBuilder,
        router: ProjectionRouter,
        canonicalizer: DeltaCanonicalizer,
        integrator: BrainStateIntegrator,
        scheduler: ResourceScheduler,
        coordinator: KernelTaskCoordinator,
        dispatcher: EffectorDispatcher,
        issuer: IdentifierIssuer,
        event_log: EventLog,
        initial_state: BrainState | None = None,
        state_sample_interval: int = 0,
    ) -> None:
        self._units = units
        self._claim_permissions = claim_permissions
        self._intake = intake
        self._view_builder = view_builder
        self._router = router
        self._canonicalizer = canonicalizer
        self._integrator = integrator
        self._scheduler = scheduler
        self._coordinator = coordinator
        self._dispatcher = dispatcher
        self._issuer = issuer
        self._log = event_log
        self._state = initial_state or BrainState()
        self._state_sample_interval = state_sample_interval

    @property
    def brain_state(self) -> BrainState:
        return self._state

    async def run_pulse(self, context: PulseContext) -> None:
        pulse = context.pulse
        self._log.append(
            RuntimeEvent(RuntimeEventType.PULSE, pulse, {"now": context.now, "dt": context.delta_time})
        )
        produced: list[StateDelta] = []
        pending: list[_PendingRequest] = []

        # 1. 感覚入力（Receptor は View を持たないので、来歴の起点になる）
        for receptor_id, proposal in self._intake.collect():
            produced += self._publish(receptor_id, proposal, frozenset(), None, None, pulse)

        # 2. この Pulse の View はすべて同じスナップショットから作る
        snapshot = BrainStateSnapshot(self._issuer.snapshot_id(), pulse, self._state)

        # 3. 前の Pulse までに終わった思考を、依頼元の Unit に返す
        for task, result in self._coordinator.collect_completed():
            self._log.append(
                RuntimeEvent(
                    RuntimeEventType.TASK_COMPLETED,
                    pulse,
                    {"task_id": task.task_id, "unit_id": task.unit_id,
                     "started_pulse": task.started_pulse, "status": result.status,
                     "without_evidence": _without_evidence(task.input_delta_ids),
                     "output": result.output, "error": result.error},
                )
            )
            step = self._units.get(task.unit_id).handle_kernel_result(task, result, context)
            produced += self._collect_step(
                task.unit_id, step, frozenset(task.input_delta_ids), task.snapshot_id,
                task.task_id, pulse, pending,
            )

        # 4. 全 Unit を進める
        for unit in self._units.all():
            view = self._view_builder.build(unit.unit_id, snapshot)
            self._log.append(
                RuntimeEvent(
                    RuntimeEventType.VIEW,
                    pulse,
                    {"unit_id": unit.unit_id, "snapshot_id": snapshot.snapshot_id,
                     "delta_ids": [d.delta_id for d in view.deltas]},
                )
            )
            step = unit.tick(view, context)
            produced += self._collect_step(
                unit.unit_id, step, view.delta_ids(), snapshot.snapshot_id, None, pulse, pending
            )

        # 5. 計算資源の割り当て（Scheduler に見せるのは claim の数値だけ）
        self._schedule(pending, pulse)

        # 6. Pulse の境界で反映（ここで確定した Delta は次の Pulse から見える）
        for delta in produced:
            self._log.append(RuntimeEvent(RuntimeEventType.DELTA, pulse, asdict(delta)))
        to_brain = [d for d in produced if not is_effector(d.target_id)]
        to_effectors = [d for d in produced if is_effector(d.target_id)]
        self._state = self._integrator.integrate(self._state, to_brain, pulse)

        # 7. 外界への作用
        await self._dispatcher.dispatch(to_effectors)
        for delta in to_effectors:
            self._log.append(
                RuntimeEvent(RuntimeEventType.EFFECT, pulse,
                             {"delta_id": delta.delta_id, "effector_id": delta.target_id})
            )

        # 8. 観察用：Unit の私的な状態の標本（Runtime は中身を解釈せず、そのまま記録するだけ）
        if self._state_sample_interval and pulse % self._state_sample_interval == 0:
            for unit in self._units.all():
                self._log.append(
                    RuntimeEvent(RuntimeEventType.UNIT_STATE, pulse,
                                 {"unit_id": unit.unit_id, "state": unit.export_state()})
                )

    def _collect_step(
        self,
        unit_id: UnitId,
        step: UnitStepResult,
        visible: frozenset[DeltaId],
        snapshot_id: SnapshotId,
        task_id: TaskId | None,
        pulse: int,
        pending: list[_PendingRequest],
    ) -> list[StateDelta]:
        produced: list[StateDelta] = []
        for proposal in step.proposed_deltas:
            produced += self._publish(unit_id, proposal, visible, snapshot_id, task_id, pulse)
        for request in step.compute_requests:
            pending.append((unit_id, request, snapshot_id))
        return produced

    def _publish(
        self,
        source_id: ComponentId,
        proposal: ProposedDelta,
        visible: frozenset[DeltaId],
        snapshot_id: SnapshotId | None,
        task_id: TaskId | None,
        pulse: int,
    ) -> list[StateDelta]:
        projections = self._router.route(source_id, proposal.output_port)
        if not projections:
            self._log.append(
                RuntimeEvent(RuntimeEventType.UNROUTED, pulse,
                             {"source_id": source_id, "port": proposal.output_port})
            )
            return []
        outcome = self._canonicalizer.canonicalize(
            source_id=source_id,
            proposal=proposal,
            projections=projections,
            visible_delta_ids=visible,
            origin_snapshot_id=snapshot_id,
            origin_task_id=task_id,
            pulse=pulse,
        )
        if outcome.rejected_citations:
            self._violation(pulse, source_id, "uncited_reference",
                            {"delta_ids": list(outcome.rejected_citations)})
        unknown = [d.target_id for d in outcome.deltas
                   if is_effector(d.target_id) and not self._dispatcher.knows(d.target_id)]
        if unknown:
            self._violation(pulse, source_id, "unknown_effector", {"targets": unknown})
        return [d for d in outcome.deltas if d.target_id not in unknown]

    def _schedule(self, pending: list[_PendingRequest], pulse: int) -> None:
        busy = self._coordinator.busy_units()
        eligible: list[_PendingRequest] = []
        seen_units: set[UnitId] = set()
        for unit_id, request, snapshot_id in pending:
            claim = request.claim
            self._log.append(
                RuntimeEvent(RuntimeEventType.CLAIM, pulse,
                             {"unit_id": unit_id, "resource_class": claim.resource_class,
                              "strength": claim.strength})
            )
            if claim.resource_class not in self._claim_permissions.get(unit_id, frozenset()):
                self._violation(pulse, unit_id, "resource_not_allowed",
                                {"resource_class": claim.resource_class})
                continue
            if unit_id in seen_units:
                # 1 Unit が 1 Pulse に出せる計算依頼は 1 件まで。2 件目以降は棄却して記録する
                self._violation(pulse, unit_id, "extra_compute_request",
                                {"resource_class": claim.resource_class})
                continue
            seen_units.add(unit_id)
            if unit_id in busy:
                continue  # 思考中の Unit は新しい依頼を出せない（1 Unit 1 タスク。schedule.busy に残る）
            eligible.append((unit_id, request, snapshot_id))

        entries = [ClaimEntry(unit_id, request.claim) for unit_id, request, _ in eligible]
        decision = self._scheduler.select(entries, self._coordinator.free_capacity(), pulse)
        accepted_units = {entry.unit_id for entry in decision.accepted}
        self._log.append(
            RuntimeEvent(RuntimeEventType.SCHEDULE, pulse,
                         {"accepted": sorted(accepted_units),
                          "rejected": sorted(e.unit_id for e in decision.rejected),
                          "busy": sorted(busy),
                          "tie_broken": list(decision.tie_broken)})
        )
        for unit_id, request, snapshot_id in eligible:
            if unit_id not in accepted_units:
                continue
            task = self._coordinator.start(
                unit_id=unit_id,
                resource_class=request.claim.resource_class,
                draft=request.draft,
                snapshot_id=snapshot_id,
                pulse=pulse,
            )
            self._log.append(
                RuntimeEvent(RuntimeEventType.TASK_STARTED, pulse,
                             {"task_id": task.task_id, "unit_id": unit_id,
                              "resource_class": task.resource_class,
                              "snapshot_id": snapshot_id,
                              "input_delta_ids": list(task.input_delta_ids),
                              "without_evidence": _without_evidence(task.input_delta_ids)})
            )

    def _violation(self, pulse: int, source_id: ComponentId, rule: str, detail: dict) -> None:
        self._log.append(
            RuntimeEvent(RuntimeEventType.VIOLATION, pulse,
                         {"source_id": source_id, "rule": rule, **detail})
        )
