from typing import Protocol

from anima_ll.domain.model.sensory_event import SensoryEvent
from anima_ll.domain.model.identifiers import ComponentId, PulseNumber


class Receptor(Protocol):
    """感覚器。Runtime が Pulse ごとに入力を取りに来る（pull）。"""

    @property
    def receptor_id(self) -> ComponentId: ...

    def drain(self, pulse: PulseNumber) -> tuple[SensoryEvent, ...]:
        """前回呼ばれてから成立した感覚の出来事をすべて返す。

        pulse は今の Pulse の番号（Runtime が機械的に渡す）。Receptor は、返す出来事すべてに
        この pulse を成立の Pulse として書き込む（それ以外の Pulse を申告しない。契約）。
        """
        ...
