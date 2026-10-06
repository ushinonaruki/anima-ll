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


@dataclass(frozen=True)
class ComputeRequest:
    claim: ComputeClaim
    draft: KernelTaskDraft
