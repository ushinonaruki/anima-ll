from anima_ll.domain.model.claim import ComputeClaim, ComputeRequest, KernelTaskDraft
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.identifiers import ResourceClass
from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class KernelRequestOutput:
    """発火したら計算資源を要求し、結果が返ったらそれを出力する。

    入力は受容野に届いている Delta だけ。人格や振る舞いの指示は入れない
    （Kernel に渡す形式は io_template が決め、そこにも入出力の形式しか書かない）。
    """

    def __init__(
        self, resource_class: ResourceClass, io_template: str | None, max_inputs: int = 8
    ) -> None:
        self._resource_class = resource_class
        self._io_template = io_template
        self._max_inputs = max_inputs

    def on_fire(self, view: ReceptiveView, strength: float) -> UnitStepResult:
        recent = sorted(view.deltas, key=lambda d: (d.created_pulse, d.delta_id))[-self._max_inputs:]
        draft = KernelTaskDraft(
            inputs={"items": [{"from": d.source_id, "content": d.payload} for d in recent]},
            input_delta_ids=tuple(d.delta_id for d in recent),
            io_template=self._io_template,
        )
        claim = ComputeClaim(resource_class=self._resource_class, strength=strength)
        return UnitStepResult(compute_requests=(ComputeRequest(claim=claim, draft=draft),))

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
