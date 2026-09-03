"""The engine never reaches back up into willow-mcp.

Operator direction, 2026-09-02: "willow gains the dependency on the engine, but
the apps here will only run on it." Willow depends on the Forge; the Forge
soft-depends on Nestor and kartikeya; kartikeya is already under Willow. The
day the Forge imports willow_mcp, that is a cycle, and the first thing that
breaks is the install. Same invariant kartikeya and jeles hold — neither
imports willow_mcp — and the reason willow-mcp can take all three cheaply.

The three vendored modules (human_loop, friction_floor, model_egress) are
COPIES from willow-mcp, deliberately, not imports — tools/vendor_sync_check.py
keeps them honest until they go home the other way (engine build plan, Phase 5).
This test is what makes "vendored, not imported" a checked property rather
than a comment.

Walks the AST rather than grepping, so a comment that names willow_mcp (there
are many — the vendor notes) is not a violation and a real import is.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCANNED_DIRS = ("forge", "demo", "tools")
_FORBIDDEN_ROOTS = ("willow_mcp",)


def _py_files():
    for d in _SCANNED_DIRS:
        yield from sorted((_REPO / d).rglob("*.py"))


def _imports_of(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize("path", list(_py_files()), ids=lambda p: str(p.relative_to(_REPO)))
def test_the_engine_never_imports_willow_mcp(path: Path):
    offending = [n for n in _imports_of(path)
                 if any(n == r or n.startswith(r + ".") for r in _FORBIDDEN_ROOTS)]
    assert not offending, (
        f"{path.relative_to(_REPO)} imports {offending}: the Forge must never depend on "
        f"willow-mcp (Willow depends on the Forge; the reverse is a cycle). Vendor the "
        f"piece byte-for-byte under tools/vendor_sync_check.py instead, or move it home."
    )


def test_the_scan_actually_covered_the_engine():
    files = list(_py_files())
    assert any(p.name == "checkpoint.py" for p in files), files
    assert len(files) > 10, "the scan found almost nothing; the directories moved?"
