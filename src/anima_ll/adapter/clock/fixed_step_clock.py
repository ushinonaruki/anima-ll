import asyncio


class FixedStepClock:
    """テスト用の時計。next_pulse のたびに決まった秒数だけ進み、実時間は待たない。"""

    def __init__(self, step_seconds: float = 1.0, start: float = 0.0) -> None:
        self._step = step_seconds
        self._now = start
        self._advanced = asyncio.Event()

    def now(self) -> float:
        return self._now

    async def next_pulse(self) -> None:
        self._now += self._step
        advanced, self._advanced = self._advanced, asyncio.Event()
        advanced.set()

    async def wait_until(self, deadline: float) -> None:
        while self._now < deadline:
            await self._advanced.wait()
