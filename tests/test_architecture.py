"""Dependency rules from docs/ARCHITECTURE.md, checked so they can't drift.

* Feature packages never import each other (shared code goes in a
  cross-cutting module instead).
* Cross-cutting modules and compliance/ never import a feature package.
* compliance/rules.py stays pure: no Flask, no database.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
FEATURES = {
    "auth",
    "main",
    "dashboard",
    "drivers",
    "fleet",
    "hos",
    "training",
    "imports",
    "integrations",
}


def _imported_app_packages(path: Path) -> set[str]:
    """Top-level app packages a module imports (``from ..fleet import x`` -> "fleet")."""
    package = path.relative_to(APP).parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                parts = (node.module or "").split(".")
                if parts[0] == "app" and len(parts) > 1:
                    found.add(parts[1])
                continue
            base = package[: len(package) - node.level + 1]
            target = (*base, *(node.module or "").split(".")) if node.module else base
            if target:
                found.add(target[0])
            elif node.module is None:  # "from .. import audit" at the app root
                found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "app" and len(parts) > 1:
                    found.add(parts[1])
    return found


def _modules(where: Path) -> list[Path]:
    return sorted(where.rglob("*.py"))


@pytest.mark.parametrize("feature", sorted(FEATURES))
def test_features_do_not_import_each_other(feature):
    for path in _modules(APP / feature):
        crossed = (_imported_app_packages(path) & FEATURES) - {feature}
        assert not crossed, f"{path.relative_to(APP)} imports feature {crossed}"


def test_shared_modules_do_not_import_features():
    shared = [p for p in APP.glob("*.py") if p.name != "__init__.py"]  # factory wires features
    shared += _modules(APP / "compliance") + _modules(APP / "audit")
    for path in shared:
        crossed = _imported_app_packages(path) & FEATURES
        assert not crossed, f"{path.relative_to(APP)} imports feature {crossed}"


def test_compliance_rules_are_pure():
    tree = ast.parse((APP / "compliance" / "rules.py").read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add((node.module or "").split(".")[0])
    assert not names & {"flask", "sqlalchemy", "flask_sqlalchemy"}
    assert "extensions" not in _imported_app_packages(APP / "compliance" / "rules.py")
