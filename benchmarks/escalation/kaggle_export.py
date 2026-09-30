#!/usr/bin/env python3
"""Export the escalation prompts for a hosted run (stdlib only).

A hosted runner (Kaggle Benchmarks) cannot import this repo, so the prompts travel as
data: one JSON line per fixture item, in ``<shape>.jsonl``::

    {"id", "shape", "messages": [{"role": "system", ...}, {"role": "user", ...}], "schema"}

``messages`` is exactly what ``runner.build_chat_payload`` sends for a model that is not
Qwen (no ``/no_think`` suffix), built by calling the runner's own functions, so the
hosted prompt and the local prompt cannot drift. ``schema`` is the runner's
``ANSWER_SCHEMA``. The answer key never leaves: ``expected``, ``answerable`` and
``rationale`` are not exported, and each line is checked against an exact key set before
it is written.

Usage: ``python kaggle_export.py --out STAGING_DIR``. The staging directory must be
outside every git tree, so an export can never be committed by accident.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import runner  # noqa: E402

BENCH = _HERE
SHAPES = runner.SHAPES
EXPORT_KEYS = ("id", "messages", "schema", "shape")
#: A model name that is not Qwen, so the runner adds no model-specific suffix.
NEUTRAL_MODEL = "hosted-export"


def inside_git_tree(path: Path) -> bool:
    """Whether ``path`` (which need not exist yet) sits under a directory with a ``.git``."""
    resolved = path.resolve()
    return any((d / ".git").exists() for d in (resolved, *resolved.parents))


def export_item(shape: str, item: dict, system: str) -> dict:
    """One exported line for one fixture item."""
    user = runner.user_prompt(shape, item)
    payload = runner.build_chat_payload(NEUTRAL_MODEL, system, user)
    line = {
        "id": item["id"],
        "shape": shape,
        "messages": payload["messages"],
        "schema": payload["format"],
    }
    if tuple(sorted(line)) != EXPORT_KEYS:  # pragma: no cover - guards future edits
        raise ValueError(f"export keys drifted: {sorted(line)}")
    return line


def export_shape(shape: str, bench: Path = BENCH) -> list[dict]:
    system = runner.system_prompt(shape, bench)
    return [export_item(shape, item, system) for item in runner.load_fixtures(shape, bench)]


def write_export(out: Path, bench: Path = BENCH, shapes=SHAPES) -> dict[str, int]:
    """Write ``<shape>.jsonl`` into ``out``; return {shape: line count}."""
    if inside_git_tree(out):
        raise ValueError("the export directory must be outside every git tree")
    out.mkdir(parents=True, exist_ok=True)
    counts = {}
    for shape in shapes:
        lines = export_shape(shape, bench)
        text = "".join(json.dumps(line, sort_keys=True) + "\n" for line in lines)
        (out / f"{shape}.jsonl").write_text(text, encoding="utf-8", newline="\n")
        counts[shape] = len(lines)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="staging directory (outside git)")
    ap.add_argument("--bench", type=Path, default=BENCH, help="benchmark directory override")
    args = ap.parse_args(argv)
    try:
        counts = write_export(args.out, args.bench)
    except ValueError as exc:
        print(f"kaggle_export: {exc}", file=sys.stderr)
        return 2
    print(f"exported {sum(counts.values())} items to {args.out}: {counts}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
