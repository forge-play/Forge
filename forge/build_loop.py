#!/usr/bin/env python3
"""forge/build_loop.py — resolve a plan's decisions through memory, and find
out whether the proposer's confidence was earned.

    decision_extract  →  run_checkpoint (per decision, in plan order)  →  the
    answer substituted back into the plan  →  a plan with no fork left in it.

The model never touches the router: extraction is rule-based, the band comes
from the maker's own memory, and a fork's `recommended` is only ever a
suggestion the deferral path may fall back to. What the model DOES get is a
scorecard. For every fork that carried a `recommended` and a `confidence`:

    before the ask   calibration_ledger.record_prediction(
                         claim="<decision_type>: maker picks <recommended>",
                         confidence)
    after the ask    calibration_ledger.resolve_prediction(
                         outcome = (chosen == recommended))

Ground truth that arrives on its own — the maker's pick IS the outcome, no
opinion enters — which is the loop the Forge exists to close and which, until
this module, nothing outside the ledger's own tests had ever called. A fork
without a confidence records nothing: no fabricated 0.5.

Refusals: a plan whose extraction refused a fork cannot be resolved (the
reasons are in the error); a plan that still holds a fork after resolution is
a bug and is refused rather than returned; a memory answer that names no
option on offer is refused rather than guessed at.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import calibration_ledger, checkpoint, checkpoint_memory, decision_extract, plan_shape
from .decision_extract import ORIGIN_CONFLICT, ORIGIN_ENTRY, ORIGIN_FORK, Extraction
from .plan_shape import FileWrite, Fork, PlanDoc

__all__ = ["BuildLoopError", "Resolved", "resolve", "label_from_chosen"]


class BuildLoopError(Exception):
    """A plan that cannot be resolved, or an answer that cannot be placed."""


@dataclass
class Resolved:
    plan: PlanDoc
    outcomes: list[checkpoint.CheckpointOutcome] = field(default_factory=list)
    predictions: list[dict] = field(default_factory=list)   # {claim, confidence, outcome | already_settled}
    chosen: dict[str, str] = field(default_factory=dict)    # decision_type -> chosen label

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return {"plan": self.plan.to_dict(), "outcomes": [asdict(o) for o in self.outcomes],
                "predictions": self.predictions, "chosen": self.chosen}


def label_from_chosen(chosen: str, labels: tuple[str, ...] | list[str]) -> str | None:
    """A memory answer is `label` (fresh) or `label: rationale` (a prior seal's
    one canonical string — `CheckpointOutcome.chosen` says why it is not split).
    Longest label that the answer starts with wins; nothing matching is None,
    and the caller refuses rather than guesses."""
    c = chosen.strip()
    for lab in sorted(labels, key=len, reverse=True):
        if c == lab or c.startswith(lab + ":") or c.startswith(lab + " "):
            return lab
    return None


def _predict(builder_id: str, x: decision_extract.Extracted, root: Path) -> dict | None:
    if x.recommended is None or x.confidence is None:
        return None
    claim = f"{x.decision.decision_type}: maker picks {x.recommended}"
    try:
        rec = calibration_ledger.record_prediction(builder_id, claim, x.confidence, kind="fork", root=root)
    except calibration_ledger.CalibrationLedgerError as e:
        # The same claim already settled (a re-run of a resolved plan). A
        # settled prediction is history; do not re-open it, do not fabricate.
        return {"claim": claim, "confidence": x.confidence, "already_settled": True, "note": str(e)}
    return {"claim": claim, "confidence": x.confidence, "prediction_id": rec["id"]}


def _settle(builder_id: str, pred: dict | None, hit: bool, root: Path) -> None:
    if pred is None or pred.get("already_settled"):
        return
    rec = calibration_ledger.resolve_prediction(builder_id, pred["prediction_id"], hit, root=root)
    pred["outcome"] = rec["outcome"]


def resolve(
    plan: PlanDoc,
    *,
    builder_id: str,
    responder: checkpoint.Responder,
    root: Path = checkpoint_memory.DEFAULT_CHECKPOINT_ROOT,
    entry=None,
    extraction: Extraction | None = None,
    recognize_threshold: float = checkpoint.DEFAULT_RECOGNIZE_THRESHOLD,
) -> Resolved:
    ex = extraction if extraction is not None else decision_extract.extract(plan, entry=entry)
    if ex.refused:
        raise BuildLoopError("plan holds a fork that cannot be asked: " +
                             "; ".join(f"entries[{r.index}]: {r.reason}" for r in ex.refused))

    out = Resolved(plan=plan)
    replacements: dict[int, tuple[FileWrite, ...] | None] = {}   # entry index -> what replaces it
    drop: set[int] = set()

    for x in ex.items:
        pred = _predict(builder_id, x, root)
        outcome = checkpoint.run_checkpoint(
            x.decision, builder_id=builder_id, responder=responder, root=root,
            recognize_threshold=recognize_threshold,
        )
        out.outcomes.append(outcome)
        label = label_from_chosen(outcome.chosen, x.decision.options and [o.label for o in x.decision.options])
        if label is None:
            raise BuildLoopError(
                f"memory answered {outcome.chosen!r} for {x.decision.decision_type!r}, which names none of "
                f"{[o.label for o in x.decision.options]} — refusing to guess")
        out.chosen[x.decision.decision_type] = label
        _settle(builder_id, pred, label == x.recommended, root)
        if pred is not None:
            out.predictions.append(pred)

        if x.origin == ORIGIN_FORK and x.index is not None:
            fork = plan.entries[x.index]
            assert isinstance(fork, Fork)
            replacements[x.index] = fork.resolves.get(label, ())
        elif x.origin == ORIGIN_CONFLICT:
            keep = int(label.split()[-1])           # "entry N"
            drop.update(i for i in x.indices if i != keep)
        elif x.origin == ORIGIN_ENTRY:
            pass                                    # the entry's major; nothing in the plan changes

    entries: list = []
    for i, e in enumerate(plan.entries):
        if i in drop:
            continue
        if i in replacements:
            entries.extend(replacements[i] or ())
            continue
        entries.append(e)
    resolved = PlanDoc(app_name=plan.app_name, entries=tuple(entries))
    if resolved.has_forks:
        raise BuildLoopError("a fork survived resolution — refusing to return an unresolved plan")
    out.plan = resolved
    return out


# ── CLI (dev shape) ─────────────────────────────────────────────────────────

class _PickResponder:
    def __init__(self, picks: dict[str, str], why: str):
        self._picks, self._why = picks, why

    def confirm(self, prompt: str) -> bool:
        print(f"[confirm] {prompt}\n[confirm] -> yes", file=sys.stderr)
        return True

    def choose(self, d: checkpoint.Decision) -> checkpoint.ChoiceResult:
        label = self._picks.get(d.decision_type) or d.options[0].label
        print(f"[choose] {d.surface}\n[choose] -> {label}", file=sys.stderr)
        return checkpoint.ChoiceResult(chosen_label=label, rationale=self._why)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="build_loop.py", description="resolve a plan's forks through memory")
    p.add_argument("plan")
    p.add_argument("--builder", required=True, dest="builder_id")
    p.add_argument("--root", default=str(checkpoint_memory.DEFAULT_CHECKPOINT_ROOT))
    p.add_argument("--choose", action="append", default=[], metavar="TYPE=LABEL",
                   help="what to pick if asked, per decision_type (default: first option)")
    p.add_argument("--why", default="picked at the command line")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    picks = dict(s.split("=", 1) for s in a.choose)
    try:
        plan = plan_shape.load(a.plan)
        res = resolve(plan, builder_id=a.builder_id, responder=_PickResponder(picks, a.why), root=Path(a.root))
    except (plan_shape.PlanShapeError, BuildLoopError, checkpoint_memory.CheckpointMemoryError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    card = calibration_ledger.scorecard(a.builder_id, root=Path(a.root))
    if a.json:
        print(json.dumps({**res.to_dict(), "scorecard": card}, indent=2, default=str))
    else:
        for o in res.outcomes:
            print(f"{o.decision_type:24} band {o.band:9} → {res.chosen[o.decision_type]}")
        for pr in res.predictions:
            print(f"  prediction {pr['claim']!r} @ {pr['confidence']:.2f} → "
                  f"{'already settled' if pr.get('already_settled') else pr.get('outcome')}")
        print(f"resolved plan: {len(res.plan.entries)} entries, no forks")
        print(f"scorecard: {card['resolved']} resolved, {card['pending']} pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
