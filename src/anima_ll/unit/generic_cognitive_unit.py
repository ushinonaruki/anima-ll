from dataclasses import replace

from anima_ll.domain.model.activity import ActivityEvent
from anima_ll.domain.model.identifiers import JsonValue, UnitId
from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_ll.unit.dynamics.activity_dynamics import ActivityDynamics, ActivityState
from anima_ll.unit.output.unit_output import UnitOutput


class GenericCognitiveUnit:
    """唯一の Unit 実装。役割を持たず、違いは配線と部品とパラメータだけ。

    刺激は「届いた駆動の重みの合計」（活動の伝達 仕様 §3.3）。Delta（中身）は刺激に使わない。
    発火したら、出力の部品が何を出すかとは独立に ActivityEvent を作る（B2・C2）。
    """

    def __init__(
        self,
        unit_id: UnitId,
        dynamics: ActivityDynamics,
        output: UnitOutput,
        initial_state: ActivityState | None = None,
    ) -> None:
        self._unit_id = unit_id
        self._dynamics = dynamics
        self._output = output
        self._state = initial_state or ActivityState()

    @property
    def unit_id(self) -> UnitId:
        return self._unit_id

    @property
    def state(self) -> ActivityState:
        return self._state

    def tick(self, view: ReceptiveView, context: PulseContext) -> UnitStepResult:
        stimulus = sum(d.weight for d in view.drives)
        self._state, firing = self._dynamics.advance(self._state, stimulus, context.delta_time)
        if firing is None:
            return UnitStepResult.empty()
        step = self._output.on_fire(view, firing.strength)
        return replace(step, activity=ActivityEvent(self._unit_id, context.pulse))

    def handle_kernel_result(
        self, task: KernelTask, result: KernelResult, context: PulseContext
    ) -> UnitStepResult:
        return self._output.on_kernel_result(task, result)

    def export_state(self) -> JsonValue:
        return {
            "activity": self._state.activity,
            "refractory_remaining": self._state.refractory_remaining,
            "adaptation": self._state.adaptation,
            "fire_count": self._state.fire_count,
            "dynamics": self._dynamics.describe(),
        }

    def import_state(self, state: JsonValue) -> None:
        self._state = ActivityState(
            activity=float(state["activity"]),
            refractory_remaining=int(state["refractory_remaining"]),
            adaptation=float(state.get("adaptation", 0.0)),  # L1 までのスナップショットには無い
            fire_count=int(state.get("fire_count", 0)),
        )
