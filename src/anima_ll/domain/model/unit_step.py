from dataclasses import dataclass

from anima_ll.domain.model.activity import ActivityEvent
from anima_ll.domain.model.compute_request import ComputeRequest
from anima_ll.domain.model.delta import ProposedDelta


@dataclass(frozen=True)
class UnitStepResult:
    """Unit が 1 回の呼び出しで返すもの。L2 で調節信号（modulations）を追加する。"""

    proposed_deltas: tuple[ProposedDelta, ...] = ()
    compute_requests: tuple[ComputeRequest, ...] = ()
    activity: ActivityEvent | None = None
    """この呼び出しで成立した発火。tick（力学を進める呼び出し）でだけ Unit が作る。
    出力の部品・Kernel の結果からは作られない（活動の伝達 仕様 C4）。"""

    @staticmethod
    def empty() -> "UnitStepResult":
        return UnitStepResult()
