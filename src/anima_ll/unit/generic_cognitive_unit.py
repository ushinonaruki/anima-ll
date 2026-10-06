from anima_ll.domain.model.claim import ComputeRequest
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
        # 出力の部品は毎 Pulse 進める（発火していない Pulse にも、持ち越している要求などを扱えるように）
        return self._output.advance(view, context, None if firing is None else firing.strength)

    def handle_kernel_result(
        self, task: KernelTask, result: KernelResult, context: PulseContext
    ) -> UnitStepResult:
        return self._output.on_kernel_result(task, result)

    def handle_compute_outcome(
        self, request: ComputeRequest, outcome: str, context: PulseContext
    ) -> None:
        self._output.on_compute_outcome(request, outcome)

    def export_state(self) -> JsonValue:
        return {
            "activity": self._state.activity,
            "refractory_remaining": self._state.refractory_remaining,
            "adaptation": self._state.adaptation,
            "fire_count": self._state.fire_count,
            "dynamics": self._dynamics.describe(),
            "output_state": self._output.export_state(),
        }

    def import_state(self, state: JsonValue) -> None:
        self._state = ActivityState(
            activity=float(state["activity"]),
            refractory_remaining=int(state["refractory_remaining"]),
            adaptation=float(state.get("adaptation", 0.0)),  # L1 までのスナップショットには無い
            fire_count=int(state.get("fire_count", 0)),
        )
        self._output.import_state(state.get("output_state") or {})  # L2-1 までのスナップショットには無い
