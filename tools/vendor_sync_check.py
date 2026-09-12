#!/usr/bin/env python3
"""Every vendored — or canonical-here — body named in tools/vendor_manifest.json
still hashes to what the manifest pins. Exit non-zero naming every drift.

WHY THIS EXISTS
---------------
This repo had a tools/vendor_sync_check.py before: 308 lines that diffed the
three modules vendored from willow-mcp against a willow-mcp checkout on disk
(and skipped without one), retired on 2026-09-02 (a9ee4c2) when those modules
came home and willow-mcp began importing them — "there is no copy left to
keep honest". That reasoning missed one: forge/friction_floor.py is still a
copy of willow-gate's scorer, and the same commit's claim that it was
byte-for-byte with willow-gate was measured false on 2026-09-12 (#25).
Meanwhile two test docstrings (tests/test_no_reach_back.py,
tests/test_human_loop.py) went on citing the retired script as what enforced
their contracts, and the only live guards were downstream: willow-mcp pins
friction_floor's body by SHA-256 (its tests/test_stance_friction.py) and
identity-checks human_loop and model_egress (its tests/test_forge_take.py).
Nothing here would notice a drift until a consumer's release broke.

This is the checker those docstrings named, back under the same name and
built differently on purpose: the old one needed the upstream checkout to
compare against, so it could not run in CI and skipped on every machine
without one; this one pins hashes in a manifest and needs nothing but the
tree. The manifest is the one place a pinned hash lives, and a deliberate
change is `--print`, paste, and a note saying why.

WHAT A PIN MEANS
----------------
Each manifest entry pins a `path` to a `sha256` of its *body* — the whole file
when `body_from` is null, else from the first line that reads exactly
`body_from` through EOF. A body pin lets the header comment above a vendored
docstring be corrected (as #25 did on friction_floor.py) without moving the
bytes a consumer hashes. `origin` is `<org/repo>:<path>` for a copy taken from
elsewhere, or `self` when this repo IS the canonical home and the pin exists
so a change here is noticed as the fleet event it is.

USAGE
-----
    python tools/vendor_sync_check.py            # exit 1 naming every drift
    python tools/vendor_sync_check.py --print    # current hashes, to paste
    python tools/vendor_sync_check.py --manifest M --root DIR   # for the tests
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "tools" / "vendor_manifest.json"


def pinned_body(text: str, body_from: str | None) -> str:
    """The slice of `text` the manifest pins: all of it when `body_from` is
    None, else from the first line reading exactly `body_from` through EOF."""
    if body_from is None:
        return text
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.rstrip("\r\n") == body_from:
            return text[offset:]
        offset += len(line)
    raise ValueError(f"no line reads {body_from!r}, so there is no body to pin")


def body_hash(root: Path, entry: dict) -> str:
    text = (root / entry["path"]).read_text(encoding="utf-8")
    body = pinned_body(text, entry.get("body_from"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _advice(entry: dict) -> str:
    if entry["origin"] == "self":
        return (
            "this repo is the canonical home: update the manifest with the "
            "decision (`--print`), and tell the consumers — it is a fleet event"
        )
    return f"re-sync from {entry['origin']}, or update the manifest with the decision"


def drifts(manifest: Path = MANIFEST, root: Path = REPO) -> list[str]:
    """One line per pinned body that is missing, unsliceable, or hashes
    differently from its pin. Empty means every pin holds."""
    problems: list[str] = []
    for entry in json.loads(manifest.read_text(encoding="utf-8"))["pins"]:
        path = entry["path"]
        try:
            actual = body_hash(root, entry)
        except FileNotFoundError:
            problems.append(f"{path}: file is missing — {_advice(entry)}")
            continue
        except ValueError as exc:
            problems.append(f"{path}: {exc} — {_advice(entry)}")
            continue
        if actual != entry["sha256"]:
            problems.append(f"{path}: pinned {entry['sha256']}, found {actual} — {_advice(entry)}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--root", type=Path, default=REPO)
    ap.add_argument(
        "--print",
        action="store_true",
        dest="show",
        help="print each pin's current hash instead of checking",
    )
    args = ap.parse_args(argv)
    if args.show:
        for entry in json.loads(args.manifest.read_text(encoding="utf-8"))["pins"]:
            try:
                print(f"{body_hash(args.root, entry)}  {entry['path']}")
            except (FileNotFoundError, ValueError) as exc:
                print(f"{'?' * 64}  {entry['path']}  ({exc})")
        return 0
    problems = drifts(args.manifest, args.root)
    for line in problems:
        print(f"vendor drift: {line}", file=sys.stderr)
    if problems:
        return 1
    print(f"vendor pins hold: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
