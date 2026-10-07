from collections import defaultdict

from anima_ll.domain.model.identifiers import DeltaId, SnapshotId, TaskId


class IdentifierIssuer:
    """ID を採番する。意味を持たない連番。"""

    def __init__(self, namespace: str = "") -> None:
        self._namespace = f"{namespace}:" if namespace else ""
        self._counters: dict[str, int] = defaultdict(int)

    def _issue(self, prefix: str) -> str:
        self._counters[prefix] += 1
        return f"{self._namespace}{prefix}{self._counters[prefix]:06d}"

    def delta_id(self) -> DeltaId:
        return self._issue("d")

    def task_id(self) -> TaskId:
        return self._issue("t")

    def intent_id(self) -> str:
        return self._issue("i")

    def snapshot_id(self) -> SnapshotId:
        return self._issue("s")
