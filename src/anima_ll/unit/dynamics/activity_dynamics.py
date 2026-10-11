from dataclasses import dataclass
from typing import Protocol

from anima_ll.domain.model.identifiers import JsonValue


@dataclass(frozen=True)
class ActivityState:
    """Unit の私的な内部状態。Shared Brain State には出さない。"""

    activity: float = 0.0
    """現在たまっている駆動。"""
    refractory_remaining: int = 0
    adaptation: float = 0.0
    """最近発火したために一時的に上がっている発火しにくさ（実効閾値への上乗せ）。"""
    fire_count: int = 0
    """これまでの発火回数。観察用（力学には使わない）。"""


@dataclass(frozen=True)
class Firing:
    """発火した、という力学の結果。強さは持たない（使う場所がないため。計算資源境界 §7・接続の状態 仕様 §4.1）。"""


class ActivityDynamics(Protocol):
    """内容に依存しない基礎力学。何に反応するかの意味は持たない。"""

    def advance(
        self, state: ActivityState, stimulus: float, delta_time: float
    ) -> tuple[ActivityState, Firing | None]: ...

    def describe(self) -> dict[str, JsonValue]: ...
