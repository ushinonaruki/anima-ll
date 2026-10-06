from typing import Protocol

from anima_ll.domain.model.runtime_event import RuntimeEvent


class EventLog(Protocol):
    """来歴ログ。追記するだけ。"""

    def append(self, event: RuntimeEvent) -> None: ...
