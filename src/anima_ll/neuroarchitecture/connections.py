"""接続の状態（ConnectionState）の置き場（接続の状態 仕様 v0.2）。

- 初期の重みと可塑性の規則は設計図から作る。個体の今の重み・痕跡はここが持つ（Life History）
- Runtime はここから「Pulse の冒頭の重み」を受け取って伝達に凍結するだけで、重みを決めない・書き換えない
- 重みが変わるのは、Pulse の境界で、その Pulse の発火の出来事を渡されたときだけ（apply_activity）
"""

from collections.abc import Collection, Mapping
from types import MappingProxyType

from anima_ll.domain.model.identifiers import ComponentId, JsonValue
from anima_ll.domain.model.manifest import NeuroarchitectureManifest
from anima_ll.domain.port.connection_state import ConnectionKey
from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window

_RULES = {"balanced_pair_window": balanced_pair_window}


class ConnectionStore:
    def __init__(self, manifest: NeuroarchitectureManifest) -> None:
        self._spec = manifest.plasticity
        self._keys = {p.connection_id: (p.source_id, p.source_port, p.target_id) for p in manifest.projections}
        self._weights: dict[ConnectionKey, float] = {
            (p.source_id, p.source_port, p.target_id): p.weight for p in manifest.projections
        }
        self._plastic: dict[ConnectionKey, PlasticState] = {
            (p.source_id, p.source_port, p.target_id): PlasticState(weight=p.weight)
            for p in manifest.projections if p.plastic
        }
        self._rule = _RULES[self._spec.rule] if self._spec is not None else None

    def weights(self) -> Mapping[ConnectionKey, float]:
        """今の重みの固定した写し（Pulse の冒頭に Runtime が受け取り、この Pulse の伝達に使う）。"""
        return MappingProxyType(dict(self._weights))

    def apply_activity(self, fired: Collection[ComponentId], delta_time: float) -> None:
        """Pulse の境界で、その Pulse に発火した Unit の集合を受け取り、可塑性の規則で更新する。

        処理の順番に依存しない（各接続は、この Pulse の発火と自分の状態だけで更新される）。
        """
        if self._rule is None:
            return
        fired = frozenset(fired)
        for key, state in self._plastic.items():
            source, _port, target = key
            new = self._rule(state, pre_fired=source in fired, post_fired=target in fired,
                             delta_time=delta_time, spec=self._spec)
            self._plastic[key] = new
            self._weights[key] = new.weight

    def export_state(self) -> dict[str, JsonValue]:
        """保存用（IndividualSnapshot.connections）。可塑性の対象の接続の重みと痕跡。"""
        return {
            cid: {"weight": self._plastic[key].weight, "pre_trace": self._plastic[key].pre_trace,
                  "post_trace": self._plastic[key].post_trace}
            for cid, key in sorted(self._keys.items()) if key in self._plastic
        }

    def import_state(self, state: Mapping[str, JsonValue]) -> None:
        for cid, values in state.items():
            key = self._keys[cid]
            if key not in self._plastic:
                raise ValueError(f"{cid} は可塑性の対象ではありません")
            restored = PlasticState(float(values["weight"]), float(values["pre_trace"]),
                                    float(values["post_trace"]))
            self._plastic[key] = restored
            self._weights[key] = restored.weight
