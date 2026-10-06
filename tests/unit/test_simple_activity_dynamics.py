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
