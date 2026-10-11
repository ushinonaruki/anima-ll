from collections.abc import Collection, Mapping
from typing import Protocol

from anima_ll.domain.model.identifiers import ComponentId, JsonValue

ConnectionKey = tuple[ComponentId, str, ComponentId]
"""(送り手, 出力路, 受け手)。"""


class ConnectionStatePort(Protocol):
    """個体の Neuroarchitecture の接続の状態（接続の状態 仕様 v0.2）。

    Runtime が使ってよいのはこの 3 つだけ：Pulse の冒頭の重みの写しを受け取る、Pulse の境界で
    その Pulse の発火の出来事を渡す、保存・観察のために書き出す。重みを決めたり書き換えたりはしない。
    """

    def weights(self) -> Mapping[ConnectionKey, float]: ...

    def apply_activity(self, fired: Collection[ComponentId], delta_time: float) -> None: ...

    def export_state(self) -> dict[str, JsonValue]: ...
