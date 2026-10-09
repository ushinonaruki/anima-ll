from anima_ll.domain.model.delta import ProposedDelta
from anima_ll.domain.model.manifest import ProjectionSpec
from anima_ll.runtime.delta_canonicalizer import DeltaCanonicalizer
from anima_ll.runtime.identifier_issuer import IdentifierIssuer


def test_runtime_assigns_provenance_and_filters_citations() -> None:
    canonicalizer = DeltaCanonicalizer(IdentifierIssuer(), ttl_pulses=5)
    outcome = canonicalizer.canonicalize(
        source_id="u1",
        proposal=ProposedDelta(kind="content", payload="x", cited_delta_ids=("seen", "unseen")),
        projections=[ProjectionSpec("u1", "main", "u2", 0.5), ProjectionSpec("u1", "main", "u3", 1.0)],
        visible_delta_ids=frozenset({"seen"}),
        origin_snapshot_id="s1",
        origin_task_id=None,
        pulse=7,
    )
    assert [d.target_id for d in outcome.deltas] == ["u2", "u3"]
    assert all(d.source_id == "u1" and d.created_pulse == 7 for d in outcome.deltas)
    assert all(d.parent_delta_ids == ("seen",) for d in outcome.deltas)
    assert outcome.rejected_citations == ("unseen",)
    assert outcome.deltas[0].expires_after_pulse == 12
    assert len({d.delta_id for d in outcome.deltas}) == 2
