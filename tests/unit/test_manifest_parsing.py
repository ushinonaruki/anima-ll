from pathlib import Path

import pytest

from anima_ll.adapter.manifest.yaml_manifest_source import (
    ManifestError,
    YamlManifestSource,
    parse_manifest,
)

ROOT = Path(__file__).resolve().parents[2]


def base() -> dict:
    return {
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed"}},
        "receptors": [{"id": "receptor.console", "kind": "scripted"}],
        "effectors": [{"id": "effector.console", "kind": "recording"}],
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
    manifest = YamlManifestSource(ROOT / "config/neuroarchitecture/minimal-v0.yaml").load()
    assert [u.unit_id for u in manifest.units] == ["u0", "u1", "u2", "u3"]


def test_ports_and_permissions() -> None:
    manifest = parse_manifest(base())
    assert manifest.projections_from("u0", "main")[0].weight == 0.5
    assert manifest.projections_from("receptor.console", "main")[0].target_id == "u0"
    assert manifest.unit("u1").allowed_resource_classes == frozenset({"llm_pool"})
    assert manifest.unit("u0").allowed_resource_classes == frozenset()


def test_unit_role_is_rejected() -> None:
    raw = base()
    raw["units"][0]["role"] = "memory"
    with pytest.raises(ManifestError, match="役割"):
        parse_manifest(raw)


def test_unknown_projection_target_is_rejected() -> None:
    raw = base()
    raw["projections"].append({"from": "u1", "to": "u9"})
    with pytest.raises(ManifestError):
        parse_manifest(raw)
