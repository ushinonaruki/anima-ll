from anima_ll.domain.model.brain_state import BrainStateSnapshot
from anima_ll.domain.model.identifiers import UnitId
from anima_ll.domain.model.receptive_view import ReceptiveView


class ReceptiveViewBuilder:
    """スナップショットから、Unit ごとの View を切り出す。

    Projection で届いた Delta と駆動だけを入れる。内容で絞り込まない。
    """

    def build(self, unit_id: UnitId, snapshot: BrainStateSnapshot) -> ReceptiveView:
        return ReceptiveView(
            unit_id=unit_id,
            snapshot_id=snapshot.snapshot_id,
            pulse=snapshot.pulse,
            deltas=snapshot.state.addressed_to(unit_id),
            drives=snapshot.state.drives_to(unit_id),
        )
