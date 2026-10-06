from dataclasses import dataclass
from typing import Protocol

from anima_ll.domain.model.identifiers import JsonValue


@dataclass(frozen=True)
class ActivityState:
    """Unit の私的な内部状態。Shared Brain State には出さない。"""

    activity: float = 0.0
    refractory_remaining: int = 0


@dataclass(frozen=True)
class Firing:
    strength: float
    """発火の強さ（0〜1）。claim の強さとして使われる。"""


class ActivityDynamics(Protocol):
    """内容に依存しない基礎力学。何に反応するかの意味は持たない。"""

    def advance(
        self, state: ActivityState, stimulus: float, delta_time: float
    ) -> tuple[ActivityState, Firing | None]: ...

    def describe(self) -> dict[str, JsonValue]: ...
