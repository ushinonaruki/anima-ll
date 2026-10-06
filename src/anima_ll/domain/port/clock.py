from typing import Protocol


class Clock(Protocol):
    """時間の源と、Pulse の歩調。

    実時間で動かすか、テスト用に決まった刻みで進めるかを差し替えられる。
    """

    def now(self) -> float:
        """現在時刻（秒）。"""
        ...

    async def next_pulse(self) -> None:
        """次の Pulse の時刻まで進む（実時間なら待ち、テスト用なら時計を進める）。"""
        ...

    async def wait_until(self, deadline: float) -> None:
        """指定時刻になるまで待つ。"""
        ...
