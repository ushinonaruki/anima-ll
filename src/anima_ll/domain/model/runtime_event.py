from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import JsonValue, PulseNumber


class RuntimeEventType:
    RUN = "run"            # 起動時に 1 回：どの設計図・環境・個体で動いたか
    PULSE = "pulse"
    VIEW = "view"
    CLAIM = "claim"
    SCHEDULE = "schedule"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    DELTA = "delta"
    EFFECT = "effect"
    VIOLATION = "violation"
    UNROUTED = "unrouted"
    UNIT_STATE = "unit_state"  # 観察用：Unit の私的な状態の標本（間隔は設定で決める。既定は記録しない）


@dataclass(frozen=True)
class RuntimeEvent:
    """来歴ログの 1 行。あとから因果を辿るために、Runtime の出来事をすべて記録する。"""

    type: str
    pulse: PulseNumber
    data: dict[str, JsonValue] = field(default_factory=dict)
