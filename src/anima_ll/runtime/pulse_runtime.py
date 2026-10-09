import hashlib
import json
from dataclasses import asdict

from anima_ll.domain.model.activity import Drive
from anima_ll.domain.model.brain_state import BrainState, BrainStateSnapshot
from anima_ll.domain.model.compute_request import ComputeRequest, KernelTaskDraft
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta, StateDelta
from anima_ll.domain.model.identifiers import (
    ComponentId,
    PulseNumber,
    DeltaId,
    ResourceClass,
    SnapshotId,
    TaskId,
    UnitId,
    is_effector,
)
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.runtime_event import RuntimeEvent, RuntimeEventType
from anima_ll.domain.model.kernel_task import KernelStatus
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_ll.domain.port.event_log import EventLog
from anima_ll.runtime.brain_state_integrator import BrainStateIntegrator
from anima_ll.runtime.compute_intent import ComputeIntent
from anima_ll.runtime.delta_canonicalizer import DeltaCanonicalizer
from anima_ll.runtime.effector_dispatcher import EffectorDispatcher
from anima_ll.runtime.execution_queue import ExecutionQueue
from anima_ll.runtime.external_event_intake import ExternalEventIntake
from anima_ll.runtime.identifier_issuer import IdentifierIssuer
from anima_ll.runtime.kernel_task_coordinator import KernelTaskCoordinator
from anima_ll.runtime.projection_router import ProjectionRouter
from anima_ll.runtime.receptive_view_builder import ReceptiveViewBuilder
from anima_ll.runtime.unit_registry import UnitRegistry

_PendingRequest = tuple[UnitId, ComputeRequest, SnapshotId]


def _without_evidence(input_delta_ids: tuple[DeltaId, ...]) -> bool:
    """受容野から 1 つも Delta を受け取らずに始まった計算か（中身は読まず、数だけを見る）。

    L1 では「何も起きなかった」を情報として表す手段がまだないため、
    このような計算は禁止せずに印をつけて観察する（v1.4 §6）。
    """
    return len(input_delta_ids) == 0


def _draft_hash(draft: KernelTaskDraft) -> str:
    """凍結した下書きの指紋（Worker の数で意図の中身が変わらないことの確認用）。"""
    text = json.dumps(asdict(draft), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


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
        queue: ExecutionQueue,
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
        self._queue = queue
        self._intent_seq = 0
        self._degraded = False
        self._coordinator = coordinator
        self._dispatcher = dispatcher
        self._issuer = issuer
        self._log = event_log
        self._state = initial_state or BrainState()
        self._state_sample_interval = state_sample_interval

    @property
    def brain_state(self) -> BrainState:
        return self._state

    @property
    def degraded(self) -> bool:
        """列があふれたことがあるか。あふれた run の結果は認知として解釈しない（仕様 §3.3）。"""
        return self._degraded

    async def run_pulse(self, context: PulseContext) -> None:
        pulse = context.pulse
        self._log.append(
            RuntimeEvent(RuntimeEventType.PULSE, pulse, {"now": context.now, "dt": context.delta_time})
        )
        produced: list[StateDelta] = []
        drives: list[Drive] = []
        pending: list[_PendingRequest] = []

        # 1. 感覚の出来事（Receptor が成立させたもの）。駆動は Unit の発火と同じ運び方で運ぶ。
        #    中身が添えられていれば、中身の Delta として運ぶ（Receptor は View を持たないので来歴の起点）
        for event in self._intake.collect():
            self._log.append(RuntimeEvent(RuntimeEventType.SENSORY, pulse,
                                          {"receptor_id": event.receptor_id,
                                           "with_material": event.material is not None}))
            drives += self._transmit(event.receptor_id, pulse)
            if event.material is not None:
                proposal = ProposedDelta(kind=DeltaKind.CONTENT, payload=event.material)
                produced += self._publish(event.receptor_id, proposal, frozenset(), None, None, pulse)

        # 2. この Pulse の View はすべて同じスナップショットから作る
        snapshot = BrainStateSnapshot(self._issuer.snapshot_id(), pulse, self._state)

        # 3. 前の Pulse までに終わった思考を、依頼元の Unit に返す
        for intent, task, result in self._coordinator.collect_completed():
            event_type = (RuntimeEventType.INTENT_COMPLETED if result.status == KernelStatus.OK
                          else RuntimeEventType.INTENT_KERNEL_ERROR)
            self._log.append(
                RuntimeEvent(
                    event_type,
                    pulse,
                    {"intent_id": intent.intent_id, "task_id": task.task_id,
                     "unit_id": task.unit_id, "created_pulse": intent.created_pulse,
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
                     "delta_ids": [d.delta_id for d in view.deltas],
                     "drives": [[d.source_id, d.weight] for d in view.drives]},
                )
            )
            step = unit.tick(view, context)
            if step.activity is not None:
                self._log.append(RuntimeEvent(RuntimeEventType.ACTIVITY, pulse,
                                              {"unit_id": step.activity.unit_id}))
                drives += self._transmit(step.activity.unit_id, pulse)
            produced += self._collect_step(
                unit.unit_id, step, view.delta_ids(), snapshot.snapshot_id, None, pulse, pending
            )

        # 5. 計算の意図を受理して列に並べ、空いた Worker に渡す（中身・強さは見ない）
        self._admit(pending, pulse)
        self._dispatch(pulse)

        # 6. Pulse の境界で反映（ここで確定した Delta は次の Pulse から見える）
        for delta in produced:
            self._log.append(RuntimeEvent(RuntimeEventType.DELTA, pulse, asdict(delta)))
        to_brain = [d for d in produced if not is_effector(d.target_id)]
        to_effectors = [d for d in produced if is_effector(d.target_id)]
        self._state = self._integrator.integrate(self._state, to_brain, drives, pulse)

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

    def _transmit(self, source_id: ComponentId, pulse: PulseNumber) -> list[Drive]:
        """成立済みの出来事（Unit の発火・Receptor の感覚）を、接続に沿って駆動として運ぶ。

        送り手が Unit でも Receptor でも同じ運び方（活動の伝達 仕様 §3.3）：
        接続を引き、この Pulse の重みを凍結し、次の Pulse に届ける。何が刺激かを判断しない。
        """
        return [
            Drive(source_id=source_id, target_id=p.target_id, weight=p.weight, created_pulse=pulse)
            for p in self._router.route_activity(source_id)
        ]

    def _admit(self, pending: list[_PendingRequest], pulse: PulseNumber) -> None:
        """合法な要求を ComputeIntent として凍結し、列に受理する。

        容量不足や計算中を理由に捨てない。捨てるのは列の上限を超えたとき（tail-drop）だけで、
        それも明示的に記録し、run を劣化として扱う。
        """
        seen_units: set[UnitId] = set()
        for unit_id, request, snapshot_id in pending:
            if request.resource_class not in self._claim_permissions.get(unit_id, frozenset()):
                self._violation(pulse, unit_id, "resource_not_allowed",
                                {"resource_class": request.resource_class})
                continue
            if unit_id in seen_units:
                # 1 Unit が 1 Pulse に出せる計算の要求は 1 件まで（Runtime の暫定の契約）。
                # 2 件目以降は棄却して記録する
                self._violation(pulse, unit_id, "extra_compute_request",
                                {"resource_class": request.resource_class})
                continue
            seen_units.add(unit_id)
            self._intent_seq += 1
            intent = ComputeIntent(
                intent_id=self._issuer.intent_id(),
                intent_seq=self._intent_seq,
                unit_id=unit_id,
                created_pulse=pulse,
                resource_class=request.resource_class,
                origin_snapshot_id=snapshot_id,
                draft=request.draft,
            )
            self._log.append(
                RuntimeEvent(RuntimeEventType.INTENT_CREATED, pulse,
                             {"intent_id": intent.intent_id, "intent_seq": intent.intent_seq,
                              "unit_id": unit_id, "resource_class": intent.resource_class,
                              "origin_snapshot_id": snapshot_id,
                              "input_delta_ids": list(intent.input_delta_ids),
                              "draft_hash": _draft_hash(intent.draft),
                              "without_evidence": _without_evidence(intent.input_delta_ids)})
            )
            if self._queue.admit(intent):
                self._log.append(
                    RuntimeEvent(RuntimeEventType.INTENT_ADMITTED, pulse,
                                 {"intent_id": intent.intent_id,
                                  "waiting": len(self._queue.waiting(intent.resource_class))})
                )
                continue
            self._log.append(
                RuntimeEvent(RuntimeEventType.INTENT_REJECTED_OVERFLOW, pulse,
                             {"intent_id": intent.intent_id, "unit_id": unit_id,
                              "resource_class": intent.resource_class})
            )
            if not self._degraded:
                self._degraded = True
                self._log.append(
                    RuntimeEvent(RuntimeEventType.RUNTIME_DEGRADED, pulse,
                                 {"reason": "queue_overflow",
                                  "resource_class": intent.resource_class})
                )

    def _dispatch(self, pulse: PulseNumber) -> None:
        for intent in self._queue.take_dispatchable(
            self._coordinator.free_capacity(), self._coordinator.busy_units()
        ):
            task = self._coordinator.start(intent, pulse)
            self._log.append(
                RuntimeEvent(RuntimeEventType.INTENT_STARTED, pulse,
                             {"intent_id": intent.intent_id, "task_id": task.task_id,
                              "unit_id": intent.unit_id,
                              "resource_class": intent.resource_class,
                              "created_pulse": intent.created_pulse,
                              "snapshot_id": intent.origin_snapshot_id,
                              "input_delta_ids": list(intent.input_delta_ids),
                              "without_evidence": _without_evidence(intent.input_delta_ids)})
            )

    def record_outstanding(self, pulse: PulseNumber) -> None:
        """run の終了時点で実行中・待ちのまま残った意図を記録する（消えたのではない）。"""
        for intent in sorted(self._coordinator.in_flight(), key=lambda i: i.intent_seq):
            self._log.append(
                RuntimeEvent(RuntimeEventType.INTENT_OUTSTANDING, pulse,
                             {"intent_id": intent.intent_id, "unit_id": intent.unit_id,
                              "state": "running"})
            )
        for intent in self._queue.waiting():
            self._log.append(
                RuntimeEvent(RuntimeEventType.INTENT_OUTSTANDING, pulse,
                             {"intent_id": intent.intent_id, "unit_id": intent.unit_id,
                              "state": "waiting"})
            )

    def _violation(self, pulse: int, source_id: ComponentId, rule: str, detail: dict) -> None:
        self._log.append(
            RuntimeEvent(RuntimeEventType.VIOLATION, pulse,
                         {"source_id": source_id, "rule": rule, **detail})
        )
