from typing import Protocol

from anima_ll.domain.model.claim import ComputeRequest
from anima_ll.domain.model.identifiers import JsonValue
from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class UnitOutput(Protocol):
    """Unit が何を出すか。出力先は知らない（Projection が決める）。

    毎 Pulse 1 回 advance が呼ばれる。firing_strength はこの Pulse に発火したならその強さ、しなければ None。
    発火していない Pulse にも、部品の私的な状態（持ち越している計算の要求など）を進められる。
    """

    def advance(
        self, view: ReceptiveView, context: PulseContext, firing_strength: float | None
    ) -> UnitStepResult: ...

    def on_kernel_result(self, task: KernelTask, result: KernelResult) -> UnitStepResult: ...

    def on_compute_outcome(self, request: ComputeRequest, outcome: str) -> None: ...

    def export_state(self) -> JsonValue: ...

    def import_state(self, state: JsonValue) -> None: ...
