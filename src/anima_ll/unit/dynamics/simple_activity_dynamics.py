from dataclasses import dataclass

from anima_ll.domain.model.identifiers import JsonValue
from anima_ll.unit.dynamics.activity_dynamics import ActivityState, Firing


@dataclass(frozen=True)
class SimpleActivityDynamics:
    """減衰・内在的駆動・閾値・不応期だけの最小の力学。

    activity ← activity × decay^Δt ＋ 刺激 ＋ intrinsic_drive × Δt
    閾値を超えたら発火し、activity を 0 に戻して一定 Pulse の間は発火しない。

    intrinsic_drive は「暇なら喋る」という心理ルールではなく、
    入力がなくても神経活動がゆっくり動き続けるという内容非依存の基礎力学。
    """

    decay_per_second: float
    threshold: float
    refractory_pulses: int
    intrinsic_drive_per_second: float

    def advance(
        self, state: ActivityState, stimulus: float, delta_time: float
    ) -> tuple[ActivityState, Firing | None]:
        activity = (
            state.activity * (self.decay_per_second ** delta_time)
            + stimulus
            + self.intrinsic_drive_per_second * delta_time
        )
        if state.refractory_remaining > 0:
            return ActivityState(activity, state.refractory_remaining - 1), None
        if activity >= self.threshold:
            strength = min(1.0, activity)
            return ActivityState(0.0, self.refractory_pulses), Firing(strength)
        return ActivityState(activity, 0), None

    def describe(self) -> dict[str, JsonValue]:
        return {
            "kind": "simple_activity",
            "decay_per_second": self.decay_per_second,
            "threshold": self.threshold,
            "refractory_pulses": self.refractory_pulses,
            "intrinsic_drive_per_second": self.intrinsic_drive_per_second,
        }
