"""実行環境（Environment）のドメイン表現。

脳の設計図が宣言した口（計算資源・Receptor・Effector の ID）に、
どの実装を・どれだけの容量でつなぐかを表す。脳の仮説は含まない。
"""

from dataclasses import dataclass, field

from anima_ll.domain.model.identifiers import ComponentId, JsonValue, ResourceClass
from anima_ll.domain.model.manifest import NeuroarchitectureManifest


@dataclass(frozen=True)
class ResourceSpec:
    resource_class: ResourceClass
    capacity: int
    kernel: str
    """Kernel 実装を指すキー（例: "fake_delayed", "ollama"）。"""
    params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class ComponentSpec:
    """Receptor・Effector の実装の指定。"""

    component_id: ComponentId
    kind: str
    params: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class EnvironmentSpec:
    resources: tuple[ResourceSpec, ...]
    receptors: tuple[ComponentSpec, ...]
    effectors: tuple[ComponentSpec, ...]

    def capacities(self) -> dict[ResourceClass, int]:
        return {r.resource_class: r.capacity for r in self.resources}

    def binding_mismatches(self, manifest: NeuroarchitectureManifest) -> list[str]:
        """設計図が宣言した口と、この環境がつないだ口の食い違いを列挙する。"""
        problems: list[str] = []
        pairs = (
            ("resource", manifest.resource_classes, {r.resource_class for r in self.resources}),
            ("receptor", set(manifest.receptor_ids), {c.component_id for c in self.receptors}),
            ("effector", set(manifest.effector_ids), {c.component_id for c in self.effectors}),
        )
        for label, declared, bound in pairs:
            for missing in sorted(set(declared) - bound):
                problems.append(f"{label} {missing} が実行環境でつながれていません")
            for extra in sorted(bound - set(declared)):
                problems.append(f"{label} {extra} は脳の設計図で宣言されていません")
        return problems
