from dataclasses import dataclass, field

from anima_ll.domain.model.activity import Drive
from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import ComponentId, PulseNumber, SnapshotId


@dataclass(frozen=True)
class BrainState:
    """Shared Brain State。確定済みの Delta と、次の Pulse に届く駆動の置き場。意味を持たない。"""

    deltas: tuple[StateDelta, ...] = field(default_factory=tuple)
    drives: tuple[Drive, ...] = field(default_factory=tuple)
    """前の Pulse に成立し、この Pulse に受け手へ届く駆動（1 Pulse だけ存在する）。"""

    def addressed_to(self, target_id: ComponentId) -> tuple[StateDelta, ...]:
        return tuple(d for d in self.deltas if d.target_id == target_id)

    def drives_to(self, target_id: ComponentId) -> tuple[Drive, ...]:
        return tuple(d for d in self.drives if d.target_id == target_id)


@dataclass(frozen=True)
class BrainStateSnapshot:
    """Pulse 冒頭に固定した BrainState。この Pulse の View はすべてここから作る。"""

    snapshot_id: SnapshotId
    pulse: PulseNumber
    state: BrainState
