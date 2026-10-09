from dataclasses import dataclass

from anima_ll.domain.model.activity import Drive
from anima_ll.domain.model.delta import StateDelta
from anima_ll.domain.model.identifiers import DeltaId, PulseNumber, SnapshotId, UnitId


@dataclass(frozen=True)
class ReceptiveView:
    """ある Unit が、ある Pulse に読んでよい範囲。Projection で届いた Delta だけを含む。"""

    unit_id: UnitId
    snapshot_id: SnapshotId
    pulse: PulseNumber
    deltas: tuple[StateDelta, ...]
    """この Unit 宛てで、まだ期限の切れていない Delta（中身。駆動には使わない）。"""
    drives: tuple[Drive, ...] = ()
    """前の Pulse に成立し、この Pulse に届いた駆動。Unit を外から動かすのはこれだけ。"""

    def new_deltas(self) -> tuple[StateDelta, ...]:
        """前の Pulse に確定し、この Pulse で初めて見える Delta（Pulse barrier）。"""
        return tuple(d for d in self.deltas if d.created_pulse == self.pulse - 1)

    def delta_ids(self) -> frozenset[DeltaId]:
        return frozenset(d.delta_id for d in self.deltas)
