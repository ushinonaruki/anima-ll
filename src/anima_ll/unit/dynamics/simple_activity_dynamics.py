import math
from dataclasses import dataclass

from anima_ll.domain.model.identifiers import JsonValue
from anima_ll.unit.dynamics.activity_dynamics import ActivityState, Firing


@dataclass(frozen=True)
class SimpleActivityDynamics:
    """減衰・内在的駆動・閾値・不応期・発火履歴への順応だけの最小の力学。

    activity   ← activity × decay^Δt ＋ 刺激 ＋ intrinsic_drive × Δt
    adaptation ← adaptation × exp(−Δt / τ_a)
    activity ≥ threshold ＋ adaptation なら発火し、activity を 0 に戻して一定 Pulse の間は発火しない。
    発火するたびに adaptation が α だけ上がる。

    intrinsic_drive は「暇なら喋る」という心理ルールではなく、
    入力がなくても神経活動がゆっくり動き続けるという内容非依存の基礎力学。

    adaptation は発火頻度順応（spike-frequency adaptation、Biological mechanism）を
    「実効閾値の一時的な上昇」という 1 変数に粗視化したもの（Computational hypothesis）。
    発火の中身ではなく、回数とタイミングだけで決まる。乱数は使わない。
    α = 0 なら順応のない L1 までの力学とまったく同じになる。
    """

    decay_per_second: float
    threshold: float
    refractory_pulses: int
    intrinsic_drive_per_second: float
    adaptation_increment: float = 0.0
    """1 回の発火で adaptation が上がる量（α）。"""
    adaptation_tau_seconds: float = 0.0
    """adaptation が戻る時定数（τ_a、秒）。0 以下なら戻らない（α = 0 のときは無関係）。"""

    def advance(
        self, state: ActivityState, stimulus: float, delta_time: float
    ) -> tuple[ActivityState, Firing | None]:
        activity = (
            state.activity * (self.decay_per_second ** delta_time)
            + stimulus
            + self.intrinsic_drive_per_second * delta_time
        )
        adaptation = state.adaptation
        if adaptation and self.adaptation_tau_seconds > 0:
            adaptation *= math.exp(-delta_time / self.adaptation_tau_seconds)

        if state.refractory_remaining > 0:
            return ActivityState(activity, state.refractory_remaining - 1, adaptation, state.fire_count), None
        if activity >= self.threshold + adaptation:
            strength = min(1.0, activity)  # claim の式は変えない（順応は発火のタイミングを通して間接に効く）
            return (
                ActivityState(
                    0.0,
                    self.refractory_pulses,
                    adaptation + self.adaptation_increment,
                    state.fire_count + 1,
                ),
                Firing(strength),
            )
        return ActivityState(activity, 0, adaptation, state.fire_count), None

    def describe(self) -> dict[str, JsonValue]:
        return {
            "kind": "simple_activity",
            "decay_per_second": self.decay_per_second,
            "threshold": self.threshold,
            "refractory_pulses": self.refractory_pulses,
            "intrinsic_drive_per_second": self.intrinsic_drive_per_second,
            "adaptation_increment": self.adaptation_increment,
            "adaptation_tau_seconds": self.adaptation_tau_seconds,
        }
