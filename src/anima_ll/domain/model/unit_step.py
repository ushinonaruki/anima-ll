from dataclasses import dataclass

from anima_ll.domain.model.compute_request import ComputeRequest
from anima_ll.domain.model.delta import ProposedDelta


@dataclass(frozen=True)
class UnitStepResult:
    """Unit が 1 回の呼び出しで返すもの。L2 で調節信号（modulations）を追加する。"""

    proposed_deltas: tuple[ProposedDelta, ...] = ()
    compute_requests: tuple[ComputeRequest, ...] = ()

    @staticmethod
    def empty() -> "UnitStepResult":
        return UnitStepResult()
