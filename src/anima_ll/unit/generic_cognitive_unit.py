from anima_ll.domain.model.identifiers import JsonValue, UnitId
from anima_ll.domain.model.kernel_task import KernelResult, KernelTask
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.unit_step import UnitStepResult
from anima_ll.unit.dynamics.activity_dynamics import ActivityDynamics, ActivityState
from anima_ll.unit.output.unit_output import UnitOutput


class GenericCognitiveUnit:
    """唯一の Unit 実装。役割を持たず、違いは配線と部品とパラメータだけ。

    刺激は「新しく届いた Delta の数 × 結合の重み」。中身は読まない（意味を扱うのは Kernel だけ）。
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
        stimulus = sum(d.projection_weight for d in view.new_deltas())
        self._state, firing = self._dynamics.advance(self._state, stimulus, context.delta_time)
        if firing is None:
            return UnitStepResult.empty()
        return self._output.on_fire(view, firing.strength)

    def handle_kernel_result(
        self, task: KernelTask, result: KernelResult, context: PulseContext
    ) -> UnitStepResult:
        return self._output.on_kernel_result(task, result)

    def export_state(self) -> JsonValue:
        return {
            "activity": self._state.activity,
            "refractory_remaining": self._state.refractory_remaining,
            "dynamics": self._dynamics.describe(),
        }

    def import_state(self, state: JsonValue) -> None:
        self._state = ActivityState(
            activity=float(state["activity"]),
            refractory_remaining=int(state["refractory_remaining"]),
        )
