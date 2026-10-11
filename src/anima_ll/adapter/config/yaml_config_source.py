"""YAML の設定 3 種を読み、検証してドメインの形に変換する。

- 脳の設計図（Neuroarchitecture）：Unit・配線・力学。外との口は ID だけ
- 実行環境（Environment）：口にどの実装をつなぐか
- 個体（BirthState）：個体 ID と seed

Manifest に Unit の役割（role: memory など）を書く欄はない。書かれていたら誤りとして扱う。
"""

from pathlib import Path
from typing import Any

import yaml

from anima_ll.domain.model.environment import ComponentSpec, EnvironmentSpec, ResourceSpec
from anima_ll.domain.model.identifiers import (
    DEFAULT_PORT,
    EFFECTOR_PREFIX,
    RECEPTOR_PREFIX,
)
from anima_ll.domain.model.individual import BirthState
import math

from anima_ll.domain.model.manifest import (
    NeuroarchitectureManifest,
    PartSpec,
    PlasticitySpec,
    ProjectionSpec,
    UnitSpec,
)

_FORBIDDEN_UNIT_KEYS = {"role", "function", "name"}
_MOVED_KEYS = {
    "seed": "seed は個体の設定（config/individual/）に書きます",
    "resources": "計算資源の実装は実行環境（config/environment/）に書き、ここでは interfaces.resources に ID だけを書きます",
    "receptors": "Receptor の実装は実行環境（config/environment/）に書き、ここでは interfaces.receptors に ID だけを書きます",
    "effectors": "Effector の実装は実行環境（config/environment/）に書き、ここでは interfaces.effectors に ID だけを書きます",
}


class ConfigError(ValueError):
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: 最上位はマッピングである必要があります")
    return raw


class YamlNeuroarchitectureSource:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> NeuroarchitectureManifest:
        return parse_neuroarchitecture(_read_yaml(self._path))


class YamlEnvironmentSource:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> EnvironmentSpec:
        return parse_environment(_read_yaml(self._path))


class YamlBirthStateSource:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> BirthState:
        return parse_birth_state(_read_yaml(self._path))


# ---- 脳の設計図 -------------------------------------------------------------

def parse_neuroarchitecture(raw: dict[str, Any]) -> NeuroarchitectureManifest:
    for key, hint in _MOVED_KEYS.items():
        if key in raw:
            raise ConfigError(f"脳の設計図に {key} は書けません。{hint}")

    interfaces = raw.get("interfaces") or {}
    resource_classes = frozenset(str(r) for r in interfaces.get("resources") or ())
    receptor_ids = tuple(_interface_id(r, RECEPTOR_PREFIX) for r in interfaces.get("receptors") or ())
    effector_ids = tuple(_interface_id(e, EFFECTOR_PREFIX) for e in interfaces.get("effectors") or ())

    default_dynamics = dict((raw.get("defaults") or {}).get("dynamics") or {})
    units = tuple(_unit(u, default_dynamics, resource_classes) for u in raw.get("units") or ())

    ids = [u.unit_id for u in units] + list(receptor_ids) + list(effector_ids)
    if len(set(ids)) != len(ids):
        raise ConfigError("ID が重複しています")

    sources = {u.unit_id for u in units} | set(receptor_ids)
    targets = {u.unit_id for u in units} | set(effector_ids)
    projections = tuple(_projection(p, sources, targets) for p in raw.get("projections") or ())
    # 接続の ID は (送り手, 出力路, 受け手) の組から決まる（接続の状態 仕様 §3.1）。
    # 同じ組を 2 本書くと、伝達は 2 本分起きるのに接続の状態は 1 本になるので、設計図の時点で拒否する
    seen_connections: set[str] = set()
    for p in projections:
        if p.connection_id in seen_connections:
            raise ConfigError(f"projection {p.connection_id} が重複しています（同じ送り手・出力路・受け手の接続は 1 本だけ）")
        seen_connections.add(p.connection_id)
    plasticity = _plasticity(raw.get("plasticity"), default_dynamics, units)
    if plasticity is None and any(p.plastic for p in projections):
        raise ConfigError("plastic: true の接続がありますが、plasticity（規則）が書かれていません")
    if plasticity is not None:
        for p in projections:
            if p.plastic and not (plasticity.w_min <= p.weight <= plasticity.w_max):
                raise ConfigError(f"{p.connection_id}: 初期の重み {p.weight} が w_min〜w_max の外です")

    return NeuroarchitectureManifest(
        version=int(raw.get("version", 0)),
        delta_ttl_pulses=int(_required_key(raw, "delta_ttl_pulses", "脳の設計図")),
        resource_classes=resource_classes,
        receptor_ids=receptor_ids,
        effector_ids=effector_ids,
        units=units,
        projections=projections,
        plasticity=plasticity,
    )


_PLASTICITY_RULES = {"balanced_pair_window"}
_PLASTICITY_TRACES = {"additive"}
_PLASTICITY_BOUNDS = {"soft"}


def _shared_dynamics_value(key: str, default_dynamics: dict[str, Any], units: tuple[UnitSpec, ...]) -> float:
    """記号（threshold・activity_time_constant）を解決するための、全 Unit で共通の力学の値。"""
    if key not in default_dynamics:
        raise ConfigError(f"plasticity: defaults.dynamics.{key} がないので記号を解決できません")
    value = default_dynamics[key]
    for u in units:
        if u.dynamics.params.get(key) != value:
            raise ConfigError(f"plasticity: {u.unit_id} の {key} が defaults と違うので、記号を一つに解決できません")
    return float(value)


def _plasticity(raw: Any, default_dynamics: dict[str, Any], units: tuple[UnitSpec, ...]) -> PlasticitySpec | None:
    if raw is None:
        return None
    where = "plasticity"
    rule = str(_required_key(raw, "rule", where))
    trace = str(_required_key(raw, "trace", where))
    bounds = str(_required_key(raw, "bounds", where))
    for value, allowed, name in ((rule, _PLASTICITY_RULES, "rule"), (trace, _PLASTICITY_TRACES, "trace"),
                                 (bounds, _PLASTICITY_BOUNDS, "bounds")):
        if value not in allowed:
            raise ConfigError(f"plasticity.{name}: 未知の値 {value}（{', '.join(sorted(allowed))}）")

    tau_raw = _required_key(raw, "trace_tau", where)
    if tau_raw == "activity_time_constant":
        decay = _shared_dynamics_value("decay", default_dynamics, units)
        if not 0.0 < decay < 1.0:
            raise ConfigError(f"plasticity: decay {decay} からは時定数を決められません（0 < decay < 1 が必要）")
        tau = -1.0 / math.log(decay)      # Unit の activity の時定数 τ_m（秒）
    else:
        tau = float(tau_raw)

    w_max_raw = _required_key(raw, "w_max", where)
    w_max = (_shared_dynamics_value("threshold", default_dynamics, units)
             if w_max_raw == "threshold" else float(w_max_raw))
    w_min = float(_required_key(raw, "w_min", where))
    if w_min != 0.0:
        raise ConfigError("plasticity.w_min: 柔らかい上限・下限（soft）は下限 0 でだけ定義している")
    if not (math.isfinite(tau) and tau > 0 and math.isfinite(w_max) and w_max > 0):
        raise ConfigError("plasticity: trace_tau と w_max は有限の正の値が必要です")
    amplitude_ratio = float(_required_key(raw, "amplitude_ratio", where))
    # 負の値は「先に発火した側から後の側への接続を強める」という規則の向きを逆にしてしまう。0 は規則が働かない
    if not (math.isfinite(amplitude_ratio) and amplitude_ratio > 0):
        raise ConfigError(f"plasticity.amplitude_ratio: 有限の正の値が必要です（{amplitude_ratio}）")
    amplitude = amplitude_ratio * w_max
    return PlasticitySpec(rule=rule, trace=trace, bounds=bounds, trace_tau_seconds=tau,
                          w_min=w_min, w_max=w_max, amplitude=amplitude)


def _interface_id(raw: Any, prefix: str) -> str:
    component_id = str(raw)
    if not component_id.startswith(prefix):
        raise ConfigError(f"{component_id} は {prefix} で始まる必要があります")
    return component_id


def _part(raw: str | dict[str, Any] | None, defaults: dict[str, Any] | None = None) -> PartSpec:
    merged: dict[str, Any] = dict(defaults or {})
    if isinstance(raw, str):
        merged["kind"] = raw
    elif isinstance(raw, dict):
        merged.update(raw)
    if "kind" not in merged:
        raise ConfigError(f"部品の kind がありません: {raw}")
    kind = str(merged.pop("kind"))
    return PartSpec(kind=kind, params=merged)


def _unit(raw: dict[str, Any], default_dynamics: dict[str, Any], resources: frozenset[str]) -> UnitSpec:
    unit_id = str(raw["id"])
    forbidden = _FORBIDDEN_UNIT_KEYS & set(raw)
    if forbidden:
        raise ConfigError(
            f"{unit_id}: Unit に役割は書けません（{', '.join(sorted(forbidden))}）。違いは配線とパラメータで表します"
        )
    if unit_id.startswith((RECEPTOR_PREFIX, EFFECTOR_PREFIX)) or "." in unit_id:
        raise ConfigError(f"Unit ID に '.' や予約接頭辞は使えません: {unit_id}")
    output = _part(raw.get("output"))
    allowed: frozenset[str] = frozenset()
    if "resource" in output.params:
        resource = str(output.params["resource"])
        if resource not in resources:
            raise ConfigError(f"{unit_id}: interfaces.resources にない resource {resource}")
        allowed = frozenset({resource})
    return UnitSpec(
        unit_id=unit_id,
        dynamics=_part(raw.get("dynamics"), default_dynamics),
        output=output,
        allowed_resource_classes=allowed,
    )


def _projection(raw: dict[str, Any], sources: set[str], targets: set[str]) -> ProjectionSpec:
    source_ref = str(raw["from"])
    if source_ref in sources:
        source_id, port = source_ref, DEFAULT_PORT
    else:
        source_id, _, port = source_ref.rpartition(".")
        if source_id not in sources:
            raise ConfigError(f"projection の from が不明です: {source_ref}")
    target_id = str(raw["to"])
    if target_id not in targets:
        raise ConfigError(f"projection の to が不明です: {target_id}")
    if target_id.startswith(EFFECTOR_PREFIX):
        # Effector は力学を持たず、結合の重みを使わない。書かなくてよい（書いても効かない）
        weight = float(raw.get("weight", 1.0))
    else:
        weight = float(_required_key(raw, "weight", f"projection {source_ref} → {target_id}"))
    if not math.isfinite(weight):
        raise ConfigError(f"projection {source_ref} → {target_id}: weight は有限の値が必要です（{weight}）")
    plastic = bool(raw.get("plastic", False))   # 書かなければ可塑性の対象外（機構の有無の表し方。§2.4）
    if plastic and (source_id.startswith(RECEPTOR_PREFIX) or target_id.startswith(EFFECTOR_PREFIX)):
        raise ConfigError(f"projection {source_ref} → {target_id}: v1 の可塑性は Unit どうしの接続だけが対象です")
    return ProjectionSpec(source_id=source_id, source_port=port, target_id=target_id, weight=weight,
                          plastic=plastic)


# ---- 実行環境 ---------------------------------------------------------------

def _required_key(raw: dict[str, Any], key: str, where: str) -> Any:
    """認知の力学に効く値は、設計図に明示させる（コードに隠れた既定値を持たせない）。"""
    if key not in raw:
        raise ConfigError(f"{where}: {key} が書かれていません（コードに既定値は持たせません）")
    return raw[key]


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def parse_environment(raw: dict[str, Any]) -> EnvironmentSpec:
    resources = tuple(
        ResourceSpec(
            resource_class=str(name),
            capacity=int(spec["capacity"]),
            kernel=str(spec["kernel"]),
            queue_capacity=_optional_int(spec.get("queue_capacity")),
            params={k: v for k, v in spec.items() if k not in ("capacity", "kernel", "queue_capacity")},
        )
        for name, spec in (raw.get("resources") or {}).items()
    )
    receptors = tuple(
        _component(cid, spec, RECEPTOR_PREFIX) for cid, spec in (raw.get("receptors") or {}).items()
    )
    effectors = tuple(
        _component(cid, spec, EFFECTOR_PREFIX) for cid, spec in (raw.get("effectors") or {}).items()
    )
    runtime = raw.get("runtime") or {}
    interval = runtime.get("pulse_interval_seconds")
    return EnvironmentSpec(resources=resources, receptors=receptors, effectors=effectors,
                           pulse_interval_seconds=None if interval is None else float(interval))


def _component(component_id: Any, raw: dict[str, Any] | str, prefix: str) -> ComponentSpec:
    component_id = _interface_id(component_id, prefix)
    spec = {"kind": raw} if isinstance(raw, str) else dict(raw or {})
    if "kind" not in spec:
        raise ConfigError(f"{component_id}: kind がありません")
    return ComponentSpec(
        component_id=component_id,
        kind=str(spec.pop("kind")),
        params=spec,
    )


# ---- 個体 -------------------------------------------------------------------

def parse_birth_state(raw: dict[str, Any]) -> BirthState:
    if "individual_id" not in raw or "seed" not in raw:
        raise ConfigError("個体の設定には individual_id と seed が必要です")
    return BirthState(individual_id=str(raw["individual_id"]), seed=int(raw["seed"]))
