from anima_ll.domain.model.compute_request import KernelTaskDraft
from anima_ll.runtime.compute_intent import ComputeIntent
from anima_ll.runtime.execution_queue import ExecutionQueue


def intent(seq: int, unit: str, rc: str = "llm_pool") -> ComputeIntent:
    return ComputeIntent(f"i{seq}", seq, unit, seq, rc, "s1", KernelTaskDraft({}, ()))


def test_fifo_by_intent_seq() -> None:
    q = ExecutionQueue({"llm_pool": None})
    for i in (intent(1, "u1"), intent(2, "u2"), intent(3, "u3")):
        assert q.admit(i)
    assert [i.intent_seq for i in q.take_dispatchable({"llm_pool": 2}, ())] == [1, 2]
    assert [i.intent_seq for i in q.waiting()] == [3]


def test_never_drops_when_no_worker_is_free() -> None:
    q = ExecutionQueue({"llm_pool": None})
    q.admit(intent(1, "u1"))
    assert q.take_dispatchable({"llm_pool": 0}, ()) == []
    assert [i.intent_seq for i in q.waiting()] == [1]


def test_busy_unit_is_skipped_but_keeps_its_place() -> None:
    q = ExecutionQueue({"llm_pool": None})
    for i in (intent(1, "u1"), intent(2, "u2"), intent(3, "u1")):
        q.admit(i)
    taken = q.take_dispatchable({"llm_pool": 4}, {"u1"})
    assert [i.intent_seq for i in taken] == [2]
    assert [i.intent_seq for i in q.waiting()] == [1, 3]


def test_same_unit_is_serialized_within_one_dispatch() -> None:
    q = ExecutionQueue({"llm_pool": None})
    for i in (intent(1, "u1"), intent(2, "u1"), intent(3, "u2")):
        q.admit(i)
    assert [i.intent_seq for i in q.take_dispatchable({"llm_pool": 4}, ())] == [1, 3]


def test_tail_drop_at_capacity() -> None:
    q = ExecutionQueue({"llm_pool": 2})
    assert q.admit(intent(1, "u1")) and q.admit(intent(2, "u2"))
    assert not q.admit(intent(3, "u3"))
    assert [i.intent_seq for i in q.waiting()] == [1, 2]  # 受理済みのものは捨てない


def test_capacity_is_per_resource_class() -> None:
    q = ExecutionQueue({"llm_pool": 1, "vision_pool": 1})
    assert q.admit(intent(1, "u1", "llm_pool"))
    assert q.admit(intent(2, "u2", "vision_pool"))
    assert not q.admit(intent(3, "u3", "llm_pool"))
