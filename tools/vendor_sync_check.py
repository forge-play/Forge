#!/usr/bin/env python3
"""tools/vendor_sync_check.py — has Forge's vendored code drifted from upstream?

The Forge vendors a handful of modules from willow-mcp (`friction_floor.py`,
`human_loop.py`, and the detection half of `model_egress.py`) rather than
depending on the package — see each file's own "vendor note" header for why.
The tradeoff that discipline accepts: a fix that lands upstream does NOT reach
the Forge for free. It already happened once (`human_loop.py`'s
`resolve_human_required` used to raise `HumanLoopError` on an unknown item;
willow-mcp changed that to a returned `{"error": ...}` dict and the Forge's
copy never got the memo — this script is what would have caught it).

This script re-derives the mapping from vendored Forge file -> upstream
willow-mcp source, strips each side down to the part that is actually meant
to be identical (the SAFE App Store vendor-note header block on the Forge
side; for the partial vendor, just the vendored functions), and diffs what's
left. It does not replace reading the vendor-note headers — it automates the
"did anything change" check they ask a maintainer to do by hand.

Usage:
    python tools/vendor_sync_check.py --upstream /path/to/willow-mcp
    python tools/vendor_sync_check.py --upstream /path/to/willow-mcp --quiet

Exit code 0: every vendored file matches its upstream source (module the
header block and the documented intentional differences). Exit code 1: at
least one file has drifted, or upstream/mapping could not be resolved.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── the vendor map ────────────────────────────────────────────────────────
#
# Two shapes of vendoring show up in forge/, found by grepping forge/*.py for
# "vendor"/"Vendored from" headers and checking which point at willow-mcp
# (as opposed to e.g. calibration.py, vendored from THIS repo's own
# apps/oakenscrolls-office/, or _ids.py, vendored from safe-app-store's
# principal.py — neither has a willow-mcp upstream to check against):
#
#   * FullFileVendor  — the whole file is copied byte-for-byte except a
#     Forge-specific header block bolted on top (human_loop.py,
#     friction_floor.py). Strip that block, diff the rest.
#
#   * PartialFunctionVendor — only specific top-level functions are copied
#     (model_egress.py vendors just `model_host`/`_addresses`/`is_local_host`,
#     deliberately leaving out upstream's `denial()` and its `consent`
#     import — see the file's own header for why). Compare function bodies
#     by name via the AST, not the whole file.


@dataclass(frozen=True)
class FullFileVendor:
    """A vendored file that is the upstream file plus a header block."""

    forge_path: str
    upstream_path: str
    # The Forge-side header to drop before comparing: everything from the
    # first line matching `strip_from` up to (not including) the first
    # SUBSEQUENT line matching `strip_until`. Both must match something, or
    # the check fails loudly rather than silently comparing the header too
    # (the header format changed and this mapping needs updating).
    strip_from: str
    strip_until: str
    kind: str = field(default="full", init=False)


@dataclass(frozen=True)
class PartialFunctionVendor:
    """Only named top-level functions are vendored, not the whole file."""

    forge_path: str
    upstream_path: str
    functions: tuple[str, ...]
    # Lines dropped from both sides' function bodies before comparing —
    # documented, intentional differences that aren't drift. Today that's
    # local `import`/`from ... import` statements the partial vendor needs
    # because it doesn't carry the source module's top-level imports along
    # with the functions it vendors.
    ignore_line_patterns: tuple[str, ...] = ()
    kind: str = field(default="partial", init=False)


VENDORED: list[FullFileVendor | PartialFunctionVendor] = [
    FullFileVendor(
        forge_path="forge/human_loop.py",
        upstream_path="src/willow_mcp/human_loop.py",
        strip_from=r"SAFE App Store vendor note",
        strip_until=r'^"""human_loop',
    ),
    FullFileVendor(
        forge_path="forge/friction_floor.py",
        upstream_path="src/willow_mcp/friction_floor.py",
        strip_from=r"SAFE App Store vendor note",
        strip_until=r"^# Vendored from willow-gate",
    ),
    PartialFunctionVendor(
        forge_path="forge/model_egress.py",
        upstream_path="src/willow_mcp/model_egress.py",
        functions=("model_host", "_addresses", "is_local_host"),
        ignore_line_patterns=(
            r"^\s*import socket\s*$",
            r"^\s*from urllib\.parse import urlparse\s*$",
        ),
    ),
]


# ── result plumbing ───────────────────────────────────────────────────────


@dataclass
class CheckResult:
    forge_path: str
    upstream_path: str
    in_sync: bool
    detail: str          # unified diff, or a human-readable error
    error: bool = False  # True if this is a "couldn't check" rather than a clean diff


def _read_lines(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _strip_header(lines: list[str], strip_from: str, strip_until: str) -> list[str] | str:
    """Drop the Forge-only header block. Returns the trimmed lines, or an
    error string if the markers weren't both found (header format drifted
    out from under this script's mapping)."""
    from_re, until_re = re.compile(strip_from), re.compile(strip_until)

    start = next((i for i, ln in enumerate(lines) if from_re.search(ln)), None)
    if start is None:
        return f"could not find header start marker {strip_from!r} — mapping is stale"

    end = next(
        (i for i in range(start + 1, len(lines)) if until_re.search(lines[i])),
        None,
    )
    if end is None:
        return f"could not find header end marker {strip_until!r} — mapping is stale"

    return lines[:start] + lines[end:]


def check_full_file(entry: FullFileVendor, forge_root: Path, upstream_root: Path) -> CheckResult:
    forge_file = forge_root / entry.forge_path
    upstream_file = upstream_root / entry.upstream_path

    forge_lines = _read_lines(forge_file)
    if forge_lines is None:
        return CheckResult(entry.forge_path, entry.upstream_path, False,
                            f"missing: {forge_file}", error=True)

    upstream_lines = _read_lines(upstream_file)
    if upstream_lines is None:
        return CheckResult(entry.forge_path, entry.upstream_path, False,
                            f"upstream missing: {upstream_file}", error=True)

    trimmed = _strip_header(forge_lines, entry.strip_from, entry.strip_until)
    if isinstance(trimmed, str):
        return CheckResult(entry.forge_path, entry.upstream_path, False, trimmed, error=True)

    if trimmed == upstream_lines:
        return CheckResult(entry.forge_path, entry.upstream_path, True, "")

    diff = "".join(difflib.unified_diff(
        upstream_lines, trimmed,
        fromfile=f"upstream:{entry.upstream_path}",
        tofile=f"forge:{entry.forge_path} (header stripped)",
    ))
    return CheckResult(entry.forge_path, entry.upstream_path, False, diff)


def _function_source(path: Path, name: str) -> str | None:
    """Source text of top-level function/async-function `name` in `path`, or
    None if the file doesn't parse or has no such function."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(path.read_text(encoding="utf-8"), node)
    return None


def _normalize(source: str, ignore_line_patterns: tuple[str, ...]) -> list[str]:
    patterns = [re.compile(p) for p in ignore_line_patterns]
    return [
        ln for ln in source.splitlines(keepends=True)
        if not any(p.search(ln) for p in patterns)
    ]


def check_partial(entry: PartialFunctionVendor, forge_root: Path, upstream_root: Path) -> CheckResult:
    forge_file = forge_root / entry.forge_path
    upstream_file = upstream_root / entry.upstream_path

    if not forge_file.is_file():
        return CheckResult(entry.forge_path, entry.upstream_path, False,
                            f"missing: {forge_file}", error=True)
    if not upstream_file.is_file():
        return CheckResult(entry.forge_path, entry.upstream_path, False,
                            f"upstream missing: {upstream_file}", error=True)

    diffs: list[str] = []
    for fn in entry.functions:
        forge_src = _function_source(forge_file, fn)
        upstream_src = _function_source(upstream_file, fn)

        if forge_src is None:
            diffs.append(f"--- def {fn}: missing from forge:{entry.forge_path}\n")
            continue
        if upstream_src is None:
            diffs.append(f"--- def {fn}: missing from upstream:{entry.upstream_path}\n")
            continue

        forge_lines = _normalize(forge_src, entry.ignore_line_patterns)
        upstream_lines = _normalize(upstream_src, entry.ignore_line_patterns)
        if forge_lines == upstream_lines:
            continue

        diffs.append("".join(difflib.unified_diff(
            upstream_lines, forge_lines,
            fromfile=f"upstream:{entry.upstream_path}::{fn}",
            tofile=f"forge:{entry.forge_path}::{fn}",
        )))

    if not diffs:
        return CheckResult(entry.forge_path, entry.upstream_path, True, "")
    return CheckResult(entry.forge_path, entry.upstream_path, False, "".join(diffs))


def run_checks(forge_root: Path, upstream_root: Path) -> list[CheckResult]:
    results = []
    for entry in VENDORED:
        if entry.kind == "full":
            results.append(check_full_file(entry, forge_root, upstream_root))
        else:
            results.append(check_partial(entry, forge_root, upstream_root))
    return results


# ── CLI ────────────────────────────────────────────────────────────────────


def _truncate(text: str, max_lines: int = 40) -> str:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    shown = "\n".join(lines[:max_lines])
    return f"{shown}\n... ({len(lines) - max_lines} more lines, run with the full diff for detail)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check whether the Forge's vendored files have drifted from "
                     "their willow-mcp upstream sources.",
    )
    parser.add_argument(
        "--upstream", required=True, type=Path,
        help="path to a willow-mcp checkout (the repo root, containing src/willow_mcp/)",
    )
    parser.add_argument(
        "--forge-root", type=Path, default=REPO_ROOT,
        help="path to the Forge repo root (default: this script's repo)",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="only print a one-line summary per file, no diffs",
    )
    args = parser.parse_args(argv)

    upstream_root = args.upstream.resolve()
    forge_root = args.forge_root.resolve()

    if not upstream_root.is_dir():
        print(f"vendor-sync: upstream path does not exist: {upstream_root}", file=sys.stderr)
        return 1

    results = run_checks(forge_root, upstream_root)

    drifted = [r for r in results if not r.in_sync]
    for r in results:
        status = "OK   " if r.in_sync else ("ERROR" if r.error else "DRIFT")
        print(f"[{status}] {r.forge_path}  <-  {r.upstream_path}")
        if not r.in_sync and not args.quiet:
            print(_truncate(r.detail))
            print()

    print(f"vendor-sync: {len(results) - len(drifted)}/{len(results)} in sync"
          + (f", {len(drifted)} drifted" if drifted else ""))

    return 1 if drifted else 0


if __name__ == "__main__":
    raise SystemExit(main())
