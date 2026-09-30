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
* truncated: rows without an error whose ``done_reason`` is ``length`` (the reply hit
  the runner's output cap). A count, not a rate; such a row is scored as usual, so a
  truncation shows up here instead of passing silently as an unparseable reply.
* Brier score and a 5-bin reliability table, computed here in the standard library.
  Brier = mean((confidence - outcome) ** 2), where outcome is 1 when the answer was
  right (an ``ESCALATE`` on an unanswerable item is right) and 0 when it was not.
  Confidence is clamped to [0.5, 0.99]; rows without a numeric confidence are left out.

Equality by shape: route = tool and args exact; classify = all three fields exact;
judge = label exact; ground = normalized exact (case, spacing and edge punctuation).

Each rate carries its Wilson 95% interval (``*_ci``, ``{"lo", "hi"}`` or null when the
denominator is 0). Two optional statistics, printed after the table (md) or under the
``_stats`` key (json):

* ``--pair A B``: exact McNemar test (two-sided binomial on the discordant items) between
  two models on the unanswerable items both answered with a parsed reply. ``b`` counts
  items where A refused and B did not, ``c`` the reverse. One row per model and item
  is used; if a file carries several, the last one wins.
* ``--rank``: Spearman correlation between task score and false-confidence rate across
  models (the ``all`` line), with a percentile bootstrap 95% interval over models
  (``--resamples``, default 10000, ``--seed``, default 0).

Usage: ``python aggregate.py rows.jsonl [more.jsonl ...] [--format md|json]
[--pair A B] [--rank] [--seed N]``
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
Z95 = 1.96
DEFAULT_SEED = 0
DEFAULT_RESAMPLES = 10_000
ESCALATE = "ESCALATE"
SHAPES = ("route", "classify", "judge", "ground")
CONF_LO, CONF_HI = 0.5, 0.99
# Five equal-width reliability bins over the confidence range [0.5, 0.99]; the last
# bin's upper edge is 1.0 so a stated confidence of 0.99 falls inside it.
BIN_EDGES = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
_EPS = 1e-9


# --- calibration: Brier, log score and reliability bins (standard library) ---------
#
# A pair is (confidence, outcome): the confidence the model stated for its answer and
# whether that answer was right.
#   Brier     = mean((p - y) ** 2), with p the stated confidence and y in {0, 1}.
#               0 is perfect, 0.25 is a coin flip at 50%, 1 is confidently wrong.
#   Log score = mean(-ln(likelihood of the outcome under p)), p floored at 1e-9.
#   Bins      = per confidence band, the count, the mean stated confidence and the
#               share of answers that were right.


def _brier_term(confidence: float, outcome: bool) -> float:
    return (confidence - (1.0 if outcome else 0.0)) ** 2


def _log_term(confidence: float, outcome: bool) -> float:
    p = confidence if outcome else 1.0 - confidence
    return -math.log(max(p, _EPS))


def _reliability_bins(pairs: list[tuple[float, bool]]) -> list[dict]:
    out = []
    for lo, hi in zip(BIN_EDGES, BIN_EDGES[1:]):
        members = [(c, o) for c, o in pairs if lo <= c < hi or (hi == 1.0 and c == 1.0)]
        n = len(members)
        out.append(
            {
                "lo": lo,
                "hi": hi,
                "n": n,
                "mean_confidence": sum(c for c, _ in members) / n if n else None,
                "hit_rate": sum(1 for _, o in members if o) / n if n else None,
            }
        )
    return out


def _calibration_summary(pairs: list[tuple[float, bool]]) -> dict:
    n = len(pairs)
    if not n:
        return {"n": 0, "brier": None, "log_score": None, "overconfidence": None}
    mean_conf = sum(c for c, _ in pairs) / n
    hit_rate = sum(1 for _, o in pairs if o) / n
    return {
        "n": n,
        "brier": sum(_brier_term(c, o) for c, o in pairs) / n,
        "log_score": sum(_log_term(c, o) for c, o in pairs) / n,
        "overconfidence": mean_conf - hit_rate,
    }


# --- intervals and tests (standard library) -----------------------------------


def wilson_interval(k: int, n: int, z: float | None = None) -> dict | None:
    """Wilson score interval for k successes in n trials; None when n is 0."""
    if not n:
        return None
    z = Z95 if z is None else z
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"lo": max(0.0, centre - half), "hi": min(1.0, centre + half)}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p on b and c discordant items: binomial(b + c, 0.5)."""
    n = b + c
    if not n:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def _unanswerable_outcomes(rows: list[dict], truth: dict[str, dict], model) -> dict[str, bool]:
    """{fixture_id: escalated} for the model's parsed replies on unanswerable items."""
    out: dict[str, bool] = {}
    for row in rows:
        t = truth.get(row.get("fixture_id"))
        if row.get("model") != model or t is None or t["answerable"]:
            continue
        if row.get("error") or not row.get("parse_ok"):
            continue
        out[row["fixture_id"]] = is_escalate(row.get("answer"))
    return out


def pair_test(rows: list[dict], truth: dict[str, dict], model_a, model_b) -> dict:
    """McNemar between two models on their shared unanswerable items."""
    a = _unanswerable_outcomes(rows, truth, model_a)
    b = _unanswerable_outcomes(rows, truth, model_b)
    shared = sorted(a.keys() & b.keys())
    only_a = sum(1 for f in shared if a[f] and not b[f])  # A refused, B did not
    only_b = sum(1 for f in shared if b[f] and not a[f])
    return {
        "model_a": model_a,
        "model_b": model_b,
        "n_shared": len(shared),
        "n_discordant": only_a + only_b,
        "b": only_a,
        "c": only_b,
        "p_value": mcnemar_exact(only_a, only_b),
    }


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rho (Pearson on average ranks); None under 3 points or a constant side."""
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    rx, ry = _average_ranks(xs), _average_ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if not sxx or not syy:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / math.sqrt(sxx * syy)


def bootstrap_spearman(
    xs: list[float], ys: list[float], resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED
) -> dict:
    """Spearman rho with a percentile 95% bootstrap interval, resampling models."""
    rho = spearman(xs, ys)
    out = {"n_models": len(xs), "rho": rho, "ci": None, "n_resamples": resamples, "seed": seed}
    if rho is None:
        return out
    rng = random.Random(seed)
    rhos = []
    for _ in range(resamples):
        idx = [rng.randrange(len(xs)) for _ in xs]
        r = spearman([xs[i] for i in idx], [ys[i] for i in idx])
        if r is not None:
            rhos.append(r)
    out["n_valid_resamples"] = len(rhos)
    if rhos:
        rhos.sort()
        out["ci"] = {
            "lo": rhos[min(len(rhos) - 1, int(0.025 * len(rhos)))],
            "hi": rhos[min(len(rhos) - 1, int(0.975 * len(rhos)))],
        }
    return out


def rank_test(result: dict, resamples: int = DEFAULT_RESAMPLES, seed: int = DEFAULT_SEED) -> dict:
    """Task score against false-confidence rate across models' ``all`` lines."""
    models, xs, ys = [], [], []
    for model, cells in result.items():
        c = cells["all"]
        if c["task_score"] is not None and c["false_confidence_rate"] is not None:
            models.append(model)
            xs.append(c["task_score"])
            ys.append(c["false_confidence_rate"])
    out = bootstrap_spearman(xs, ys, resamples, seed)
    out["models"] = models
    return out


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
    n_rows = n_errors = n_unparseable = n_unknown = n_truncated = 0
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
        if row.get("done_reason") == "length":
            n_truncated += 1
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
    summary = _calibration_summary(pairs)
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
        "n_truncated": n_truncated,
        "n_calibrated": summary["n"],
        "brier": summary["brier"],
        "log_score": summary["log_score"],
        "overconfidence": summary["overconfidence"],
        "reliability": _reliability_bins(pairs),
        "task_score_ci": wilson_interval(n_correct, n_answerable),
        "false_confidence_ci": wilson_interval(n_false_confident, n_unanswerable_parsed),
        "over_escalation_ci": wilson_interval(n_escalated, n_answerable_parsed),
        "unparseable_ci": wilson_interval(n_unparseable, scored),
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


def _ci(interval: dict | None) -> str:
    if interval is None:
        return "-"
    return f"[{interval['lo'] * 100:.1f}%, {interval['hi'] * 100:.1f}%]"


def to_markdown(result: dict, stats: dict | None = None) -> str:
    lines = [
        "| Model | Shape | Task score | False-confidence | Over-escalation | Unparseable "
        "| Truncated | Errors | Brier | Task 95% CI | False-confidence 95% CI "
        "| Over-escalation 95% CI | Unparseable 95% CI |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
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
                f"| {c['n_truncated']} "
                f"| {c['n_errors']} "
                f"| {_num(c['brier'])} "
                f"| {_ci(c['task_score_ci'])} | {_ci(c['false_confidence_ci'])} "
                f"| {_ci(c['over_escalation_ci'])} | {_ci(c['unparseable_ci'])} |"
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
        "Truncated counts replies that stopped at the output cap (done_reason length); "
        "they are scored like any other reply, most often as unparseable. "
        "Brier = mean((confidence - outcome) ** 2), confidence clamped to [0.5, 0.99]. "
        "Intervals are Wilson 95% (z = 1.96) on each rate's own counts.",
    ]
    for key, block in (stats or {}).items():
        lines.append("")
        if key == "pair":
            lines += [
                f"McNemar (exact, two-sided) on shared unanswerable items, {block['model_a']} "
                f"vs {block['model_b']}: {block['n_shared']} shared, b = {block['b']} "
                f"({block['model_a']} refused, {block['model_b']} did not), c = {block['c']}, "
                f"p = {block['p_value']:.4f}.",
            ]
        elif key == "rank":
            ci = block["ci"]
            span = "-" if ci is None else f"[{ci['lo']:.3f}, {ci['hi']:.3f}]"
            lines += [
                f"Spearman, task score against false-confidence rate across "
                f"{block['n_models']} models: rho = {_num(block['rho'])}, bootstrap 95% "
                f"interval over models {span} ({block['n_resamples']} resamples, "
                f"seed {block['seed']}).",
            ]
    return "\n".join(lines) + "\n"


def to_json(result: dict, stats: dict | None = None) -> str:
    payload = dict(result)
    if stats:
        payload["_stats"] = stats
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("rows", nargs="+", type=Path, help="JSONL rows written by runner.py")
    ap.add_argument("--format", choices=("md", "json"), default="md")
    ap.add_argument("--fixtures", type=Path, default=None, help="fixtures directory override")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"), help="exact McNemar between two models")
    ap.add_argument("--rank", action="store_true", help="Spearman + bootstrap over models")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED, help="bootstrap seed (default 0)")
    ap.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    args = ap.parse_args(argv)
    rows, truth = read_rows(args.rows), load_truth(args.fixtures)
    result = aggregate(rows, truth)
    stats: dict = {}
    if args.pair:
        stats["pair"] = pair_test(rows, truth, *args.pair)
    if args.rank:
        stats["rank"] = rank_test(result, args.resamples, args.seed)
    sys.stdout.write(to_markdown(result, stats) if args.format == "md" else to_json(result, stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
