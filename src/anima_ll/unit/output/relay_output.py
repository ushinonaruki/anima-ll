from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class RelayOutput:
    """発火したら、新しく届いた内容をそのまま転送する。計算資源を使わない。"""

    def on_fire(self, view: ReceptiveView, strength: float) -> UnitStepResult:
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
