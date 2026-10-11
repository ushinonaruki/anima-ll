"""Neuroarchitecture Manifest（脳の設計図）のドメイン表現。

Unit に役割（記憶・感情など）を書く欄はない。違いは配線とパラメータだけで表す。
外とつながる口（計算資源・Receptor・Effector）は ID だけを宣言し、
何をつなぐかは実行環境（EnvironmentSpec）が決める。
"""

from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import (
    ComponentId,
    JsonValue,
    ResourceClass,
    UnitId,
)


@dataclass(frozen=True)
class PartSpec:
    """Unit 内部の部品（dynamics・output）の指定。"""

    kind: str
    params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class UnitSpec:
    unit_id: UnitId
    dynamics: PartSpec
    output: PartSpec
    allowed_resource_classes: frozenset[ResourceClass] = frozenset()


@dataclass(frozen=True)
class ProjectionSpec:
    source_id: ComponentId
    source_port: str
    target_id: ComponentId
    weight: float = 1.0
    """初期の重み。個体の今の重みは ConnectionState が持つ（接続の状態 仕様 §3）。"""
    plastic: bool = False
    """可塑性の対象か。設計図で明示する（書かなければ対象外）。"""

    @property
    def connection_id(self) -> str:
        return f"{self.source_id}.{self.source_port}->{self.target_id}"


@dataclass(frozen=True)
class PlasticitySpec:
    """可塑性の規則とパラメータ（可塑性 v1 の設計案 §2・3）。値は解決済みの数で持つ。

    設計図の書き方（threshold・activity_time_constant などの記号）は、読み込みのときに
    defaults.dynamics の値から解決する。コードに既定値は置かない。
    """

    rule: str                 # balanced_pair_window
    trace: str                # additive
    bounds: str               # soft
    trace_tau_seconds: float  # τ_x
    w_min: float
    w_max: float
    amplitude: float          # A（絶対値。amplitude_ratio × w_max）


@dataclass(frozen=True)
class NeuroarchitectureManifest:
    version: int
    delta_ttl_pulses: int
    resource_classes: frozenset[ResourceClass]
    receptor_ids: tuple[ComponentId, ...]
    effector_ids: tuple[ComponentId, ...]
    units: tuple[UnitSpec, ...]
    projections: tuple[ProjectionSpec, ...]
    plasticity: PlasticitySpec | None = None
    """None なら可塑性はない（重みは初期の重みのまま）。"""

    def projections_from(self, source_id: ComponentId, port: str) -> tuple[ProjectionSpec, ...]:
        return tuple(
            p for p in self.projections if p.source_id == source_id and p.source_port == port
        )

    def unit(self, unit_id: UnitId) -> UnitSpec:
        for spec in self.units:
            if spec.unit_id == unit_id:
                return spec
        raise KeyError(unit_id)
