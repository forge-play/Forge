#!/usr/bin/env python3
"""Turn a ``kaggle b t download`` tree into runner-format rows (stdlib only).

The hosted tasks (``kaggle/<shape>_task.py``) record the raw reply text per item and
nothing else. This script reads the downloaded run files and writes the rows
``runner.py`` would have written, so the unchanged ``aggregate.py`` scores them.

The tree is what the download command lays out::

    <out>/<task>/<version>/<model>/<run_id>/<task>-<run>.run.json   (+ one file per item)

``<task>`` is ``escalation-<shape>``. A run's top-level file carries the items as
``subruns``; each item's result is a dict ``{item_id, text, error, tokens_in,
tokens_out, latency_ms}``. Item results are found by that content, never by file name:
the top-level file and the per-item files share a name prefix.

The download directory holds a normalized model name (``google/gemini-x`` becomes
``gemini-x``). The run file itself carries the platform's full slug in
``modelVersion.slug``; that is the model name the rows use. ``--model-from dir`` uses
the directory name instead.

One row per fixture item, in fixture order, per (task, model): the newest run wins
when a model has several. ``done_reason`` is the item's own if the run file carries one, else ``unknown``: the SDK
records no finish reason, and the aggregator reports that as unknown, not as no truncation.
An item whose call failed becomes a row with ``error`` set; an item with no result in
the files at all becomes one too, so it is counted rather than silently missing.

Usage: ``python kaggle_rows.py TREE --run-id ID [--out rows.jsonl] [--model-from file|dir]``.
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
TASK_PREFIX = "escalation-"
RUN_SUFFIX = ".run.json"
DONE_UNKNOWN = "unknown"  # aggregate.DONE_UNKNOWN
MISSING = "no result for this item in the downloaded run files"


def iter_runs(run: dict):
    """A run and every run nested under it."""
    yield run
    for sub in run.get("subruns") or []:
        yield from iter_runs(sub)


def item_result(run: dict) -> dict | None:
    """The per-item result dict of a run, or None when the run is not an item run."""
    for result in run.get("results") or []:
        value = result.get("dictResult") or result.get("dict_result")
        if isinstance(value, dict) and "item_id" in value:
            return value
    return None


def _slug(run: dict) -> str | None:
    slug = (run.get("modelVersion") or {}).get("slug")
    return slug if isinstance(slug, str) and slug else None


def _int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


class RunDir:
    """One downloaded run directory: its task, model and the item results inside it."""

    def __init__(self, task: str, version: str, model_dir: str, run_dir: str, files: list[Path]):
        self.task, self.version, self.model_dir, self.run_dir = task, version, model_dir, run_dir
        self.model_slug: str | None = None
        self.end_time = ""
        self.items: dict[str, dict] = {}
        for path in files:
            top = json.loads(path.read_text(encoding="utf-8"))
            if (top.get("taskVersion") or {}).get("name") == task:
                self.end_time = max(self.end_time, str(top.get("endTime") or ""))
            for run in iter_runs(top):
                self.model_slug = self.model_slug or _slug(run)
                found = item_result(run)
                if found is not None:
                    self.items[str(found["item_id"])] = found

    @property
    def shape(self) -> str | None:
        shape = self.task.removeprefix(TASK_PREFIX)
        return shape if self.task.startswith(TASK_PREFIX) and shape in runner.SHAPES else None


def find_run_dirs(tree: Path) -> list[RunDir]:
    groups: dict[tuple[str, str, str, str], list[Path]] = {}
    for path in sorted(tree.rglob(f"*{RUN_SUFFIX}")):
        parts = path.relative_to(tree).parts
        if len(parts) == 5:
            groups.setdefault(parts[:4], []).append(path)
    return [RunDir(*key, files) for key, files in sorted(groups.items())]


def newest_per_model(run_dirs: list[RunDir]) -> list[RunDir]:
    """One run dir per (task, model dir): the newest by end time, then by directory name."""
    best: dict[tuple[str, str], RunDir] = {}
    for rd in run_dirs:
        key = (rd.task, rd.model_dir)
        if key not in best or (rd.end_time, rd.run_dir) > (best[key].end_time, best[key].run_dir):
            best[key] = rd
    return [best[k] for k in sorted(best)]


def make_rows(rd: RunDir, run_id: str, model: str, bench: Path = BENCH) -> list[dict]:
    """One row per fixture item of the run dir's shape, in fixture order."""
    shape = rd.shape
    system = runner.system_prompt(shape, bench)
    rows = []
    for item in runner.load_fixtures(shape, bench):
        user = runner.user_prompt(shape, item)
        result = rd.items.get(item["id"])
        if result is not None and not result.get("error"):
            reply = {
                "text": result.get("text"),
                "tokens_in": _int(result.get("tokens_in")),
                "tokens_out": _int(result.get("tokens_out")),
            }
            row = runner.make_row(run_id, model, shape, item, system, user, lambda *_: reply)
            row["latency_ms"] = _int(result.get("latency_ms"))
            row["done_reason"] = _done_reason(result)
        else:
            row = runner.make_row(run_id, model, shape, item, system, user, _refusal)
            row["error"] = str((result or {}).get("error") or MISSING)
            row["latency_ms"] = _int((result or {}).get("latency_ms"))
        rows.append(row)
    return rows


def _done_reason(result: dict) -> str:
    """The item's finish reason if the run file carries one, else ``unknown``.

    kaggle-benchmarks 0.6.1 records no finish reason, so a hosted row is marked unknown
    rather than left null, which the aggregator would read like a local backend that
    reports none.
    """
    value = result.get("done_reason")
    return value if isinstance(value, str) and value else DONE_UNKNOWN


def _refusal(*_):
    raise RuntimeError("never called for its message")


def convert(tree: Path, run_id: str, model_from: str = "file", bench: Path = BENCH) -> list[dict]:
    rows: list[dict] = []
    for rd in newest_per_model(find_run_dirs(tree)):
        if rd.shape is None:
            print(
                f"kaggle_rows: skipping task {rd.task!r}: not an escalation task", file=sys.stderr
            )
            continue
        model = rd.model_dir if model_from == "dir" else (rd.model_slug or rd.model_dir)
        rows.extend(make_rows(rd, run_id, model, bench))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("tree", type=Path, help="the output directory of `kaggle b t download`")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", type=Path, default=None, help="rows file (default: stdout)")
    ap.add_argument("--model-from", choices=("file", "dir"), default="file")
    ap.add_argument("--bench", type=Path, default=BENCH, help="benchmark directory override")
    args = ap.parse_args(argv)
    if not args.tree.is_dir():
        ap.error(f"not a directory: {args.tree}")
    rows = convert(args.tree, args.run_id, args.model_from, args.bench)
    if not rows:
        print("kaggle_rows: no escalation run files found under the tree", file=sys.stderr)
        return 1
    text = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    if args.out:
        args.out.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)
    errors = sum(1 for row in rows if row["error"])
    print(f"wrote {len(rows)} rows ({errors} with an error)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
