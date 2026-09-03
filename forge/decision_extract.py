#!/usr/bin/env python3
"""forge/decision_extract.py — noticing THAT a decision is being made (layer 2).

Every design doc named this as the next piece: the checkpoint loop decides
WHEN to ask (`checkpoint.run_checkpoint`'s three bands) and had nothing to
route, because nothing noticed that a decision was happening. This is the
noticing — deterministic, over the plan's structure, no model:

  R1  the entry's major ambiguity (`forge.entry`): more than one major and no
      decision recorded yet → a `Decision` (the majors as options).
  R2  every `fork` entry in the plan (`forge.plan_shape`) → a `Decision`. A
      fork that cannot be asked — one option, a bad decision_type, a
      confidence in nothing — is REFUSED WITH ITS REASON, never dropped.
  R3  two `file_write` entries with the same dest_path → a `Decision`: which
      content stands? The plan cannot mean both.

A plan with none of these extracts to nothing, and the report says so
(`nothing_to_decide=True`): the host's stub plan lands here today, honestly.
That is the boundary between "no decision here" and "could not look", which
the measuring panel taught the fleet to keep.

D8's open question — where exactly a decision starts — is answered here by
construction, not by judgement: a decision is a fork the proposer declared,
a major the sentence left open, or a conflict the plan cannot resolve itself.
"The kind of choice a domain expert would have an opinion about" is what a
fork IS; a proposer that hides a choice inside a file_write has not made a
decision the engine can see, and the panel (not this module) is what catches
that class.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .checkpoint import Decision, Option
from .plan_shape import FileWrite, Fork, PlanDoc

__all__ = ["Extracted", "Refusal", "Extraction", "extract",
           "ORIGIN_ENTRY", "ORIGIN_FORK", "ORIGIN_CONFLICT", "DECISION_TYPE_CONFLICT"]

ORIGIN_ENTRY = "entry-major"
ORIGIN_FORK = "fork"
ORIGIN_CONFLICT = "conflicting-write"
DECISION_TYPE_CONFLICT = "conflicting-write"


@dataclass(frozen=True)
class Extracted:
    """One decision and where it came from — enough for `build_loop` to put
    the answer back into the plan."""
    decision: Decision
    origin: str                          # ORIGIN_*
    index: int | None = None             # the plan entry (fork / first conflicting write)
    indices: tuple[int, ...] = ()        # R3: every entry that conflicts
    recommended: str | None = None
    confidence: float | None = None


@dataclass(frozen=True)
class Refusal:
    index: int
    reason: str


@dataclass
class Extraction:
    items: list[Extracted] = field(default_factory=list)
    refused: list[Refusal] = field(default_factory=list)

    @property
    def decisions(self) -> list[Decision]:
        return [x.decision for x in self.items]

    @property
    def nothing_to_decide(self) -> bool:
        return not self.items and not self.refused

    def to_dict(self) -> dict:
        return {
            "decisions": [{"decision_type": x.decision.decision_type, "surface": x.decision.surface,
                           "options": [o.label for o in x.decision.options], "origin": x.origin,
                           "index": x.index, "recommended": x.recommended, "confidence": x.confidence}
                          for x in self.items],
            "refused": [{"index": r.index, "reason": r.reason} for r in self.refused],
            "nothing_to_decide": self.nothing_to_decide,
        }


def _r1_entry(entry) -> Extracted | None:
    """The entry's own ambiguity, if it is still open. `entry` is duck-typed
    (`forge.entry.Entry`): `majors` (major → keywords), `hits` (with `.target`
    and `.reason`), `decision_outcome`, `sentence`."""
    if entry is None or getattr(entry, "decision_outcome", None) is not None:
        return None
    majors = list(getattr(entry, "majors", {}) or {})
    if len(majors) < 2:
        return None
    reasons: dict[str, list[str]] = {}
    for h in getattr(entry, "hits", []) or []:
        reasons.setdefault(h.target, [])
        if h.reason not in reasons[h.target]:
            reasons[h.target].append(h.reason)
    options = tuple(Option(label=m, tradeoff="; ".join(reasons.get(m, []))) for m in majors)
    sentence = getattr(entry, "sentence", "")
    return Extracted(
        decision=Decision(decision_type="major",
                          surface=f"'{sentence}' could be {', '.join(majors)} — which major?",
                          options=options, recommended=None),
        origin=ORIGIN_ENTRY,
    )


def _r2_fork(i: int, f: Fork) -> Extracted | Refusal:
    problems = f.problems()
    if problems:
        return Refusal(index=i, reason="; ".join(problems))
    return Extracted(
        decision=Decision(decision_type=f.decision_type, surface=f.surface,
                          options=tuple(Option(label=o.label, tradeoff=o.tradeoff) for o in f.options),
                          recommended=f.recommended),
        origin=ORIGIN_FORK, index=i, indices=(i,), recommended=f.recommended, confidence=f.confidence,
    )


def _first_line(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "(empty)"
    return line if len(line) <= 60 else line[:57] + "…"


def _r3_conflicts(plan: PlanDoc) -> list[Extracted]:
    by_path: dict[str, list[int]] = {}
    for i, e in enumerate(plan.entries):
        if isinstance(e, FileWrite):
            by_path.setdefault(e.dest_path, []).append(i)
    out: list[Extracted] = []
    for path, idxs in by_path.items():
        if len(idxs) < 2:
            continue
        options = tuple(
            Option(label=f"entry {i}", tradeoff=f"{path}: {_first_line(plan.entries[i].content)}")  # type: ignore[union-attr]
            for i in idxs
        )
        out.append(Extracted(
            decision=Decision(decision_type=DECISION_TYPE_CONFLICT,
                              surface=f"{len(idxs)} entries write {path}; which content stands?",
                              options=options, recommended=None),
            origin=ORIGIN_CONFLICT, index=idxs[0], indices=tuple(idxs),
        ))
    return out


def extract(plan: PlanDoc, *, entry=None) -> Extraction:
    """Every decision the plan (and the entry) holds, in plan order, with the
    reasons for any fork that could not be asked."""
    ex = Extraction()
    r1 = _r1_entry(entry)
    if r1 is not None:
        ex.items.append(r1)
    for i, e in enumerate(plan.entries):
        if isinstance(e, Fork):
            got = _r2_fork(i, e)
            (ex.refused if isinstance(got, Refusal) else ex.items).append(got)  # type: ignore[arg-type]
    ex.items.extend(_r3_conflicts(plan))
    return ex


if __name__ == "__main__":
    import argparse
    import json
    from . import plan_shape
    p = argparse.ArgumentParser(prog="decision_extract.py", description="what decisions does this plan hold?")
    p.add_argument("plan")
    a = p.parse_args()
    print(json.dumps(extract(plan_shape.load(a.plan)).to_dict(), indent=2))
