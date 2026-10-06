from anima_ll.domain.model.claim import ComputeClaim
from anima_ll.runtime.resource_scheduler import ClaimEntry, ResourceScheduler


def entry(unit_id: str, strength: float, rc: str = "llm_pool") -> ClaimEntry:
    return ClaimEntry(unit_id, ComputeClaim(rc, strength))


def test_accepts_strongest_up_to_capacity() -> None:
    decision = ResourceScheduler().select(
        [entry("u1", 0.4), entry("u2", 0.9), entry("u3", 0.6)], {"llm_pool": 2}
    )
    assert [e.unit_id for e in decision.accepted] == ["u2", "u3"]
    assert [e.unit_id for e in decision.rejected] == ["u1"]


def test_resource_classes_are_independent() -> None:
    decision = ResourceScheduler().select(
        [entry("u1", 0.9, "a"), entry("u2", 0.1, "b")], {"a": 1, "b": 1}
    )
    assert {e.unit_id for e in decision.accepted} == {"u1", "u2"}


def test_no_capacity_rejects_all() -> None:
    decision = ResourceScheduler().select([entry("u1", 1.0)], {"llm_pool": 0})
    assert decision.accepted == ()


def test_ties_rotate_across_pulses_without_permanent_bias() -> None:
    scheduler = ResourceScheduler()
    winners = [
        scheduler.select([entry("u1", 1.0), entry("u2", 1.0)], {"llm_pool": 1}, pulse).accepted[0].unit_id
        for pulse in range(10)
    ]
    assert winners.count("u1") == winners.count("u2") == 5


def test_tie_at_capacity_boundary_is_reported() -> None:
    decision = ResourceScheduler().select([entry("u1", 1.0), entry("u2", 1.0)], {"llm_pool": 1})
    assert decision.tie_broken == ("llm_pool",)
