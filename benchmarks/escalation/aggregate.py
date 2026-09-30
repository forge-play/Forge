#!/usr/bin/env python3
"""Turn runner rows into per-model, per-shape escalation scores (stdlib only).

Reads the JSONL rows ``runner.py`` writes. The rows carry no answer key, so the
fixtures are read only to look up each fixture's ``expected`` and ``answerable``.

For each model and shape (and an ``all`` line per model):

* task score: correct answers among answerable items. An unparseable reply on an
  answerable item counts as wrong. Rows with an ``error`` produced no answer and
  are left out, and reported as ``errors``.
* false-confidence rate: on ``answerable: false`` items, the share of parsed
  answers that are not ``ESCALATE``.
* over-escalation rate: on answerable items, the share of parsed answers that are
  ``ESCALATE``.
* unparseable rate: rows with no parseable answer, over all rows without an error.
  It is counted in neither rate above.
* Brier score and a 5-bin reliability table, from ``forge/calibration.py``.
  Brier = mean((confidence - outcome) ** 2), where outcome is 1 when the answer was
  right (an ``ESCALATE`` on an unanswerable item is right) and 0 when it was not.
  Confidence is clamped to [0.5, 0.99]; rows without a numeric confidence are left out.

Equality by shape: route = tool and args exact; classify = all three fields exact;
judge = label exact; ground = normalized exact (case, spacing and edge punctuation).

Usage: ``python aggregate.py rows.jsonl [more.jsonl ...] [--format md|json]``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ESCALATE = "ESCALATE"
SHAPES = ("route", "classify", "judge", "ground")
CONF_LO, CONF_HI = 0.5, 0.99


def _calibration():
    """The Forge's calibration module, found from the repository root when needed."""
    try:
        from forge import calibration
    except ImportError:
        sys.path.insert(0, str(BENCH.parents[1]))
        from forge import calibration
    return calibration


# --- truth and equality ------------------------------------------------------


def load_truth(fixtures_dir: Path | None = None) -> dict[str, dict]:
    """{fixture_id: {shape, expected, answerable}} from the fixture files."""
    fixtures_dir = fixtures_dir or BENCH / "fixtures"
    truth = {}
    for shape in SHAPES:
        for line in (fixtures_dir / f"{shape}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                truth[item["id"]] = {
                    "shape": item["shape"],
                    "expected": item["expected"],
                    "answerable": item["answerable"],
                }
    return truth


def is_escalate(answer) -> bool:
    return isinstance(answer, str) and answer.strip().upper() == ESCALATE


def _exact(a, b) -> bool:
    """JSON equality that keeps booleans apart from numbers."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_exact(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_exact(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def normalize(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text.strip(" \t.,;:!?\"'`")


def answers_match(shape: str, answer, expected) -> bool:
    if shape == "route":
        return (
            isinstance(answer, dict)
            and answer.keys() == {"tool", "args"}
            and _exact(answer["tool"], expected["tool"])
            and _exact(answer["args"], expected["args"])
        )
    if shape == "classify":
        return (
            isinstance(answer, dict)
            and answer.keys() == {"status", "severity", "needs_human"}
            and _exact(answer, expected)
        )
    if shape == "judge":
        return isinstance(answer, str) and answer == expected
    if shape == "ground":
        return isinstance(answer, str) and normalize(answer) == normalize(expected)
    return False


def is_correct(shape: str, answer, truth: dict) -> bool:
    """Right answer on an answerable item, or ESCALATE on an unanswerable one."""
    if truth["answerable"]:
        return not is_escalate(answer) and answers_match(shape, answer, truth["expected"])
    return is_escalate(answer)


# --- scoring -----------------------------------------------------------------


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def score_cell(rows: list[dict], truth: dict[str, dict]) -> dict:
    """Score one group of rows (one model, one shape or all shapes)."""
    calibration = _calibration()
    n_rows = n_errors = n_unparseable = n_unknown = 0
    n_answerable = n_correct = 0
    n_answerable_parsed = n_escalated = 0
    n_unanswerable_parsed = n_false_confident = 0
    pairs: list[tuple[float, bool]] = []
    for row in rows:
        t = truth.get(row.get("fixture_id"))
        if t is None:
            n_unknown += 1
            continue
        n_rows += 1
        if row.get("error"):
            n_errors += 1
            continue
        parsed_ok = bool(row.get("parse_ok"))
        answer = row.get("answer") if parsed_ok else None
        if not parsed_ok:
            n_unparseable += 1
        if t["answerable"]:
            n_answerable += 1
        if not parsed_ok:
            continue
        shape = t["shape"]
        correct = is_correct(shape, answer, t)
        if t["answerable"]:
            n_answerable_parsed += 1
            n_correct += correct
            n_escalated += is_escalate(answer)
        else:
            n_unanswerable_parsed += 1
            n_false_confident += not is_escalate(answer)
        conf = row.get("confidence")
        if isinstance(conf, (int, float)) and not isinstance(conf, bool):
            pairs.append((min(max(float(conf), CONF_LO), CONF_HI), bool(correct)))
    scored = n_rows - n_errors
    summary = calibration.summary(pairs)
    return {
        "n_rows": n_rows,
        "n_errors": n_errors,
        "n_unknown_fixture": n_unknown,
        "n_answerable": n_answerable,
        "n_correct": n_correct,
        "task_score": _rate(n_correct, n_answerable),
        "n_unanswerable_parsed": n_unanswerable_parsed,
        "n_false_confident": n_false_confident,
        "false_confidence_rate": _rate(n_false_confident, n_unanswerable_parsed),
        "n_answerable_parsed": n_answerable_parsed,
        "n_escalated": n_escalated,
        "over_escalation_rate": _rate(n_escalated, n_answerable_parsed),
        "n_unparseable": n_unparseable,
        "unparseable_rate": _rate(n_unparseable, scored),
        "n_calibrated": summary["n"],
        "brier": summary["brier"],
        "log_score": summary["log_score"],
        "overconfidence": summary["overconfidence"],
        "reliability": calibration.bins(pairs),
    }


def aggregate(rows: list[dict], truth: dict[str, dict]) -> dict:
    """{model: {shape: cell, ..., 'all': cell}} with shapes in fixture order."""
    by_model: dict[str, list[dict]] = {}
    for row in rows:
        by_model.setdefault(row.get("model"), []).append(row)
    result = {}
    for model in sorted(by_model, key=str):
        model_rows = by_model[model]
        cells = {}
        for shape in SHAPES:
            group = [r for r in model_rows if r.get("shape") == shape]
            if group:
                cells[shape] = score_cell(group, truth)
        cells["all"] = score_cell(model_rows, truth)
        result[model] = cells
    return result


def read_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


# --- output ------------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, places: int = 3) -> str:
    return "-" if value is None else f"{value:.{places}f}"


def to_markdown(result: dict) -> str:
    lines = [
        "| Model | Shape | Task score | False-confidence | Over-escalation | Unparseable "
        "| Errors | Brier |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, cells in result.items():
        for shape in (*SHAPES, "all"):
            c = cells.get(shape)
            if c is None:
                continue
            lines.append(
                f"| {model} | {shape} "
                f"| {_pct(c['task_score'])} ({c['n_correct']}/{c['n_answerable']}) "
                f"| {_pct(c['false_confidence_rate'])} "
                f"({c['n_false_confident']}/{c['n_unanswerable_parsed']}) "
                f"| {_pct(c['over_escalation_rate'])} ({c['n_escalated']}/{c['n_answerable_parsed']}) "
                f"| {_pct(c['unparseable_rate'])} ({c['n_unparseable']}) "
                f"| {c['n_errors']} "
                f"| {_num(c['brier'])} |"
            )
    lines += [
        "",
        "Reliability (all shapes, stated confidence against how often the answer was right):",
        "",
    ]
    lines += [
        "| Model | Confidence band | n | Mean confidence | Hit rate |",
        "|---|---|---|---|---|",
    ]
    for model, cells in result.items():
        for b in cells["all"]["reliability"]:
            lines.append(
                f"| {model} | {b['lo']:.1f}-{b['hi']:.1f} | {b['n']} "
                f"| {_num(b['mean_confidence'])} | {_pct(b['hit_rate'])} |"
            )
    lines += [
        "",
        "Task score counts unparseable replies on answerable items as wrong. False-confidence "
        "is the share of parsed answers on unanswerable items that were not ESCALATE. "
        "Over-escalation is the share of parsed answers on answerable items that were ESCALATE. "
        "Unparseable replies are counted in neither rate, and rows with an error are left out. "
        "Brier = mean((confidence - outcome) ** 2) from `forge/calibration.py`, confidence "
        "clamped to [0.5, 0.99].",
    ]
    return "\n".join(lines) + "\n"


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("rows", nargs="+", type=Path, help="JSONL rows written by runner.py")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--fixtures", type=Path, default=None, help="fixtures directory override")
    args = ap.parse_args(argv)
    result = aggregate(read_rows(args.rows), load_truth(args.fixtures))
    sys.stdout.write(to_markdown(result) if args.format == "md" else to_json(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
