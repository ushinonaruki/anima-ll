from dataclasses import dataclass

from anima_ll.domain.model.identifiers import DeltaId, JsonValue, ResourceClass


@dataclass(frozen=True)
class KernelTaskDraft:
    """Kernel に渡す入力の下書き。計算を要求した Pulse の View から作り、あとで作り直さない。"""

    inputs: JsonValue
    input_delta_ids: tuple[DeltaId, ...]
    io_template: str | None = None


@dataclass(frozen=True)
class ComputeRequest:
    """Unit が「この資源で、この材料を使って計算したい」と出すもの。

    優先度や強さは持たない。実行の順番は実行基盤の工学的な方針が決め、
    Unit の状態（activity など）には依らない（計算資源境界 仕様 v0.3.1 §4・§7）。
    """

    resource_class: ResourceClass
    draft: KernelTaskDraft
