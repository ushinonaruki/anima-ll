from anima_ll.domain.model.runtime_event import RuntimeEvent


class InMemoryEventLog:
    """来歴ログをメモリに保持する。テスト用。"""

    def __init__(self) -> None:
        self.events: list[RuntimeEvent] = []

    def append(self, event: RuntimeEvent) -> None:
        self.events.append(event)

    def of_type(self, event_type: str) -> list[RuntimeEvent]:
        return [e for e in self.events if e.type == event_type]
