"""KernelRequestOutput の計算の要求の持ち越し（L2-2）。"""

import math

from anima_ll.domain.model.claim import ComputeOutcome, RequestOrigin
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.unit.output.kernel_request_output import KernelRequestOutput

VIEW = ReceptiveView(unit_id="u2", snapshot_id="s1", pulse=1, deltas=())
CTX = PulseContext(pulse=1, now=1.0, delta_time=1.0)


def output(tau: float = 5.0, floor: float = 0.1) -> KernelRequestOutput:
    return KernelRequestOutput("llm_pool", None, pending_tau_seconds=tau, pending_floor=floor)


def only_request(step):
    assert len(step.compute_requests) == 1
    return step.compute_requests[0]


def test_rejected_request_is_carried_over_and_decays() -> None:
    out = output()
    req = only_request(out.advance(VIEW, CTX, 0.8))
    assert req.origin == RequestOrigin.FIRING
    out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
    assert out.pending == 0.8
    retry = only_request(out.advance(VIEW, CTX, None))  # 発火していない Pulse でも再提示する
    assert retry.origin == RequestOrigin.PENDING
    assert abs(retry.claim.strength - 0.8 * math.exp(-1 / 5)) < 1e-12


def test_started_or_busy_clears_pending() -> None:
    for outcome in (ComputeOutcome.STARTED, ComputeOutcome.DROPPED_BUSY):
        out = output()
        req = only_request(out.advance(VIEW, CTX, 0.8))
        out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
        retry = only_request(out.advance(VIEW, CTX, None))
        out.on_compute_outcome(retry, outcome)
        assert out.pending == 0.0
        assert out.advance(VIEW, CTX, None).compute_requests == ()


def test_gives_up_below_floor() -> None:
    out = output(tau=1.0, floor=0.3)
    req = only_request(out.advance(VIEW, CTX, 0.5))
    out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
    # 0.5 × e^-1 ≒ 0.18 < 0.3
    assert out.advance(VIEW, CTX, None).compute_requests == ()
    assert out.pending == 0.0


def test_fresh_firing_coalesces_into_one_request() -> None:
    out = output()
    req = only_request(out.advance(VIEW, CTX, 0.9))
    out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
    merged = only_request(out.advance(VIEW, CTX, 0.3))  # 1 Pulse に 1 本だけ
    assert merged.origin == RequestOrigin.MERGED
    assert abs(merged.claim.strength - 0.9 * math.exp(-1 / 5)) < 1e-12  # 強い方


def test_zero_tau_never_carries_over() -> None:
    out = output(tau=0.0)
    req = only_request(out.advance(VIEW, CTX, 0.8))
    out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
    assert out.pending == 0.0
    assert out.advance(VIEW, CTX, None).compute_requests == ()


def test_pending_survives_snapshot() -> None:
    out = output()
    req = only_request(out.advance(VIEW, CTX, 0.8))
    out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
    restored = output()
    restored.import_state(out.export_state())
    assert restored.pending == 0.8
    fresh = output()
    fresh.import_state({})  # L2-1 までのスナップショット
    assert fresh.pending == 0.0


def test_fresh_firing_after_giving_up_is_a_new_request_not_a_merge() -> None:
    """持ち越しが p_min 未満に弱まって諦めた Pulse に新しく発火したら、統合ではなく新しい要求。"""
    out = output(tau=1.0, floor=0.3)
    req = only_request(out.advance(VIEW, CTX, 0.5))
    out.on_compute_outcome(req, ComputeOutcome.REJECTED_CAPACITY)
    fresh = only_request(out.advance(VIEW, CTX, 0.6))  # 0.5 × e^-1 ≒ 0.18 < 0.3 で諦めた直後の発火
    assert fresh.origin == RequestOrigin.FIRING
    assert fresh.claim.strength == 0.6
