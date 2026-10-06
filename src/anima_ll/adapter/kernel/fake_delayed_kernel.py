import random

from anima_ll.domain.model.kernel_task import KernelResult, KernelStatus, KernelTask
from anima_ll.domain.port.clock import Clock


class FakeDelayedKernel:
    """L0 用の偽 Kernel。決まった秒数のあと、入力の要約を返す。LLM は使わない。

    delay_jitter_seconds を与えると、遅延が ±その秒数の範囲でばらつく
    （実験 0002 のアブレーション用：推論時間のばらつきだけの影響を見る）。
    """

    def __init__(
        self,
        clock: Clock,
        delay_seconds: float,
        delay_jitter_seconds: float = 0.0,
        seed: int = 0,
    ) -> None:
        self._clock = clock
        self._delay = delay_seconds
        self._jitter = delay_jitter_seconds
        self._rng = random.Random(seed)

    async def execute(self, task: KernelTask) -> KernelResult:
        delay = self._delay
        if self._jitter:
            delay = max(0.0, delay + self._rng.uniform(-self._jitter, self._jitter))
        await self._clock.wait_until(self._clock.now() + delay)
        items = task.inputs.get("items", []) if isinstance(task.inputs, dict) else []
        sources = ",".join(sorted({str(item.get("from")) for item in items})) or "-"
        return KernelResult(
            task_id=task.task_id,
            status=KernelStatus.OK,
            output=f"<{task.unit_id}:{task.task_id} inputs={len(items)} from={sources}>",
        )
