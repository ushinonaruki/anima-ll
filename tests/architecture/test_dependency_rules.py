"""依存ルールの検査。

- domain   は domain だけを import する
- runtime  は domain と runtime だけ
- unit     は domain と unit だけ
- adapter.X は domain と adapter.X だけ（adapter 同士も依存しない）
- bootstrap と __main__ だけが全部を import できる
- domain・runtime・unit は外部ライブラリを使わない（標準ライブラリだけ）
"""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "anima_ll"
PACKAGE = "anima_ll"
FREE_LAYERS = {"bootstrap", "__main__"}
PURE_LAYERS = {"domain", "runtime", "unit"}


def layer_of_module_path(relative: Path) -> str:
    parts = relative.with_suffix("").parts
    if parts[0] == "adapter":
        return f"adapter.{parts[1]}" if len(parts) > 2 else "adapter"
    return parts[0]


def layer_of_import(module: str) -> str:
    parts = module.split(".")[1:]
    if not parts:
        return "package"
    if parts[0] == "adapter":
        return f"adapter.{parts[1]}" if len(parts) > 1 else "adapter"
    return parts[0]


def allowed_layers(layer: str) -> set[str]:
    if layer in ("domain",):
        return {"domain"}
    if layer == "runtime":
        return {"domain", "runtime"}
    if layer == "unit":
        return {"domain", "unit"}
    if layer.startswith("adapter"):
        return {"domain", layer}
    return set()


def imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


SOURCE_FILES = sorted(
    p for p in PACKAGE_ROOT.rglob("*.py") if p.name != "__init__.py"
)


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: str(p.relative_to(PACKAGE_ROOT)))
def test_layer_dependencies(path: Path) -> None:
    relative = path.relative_to(PACKAGE_ROOT)
    layer = layer_of_module_path(relative)
    if layer in FREE_LAYERS:
        return
    allowed = allowed_layers(layer)
    for module in imports_of(path):
        top = module.split(".")[0]
        if top == PACKAGE:
            target = layer_of_import(module)
            assert target in allowed, f"{relative}（{layer}）が {module}（{target}）を import している"
        elif layer.split(".")[0] in PURE_LAYERS:
            assert top in sys.stdlib_module_names, (
                f"{relative}（{layer}）が外部ライブラリ {module} を import している"
            )


def test_rule_detects_violation(tmp_path: Path) -> None:
    """検査そのものが違反を検出できることの確認。"""
    bad = tmp_path / "bad.py"
    bad.write_text("from anima_ll.adapter.kernel.fake_delayed_kernel import FakeDelayedKernel\n")
    assert "adapter.kernel" not in allowed_layers("domain")
    assert layer_of_import(imports_of(bad)[0]) == "adapter.kernel"
