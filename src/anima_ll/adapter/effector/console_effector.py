from collections.abc import Callable

from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import ComponentId


class ConsoleEffector:
    """届いた内容を画面に出す。"""

    def __init__(self, effector_id: ComponentId, write: Callable[[str], None] = print) -> None:
        self._effector_id = effector_id
        self._write = write

    @property
    def effector_id(self) -> ComponentId:
        return self._effector_id

    async def execute(self, delta: StateDelta) -> None:
        self._write(str(delta.payload))
