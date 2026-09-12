"""The engine never reaches back up into willow-mcp.

Operator direction, 2026-09-02: "willow gains the dependency on the engine, but
the apps here will only run on it." Willow depends on the Forge; the Forge
soft-depends on Nestor and kartikeya; kartikeya is already under Willow. The
day the Forge imports willow_mcp, that is a cycle, and the first thing that
breaks is the install. Same invariant kartikeya and jeles hold — neither
imports willow_mcp — and the reason willow-mcp can take all three cheaply.

The three vendored modules (human_loop, friction_floor, model_egress) are
COPIES, deliberately, not imports — vendored from willow-mcp on 2026-08-11 and
canonical here since 2026-09-03, when willow-mcp switched to re-exporting them
from forge-play instead. tools/vendor_sync_check.py keeps them honest — real
since 2026-09-12 (G2-vendor-pins-forge; this docstring named it for a year
before it existed): tools/vendor_manifest.json pins each body by SHA-256,
friction_floor against its willow-gate origin under a recorded local override
(the manifest note says what diverged and why the body is not touched here),
human_loop and model_egress as canonical here, and tests/test_vendor_sync_check.py
plus a step in tests.yml run it. willow-mcp's own guards still stand
downstream (tests/test_forge_take.py's identity check, tests/test_stance_friction.py's
hash pin). This test is what makes "the Forge never imports willow-mcp" a
checked property rather than a comment.

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


def _forbidden_imports(path: Path) -> list[str]:
    """The imports in `path` that reach into a forbidden root, dotted
    submodules included; `willow_mcp_tools` would not match `willow_mcp`."""
    return [n for n in _imports_of(path)
            if any(n == r or n.startswith(r + ".") for r in _FORBIDDEN_ROOTS)]


@pytest.mark.parametrize("path", list(_py_files()), ids=lambda p: str(p.relative_to(_REPO)))
def test_the_engine_never_imports_willow_mcp(path: Path):
    offending = _forbidden_imports(path)
    assert not offending, (
        f"{path.relative_to(_REPO)} imports {offending}: the Forge must never depend on "
        f"willow-mcp (Willow depends on the Forge; the reverse is a cycle). Vendor the "
        f"piece byte-for-byte instead and pin its body in tools/vendor_manifest.json "
        f"so tools/vendor_sync_check.py holds it, or move it home."
    )


def test_the_scan_actually_covered_the_engine():
    files = list(_py_files())
    assert any(p.name == "checkpoint.py" for p in files), files
    assert len(files) > 10, "the scan found almost nothing; the directories moved?"


def test_the_scan_catches_a_planted_reach_back(tmp_path):
    """Planted: a module that imports willow_mcp three ways — bare, dotted
    with an alias, and `from ... import` — beside a comment and a string
    literal that merely name it, and an import of a different root that
    shares the prefix. Exactly the three imports must be reported: the vendor
    notes in forge/ name willow_mcp in comments constantly, which is why this
    walks the AST, and until 2026-09-12 nothing had ever shown `_imports_of`
    reporting anything (the meta-scan in tests/test_scans_fire.py found it
    unplanted; every file it scanned was clean, which is the point)."""
    probe = tmp_path / "reach.py"
    probe.write_text(
        "# vendored from willow_mcp — a comment is not an import\n"
        "NOTE = 'willow_mcp.human_loop'\n"
        "import willow_mcp\n"
        "import willow_mcp.human_loop as hl\n"
        "from willow_mcp.friction_floor import score\n"
        "import willow_mcp_tools\n"
        "from forge import paths\n",
        encoding="utf-8",
    )
    assert _forbidden_imports(probe) == [
        "willow_mcp", "willow_mcp.human_loop", "willow_mcp.friction_floor"
    ]
    assert "willow_mcp_tools" in _imports_of(probe), "the reader saw it; the filter excluded it"
