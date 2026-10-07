"""テストで共有する構成（L0 の動作テスト用の脳の設計図・実行環境・個体）。

テストのファイル同士で import し合わないために、共有するデータはここに置く。
pyproject.toml の pytest の pythonpath に tests/ を入れてあるので、`from anima_test_support import ...` で読める。
"""

import copy

BASE = {
    "neuro": {
        "version": 0,
        "delta_ttl_pulses": 10,
        "interfaces": {
            "resources": ["llm_pool"],
            "receptors": ["receptor.console"],
            "effectors": ["effector.console"],
        },
        "defaults": {"dynamics": {"kind": "simple_activity", "decay": 0.85, "threshold": 0.5,
                                  "refractory_pulses": 3, "intrinsic_drive": 0.08, "jitter": 0.1}},
        "units": [
            {"id": "u0", "output": "relay"},
            {"id": "u1", "output": {"kind": "kernel_request", "resource": "llm_pool", "max_inputs": 8}},
            {"id": "u2", "output": {"kind": "kernel_request", "resource": "llm_pool", "max_inputs": 8}},
            {"id": "u3", "output": {"kind": "kernel_request", "resource": "llm_pool", "max_inputs": 8}},
        ],
        "projections": [
            {"from": "receptor.console.main", "to": "u0", "weight": 1.0},
            {"from": "u0.main", "to": "u1", "weight": 1.0},
            {"from": "u0.main", "to": "u2", "weight": 1.0},
            {"from": "u1.main", "to": "u2", "weight": 0.4},
            {"from": "u2.main", "to": "u1", "weight": 0.4},
            {"from": "u1.main", "to": "u3", "weight": 0.6},
            {"from": "u2.main", "to": "u3", "weight": 0.6},
            {"from": "u3.main", "to": "effector.console"},
        ],
    },
    "env": {
        "resources": {"llm_pool": {"capacity": 1, "kernel": "fake_delayed", "delay_seconds": 3}},
        "receptors": {"receptor.console": {"kind": "scripted", "script": {5: "ただいま"}}},
        "effectors": {"effector.console": {"kind": "recording"}},
    },
    "birth": {"individual_id": "anima", "seed": 42},
}


def silent(cfg: dict) -> dict:
    """入力のない構成にする。"""
    cfg = copy.deepcopy(cfg)
    cfg["env"]["receptors"]["receptor.console"]["script"] = {}
    return cfg
