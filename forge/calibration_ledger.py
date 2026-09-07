#!/usr/bin/env python3
"""forge/calibration_ledger.py — the model's confidence mirror
(docs/design/the-forge-measure.md, the `calibration` class).

The measuring panel refuses a confident wrong ARTIFACT; the checkpoint loop
refuses a confident wrong DECISION. This refuses a confident wrong PREDICTOR —
the model itself. It is the panel's `calibration` class, but it is NOT a per-build
instrument like `census`/`execution`: calibration is a claim about the model
ACROSS builds, so it is a longitudinal ledger, not a directory measurement.

The mechanism the box taught (oakenscrolls-office, the confidence mirror): a
prediction is a `(confidence, outcome)` pair — the model states P(true) for a
claim it makes while building ("this file parses", "this design holds", "this
dependency exists"), and later ground truth arrives (a test runs, the panel
measures, a human rules). Grade the model's stated confidence against what
actually happened: `brier`, `log_score`, and the reliability table (`bins`) —
all from the vendored `forge/calibration.py` (rule 11: the math is
oakenscrolls', not rebuilt here). The one signal that matters is
`overconfidence` — mean stated confidence minus actual hit rate; positive means
the model promises more than it delivers.

Persistence is the same per-builder SOIL file the governance layer already uses
(`forge/soil_store.py`, D6: a builder's records live in that builder's own file
by construction), under this module's own collection. The overconfidence signal
routes through `checkpoint_governance.route_nudge` (rule 11: reuse the deduped
outbox bite 3 / #67 and the panel already feed) — it surfaces a `review` item a
human should see; it NEVER blocks a build, exactly like every other model-side
signal.

Store-side (D1): `apps/the-forge/` never imports this — a sandboxed build does
not grade its own model's confidence, any more than it marks its own homework.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path



from . import calibration
from . import soil_store
from . import checkpoint_governance as governance

# Predictions live in this module's own collection inside the builder's SOIL
# file — alongside (never colliding with) the governance queue collection.
PREDICTIONS = "calibration_predictions"

# The overconfidence signal's defaults. `MIN_N` is the floor below which a
# scorecard is too thin to route on (two lucky calls are not a calibration);
# `OVERCONFIDENCE_FLOOR` is how far stated confidence may exceed hit rate before
# it is worth a human's eyes. Both are overridable per call.
MIN_N = 5
OVERCONFIDENCE_FLOOR = 0.10

# One standing open flag per builder: route_nudge dedupes by source_ref, so a
# persistently overconfident model surfaces ONE open `review` item, not a new
# one every resolve. When a human resolves that item and the model is still
# overconfident later, a fresh open item can form (route_nudge only dedupes
# against OPEN rows) — the correct "one live flag at a time" behavior.
_SIGNAL_SOURCE_REF_PREFIX = "calibration-overconfidence:"


class CalibrationLedgerError(Exception):
    """This module's own refusal — a confidence outside the believed-direction
    range, or a prediction lifecycle violation (re-predicting a settled claim,
    resolving an unknown or already-resolved one). `soil_store`'s
    `SoilStoreError` and `governance`'s errors propagate unwrapped."""


def _store(builder_id: str, root: Path | None):
    kw = {} if root is None else {"root": Path(root)}
    return soil_store.FilesystemSoilStore(builder_id, **kw)


def _check_confidence(confidence: float) -> float:
    """House convention (calibration D3): a claim is stated in the direction
    believed, so confidence is P(the claim is true) in [0.5, 1.0]. A value below
    0.5 means the model actually believes the claim FALSE — it must be restated
    in the believed direction, not recorded as a weak 'true'. Reject rather than
    silently clamp: a clamp would fabricate a data point the model never made."""
    try:
        c = float(confidence)
    except (TypeError, ValueError) as e:
        raise CalibrationLedgerError(f"confidence must be a number, got {confidence!r}") from e
    if not (0.5 <= c <= 1.0):
        raise CalibrationLedgerError(
            f"confidence {c} outside [0.5, 1.0] — state the claim in the "
            f"direction believed (calibration D3), a claim you think false is a "
            f"true-claim restated, not a confidence below 0.5"
        )
    return c


def _prediction_id(claim: str) -> str:
    """A stable id for a claim with no explicit id — deterministic (no wall
    clock, no randomness), so re-stating the same claim addresses the same
    pending prediction rather than spawning a duplicate."""
    h = hashlib.sha256(claim.encode("utf-8")).hexdigest()[:16]
    return f"pred-{h}"


def record_prediction(
    builder_id: str,
    claim: str,
    confidence: float,
    *,
    prediction_id: str | None = None,
    kind: str = "",
    decision_type: str = "",
    root: Path | None = None,
) -> dict:
    """Record the model's stated confidence in a claim, pending ground truth.

    `confidence` is P(claim true) in [0.5, 1.0]. Idempotent on the claim: with
    no `prediction_id`, the id is derived from the claim text, so re-stating the
    same claim UPDATES its (still-pending) confidence rather than duplicating it.
    Refuses to re-record a claim that has already been RESOLVED — a settled data
    point is history, not something a later re-prediction may overwrite.

    `decision_type` is recorded as its own field rather than left to be parsed
    back out of `claim`'s prefix — a decision_type containing a colon, or a
    reworded claim, breaks that parse silently. It is the coarse grouping axis
    `scorecard(group_by=...)` reads."""
    if not isinstance(claim, str) or not claim.strip():
        raise CalibrationLedgerError("claim must be a non-empty string")
    c = _check_confidence(confidence)
    pid = prediction_id or _prediction_id(claim)
    store = _store(builder_id, root)
    existing = store.get(PREDICTIONS, pid)
    if existing is not None and existing.get("resolved"):
        raise CalibrationLedgerError(
            f"prediction {pid!r} is already resolved (outcome="
            f"{existing.get('outcome')!r}) — a settled prediction is not "
            f"re-recordable; use a fresh prediction_id for a new claim"
        )
    record = {
        "id": pid,
        "claim": claim,
        "confidence": c,
        "kind": kind,
        "decision_type": decision_type,
        "outcome": None,
        "resolved": False,
        # ── the join, filled at RESOLVE time, not here ──────────────────────
        # A prediction is recorded BEFORE the ask, on purpose — that is what
        # makes it a prediction. The decision's `pair_id` does not exist until
        # the seal does, and the band is not known until the maker answers, so
        # neither can honestly be written now. `resolve_prediction` stamps them
        # when they are real. Declared here so a row's shape is one thing, and
        # so a never-resolved row plainly reads as unjoined.
        "decision_ref": "",
        "band": "",
        "matched_band": None,
        "match_confidence": None,
        "engagement": None,
    }
    store.put(PREDICTIONS, record, record_id=pid)
    return record


def resolve_prediction(
    builder_id: str,
    prediction_id: str,
    outcome: bool,
    *,
    decision: "object | None" = None,
    root: Path | None = None,
) -> dict:
    """Settle a pending prediction with ground truth (`outcome` True/False).

    Refuses an unknown id, and refuses to re-resolve an already-settled one — a
    double-resolve would silently rewrite history (the same single-use guard the
    governance resume seam already learned to keep).

    `decision` is the `checkpoint.CheckpointOutcome` the ask produced. Passing
    it stamps the join — `decision_ref` (its Nestor `pair_id`), the `band` that
    ran, the `matched_band` memory proposed, the raw `match_confidence`, and the
    seal-time `engagement` — so a later reader can ask "for decisions that took
    band X, what was the calibration outcome?" Duck-typed rather than imported
    to keep this module free of a checkpoint dependency (calibration is the
    lower layer; `build_loop` is what knows about both). Omitting it leaves the
    row unjoined, which is honest for a caller that has no decision to point at."""
    store = _store(builder_id, root)
    record = store.get(PREDICTIONS, prediction_id)
    if record is None:
        raise CalibrationLedgerError(f"no prediction {prediction_id!r} to resolve")
    if record.get("resolved"):
        raise CalibrationLedgerError(
            f"prediction {prediction_id!r} already resolved (outcome="
            f"{record.get('outcome')!r}) — a settled prediction is single-use"
        )
    record["outcome"] = bool(outcome)
    record["resolved"] = True
    if decision is not None:
        record["decision_ref"] = getattr(decision, "pair_id", "") or ""
        record["band"] = getattr(decision, "band", "") or ""
        record["matched_band"] = getattr(decision, "matched_band", None)
        record["match_confidence"] = getattr(decision, "match_confidence", None)
        record["engagement"] = getattr(decision, "engagement", None)
        if not record.get("decision_type"):
            record["decision_type"] = getattr(decision, "decision_type", "") or ""
    store.put(PREDICTIONS, record, record_id=prediction_id)
    return record


def scorecard(builder_id: str, *, group_by: str = "", root: Path | None = None) -> dict:
    """The model's calibration mirror: the `calibration.summary` header (brier,
    log_score, hit_rate, overconfidence) plus the `calibration.bins` reliability
    table, over the builder's RESOLVED predictions, with a pending count so a
    thin scorecard reads as thin, not as confident.

    `group_by` names a row field (`"band"`, `"matched_band"`, `"decision_type"`,
    `"kind"`) and adds a `groups` mapping of that field's values to their own
    summary/bins. The maths is unchanged — `calibration.summary` per group, no
    new estimator. The ungrouped header always stays, so a grouped read can
    never be mistaken for the whole picture.

    Rows written before a field existed simply have no value for it and land
    under `""`/`None` rendered as `"(unset)"` — reported as its own group rather
    than silently folded into another, because "we did not record this" is not
    a band."""
    store = _store(builder_id, root)
    all_recs = store.all(PREDICTIONS)
    resolved = [r for r in all_recs if r.get("resolved")]
    pairs = [(float(r["confidence"]), bool(r["outcome"])) for r in resolved]
    card = {
        "builder_id": store.builder_id,
        "resolved": len(pairs),
        "pending": sum(1 for r in all_recs if not r.get("resolved")),
        "summary": calibration.summary(pairs),
        "bins": calibration.bins(pairs),
    }
    if group_by:
        groups: dict[str, list[tuple[float, bool]]] = {}
        for r in resolved:
            key = r.get(group_by)
            key = "(unset)" if key in (None, "") else str(key)
            groups.setdefault(key, []).append((float(r["confidence"]), bool(r["outcome"])))
        card["group_by"] = group_by
        card["groups"] = {
            k: {"n": len(v), "summary": calibration.summary(v), "bins": calibration.bins(v)}
            for k, v in sorted(groups.items())
        }
    return card


def overconfidence_signal(
    builder_id: str,
    *,
    root: Path | None = None,
    min_n: int = MIN_N,
    floor: float = OVERCONFIDENCE_FLOOR,
) -> dict | None:
    """Route ONE `review` nudge when the model is measurably overconfident.

    Fires only when there are at least `min_n` resolved predictions (a thin
    record is not a calibration) AND `overconfidence` (mean stated confidence −
    hit rate) is at least `floor`. Reuses `checkpoint_governance.route_nudge`,
    so it is deduped by a per-builder `source_ref` (one standing open flag) and
    persisted in the same `human_required` queue every other model-side signal
    feeds. Returns the routed item, or None when the bar is not met OR the flag
    is already open (route_nudge's dedupe). NEVER blocks — it surfaces."""
    card = scorecard(builder_id, root=root)
    n = card["resolved"]
    over = card["summary"]["overconfidence"]
    if n < min_n or over is None or over < floor:
        return None
    return governance.route_nudge(
        builder_id,
        kind="review",
        title="model overconfidence",
        summary=(
            f"calibration: {n} resolved predictions, stated confidence "
            f"{card['summary']['mean_confidence']:.2f} vs hit rate "
            f"{card['summary']['hit_rate']:.2f} (overconfidence {over:+.2f}, "
            f"brier {card['summary']['brier']:.3f}). The model promises more "
            f"than it delivers — a human should recalibrate what it asserts."
        ),
        source_ref=f"{_SIGNAL_SOURCE_REF_PREFIX}{card['builder_id']}",
        priority="normal",
        root=soil_store.DEFAULT_CHECKPOINT_ROOT if root is None else Path(root),
    )


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cmd_record(args: argparse.Namespace) -> int:
    rec = record_prediction(
        args.builder_id, args.claim, args.confidence,
        prediction_id=args.id, kind=args.kind or "", root=Path(args.root) if args.root else None,
    )
    print(json.dumps(rec, indent=2))
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    rec = resolve_prediction(
        args.builder_id, args.id, args.outcome == "true",
        root=Path(args.root) if args.root else None,
    )
    print(json.dumps(rec, indent=2))
    return 0


def _cmd_scorecard(args: argparse.Namespace) -> int:
    card = scorecard(args.builder_id, root=Path(args.root) if args.root else None)
    print(json.dumps(card, indent=2))
    # a routed overconfidence flag is a CI-visible signal (exit 1), never a block
    routed = overconfidence_signal(args.builder_id, root=Path(args.root) if args.root else None)
    return 1 if routed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="calibration_ledger.py")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("record", help="record a pending prediction (confidence in [0.5, 1.0])")
    r.add_argument("builder_id")
    r.add_argument("claim")
    r.add_argument("confidence", type=float)
    r.add_argument("--id", default=None)
    r.add_argument("--kind", default="")
    r.add_argument("--root", default=None)
    r.set_defaults(func=_cmd_record)

    v = sub.add_parser("resolve", help="settle a prediction with ground truth")
    v.add_argument("builder_id")
    v.add_argument("id")
    v.add_argument("outcome", choices=["true", "false"])
    v.add_argument("--root", default=None)
    v.set_defaults(func=_cmd_resolve)

    s = sub.add_parser("scorecard", help="the model's calibration mirror (+ routes an overconfidence nudge)")
    s.add_argument("builder_id")
    s.add_argument("--root", default=None)
    s.set_defaults(func=_cmd_scorecard)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
