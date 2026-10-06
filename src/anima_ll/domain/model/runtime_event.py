from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import JsonValue, PulseNumber


class RuntimeEventType:
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


@dataclass(frozen=True)
class RuntimeEvent:
    """来歴ログの 1 行。あとから因果を辿るために、Runtime の出来事をすべて記録する。"""

    type: str
    pulse: PulseNumber
    data: dict[str, JsonValue] = field(default_factory=dict)
