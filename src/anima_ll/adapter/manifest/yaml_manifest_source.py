"""YAML の Manifest を読み、検証してドメインの形に変換する。

Manifest に Unit の役割（role: memory など）を書く欄はない。書かれていたら誤りとして扱う。
"""

from pathlib import Path
from typing import Any

import yaml

from anima_ll.domain.model.identifiers import (
    DEFAULT_PORT,
    EFFECTOR_PREFIX,
    RECEPTOR_PREFIX,
)
from anima_ll.domain.model.manifest import (
    ComponentSpec,
    NeuroarchitectureManifest,
    PartSpec,
    ProjectionSpec,
    ResourceSpec,
    UnitSpec,
)

_FORBIDDEN_UNIT_KEYS = {"role", "function", "name"}


class ManifestError(ValueError):
    pass


class YamlManifestSource:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> NeuroarchitectureManifest:
        with self._path.open(encoding="utf-8") as f:
            return parse_manifest(yaml.safe_load(f))


def parse_manifest(raw: dict[str, Any]) -> NeuroarchitectureManifest:
    resources = tuple(
        ResourceSpec(
            resource_class=name,
            capacity=int(spec["capacity"]),
            kernel=str(spec["kernel"]),
            params={k: v for k, v in spec.items() if k not in ("capacity", "kernel")},
        )
        for name, spec in (raw.get("resources") or {}).items()
    )
    receptors = tuple(_component(c, RECEPTOR_PREFIX) for c in raw.get("receptors") or ())
    effectors = tuple(_component(c, EFFECTOR_PREFIX) for c in raw.get("effectors") or ())

    default_dynamics = dict((raw.get("defaults") or {}).get("dynamics") or {})
    resource_names = {r.resource_class for r in resources}
    units = tuple(_unit(u, default_dynamics, resource_names) for u in raw.get("units") or ())

    component_ids = (
        {u.unit_id for u in units}
        | {c.component_id for c in receptors}
        | {c.component_id for c in effectors}
    )
    if len(component_ids) != len(units) + len(receptors) + len(effectors):
        raise ManifestError("ID が重複しています")

    projections = tuple(_projection(p, units, receptors, effectors) for p in raw.get("projections") or ())

    return NeuroarchitectureManifest(
        version=int(raw.get("version", 0)),
        seed=int(raw.get("seed", 0)),
        delta_ttl_pulses=int(raw.get("delta_ttl_pulses", 10)),
        resources=resources,
        receptors=receptors,
        effectors=effectors,
        units=units,
        projections=projections,
    )


def _component(raw: dict[str, Any], prefix: str) -> ComponentSpec:
    component_id = str(raw["id"])
    if not component_id.startswith(prefix):
        raise ManifestError(f"{component_id} は {prefix} で始まる必要があります")
    return ComponentSpec(
        component_id=component_id,
        kind=str(raw["kind"]),
        params={k: v for k, v in raw.items() if k not in ("id", "kind")},
    )


def _part(raw: str | dict[str, Any] | None, defaults: dict[str, Any] | None = None) -> PartSpec:
    merged: dict[str, Any] = dict(defaults or {})
    if isinstance(raw, str):
        merged["kind"] = raw
    elif isinstance(raw, dict):
        merged.update(raw)
    if "kind" not in merged:
        raise ManifestError(f"部品の kind がありません: {raw}")
    kind = str(merged.pop("kind"))
    return PartSpec(kind=kind, params=merged)


def _unit(raw: dict[str, Any], default_dynamics: dict[str, Any], resources: set[str]) -> UnitSpec:
    unit_id = str(raw["id"])
    forbidden = _FORBIDDEN_UNIT_KEYS & set(raw)
    if forbidden:
        raise ManifestError(
            f"{unit_id}: Unit に役割は書けません（{', '.join(sorted(forbidden))}）。違いは配線とパラメータで表します"
        )
    if unit_id.startswith((RECEPTOR_PREFIX, EFFECTOR_PREFIX)) or "." in unit_id:
        raise ManifestError(f"Unit ID に '.' や予約接頭辞は使えません: {unit_id}")
    output = _part(raw.get("output"))
    allowed: frozenset[str] = frozenset()
    if "resource" in output.params:
        resource = str(output.params["resource"])
        if resource not in resources:
            raise ManifestError(f"{unit_id}: 未定義の resource {resource}")
        allowed = frozenset({resource})
    return UnitSpec(
        unit_id=unit_id,
        dynamics=_part(raw.get("dynamics"), default_dynamics),
        output=output,
        allowed_resource_classes=allowed,
    )


def _projection(
    raw: dict[str, Any],
    units: tuple[UnitSpec, ...],
    receptors: tuple[ComponentSpec, ...],
    effectors: tuple[ComponentSpec, ...],
) -> ProjectionSpec:
    sources = {u.unit_id for u in units} | {r.component_id for r in receptors}
    targets = {u.unit_id for u in units} | {e.component_id for e in effectors}
    source_ref = str(raw["from"])
    if source_ref in sources:
        source_id, port = source_ref, DEFAULT_PORT
    else:
        source_id, _, port = source_ref.rpartition(".")
        if source_id not in sources:
            raise ManifestError(f"projection の from が不明です: {source_ref}")
    target_id = str(raw["to"])
    if target_id not in targets:
        raise ManifestError(f"projection の to が不明です: {target_id}")
    return ProjectionSpec(
        source_id=source_id,
        source_port=port,
        target_id=target_id,
        weight=float(raw.get("weight", 1.0)),
    )
