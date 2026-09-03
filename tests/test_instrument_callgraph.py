"""Tests for forge/instrument_callgraph.py — the panel's first real fleet
instrument (codebase-memory-mcp call graph, docs/design/the-forge-measure.md).

The dead-code SET DIFFERENCE is a pure function, tested against captured
codebase-memory output (no binary needed). The real end-to-end drive is
`skipif`'d when the binary isn't runnable (as bite 0 skips when bwrap is
absent). The unavailable-path is always tested.

rudi193-cmd/Forge#9: the reader must never turn "could not read" into "found nothing".
The old text-table fixtures are kept below as the thing the reader now
REFUSES, not the thing it parses.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


from forge import instrument_callgraph as icg


# ── captured output, no binary ───────────────────────────────────────────────

# The CLI's compact-JSON envelope for a 3-function project
# (used<-main, dead_function uncalled, main entry-point), as the tool emits it now.
def _envelope(columns, rows):
    result = {"columns": columns, "rows": rows, "total": len(rows)}
    return {"content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}],
            "structuredContent": result, "isError": False}


_ALL = _envelope(["qn", "entry", "file"], [
    ["tmp-cbm-probe.app.used", "false", "app.py"],
    ["tmp-cbm-probe.app.dead_function", "false", "app.py"],
    ["tmp-cbm-probe.app.main", "true", "app.py"],
    ["builtins.len", "false", "<python-builtins>"],
    ["builtins.print", "false", "<python-builtins>"],
])
_CALLED = _envelope(["qn"], [["tmp-cbm-probe.app.used"]])

# What the tool USED to print — the format the first cut parsed. Kept as the
# negative case: this is what "silently zero rows on every codebase" looked like.
_OLD_TEXT_TABLE = """rows: 5  (cols: qn entry file)
  tmp-cbm-probe.app.used "false" app.py
  tmp-cbm-probe.app.dead_function "false" app.py
  tmp-cbm-probe.app.main "true" app.py
total: 5"""


def test_dead_functions_is_the_set_difference():
    dead = icg._dead_functions(icg._rows(_ALL), icg._rows(_CALLED))
    assert dead == [("tmp-cbm-probe.app.dead_function", "app.py")]
    qns = {qn for qn, _ in dead}
    assert "tmp-cbm-probe.app.used" not in qns     # called
    assert "tmp-cbm-probe.app.main" not in qns     # entry point
    assert not any(f.startswith("<") for _, f in dead)  # builtins excluded


def test_rows_reads_the_text_content_when_structured_content_is_absent():
    only_text = {"content": _ALL["content"]}
    assert icg._rows(only_text) == icg._rows(_ALL)


def test_rows_reads_a_bare_result_object_and_a_json_string():
    bare = _ALL["structuredContent"]
    assert icg._rows(bare) == icg._rows(_ALL)
    assert icg._rows(json.dumps(bare)) == icg._rows(_ALL)


def test_a_file_path_with_spaces_survives():
    env = _envelope(["qn", "entry", "file"], [["pkg.mod.orphan", "false", "src/my dir/x.py"]])
    dead = icg._dead_functions(icg._rows(env), [])
    assert dead == [("pkg.mod.orphan", "src/my dir/x.py")]


def test_python_style_booleans_are_accepted_for_entry():
    env = _envelope(["qn", "entry", "file"], [["pkg.mod.root", True, "x.py"], ["pkg.mod.leaf", False, "x.py"]])
    assert icg._dead_functions(icg._rows(env), []) == [("pkg.mod.leaf", "x.py")]


def test_empty_results_yield_no_dead():
    empty = _envelope(["qn", "entry", "file"], [])
    assert icg._dead_functions(icg._rows(empty), icg._rows(_envelope(["qn"], []))) == []


# ── rudi193-cmd/Forge#9: could-not-read is never found-nothing ──────────────────────────

def test_the_old_text_table_is_refused_not_parsed_to_zero_rows():
    with pytest.raises(icg.UnreadableResult):
        icg._rows(_OLD_TEXT_TABLE)


def test_a_total_with_no_rows_is_refused():
    env = _envelope(["qn", "entry", "file"], [])
    env["structuredContent"]["total"] = 3
    with pytest.raises(icg.UnreadableResult):
        icg._rows(env)


def test_a_short_row_is_refused_not_skipped():
    """The first cut's `if len(parts) < 3: continue` is exactly the guard that
    swallowed the whole payload. A row this reader can't place is a refusal."""
    env = _envelope(["qn", "entry", "file"], [["only-one-column"]])
    with pytest.raises(icg.UnreadableResult):
        icg._dead_functions(icg._rows(env), [])


def test_unreadable_output_becomes_a_coverage_gap_not_a_clean_report(tmp_path, monkeypatch):
    """Drive `measure` with a fake binary path and a `_call` that answers in the
    old text format: the instrument must raise InstrumentUnavailable (the panel
    then says COULD NOT RUN), never return `[]`."""
    fake = tmp_path / "codebase-memory-mcp"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    inst = icg.CallGraphInstrument(binary=str(fake))

    def fake_call(exe, tool, args, *, tolerant=False):
        if tool == "index_repository":
            return {"structuredContent": {"project": "p"}}
        if tool == "query_graph":
            return {"content": [{"type": "text", "text": _OLD_TEXT_TABLE}]}
        return {}

    monkeypatch.setattr(inst, "_call", fake_call)
    with pytest.raises(icg.InstrumentUnavailable) as e:
        inst.measure(tmp_path)
    assert "could not read" in str(e.value)


# ── unavailable path (always runs) ───────────────────────────────────────────

def test_missing_binary_is_instrument_unavailable(tmp_path):
    inst = icg.CallGraphInstrument(binary="/no/such/codebase-memory-mcp-binary")
    with pytest.raises(icg.InstrumentUnavailable):
        inst.measure(tmp_path)


# ── real end-to-end drive (skipped if the binary can't run) ──────────────────

def _binary():
    exe = shutil.which("codebase-memory-mcp") or "/tmp/forge-audit-venv/bin/codebase-memory-mcp"
    if not Path(exe).exists():
        return None
    try:
        subprocess.run([exe, "--version"], capture_output=True, timeout=30)
    except Exception:
        return None
    return exe


_BIN = _binary()


@pytest.mark.skipif(_BIN is None, reason="codebase-memory-mcp binary not runnable in this environment")
def test_drives_the_real_tool_and_flags_dead_code(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    (d / "app.py").write_text(
        "def used():\n    return 1\n\n"
        "def dead_function():\n    return 2\n\n"
        "def main():\n    return used()\n"
    )
    findings = icg.CallGraphInstrument(binary=_BIN).measure(d)
    files_flagged = {f.artifact for f in findings}
    dead_detail = " ".join(f.detail for f in findings)
    assert any("app.py" in a for a in files_flagged), findings
    assert "dead_function" in dead_detail
    assert all(f.metric == "fan_in" and f.value == 0 for f in findings)


@pytest.mark.skipif(_BIN is None, reason="codebase-memory-mcp binary not runnable in this environment")
def test_a_fully_wired_program_has_no_dead_code(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    (d / "app.py").write_text(
        "def a():\n    return 1\n\n"
        "def b():\n    return a()\n\n"
        "def main():\n    return b()\n"
    )
    # a<-b<-main, main is entry -> nothing is dead
    findings = icg.CallGraphInstrument(binary=_BIN).measure(d)
    assert findings == [], findings
