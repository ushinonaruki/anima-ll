"""ComputeIntent：Unit が出した計算の要求を、Runtime が受け取った時点で凍結した不変の仕事。

すでに成立した認知の出来事として扱う。Worker の数や Kernel の速さを理由に、
存在・生成時刻・入力内容を遡って変えない（計算資源境界 仕様 v0.3.1 §2.2・§3.1）。

意図の一生（受理・開始・完了など）の状態は Runtime の中だけにあり、Unit からは見えない。
"""

from dataclasses import dataclass

from anima_ll.domain.model.compute_request import KernelTaskDraft
from anima_ll.domain.model.identifiers import PulseNumber, ResourceClass, SnapshotId, UnitId


@dataclass(frozen=True)
class ComputeIntent:
    intent_id: str
    intent_seq: int
    """Runtime が受け取った順に付ける単調増加の番号。実行の順番はこれだけで決まる。"""
    unit_id: UnitId
    created_pulse: PulseNumber
    resource_class: ResourceClass
    origin_snapshot_id: SnapshotId
    draft: KernelTaskDraft

    @property
    def input_delta_ids(self):
        return self.draft.input_delta_ids


class IntentStatus:
    """意図の一生のログ上の状態。"""

    CREATED = "intent_created"
    ADMITTED = "intent_admitted"
    REJECTED_OVERFLOW = "intent_rejected_overflow"
    STARTED = "intent_started"
    COMPLETED = "intent_completed"
    KERNEL_ERROR = "intent_kernel_error"
