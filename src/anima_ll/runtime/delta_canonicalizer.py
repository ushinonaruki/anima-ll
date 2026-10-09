from collections.abc import Sequence
from dataclasses import dataclass

from anima_ll.domain.model.delta import ProposedDelta, StateDelta
from anima_ll.domain.model.identifiers import (
    ComponentId,
    DeltaId,
    PulseNumber,
    SnapshotId,
    TaskId,
)
from anima_ll.domain.model.manifest import ProjectionSpec
from anima_ll.runtime.identifier_issuer import IdentifierIssuer


@dataclass(frozen=True)
class CanonicalizationOutcome:
    deltas: tuple[StateDelta, ...]
    rejected_citations: tuple[DeltaId, ...]
    """Unit が根拠に挙げたが、実際には受容野に届いていなかった Delta。"""


class DeltaCanonicalizer:
    """Proposed Delta を確定させる。

    ID・発信元・Pulse・来歴は Unit の申告ではなく、ここで付ける。payload は読まない。
    """

    def __init__(self, issuer: IdentifierIssuer, ttl_pulses: int) -> None:
        self._issuer = issuer
        self._ttl_pulses = ttl_pulses

    def canonicalize(
        self,
        *,
        source_id: ComponentId,
        proposal: ProposedDelta,
        projections: Sequence[ProjectionSpec],
        visible_delta_ids: frozenset[DeltaId],
        origin_snapshot_id: SnapshotId | None,
        origin_task_id: TaskId | None,
        pulse: PulseNumber,
    ) -> CanonicalizationOutcome:
        parents = tuple(d for d in proposal.cited_delta_ids if d in visible_delta_ids)
        rejected = tuple(d for d in proposal.cited_delta_ids if d not in visible_delta_ids)
        deltas = tuple(
            StateDelta(
                delta_id=self._issuer.delta_id(),
                source_id=source_id,
                output_port=proposal.output_port,
                target_id=projection.target_id,
                created_pulse=pulse,
                kind=proposal.kind,
                payload=proposal.payload,
                parent_delta_ids=parents,
                origin_snapshot_id=origin_snapshot_id,
                origin_task_id=origin_task_id,
                expires_after_pulse=pulse + self._ttl_pulses,
            )
            for projection in projections
        )
        return CanonicalizationOutcome(deltas=deltas, rejected_citations=rejected)
