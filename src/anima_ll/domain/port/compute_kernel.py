from typing import Protocol

from anima_ll.domain.model.kernel_task import KernelResult, KernelTask


class ComputeKernel(Protocol):
    """交換可能な計算器官（LLM・小さな NN・偽 Kernel など）。本人ではない。"""

    async def execute(self, task: KernelTask) -> KernelResult: ...
