"""Import-boundary enforcement (CONSTITUTION II.1, gate 0.3).

Mirrored by a ruff `flake8-tidy-imports` ban. Both, deliberately: the lint rule catches it
while you type, and this catches it when someone adds a `# noqa`.

Walking the AST rather than importing the packages matters -- an import-time check would
pass for a module that only imports `fastapi` inside a function, and that module still
couldn't be run from a plain script.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

FORBIDDEN: dict[str, frozenset[str]] = {
    "domain": frozenset({"fastapi", "sqlalchemy", "anthropic", "claude_agent_sdk", "httpx"}),
    "adapters": frozenset({"fastapi", "claude_agent_sdk"}),
    "agent": frozenset({"fastapi"}),
    "mcp": frozenset({"fastapi"}),
}

#: `src/domain` must additionally import nothing that touches the network, a database or
#: the clock. A pure domain is what makes P5's scorer testable with no fixtures, no mocks
#: and no event loop -- and `datetime.now()` in a scorer is what makes a ranking
#: irreproducible, which CONSTITUTION II.2 forbids.
DOMAIN_FORBIDDEN_EXTRA = frozenset({"socket", "requests", "urllib", "asyncio", "time", "random"})


def _python_files(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_layer_imports_nothing_forbidden(package: str) -> None:
    banned = FORBIDDEN[package]
    violations: list[str] = []
    for path in _python_files(package):
        hits = _imported_roots(path) & banned
        if hits:
            violations.append(f"{path.relative_to(SRC.parent)}: {sorted(hits)}")
    assert not violations, "forbidden imports:\n  " + "\n  ".join(violations)


def test_domain_touches_no_network_database_or_clock() -> None:
    violations: list[str] = []
    for path in _python_files("domain"):
        hits = _imported_roots(path) & DOMAIN_FORBIDDEN_EXTRA
        if hits:
            violations.append(f"{path.relative_to(SRC.parent)}: {sorted(hits)}")
    assert not violations, "src/domain must stay pure:\n  " + "\n  ".join(violations)


#: Layers that must exist for the boundary scan to be meaningful *today*. `agent` joined
#: this set when P3 landed -- before that it had no modules, and asserting otherwise would
#: have failed for the wrong reason. The parametrised scan above covers a layer the moment
#: it appears regardless of whether it's required yet.
REQUIRED_LAYERS = frozenset({"domain", "adapters", "mcp", "agent"})


def test_layer_packages_that_exist_are_actually_scanned() -> None:
    """A boundary test that silently scans nothing passes for the wrong reason."""
    for package in REQUIRED_LAYERS:
        assert (SRC / package).is_dir(), f"src/{package} is missing"
        assert _python_files(package), f"src/{package} has no modules to scan"

    for package in FORBIDDEN:
        if (SRC / package).is_dir():
            assert _python_files(package), f"src/{package} exists but has no modules"


def test_only_the_api_layer_imports_fastapi() -> None:
    """The positive half of the rule: `fastapi` has to appear *somewhere*.

    Without this, deleting the transport layer would leave the boundary tests green while
    the constraint they encode had stopped meaning anything.
    """
    importers = {
        path.relative_to(SRC).parts[0]
        for path in SRC.rglob("*.py")
        if "fastapi" in _imported_roots(path)
    }
    assert importers == {"api"}, f"fastapi imported by {sorted(importers)}"
