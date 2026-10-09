"""出来事を成立させる層の検査（活動の伝達 仕様 C2・C3、接続の状態 仕様 B2・B3）。

- ActivityEvent を作るのは Unit の層だけ（Runtime は判定・生成しない）
- SensoryEvent を作るのは Receptor（Environment の adapter）だけ
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "anima_ll"


def constructed_in(name: str) -> set[str]:
    found = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == name:
                found.add(str(path.relative_to(SRC)))
    return found


def test_activity_events_are_created_only_by_units() -> None:
    assert constructed_in("ActivityEvent") == {"unit/generic_cognitive_unit.py"}


def test_sensory_events_are_created_only_by_receptors() -> None:
    places = constructed_in("SensoryEvent")
    assert places and all(p.startswith("adapter/receptor/") for p in places), places
