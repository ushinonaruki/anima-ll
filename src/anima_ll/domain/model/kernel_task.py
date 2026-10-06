from dataclasses import dataclass

from anima_ll.domain.model.identifiers import (
    DeltaId,
    JsonValue,
    PulseNumber,
    ResourceClass,
    SnapshotId,
    TaskId,
    UnitId,
)


@dataclass(frozen=True)
class KernelTask:
    """Kernel に渡す計算の依頼。Kernel は依頼元の Unit について何も知らない。"""

    task_id: TaskId
    unit_id: UnitId
    resource_class: ResourceClass
    snapshot_id: SnapshotId
    input_delta_ids: tuple[DeltaId, ...]
    started_pulse: PulseNumber
    inputs: JsonValue
    io_template: str | None = None


class KernelStatus:
    OK = "ok"
    ERROR = "error"


@dataclass(frozen=True)
class KernelResult:
    task_id: TaskId
    status: str
    output: JsonValue = None
    error: str | None = None
