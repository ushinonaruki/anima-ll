from collections.abc import Mapping

from anima_ll.domain.model.sensory_event import SensoryEvent
from anima_ll.domain.model.identifiers import ComponentId, JsonValue, PulseNumber


class ScriptedReceptor:
    """決めた回（drain が呼ばれた回数）に、感覚の出来事を出す。L0 とテスト用。

    台本の値が中身（material）になる。値が null なら中身のない感覚の出来事になる。
    """

    def __init__(self, receptor_id: ComponentId, script: Mapping[int, JsonValue]) -> None:
        self._receptor_id = receptor_id
        self._script = {int(k): v for k, v in script.items()}
        self._calls = 0

    @property
    def receptor_id(self) -> ComponentId:
        return self._receptor_id

    def drain(self, pulse: PulseNumber) -> tuple[SensoryEvent, ...]:
        self._calls += 1
        if self._calls in self._script:
            # 台本の回に、その Pulse で成立した感覚の出来事として出す
            return (SensoryEvent(self._receptor_id, pulse, self._script[self._calls]),)
        return ()
