from dataclasses import dataclass

from anima_ll.domain.model.identifiers import DeltaId, JsonValue, ResourceClass


@dataclass(frozen=True)
class ComputeClaim:
    """希少な計算資源への要求の強さ。Scheduler が見るのはこれだけ。

    「この Unit がどれほど重要か」ではなく「この資源を今どれだけ要求するか」。
    """

    resource_class: ResourceClass
    strength: float


@dataclass(frozen=True)
class KernelTaskDraft:
    """採択されたら Kernel に渡す入力の下書き。claim を出した Pulse の View から作る。"""

    inputs: JsonValue
    input_delta_ids: tuple[DeltaId, ...]
    io_template: str | None = None


class RequestOrigin:
    """要求がどこから来たか。観察用で、Scheduler には渡さない。"""

    FIRING = "firing"    # 発火から生じた新しい要求（持ち越している要求はなかった）
    PENDING = "pending"  # 競合に負けて持ち越している要求の再提示（発火ではない）
    MERGED = "merged"    # 生きている持ち越しの要求と、この Pulse の新しい発火を 1 本に統合した要求


@dataclass(frozen=True)
class ComputeRequest:
    claim: ComputeClaim
    draft: KernelTaskDraft
    origin: str = RequestOrigin.FIRING


class ComputeOutcome:
    """Unit が出した計算の要求が、その Pulse にどうなったか。中身は含まない。

    Runtime は、資源の使用が許可された要求それぞれに、その Pulse の中で必ず 1 回これを返す。
    許可されていない資源への要求と、1 Pulse 2 件目以降の要求は違反（violation）として記録し、結果は返さない。
    """

    STARTED = "started"                      # 採択され、計算が始まった
    REJECTED_CAPACITY = "rejected_capacity"  # 容量の取り合いに負けた
    DROPPED_BUSY = "dropped_busy"            # 自分の前の計算がまだ実行中だった
