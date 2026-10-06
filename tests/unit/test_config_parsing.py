from pathlib import Path

import pytest

from anima_ll.adapter.config.yaml_config_source import (
    ConfigError,
    YamlBirthStateSource,
    YamlEnvironmentSource,
    YamlNeuroarchitectureSource,
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"


def base() -> dict:
    return {
        "interfaces": {
            "resources": ["llm_pool"],
            "receptors": ["receptor.console"],
            "effectors": ["effector.console"],
        },
        "defaults": {"dynamics": {"kind": "simple_activity"}},
        "units": [
            {"id": "u0", "output": "relay"},
            {"id": "u1", "output": {"kind": "kernel_request", "resource": "llm_pool"}},
        ],
        "projections": [
            {"from": "receptor.console.main", "to": "u0"},
            {"from": "u0", "to": "u1", "weight": 0.5},
            {"from": "u1.main", "to": "effector.console"},
        ],
    }


def test_minimal_manifest_loads() -> None:
    manifest = YamlNeuroarchitectureSource(CONFIG / "neuroarchitecture/minimal-v0.yaml").load()
    assert [u.unit_id for u in manifest.units] == ["u0", "u1", "u2", "u3"]


@pytest.mark.parametrize("env_file", sorted((CONFIG / "environment").glob("*.yaml")), ids=lambda p: p.name)
def test_every_environment_binds_minimal_manifest(env_file: Path) -> None:
    manifest = YamlNeuroarchitectureSource(CONFIG / "neuroarchitecture/minimal-v0.yaml").load()
    environment = YamlEnvironmentSource(env_file).load()
    assert environment.binding_mismatches(manifest) == []


def test_individual_loads() -> None:
    birth = YamlBirthStateSource(CONFIG / "individual/anima.yaml").load()
    assert birth.individual_id == "anima"
    assert isinstance(birth.seed, int)


def test_ports_and_permissions() -> None:
    manifest = parse_neuroarchitecture(base())
    assert manifest.projections_from("u0", "main")[0].weight == 0.5
    assert manifest.projections_from("receptor.console", "main")[0].target_id == "u0"
    assert manifest.unit("u1").allowed_resource_classes == frozenset({"llm_pool"})
    assert manifest.unit("u0").allowed_resource_classes == frozenset()


def test_unit_role_is_rejected() -> None:
    raw = base()
    raw["units"][0]["role"] = "memory"
    with pytest.raises(ConfigError, match="役割"):
        parse_neuroarchitecture(raw)


def test_unknown_projection_target_is_rejected() -> None:
    raw = base()
    raw["projections"].append({"from": "u1", "to": "u9"})
    with pytest.raises(ConfigError):
        parse_neuroarchitecture(raw)


@pytest.mark.parametrize("key", ["seed", "resources", "receptors", "effectors"])
def test_moved_keys_are_rejected_in_neuroarchitecture(key: str) -> None:
    raw = base()
    raw[key] = 42
    with pytest.raises(ConfigError, match=key):
        parse_neuroarchitecture(raw)


def test_unit_cannot_use_undeclared_resource() -> None:
    raw = base()
    raw["units"][1]["output"]["resource"] = "gpu_pool"
    with pytest.raises(ConfigError, match="gpu_pool"):
        parse_neuroarchitecture(raw)


def test_binding_mismatches_are_listed() -> None:
    manifest = parse_neuroarchitecture(base())
    environment = parse_environment({
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed"}},
        "receptors": {"receptor.mic": "scripted"},
        "effectors": {"effector.console": {"kind": "recording"}},
    })
    problems = environment.binding_mismatches(manifest)
    assert any("receptor.console" in p for p in problems)
    assert any("receptor.mic" in p for p in problems)
    assert len(problems) == 2


def test_environment_component_requires_prefix_and_kind() -> None:
    with pytest.raises(ConfigError):
        parse_environment({"receptors": {"console": {"kind": "scripted"}}})
    with pytest.raises(ConfigError, match="kind"):
        parse_environment({"effectors": {"effector.console": {}}})


def test_birth_state_requires_id_and_seed() -> None:
    with pytest.raises(ConfigError):
        parse_birth_state({"individual_id": "anima"})
