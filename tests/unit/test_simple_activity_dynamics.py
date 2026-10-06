import math

from anima_ll.unit.dynamics.activity_dynamics import ActivityState
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics


def dynamics(drive: float = 0.0) -> SimpleActivityDynamics:
    return SimpleActivityDynamics(
        decay_per_second=0.5, threshold=1.0, refractory_pulses=2, intrinsic_drive_per_second=drive
    )


def test_decays_without_input() -> None:
    state, firing = dynamics().advance(ActivityState(0.8), stimulus=0.0, delta_time=1.0)
    assert firing is None
    assert state.activity == 0.4


def test_fires_above_threshold_then_is_refractory() -> None:
    d = dynamics()
    state, firing = d.advance(ActivityState(0.0), stimulus=1.5, delta_time=1.0)
    assert firing is not None and state.activity == 0.0 and state.refractory_remaining == 2
    state, firing = d.advance(state, stimulus=5.0, delta_time=1.0)
    assert firing is None  # 不応期は強い入力があっても発火しない
    state, firing = d.advance(state, stimulus=0.0, delta_time=1.0)
    assert firing is None
    state, firing = d.advance(state, stimulus=0.0, delta_time=1.0)
    assert firing is not None  # 不応期に溜まった活動で発火する


def test_intrinsic_drive_fires_without_any_input() -> None:
    d = dynamics(drive=0.6)  # 平衡値 0.6 / (1 - 0.5) = 1.2 > 閾値 1.0
    state, fired = ActivityState(0.0), False
    for _ in range(10):
        state, firing = d.advance(state, stimulus=0.0, delta_time=1.0)
        fired = fired or firing is not None
    assert fired


def test_intrinsic_drive_below_threshold_never_fires() -> None:
    d = dynamics(drive=0.4)  # 平衡値 0.8 < 閾値 1.0
    state = ActivityState(0.0)
    for _ in range(50):
        state, firing = d.advance(state, stimulus=0.0, delta_time=1.0)
        assert firing is None


# ---- 発火履歴への順応（L2-1） -------------------------------------------------

def adaptive(alpha: float, tau: float = 10.0, drive: float = 0.0) -> SimpleActivityDynamics:
    return SimpleActivityDynamics(
        decay_per_second=0.5, threshold=1.0, refractory_pulses=0, intrinsic_drive_per_second=drive,
        adaptation_increment=alpha, adaptation_tau_seconds=tau,
    )


def test_firing_raises_adaptation_and_counts() -> None:
    state, firing = adaptive(0.3).advance(ActivityState(), stimulus=1.2, delta_time=1.0)
    assert firing is not None
    assert state.adaptation == 0.3 and state.fire_count == 1


def test_adaptation_raises_effective_threshold() -> None:
    d = adaptive(0.3, tau=1e9)  # ほぼ戻らない
    state, _ = d.advance(ActivityState(), stimulus=1.2, delta_time=1.0)
    state, firing = d.advance(state, stimulus=1.2, delta_time=1.0)
    assert firing is None  # 1.2 < 1.0 + 0.3
    state, firing = d.advance(ActivityState(adaptation=state.adaptation), stimulus=1.4, delta_time=1.0)
    assert firing is not None  # 1.4 ≥ 1.3


def test_adaptation_recovers_over_time_even_while_refractory() -> None:
    d = SimpleActivityDynamics(
        decay_per_second=0.5, threshold=1.0, refractory_pulses=5, intrinsic_drive_per_second=0.0,
        adaptation_increment=1.0, adaptation_tau_seconds=10.0,
    )
    state, _ = d.advance(ActivityState(), stimulus=2.0, delta_time=1.0)
    for _ in range(3):
        state, _ = d.advance(state, stimulus=0.0, delta_time=1.0)
    assert state.refractory_remaining == 2
    assert abs(state.adaptation - math.exp(-3 / 10)) < 1e-12


def test_zero_alpha_is_identical_to_no_adaptation() -> None:
    plain, zero = dynamics(drive=0.6), SimpleActivityDynamics(
        decay_per_second=0.5, threshold=1.0, refractory_pulses=2, intrinsic_drive_per_second=0.6,
        adaptation_increment=0.0, adaptation_tau_seconds=300.0,
    )
    a = b = ActivityState()
    for step in range(50):
        stim = 0.7 if step % 7 == 0 else 0.0
        a, fa = plain.advance(a, stim, 1.0)
        b, fb = zero.advance(b, stim, 1.0)
        assert a == b and (fa is None) == (fb is None)


def test_adaptation_slows_spontaneous_firing() -> None:
    def count(alpha: float) -> int:
        d = SimpleActivityDynamics(
            decay_per_second=0.85, threshold=0.5, refractory_pulses=3, intrinsic_drive_per_second=0.08,
            adaptation_increment=alpha, adaptation_tau_seconds=300.0,
        )
        state = ActivityState()
        for _ in range(3600):
            state, _ = d.advance(state, 0.0, 1.0)
        return state.fire_count
    assert count(0.01) < count(0.0) / 2
