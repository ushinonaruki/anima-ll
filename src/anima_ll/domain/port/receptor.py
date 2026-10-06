from typing import Protocol

from anima_ll.domain.model.external_event import ExternalEvent
from anima_ll.domain.model.identifiers import ComponentId


class Receptor(Protocol):
    """感覚器。Runtime が Pulse ごとに入力を取りに来る（pull）。"""

    @property
    def receptor_id(self) -> ComponentId: ...

    def drain(self) -> tuple[ExternalEvent, ...]:
        """前回呼ばれてから届いた入力をすべて返す。"""
        ...
