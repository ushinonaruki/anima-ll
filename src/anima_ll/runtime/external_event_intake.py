from collections.abc import Sequence

from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.identifiers import ComponentId
from anima_ll.domain.port.receptor import Receptor


class ExternalEventIntake:
    """感覚器の入力を、Proposed Delta に変換する。入力の意味は読まない。"""

    def __init__(self, receptors: Sequence[Receptor]) -> None:
        self._receptors = tuple(sorted(receptors, key=lambda r: r.receptor_id))

    def collect(self) -> tuple[tuple[ComponentId, ProposedDelta], ...]:
        collected: list[tuple[ComponentId, ProposedDelta]] = []
        for receptor in self._receptors:
            for event in receptor.drain():
                collected.append(
                    (event.receptor_id, ProposedDelta(kind=DeltaKind.CONTENT, payload=event.payload))
                )
        return tuple(collected)
