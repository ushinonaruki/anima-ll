from typing import Protocol

from anima_ll.domain.model.sensory_event import SensoryEvent
from anima_ll.domain.model.identifiers import ComponentId


class Receptor(Protocol):
    """感覚器。Runtime が Pulse ごとに入力を取りに来る（pull）。"""

    @property
    def receptor_id(self) -> ComponentId: ...

    def drain(self) -> tuple[SensoryEvent, ...]:
        """前回呼ばれてから成立した感覚の出来事をすべて返す。"""
        ...
