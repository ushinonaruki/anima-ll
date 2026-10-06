from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.port.clock import Clock


class FakeDelayedKernel:
    """L0 用の偽 Kernel。決まった秒数のあと、入力の要約を返す。LLM は使わない。"""

    def __init__(self, clock: Clock, delay_seconds: float) -> None:
        self._clock = clock
        self._delay = delay_seconds

    async def execute(self, task: KernelTask) -> KernelResult:
        await self._clock.wait_until(self._clock.now() + self._delay)
        items = task.inputs.get("items", []) if isinstance(task.inputs, dict) else []
        sources = ",".join(sorted({str(item.get("from")) for item in items})) or "-"
        return KernelResult(
            task_id=task.task_id,
            status=KernelStatus.OK,
            output=f"<{task.unit_id}:{task.task_id} inputs={len(items)} from={sources}>",
        )
