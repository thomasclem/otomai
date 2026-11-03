"""Hexagonal dependency rules: inner layers never import outer ones."""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "src" / "otomai"
COMPOSITION = {"configs", "settings", "scripts", "__main__"}
ALLOWED = {
    "core": {"core", "logger"},
    "ports": {"core", "ports", "logger"},
    "adapters": {"core", "ports", "adapters", "logger"},
    "services": {"core", "ports", "services", "logger"},
    "strategies": {"core", "ports", "adapters", "services", "strategies", "logger"},
}


def modules(layer):
    return sorted((ROOT / layer).rglob("*.py"))


def imported_layers(path):
    for node in ast.walk(ast.parse(path.read_text())):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if parts[0] == "otomai" and len(parts) > 1:
                yield parts[1]


@pytest.mark.parametrize("layer", sorted(ALLOWED))
def test_layer_imports_only_inner_layers(layer):
    violations = [
        f"{path.relative_to(ROOT)} imports otomai.{imported}"
        for path in modules(layer)
        for imported in imported_layers(path)
        if imported not in ALLOWED[layer]
    ]
    assert not violations, violations


def test_every_module_belongs_to_a_layer():
    top = {p.stem for p in ROOT.glob("*.py")} - {"__init__", "logger"}
    assert top <= COMPOSITION
    assert {p.name for p in ROOT.iterdir() if p.is_dir() and p.name != "__pycache__"} == set(
        ALLOWED
    )


def test_ports_contain_no_vendor_code():
    for path in modules("ports"):
        assert "ccxt" not in set(imported_roots(path)), path


def imported_roots(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module.split(".")[0]


def test_services_and_strategies_never_touch_the_raw_transport():
    violations = []
    for path in modules("services") + modules("strategies"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Attribute) and node.attr in {"session", "_session"}:
                violations.append(str(path))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "info"
            ):
                violations.append(str(path))
    assert not violations, violations
