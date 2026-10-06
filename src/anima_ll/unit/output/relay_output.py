from anima_ll.domain.model.claim import ComputeRequest
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.identifiers import JsonValue
from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class RelayOutput:
    """発火したら、新しく届いた内容をそのまま転送する。計算資源を使わず、私的な状態も持たない。"""

    def advance(
        self, view: ReceptiveView, context: PulseContext, firing_strength: float | None
    ) -> UnitStepResult:
        if firing_strength is None:
            return UnitStepResult.empty()
        return UnitStepResult(
            proposed_deltas=tuple(
                ProposedDelta(
                    kind=DeltaKind.CONTENT,
                    payload=delta.payload,
                    cited_delta_ids=(delta.delta_id,),
                )
                for delta in view.new_deltas()
            )
        )

    def on_kernel_result(self, task: KernelTask, result: KernelResult) -> UnitStepResult:
        return UnitStepResult.empty()

    def on_compute_outcome(self, request: ComputeRequest, outcome: str) -> None:
        pass

    def export_state(self) -> JsonValue:
        return {}

    def import_state(self, state: JsonValue) -> None:
        pass
