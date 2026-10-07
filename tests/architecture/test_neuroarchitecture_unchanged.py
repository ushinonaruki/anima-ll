"""実験 0007 A0：計算資源境界の実装で、Unit の力学（Neuroarchitecture）を変えていないことの検査。

- Unit の状態に、実行資源の都合を表す項目（pending など）を足していない
- Unit の層が、実行の列・Worker・意図の一生の状態を参照しない
"""

import ast
from dataclasses import fields
from pathlib import Path

from anima_ll.unit.dynamics.activity_dynamics import ActivityState

UNIT_ROOT = Path(__file__).resolve().parents[2] / "src" / "anima_ll" / "unit"
RUNTIME_ONLY_NAMES = {
    "ExecutionQueue", "ComputeIntent", "IntentStatus", "KernelTaskCoordinator",
    "intent_seq", "queue_capacity", "free_capacity", "busy_units",
}


def test_activity_state_has_no_new_fields() -> None:
    assert [f.name for f in fields(ActivityState)] == [
        "activity", "refractory_remaining", "adaptation", "fire_count",
    ]


def test_unit_layer_does_not_reference_execution_infrastructure() -> None:
    for path in sorted(UNIT_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {a.name.split(".")[-1] for n in ast.walk(tree)
                  if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        modules = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not (names & RUNTIME_ONLY_NAMES), f"{path.name} が {names & RUNTIME_ONLY_NAMES} を参照している"
        assert not any(m.startswith("anima_ll.runtime") for m in modules), path.name
