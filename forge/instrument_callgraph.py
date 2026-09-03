#!/usr/bin/env python3
"""forge/instrument_callgraph.py — the measuring panel's first REAL fleet
instrument: `codebase-memory-mcp`'s call graph (docs/design/the-forge-measure.md).

The box's decoy — `login.php`'s `check_login()`, retrieved by every ranker as
"where auth lives," and never actually called — was caught by exactly one kind
of tool: one that traced the CALL GRAPH (`fan_in=0`) instead of ranking by
appearance. `codebase-memory-mcp` is that tool (rule 11: reuse it, don't rebuild
a tree-sitter graph). This adapter drives it one-shot via its `cli --json`
surface, finds functions with no callers, and emits a per-file `Finding` the
panel can converge with `census`/`hygiene` — a dead function in a file that is
ALSO an accidental commit is a much louder signal than either alone.

**Dead code = set difference, not a broken OPTIONAL-count.** codebase-memory's
query engine returns `count(a)=1` for an OPTIONAL MATCH that matched nothing
(verified), so fan_in can't be read from one aggregate. Instead: all functions
MINUS the targets of any `CALLS` edge, minus entry points (a genuine root is
not dead) and language builtins. That set difference is the pure, tested core
(`_dead_functions`); the subprocess plumbing around it degrades to
`InstrumentUnavailable` on any failure (binary absent, non-zero exit, unreadable
output) — the panel's honest-coverage path, never a crash.

**Format drift must not read as clean (rudi193-cmd/Forge#9).** The first cut parsed the
tool's indented TEXT table. The tool moved to compact JSON; the text parser
yielded the whole payload as one row, the "malformed row" guard skipped it,
and the instrument reported *found nothing* on every codebase — routing a
*could-not-read* into the *looked-and-saw-nothing* bucket, which is precisely
the distinction the panel exists to protect. Now: the query result is read as
JSON (`structuredContent.rows`, with the `content[0].text` JSON as the
fallback), the CLI is called through `--args-file` (the raw-JSON argument
form is deprecated upstream), and a payload the reader cannot make rows of —
or one that reports `total > 0` while yielding no rows — raises
`InstrumentUnavailable`, so the panel says COULD NOT RUN rather than clean.
A panel that reports clean is worse than one that reports uncovered, because
uncovered is actionable and clean is not.

Not in the panel's dependency-free DEFAULT_INSTRUMENTS: this needs the external
binary (downloaded on first use, runs a daemon), so a caller opts in
(`measure_panel` CLI `--with-callgraph`, or pass `CallGraphInstrument()`
explicitly). When it is NOT included, the panel names `call-graph` as an
uncovered class — the sigmap honesty.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


# Reuse the ONE already-loaded measure_panel if present — a second spec-load
# would give a DISTINCT InstrumentUnavailable class, so run_panel would catch
# this instrument's unavailability under its generic handler and mislabel it
# "errored" instead of "could not run" (found live). One module, one exception
# identity.
from . import measure_panel

Finding = measure_panel.Finding
InstrumentUnavailable = measure_panel.InstrumentUnavailable

_DEFAULT_BINARY = "codebase-memory-mcp"

# Column order is fixed by the RETURN clause and read positionally.
_Q_ALL = "MATCH (f:Function) RETURN f.qualified_name AS qn, f.is_entry_point AS entry, f.file_path AS file"
_Q_CALLED = "MATCH (a)-[:CALLS]->(f:Function) RETURN f.qualified_name AS qn"


# ── the pure core (unit-tested without the binary) ──────────────────────────

class UnreadableResult(ValueError):
    """The tool answered, but not in a shape this reader can turn into rows.
    Distinct from an empty result: raised so the caller can name a coverage
    gap rather than report clean."""


def _rows(payload: dict | str) -> list[list[str]]:
    """The data rows of a `query_graph` result, as lists of strings.

    Accepts the CLI's JSON envelope (`{"structuredContent": {"columns", "rows",
    "total"}, "content": [{"text": "<the same as JSON>"}]}`) or the bare
    result object, or the result as a JSON string. Refuses — `UnreadableResult`
    — anything else, including the old indented text table, so that a format
    change surfaces as *could not read* and never as *no rows*."""
    obj: object = payload
    if isinstance(obj, str):
        s = obj.strip()
        if not s.startswith("{"):
            raise UnreadableResult("query result is not JSON (the text-table format is no longer read)")
        try:
            obj = json.loads(s)
        except json.JSONDecodeError as e:
            raise UnreadableResult(f"query result is not valid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise UnreadableResult(f"query result is a {type(obj).__name__}, not an object")
    result = obj.get("structuredContent")
    if not isinstance(result, dict) or "rows" not in result:
        content = obj.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            text = content[0].get("text", "")
            return _rows(text) if isinstance(text, str) and text.strip().startswith("{") else _fail_content()
        result = obj  # a bare result object
    rows = result.get("rows")
    if not isinstance(rows, list):
        raise UnreadableResult("query result has no `rows` list")
    total = result.get("total")
    if isinstance(total, int) and total > 0 and not rows:
        raise UnreadableResult(f"query result reports total={total} but carries no rows")
    out: list[list[str]] = []
    for r in rows:
        if not isinstance(r, list):
            raise UnreadableResult(f"row is a {type(r).__name__}, not a list")
        out.append(["" if v is None else str(v) for v in r])
    return out


def _fail_content() -> list[list[str]]:
    raise UnreadableResult("query result carries neither structuredContent.rows nor JSON text content")


def _dead_functions(all_rows: list[list[str]], called_rows: list[list[str]]) -> list[tuple[str, str]]:
    """`(qualified_name, file_path)` for every function with no caller — the
    set difference `all_functions - called - entry_points - builtins`. Pure:
    takes the two query results as rows, returns the dead set. `entry` is the
    string form of the tool's boolean (`"true"`/`"false"`, or Python's
    `True`/`False` stringified — both accepted)."""
    called = {r[0] for r in called_rows if r}
    dead: list[tuple[str, str]] = []
    for row in all_rows:
        if len(row) < 3:
            raise UnreadableResult(f"function row has {len(row)} columns, expected qn/entry/file: {row!r}")
        qn, entry, file = row[0], row[1].strip('"').lower(), row[2]
        if qn in called:
            continue                    # it has a caller — not dead
        if entry == "true":
            continue                    # a genuine entry point is not "dead"
        if qn.startswith("builtins.") or file.startswith("<"):
            continue                    # language builtins, not the build's code
        dead.append((qn, file))
    return dead


# ── the instrument ──────────────────────────────────────────────────────────

class CallGraphInstrument:
    """Drives `codebase-memory-mcp` to flag dead code (`fan_in=0`). `covers` the
    `call-graph` class. Raises `InstrumentUnavailable` for any environmental
    failure — including an answer it cannot read — so the panel records a
    coverage gap rather than crashing or reporting clean."""

    name = "call-graph"
    covers = "call-graph"

    def __init__(self, binary: str = _DEFAULT_BINARY, timeout: float = 180.0):
        self.binary = binary
        self.timeout = timeout

    def measure(self, build_dir: Path) -> list["Finding"]:
        exe = shutil.which(self.binary) or (self.binary if Path(self.binary).exists() else None)
        if exe is None:
            raise InstrumentUnavailable(
                f"codebase-memory-mcp not found ({self.binary!r}); `pip install codebase-memory-mcp`"
            )
        build_dir = Path(build_dir)
        project = None
        try:
            idx = self._call(exe, "index_repository", {"repo_path": str(build_dir)})
            project = (idx.get("structuredContent") or {}).get("project")
            if not project:
                raise InstrumentUnavailable(f"index_repository returned no project: {idx!r}")
            all_rows = self._query_rows(exe, project, _Q_ALL)
            called_rows = self._query_rows(exe, project, _Q_CALLED)
            dead = _dead_functions(all_rows, called_rows)
        except InstrumentUnavailable:
            raise
        except UnreadableResult as e:
            raise InstrumentUnavailable(f"could not read codebase-memory-mcp's output: {e}") from e
        except Exception as e:  # noqa: BLE001 — any drive failure is a coverage gap, not a crash
            raise InstrumentUnavailable(f"codebase-memory-mcp drive failed: {type(e).__name__}: {e}") from e
        finally:
            if project:
                self._call(exe, "delete_project", {"project": project}, tolerant=True)

        out: list[Finding] = []
        for qn, file in dead:
            out.append(Finding(
                instrument=self.name, artifact=file, metric="fan_in", value=0, severity="med",
                detail=f"{qn} has no callers (fan_in=0) — dead code the ranker would still 'find'; the box's decoy",
            ))
        return out

    # -- subprocess plumbing --------------------------------------------------

    def _call(self, exe: str, tool: str, args: dict, *, tolerant: bool = False) -> dict:
        # `--args-file`: the raw-JSON positional form prints a deprecation
        # warning and is slated for removal; a file survives that removal.
        fd, path = tempfile.mkstemp(prefix="forge-cbm-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(args, fh)
            try:
                proc = subprocess.run(
                    [exe, "cli", "--json", tool, "--args-file", path],
                    capture_output=True, text=True, timeout=self.timeout,
                )
            except (subprocess.TimeoutExpired, OSError) as e:
                if tolerant:
                    return {}
                raise InstrumentUnavailable(f"{tool} failed to run: {e}") from e
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        for line in reversed(proc.stdout.splitlines()):  # last JSON line; skip log/hint lines
            line = line.strip()
            if line.startswith("{"):
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    break
                if d.get("isError") and not tolerant:
                    raise InstrumentUnavailable(f"{tool} error: {d.get('structuredContent') or d.get('content')}")
                return d
        if tolerant:
            return {}
        raise InstrumentUnavailable(f"{tool}: no JSON in output (exit {proc.returncode})")

    def _query_rows(self, exe: str, project: str, query: str) -> list[list[str]]:
        return _rows(self._call(exe, "query_graph", {"project": project, "query": query}))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(prog="instrument_callgraph.py")
    p.add_argument("build_dir")
    p.add_argument("--binary", default=_DEFAULT_BINARY)
    a = p.parse_args()
    for f in CallGraphInstrument(binary=a.binary).measure(Path(a.build_dir)):
        print(f"{f.artifact}: {f.detail}")
