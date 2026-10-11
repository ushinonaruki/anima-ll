"""接続の状態を Runtime が決めない・書き換えないことの検査（接続の状態 仕様 B3・T3）。

- runtime の層が接続の状態に対して使ってよいのは weights・apply_activity・export_state だけ
- runtime の層は可塑性の規則（neuroarchitecture）を import しない（依存の検査でも確かめている）
- runtime の層で、重みに代入しない
"""

import ast
from pathlib import Path

RUNTIME = Path(__file__).resolve().parents[2] / "src" / "anima_ll" / "runtime"
ALLOWED = {"weights", "apply_activity", "export_state"}


def test_runtime_uses_only_the_connection_port() -> None:
    for path in sorted(RUNTIME.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "_connections"):
                assert node.attr in ALLOWED, f"{path.name} が接続の状態の {node.attr} を使っている"


def test_runtime_never_assigns_a_weight() -> None:
    for path in sorted(RUNTIME.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets = node.targets if isinstance(node, ast.Assign) else \
                [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
            for t in targets:
                assert not (isinstance(t, ast.Attribute) and "weight" in t.attr), path.name
                assert not (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                            and "weight" in t.value.id), path.name
