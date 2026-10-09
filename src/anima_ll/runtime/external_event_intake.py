from collections.abc import Sequence

from anima_ll.domain.model.sensory_event import SensoryEvent
from anima_ll.domain.port.receptor import Receptor


class ExternalEventIntake:
    """感覚器から、成立した感覚の出来事を集める。入力の意味は読まない。

    感覚の出来事を作るのは Receptor で、ここではない。中身から駆動を作ったり、
    駆動から中身を作ったりしない（活動の伝達 仕様 §4.1）。
    """

    def __init__(self, receptors: Sequence[Receptor]) -> None:
        self._receptors = tuple(sorted(receptors, key=lambda r: r.receptor_id))

    def collect(self) -> tuple[SensoryEvent, ...]:
        collected: list[SensoryEvent] = []
        for receptor in self._receptors:
            collected.extend(receptor.drain())
        return tuple(collected)
