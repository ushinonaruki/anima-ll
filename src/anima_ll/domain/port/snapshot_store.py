from typing import Protocol

from anima_ll.domain.model.individual import IndividualSnapshot


class SnapshotStore(Protocol):
    """個体の保存先。"""

    def save(self, snapshot: IndividualSnapshot) -> None: ...

    def load_latest(self) -> IndividualSnapshot | None: ...
