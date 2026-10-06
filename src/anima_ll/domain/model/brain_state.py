from dataclasses import dataclass, field

from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import ComponentId, PulseNumber, SnapshotId


@dataclass(frozen=True)
class BrainState:
    """Shared Brain State。確定済みの Delta の置き場で、意味を持たない。"""

    deltas: tuple[StateDelta, ...] = field(default_factory=tuple)

    def addressed_to(self, target_id: ComponentId) -> tuple[StateDelta, ...]:
        return tuple(d for d in self.deltas if d.target_id == target_id)


@dataclass(frozen=True)
class BrainStateSnapshot:
    """Pulse 冒頭に固定した BrainState。この Pulse の View はすべてここから作る。"""

    snapshot_id: SnapshotId
    pulse: PulseNumber
    state: BrainState
