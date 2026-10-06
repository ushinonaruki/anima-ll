from typing import Protocol

from anima_ll.domain.model.claim import ComputeRequest
from anima_ll.domain.model.identifiers import JsonValue, UnitId
from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class CognitiveUnit(Protocol):
    """すべての Unit が従う唯一のインターフェース。

    MemoryUnit・EmotionUnit のような役割別のインターフェースは作らない。
    Unit は他の Unit を知らず、受け取るのは View、返すのは提案だけ。
    """

    @property
    def unit_id(self) -> UnitId: ...

    def tick(self, view: ReceptiveView, context: PulseContext) -> UnitStepResult:
        """毎 Pulse 呼ばれる。内部状態を更新し、出力と計算資源の要求を返す。"""
        ...

    def handle_kernel_result(
        self, task: KernelTask, result: KernelResult, context: PulseContext
    ) -> UnitStepResult:
        """自分が依頼した計算が終わったときに呼ばれる。"""
        ...

    def handle_compute_outcome(
        self, request: ComputeRequest, outcome: str, context: PulseContext
    ) -> None:
        """自分が出した計算の要求が、この Pulse にどうなったか（ComputeOutcome）を受け取る。

        自分が外へ出した要求の結果を局所回路へ戻すフィードバックであり、ほかの Unit のことは何も含まない。
        """
        ...

    def export_state(self) -> JsonValue: ...

    def import_state(self, state: JsonValue) -> None: ...
