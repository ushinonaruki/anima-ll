from typing import Protocol

from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import ComponentId


class Effector(Protocol):
    """効果器。自分宛ての確定済み Delta を受け取り、外界へ作用する。"""

    @property
    def effector_id(self) -> ComponentId: ...

    async def execute(self, delta: StateDelta) -> None: ...
