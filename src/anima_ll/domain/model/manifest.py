"""Neuroarchitecture Manifest のドメイン表現。

Unit に役割（記憶・感情など）を書く欄はない。違いは配線とパラメータだけで表す。
"""

from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import (
    ComponentId,
    JsonValue,
    ResourceClass,
    UnitId,
)


@dataclass(frozen=True)
class ResourceSpec:
    resource_class: ResourceClass
    capacity: int
    kernel: str
    """Kernel 実装を指すキー（例: "fake_delayed", "ollama"）。"""
    params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentSpec:
    """Receptor・Effector の指定。"""

    component_id: ComponentId
    kind: str
    params: dict[str, JsonValue] = field(default_factory=dict)


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


@dataclass(frozen=True)
class NeuroarchitectureManifest:
    version: int
    seed: int
    delta_ttl_pulses: int
    resources: tuple[ResourceSpec, ...]
    receptors: tuple[ComponentSpec, ...]
    effectors: tuple[ComponentSpec, ...]
    units: tuple[UnitSpec, ...]
    projections: tuple[ProjectionSpec, ...]

    def projections_from(self, source_id: ComponentId, port: str) -> tuple[ProjectionSpec, ...]:
        return tuple(
            p for p in self.projections if p.source_id == source_id and p.source_port == port
        )

    def unit(self, unit_id: UnitId) -> UnitSpec:
        for spec in self.units:
            if spec.unit_id == unit_id:
                return spec
        raise KeyError(unit_id)

    def capacities(self) -> dict[ResourceClass, int]:
        return {r.resource_class: r.capacity for r in self.resources}
