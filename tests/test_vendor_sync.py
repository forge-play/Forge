"""tests/test_vendor_sync.py — exercises tools/vendor_sync_check.py.

The script it wraps compares the Forge's vendored copies (`forge/human_loop.py`,
`forge/friction_floor.py`, `forge/model_egress.py`) against their willow-mcp
upstream sources. This suite runs it against whatever willow-mcp checkout is
on the machine, so it's necessarily environment-dependent — skipped, not
failed, when that checkout isn't there (CI can set WILLOW_MCP_PATH to point
at a real one; a contributor without willow-mcp checked out still gets a
green suite). It also unit-tests the header-stripping/function-extraction
machinery directly, against small in-memory fixtures, so drift detection
itself is covered even without willow-mcp on disk.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "tools" / "vendor_sync_check.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("vendor_sync_check", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register before exec: the module's own dataclass fields resolve
    # `cls.__module__` through sys.modules while the class body runs, which
    # fails with a bare AttributeError if the module isn't there yet.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vsc = _load_module()


def _default_upstream() -> Path | None:
    """Where to find willow-mcp for the environment-dependent tests: an
    explicit WILLOW_MCP_PATH env var first, else the conventional sibling
    checkout at ~/willow-mcp."""
    env = os.environ.get("WILLOW_MCP_PATH")
    if env:
        return Path(env)
    sibling = Path.home() / "willow-mcp"
    return sibling if sibling.is_dir() else None


UPSTREAM = _default_upstream()
requires_upstream = pytest.mark.skipif(
    UPSTREAM is None,
    reason="willow-mcp checkout not found (set WILLOW_MCP_PATH or check one out at ~/willow-mcp)",
)


# ── unit tests: header stripping and function extraction, no willow-mcp needed ──


def test_strip_header_drops_the_safe_app_store_block_only():
    lines = [
        '"""kept before"""\n',
        "# ── SAFE App Store vendor note (whatever) ──\n",
        "# drop this\n",
        "# and this\n",
        "# Vendored from willow-gate (kept, matches upstream)\n",
        "def f(): pass\n",
    ]
    trimmed = vsc._strip_header(
        lines, strip_from=r"SAFE App Store vendor note", strip_until=r"^# Vendored from willow-gate",
    )
    assert trimmed == [
        '"""kept before"""\n',
        "# Vendored from willow-gate (kept, matches upstream)\n",
        "def f(): pass\n",
    ]


def test_strip_header_reports_missing_start_marker():
    result = vsc._strip_header(["no header here\n"], strip_from="NOPE", strip_until="ALSO_NOPE")
    assert isinstance(result, str)
    assert "NOPE" in result


def test_strip_header_reports_missing_end_marker():
    result = vsc._strip_header(
        ["# SAFE App Store vendor note\n", "# more\n"],
        strip_from="SAFE App Store vendor note",
        strip_until="NEVER_APPEARS",
    )
    assert isinstance(result, str)
    assert "NEVER_APPEARS" in result


def test_check_full_file_in_sync(tmp_path: Path):
    upstream_root = tmp_path / "upstream"
    forge_root = tmp_path / "forge"
    (upstream_root / "src" / "willow_mcp").mkdir(parents=True)
    (forge_root / "forge").mkdir(parents=True)

    body = '"""m — a module."""\ndef f():\n    return 1\n'
    (upstream_root / "src" / "willow_mcp" / "m.py").write_text(body)
    (forge_root / "forge" / "m.py").write_text(
        "# ── SAFE App Store vendor note ──\n# header stuff\n" + body
    )

    entry = vsc.FullFileVendor(
        forge_path="forge/m.py",
        upstream_path="src/willow_mcp/m.py",
        strip_from=r"SAFE App Store vendor note",
        strip_until=r'^"""m',
    )
    result = vsc.check_full_file(entry, forge_root, upstream_root)
    assert result.in_sync
    assert not result.error


def test_check_full_file_detects_drift(tmp_path: Path):
    upstream_root = tmp_path / "upstream"
    forge_root = tmp_path / "forge"
    (upstream_root / "src" / "willow_mcp").mkdir(parents=True)
    (forge_root / "forge").mkdir(parents=True)

    (upstream_root / "src" / "willow_mcp" / "m.py").write_text(
        '"""m."""\ndef f():\n    return 1\n'
    )
    (forge_root / "forge" / "m.py").write_text(
        "# ── SAFE App Store vendor note ──\n# header\n"
        '"""m."""\ndef f():\n    return 2\n'  # drifted: 2, not 1
    )

    entry = vsc.FullFileVendor(
        forge_path="forge/m.py",
        upstream_path="src/willow_mcp/m.py",
        strip_from=r"SAFE App Store vendor note",
        strip_until=r'^"""m',
    )
    result = vsc.check_full_file(entry, forge_root, upstream_root)
    assert not result.in_sync
    assert not result.error
    assert "return 1" in result.detail and "return 2" in result.detail


def test_check_full_file_missing_forge_file_is_an_error(tmp_path: Path):
    entry = vsc.FullFileVendor(
        forge_path="forge/nope.py",
        upstream_path="src/willow_mcp/nope.py",
        strip_from="x",
        strip_until="y",
    )
    result = vsc.check_full_file(entry, tmp_path, tmp_path)
    assert not result.in_sync
    assert result.error


def test_check_partial_ignores_documented_local_imports(tmp_path: Path):
    upstream_root = tmp_path / "upstream"
    forge_root = tmp_path / "forge"
    (upstream_root / "src" / "willow_mcp").mkdir(parents=True)
    (forge_root / "forge").mkdir(parents=True)

    (upstream_root / "src" / "willow_mcp" / "m.py").write_text(
        "import socket\n\n\ndef f(x):\n    return socket.getaddrinfo(x, None)\n"
    )
    # forge inlines the import locally (partial vendor, no module-level import) —
    # documented as an intentional difference, should NOT read as drift.
    (forge_root / "forge" / "m.py").write_text(
        "def f(x):\n    import socket\n    return socket.getaddrinfo(x, None)\n"
    )

    entry = vsc.PartialFunctionVendor(
        forge_path="forge/m.py",
        upstream_path="src/willow_mcp/m.py",
        functions=("f",),
        ignore_line_patterns=(r"^\s*import socket\s*$",),
    )
    result = vsc.check_partial(entry, forge_root, upstream_root)
    assert result.in_sync, result.detail


def test_check_partial_detects_real_drift_in_a_vendored_function(tmp_path: Path):
    upstream_root = tmp_path / "upstream"
    forge_root = tmp_path / "forge"
    (upstream_root / "src" / "willow_mcp").mkdir(parents=True)
    (forge_root / "forge").mkdir(parents=True)

    (upstream_root / "src" / "willow_mcp" / "m.py").write_text("def f(x):\n    return x + 1\n")
    (forge_root / "forge" / "m.py").write_text("def f(x):\n    return x + 2\n")

    entry = vsc.PartialFunctionVendor(
        forge_path="forge/m.py", upstream_path="src/willow_mcp/m.py", functions=("f",),
    )
    result = vsc.check_partial(entry, forge_root, upstream_root)
    assert not result.in_sync
    assert "f" in result.detail


# ── environment-dependent: the real vendor map against a real willow-mcp ────


@requires_upstream
def test_vendor_map_files_exist_on_both_sides():
    """Sanity check on the mapping itself, independent of drift: every forge
    file and its declared upstream counterpart actually exist."""
    for entry in vsc.VENDORED:
        forge_file = REPO_ROOT / entry.forge_path
        upstream_file = UPSTREAM / entry.upstream_path
        assert forge_file.is_file(), f"vendor map is stale: {forge_file} does not exist"
        assert upstream_file.is_file(), f"vendor map is stale: {upstream_file} does not exist"


@requires_upstream
def test_vendor_sync_check_runs_end_to_end_and_reports_status():
    """Runs the real check against the real willow-mcp checkout. Does not
    assert in-sync (the whole point of this tool is that drift is an
    expected, reportable state, not a test failure) — asserts the tool
    itself completes cleanly and returns a coherent, parseable result."""
    results = vsc.run_checks(REPO_ROOT, UPSTREAM)
    assert len(results) == len(vsc.VENDORED)
    for result in results:
        # A result is always resolvable one way or another: either it
        # compared cleanly, or it has a diff/error explaining why not.
        assert result.in_sync or result.detail


@requires_upstream
def test_vendor_sync_check_cli_exit_code_matches_drift_state(capsys):
    exit_code = vsc.main(["--upstream", str(UPSTREAM), "--quiet"])
    results = vsc.run_checks(REPO_ROOT, UPSTREAM)
    expected = 1 if any(not r.in_sync for r in results) else 0
    assert exit_code == expected


@requires_upstream
def test_vendor_sync_check_cli_bad_upstream_path_fails_closed(tmp_path: Path):
    missing = tmp_path / "no-such-willow-mcp"
    assert vsc.main(["--upstream", str(missing)]) == 1
