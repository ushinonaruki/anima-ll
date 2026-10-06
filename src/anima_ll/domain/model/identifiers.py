"""AnIma-ll 内で使う識別子と値の型。

意味を持たない文字列・数値の別名だけを置く。
"""

from typing import Any, TypeAlias

UnitId: TypeAlias = str
"""Cognitive Unit の識別子（例: "u1"）。役割を表さない。"""

ComponentId: TypeAlias = str
"""Unit・Receptor・Effector を区別なく指す識別子（例: "u1", "receptor.console"）。"""

DeltaId: TypeAlias = str
TaskId: TypeAlias = str
SnapshotId: TypeAlias = str
ResourceClass: TypeAlias = str
"""Worker を取り合う計算資源の種類（例: "llm_pool"）。"""

PulseNumber: TypeAlias = int

JsonValue: TypeAlias = Any
"""JSON で表現できる値（dict / list / str / int / float / bool / None）。"""

RECEPTOR_PREFIX = "receptor."
EFFECTOR_PREFIX = "effector."
DEFAULT_PORT = "main"


def is_effector(component_id: ComponentId) -> bool:
    return component_id.startswith(EFFECTOR_PREFIX)


def is_receptor(component_id: ComponentId) -> bool:
    return component_id.startswith(RECEPTOR_PREFIX)
