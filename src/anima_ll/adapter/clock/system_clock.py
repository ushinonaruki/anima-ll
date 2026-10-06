import asyncio
import time


class SystemClock:
    """実時間で動く時計。Pulse は interval 秒ごと。"""

    def __init__(self, interval_seconds: float) -> None:
        self._interval = interval_seconds
        self._next_tick = time.monotonic()

    def now(self) -> float:
        return time.monotonic()

    async def next_pulse(self) -> None:
        self._next_tick += self._interval
        delay = self._next_tick - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        else:
            self._next_tick = time.monotonic()  # 遅れたら追いつこうとせず、今から数え直す

    async def wait_until(self, deadline: float) -> None:
        delay = deadline - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
