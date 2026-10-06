from collections.abc import Iterable

from anima_ll.domain.model.identifiers import UnitId
from anima_ll.domain.port.cognitive_unit import CognitiveUnit


class UnitRegistry:
    """Unit を保持する。Unit の役割は知らない。"""

    def __init__(self, units: Iterable[CognitiveUnit]) -> None:
        self._units: dict[UnitId, CognitiveUnit] = {}
        for unit in units:
            if unit.unit_id in self._units:
                raise ValueError(f"Unit ID が重複しています: {unit.unit_id}")
            self._units[unit.unit_id] = unit

    def all(self) -> tuple[CognitiveUnit, ...]:
        """ID 順。呼び出し順を決定的にするため。"""
        return tuple(self._units[unit_id] for unit_id in sorted(self._units))

    def get(self, unit_id: UnitId) -> CognitiveUnit:
        return self._units[unit_id]
