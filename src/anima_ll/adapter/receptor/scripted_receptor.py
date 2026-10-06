from collections.abc import Mapping

from anima_ll.domain.model.external_event import ExternalEvent
from anima_ll.domain.model.identifiers import ComponentId, JsonValue


class ScriptedReceptor:
    """決めた回（drain が呼ばれた回数）に、決めた入力を出す。L0 とテスト用。"""

    def __init__(self, receptor_id: ComponentId, script: Mapping[int, JsonValue]) -> None:
        self._receptor_id = receptor_id
        self._script = {int(k): v for k, v in script.items()}
        self._calls = 0

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self) -> tuple[ExternalEvent, ...]:
        self._calls += 1
        if self._calls in self._script:
            return (ExternalEvent(self._receptor_id, self._script[self._calls]),)
        return ()
