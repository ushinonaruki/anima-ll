import queue
import sys
import threading
from collections.abc import Callable

from anima_ll.domain.model.sensory_event import SensoryEvent
from anima_ll.domain.model.identifiers import ComponentId


class ConsoleReceptor:
    """キーボードからの入力を受け取る感覚器。

    標準入力は別スレッドで 1 行ずつ読み、Pulse ごとの drain でまとめて渡す。
    入力を待つあいだも Pulse は止まらない。入力が終わったら（EOF）読むのをやめるだけ。
    """

    def __init__(
        self, receptor_id: ComponentId, read_line: Callable[[], str] | None = None
    ) -> None:
        self._receptor_id = receptor_id
        self._read_line = read_line or sys.stdin.readline
        self._lines: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self) -> tuple[SensoryEvent, ...]:
        if self._thread is None:  # 最初の Pulse で読み取りを始める
            self._thread = threading.Thread(target=self._read_loop, name="console-receptor", daemon=True)
            self._thread.start()
        events = []
        while True:
            try:
                events.append(SensoryEvent(self._receptor_id, self._lines.get_nowait()))
            except queue.Empty:
                return tuple(events)

    def _read_loop(self) -> None:
        while True:
            try:
                line = self._read_line()
            except (OSError, ValueError):
                return
            if line == "":  # EOF
                return
            text = line.strip()
            if text:
                self._lines.put(text)
