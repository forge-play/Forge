"""Floor and consistency: two post-run views over the escalation rows.

Additive: imports aggregate.py and changes nothing in it. Every row stays in
the full table; these are selection views over it (amendment 2026-10-02).

  python reliability.py ROWS.jsonl [ROWS2.jsonl ...]            # floor
  python reliability.py --consistency RUN1.jsonl RUN2.jsonl ...  # k runs of one subset
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import aggregate as ag


def floor(result: dict) -> dict:
    """Per model: the worst shape on task score and on false confidence.

    `result` is aggregate.aggregate(rows, truth). Shapes with no measurable
    rate are skipped, never treated as 0 or 1."""
    out = {}
    for model, cells in result.items():
        shapes = {s: c for s, c in cells.items() if s != "all"}
        task = [(c["task_score"], s) for s, c in shapes.items() if c["task_score"] is not None]
        fc = [
            (c["false_confidence_rate"], s)
            for s, c in shapes.items()
            if c["false_confidence_rate"] is not None
        ]
        worst_task = min(task) if task else (None, None)
        worst_fc = max(fc) if fc else (None, None)
        out[model] = {
            "task_floor": worst_task[0],
            "task_floor_shape": worst_task[1],
            "task_floor_ci": shapes[worst_task[1]]["task_score_ci"] if worst_task[1] else None,
            "false_confidence_ceiling": worst_fc[0],
            "false_confidence_ceiling_shape": worst_fc[1],
            "false_confidence_ceiling_ci": (
                shapes[worst_fc[1]]["false_confidence_ci"] if worst_fc[1] else None
            ),
            "shapes_measured": len(task),
        }
    return out


def _canon(answer) -> str:
    return json.dumps(answer, sort_keys=True)


def _verdict(row: dict, t: dict) -> str:
    if row.get("error"):
        return "error"
    if not row.get("parse_ok"):
        return "unparseable"
    return "correct" if ag.is_correct(t["shape"], row.get("answer"), t) else "incorrect"


def consistency(runs: list[list[dict]], truth: dict[str, dict]) -> dict:
    """k runs of the same fixed subset, one row list per run.

    Per model: of the items present in every run, the share whose parsed answer
    is identical across all runs, and the share whose verdict flips. Error and
    unparseable are verdicts of their own, so they count as flips when mixed."""
    k = len(runs)
    per = {}  # (model, fixture_id) -> [row per run]
    for i, rows in enumerate(runs):
        for row in rows:
            key = (row.get("model"), row.get("fixture_id"))
            per.setdefault(key, [None] * k)[i] = row
    out: dict = {}
    for (model, fid), rows in sorted(per.items(), key=lambda x: (str(x[0][0]), str(x[0][1]))):
        t = truth.get(fid)
        if t is None or any(r is None for r in rows):
            continue
        m = out.setdefault(
            model,
            {"k": k, "n_items": 0, "n_identical": 0, "n_flipped": 0, "flipped_ids": []},
        )
        m["n_items"] += 1
        answers = {
            _canon(r.get("answer"))
            if r.get("parse_ok") and not r.get("error")
            else f"<{_verdict(r, t)}>"
            for r in rows
        }
        verdicts = {_verdict(r, t) for r in rows}
        m["n_identical"] += len(answers) == 1
        if len(verdicts) > 1:
            m["n_flipped"] += 1
            m["flipped_ids"].append(fid)  # kept by id: the flips are the tails
    for m in out.values():
        m["identical_rate"] = ag._rate(m["n_identical"], m["n_items"])
        m["identical_ci"] = ag.wilson_interval(m["n_identical"], m["n_items"])
        m["flip_rate"] = ag._rate(m["n_flipped"], m["n_items"])
        m["flip_ci"] = ag.wilson_interval(m["n_flipped"], m["n_items"])
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("rows", nargs="+", type=Path)
    p.add_argument(
        "--consistency",
        action="store_true",
        help="treat each file as one run of the same fixed subset",
    )
    a = p.parse_args()
    truth = ag.load_truth()
    if a.consistency:
        print(json.dumps(consistency([ag.read_rows([f]) for f in a.rows], truth), indent=2))
    else:
        print(json.dumps(floor(ag.aggregate(ag.read_rows(a.rows), truth)), indent=2))


if __name__ == "__main__":
    main()
