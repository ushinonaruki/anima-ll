import math

from anima_ll.domain.model.claim import (
    ComputeClaim,
    ComputeOutcome,
    ComputeRequest,
    KernelTaskDraft,
    RequestOrigin,
)
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.identifiers import JsonValue, ResourceClass
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class KernelRequestOutput:
    """発火したら計算資源を要求し、結果が返ったらそれを出力する。

    入力は受容野に届いている Delta だけ。人格や振る舞いの指示は入れない
    （Kernel に渡す形式は io_template が決め、そこにも入出力の形式しか書かない）。

    計算の要求の持ち越し（L2-2、Computational hypothesis）：
      競合に負けた要求は、pending（まだ処理されていない計算の要求の強さ）として残り、
      pending ← pending × exp(−Δt / τ_p) で弱まりながら、毎 Pulse その強さで再提示される。
      - 再提示は発火ではない（activity にも順応にも触らない）
      - 新しい発火と重なったら、1 本の要求に統合する（強さは max）
      - 持ち越すのは「計算したい」という強さだけ。Kernel に渡す中身は、提示する Pulse の受容野から作り直す
      - 計算が始まったら消える。p_min を下回ったら諦める。自分の前の計算が実行中（busy）なら持ち越さない
      τ_p = 0 なら持ち越さない（L2-1 までと同じ）。
    """

    def __init__(
        self,
        resource_class: ResourceClass,
        io_template: str | None,
        max_inputs: int = 8,
        pending_tau_seconds: float = 0.0,
        pending_floor: float = 0.1,
    ) -> None:
        self._resource_class = resource_class
        self._io_template = io_template
        self._max_inputs = max_inputs
        self._pending_tau = pending_tau_seconds
        self._pending_floor = pending_floor
        self._pending = 0.0

    @property
    def pending(self) -> float:
        return self._pending

    def advance(
        self, view: ReceptiveView, context: PulseContext, firing_strength: float | None
    ) -> UnitStepResult:
        pending = self._pending
        if pending and self._pending_tau > 0:
            pending *= math.exp(-context.delta_time / self._pending_tau)
        if pending < self._pending_floor:
            pending = 0.0  # 弱まりきったので諦める
        self._pending = 0.0  # 提示した要求の結果（on_compute_outcome）で、必要なら持ち越し直す

        if firing_strength is None and pending == 0.0:
            return UnitStepResult.empty()
        strength = max(pending, firing_strength or 0.0)
        origin = RequestOrigin.FIRING if firing_strength is not None else RequestOrigin.PENDING
        return UnitStepResult(compute_requests=(self._request(view, strength, origin),))

    def on_compute_outcome(self, request: ComputeRequest, outcome: str) -> None:
        if outcome == ComputeOutcome.REJECTED_CAPACITY and self._pending_tau > 0:
            self._pending = request.claim.strength
        else:
            self._pending = 0.0  # 始まった、または自分の前の計算が実行中

    def on_kernel_result(self, task: KernelTask, result: KernelResult) -> UnitStepResult:
        if result.status != KernelStatus.OK or result.output in (None, ""):
            return UnitStepResult.empty()
        return UnitStepResult(
            proposed_deltas=(
                ProposedDelta(
                    kind=DeltaKind.CONTENT,
                    payload=result.output,
                    cited_delta_ids=task.input_delta_ids,
                ),
            )
        )

    def export_state(self) -> JsonValue:
        return {"pending": self._pending}

    def import_state(self, state: JsonValue) -> None:
        self._pending = float((state or {}).get("pending", 0.0))

    def _request(self, view: ReceptiveView, strength: float, origin: str) -> ComputeRequest:
        recent = sorted(view.deltas, key=lambda d: (d.created_pulse, d.delta_id))[-self._max_inputs:]
        draft = KernelTaskDraft(
            inputs={"items": [{"from": d.source_id, "content": d.payload} for d in recent]},
            input_delta_ids=tuple(d.delta_id for d in recent),
            io_template=self._io_template,
        )
        claim = ComputeClaim(resource_class=self._resource_class, strength=strength)
        return ComputeRequest(claim=claim, draft=draft, origin=origin)
