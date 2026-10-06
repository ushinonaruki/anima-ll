import asyncio

from anima_ll.adapter.kernel.fake_delayed_kernel import FakeDelayedKernel
from anima_ll.domain.model.kernel_task import KernelTask


class RecordingClock:
    """待つ時間だけを記録する時計（実際には待たない）。"""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def now(self) -> float:
        return 0.0

    async def next_pulse(self) -> None:
        pass

    async def wait_until(self, deadline: float) -> None:
        self.waits.append(deadline)


TASK = KernelTask("t-1", "u1", "llm_pool", "s-1", (), 1, {"items": []})


def delays(jitter: float, seed: int, n: int = 5) -> list[float]:
    clock = RecordingClock()
    kernel = FakeDelayedKernel(clock, delay_seconds=3.0, delay_jitter_seconds=jitter, seed=seed)
    for _ in range(n):
        asyncio.run(kernel.execute(TASK))
    return clock.waits


def test_jitter_is_seeded_and_bounded() -> None:
    first, second = delays(2.0, seed=7), delays(2.0, seed=7)
    assert first == second
    assert all(1.0 <= d <= 5.0 for d in first)
    assert len(set(first)) > 1


def test_no_jitter_keeps_fixed_delay() -> None:
    assert delays(0.0, seed=7) == [3.0] * 5
