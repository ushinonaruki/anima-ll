from typing import Protocol

from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult


class UnitOutput(Protocol):
    """Unit が発火したときに何を出すか。出力先は知らない（Projection が決める）。"""

    def on_fire(self, view: ReceptiveView, strength: float) -> UnitStepResult: ...

    def on_kernel_result(self, task: KernelTask, result: KernelResult) -> UnitStepResult: ...
