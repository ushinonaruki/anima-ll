from dataclasses import dataclass

from anima_ll.domain.model.identifiers import (
    DEFAULT_PORT,
    ComponentId,
    DeltaId,
    JsonValue,
    PulseNumber,
    SnapshotId,
    TaskId,
)


class DeltaKind:
    """Delta の種類。Runtime はこの値で処理を分けない（記録のためだけに使う）。"""

    CONTENT = "content"
    REQUEST = "request"
    RESPONSE = "response"
    INTENT = "intent"


@dataclass(frozen=True)
class ProposedDelta:
    """Unit が提案する出力。来歴や宛先は含まない。

    Unit が作れるのはこれだけで、どこへ届くかは Manifest の Projection が決める。
    """

    kind: str
    payload: JsonValue
    cited_delta_ids: tuple[DeltaId, ...] = ()
    """根拠にした Delta。Runtime が受容野と照合し、実際に見ていたものだけを parents に残す。"""
    output_port: str = DEFAULT_PORT


@dataclass(frozen=True)
class StateDelta:
    """Runtime が確定させた Delta（Canonical Delta）。Unit は直接作れない。"""

    delta_id: DeltaId
    source_id: ComponentId
    output_port: str
    target_id: ComponentId
    created_pulse: PulseNumber
    kind: str
    payload: JsonValue
    parent_delta_ids: tuple[DeltaId, ...]
    origin_snapshot_id: SnapshotId | None
    """どの View を見て生まれたか。Receptor 由来なら None。"""
    origin_task_id: TaskId | None
    """Kernel の結果から生まれたなら、そのタスク。"""
    expires_after_pulse: PulseNumber
