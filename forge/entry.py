#!/usr/bin/env python3
"""forge/entry.py — the first bite: from a sentence to a major, Nestor first.

    "Nestor is the first tool, not an available one — the Forge cannot start a
    build that never asked. Not discouraged from it — unable."
    "Ask Nestor, then the box, then remote — in that order, and say which tier
    answered."                                     (the-forge-shape.md §3, §11)

This is that rule as code, and the first place a real decision reaches the
checkpoint router. `open_bite` takes a maker's opening sentence and:

  1. **asks Nestor** — the PROJECT store (`paths.project_nestor`). A sealed
     answer short-circuits: this bite was already decided by a human. Nestor
     absent is a REFUSAL (`EntryError`), not a soft degrade: `run_checkpoint`
     may run Socratic without memory because a fresh decision is still a
     decision; an entry that never asked has nothing to be honest about.
  2. **looks in the box** — a `BoxLookup` seam. The real box (the corpus under
     ~/github) is willow-side; the default here returns nothing and SAYS so.
  3. **remote** — not built; recorded as `not_attempted`, never pretended.

  then scans the sentence (`forge/majors.py`). One major: the entry knows what
  it is building. More than one: a `Decision` — the majors as options, the
  table's reasons as tradeoffs — through `checkpoint.run_checkpoint`, so the
  second time this maker says "app" they are confirmed, not re-asked. No
  keyword: an honest empty, `major=None`.

`Entry.tiers` records which tier answered and how. The model is never
consulted: the scan is a regex over a table, the routing is memory.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from . import checkpoint, checkpoint_memory, majors, paths

__all__ = ["Entry", "EntryError", "BoxLookup", "NoBox", "Candidate", "open_bite",
           "DECISION_TYPE_MAJOR"]

DECISION_TYPE_MAJOR = "major"


class EntryError(Exception):
    """A refusal at the door. The one this module owns: Nestor unavailable
    (the build cannot start because it never asked)."""


@dataclass(frozen=True)
class Candidate:
    """Something the box already holds that may answer the bite."""
    name: str
    where: str
    why: str = ""


@runtime_checkable
class BoxLookup(Protocol):
    """Tier 2. Given the scan's hits, what does the box already have?"""
    name: str

    def lookup(self, hits: list[majors.Hit]) -> list[Candidate]: ...


class NoBox:
    """The default box: nothing, and says so. The real lookup (the corpus,
    the app catalog) lives on the willow side; this is the seam it plugs into."""
    name = "no box wired"

    def lookup(self, hits: list[majors.Hit]) -> list[Candidate]:
        return []


@dataclass
class Entry:
    sentence: str
    project_id: str
    builder_id: str
    hits: list[majors.Hit] = field(default_factory=list)
    majors: dict[str, list[str]] = field(default_factory=dict)   # major -> keywords
    major: str | None = None
    answer: str | None = None                                     # a sealed project answer, if any
    candidates: list[Candidate] = field(default_factory=list)
    tiers: dict[str, str] = field(default_factory=dict)          # nestor / box / remote / scan
    decision_outcome: checkpoint.CheckpointOutcome | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hits"] = [h.__dict__ for h in self.hits]
        d["decision_outcome"] = asdict(self.decision_outcome) if self.decision_outcome else None
        return d


def _ask_project_nestor(project_id: str, sentence: str) -> dict:
    """Tier 1. Refuses if Nestor is not importable. Opens (creating) the
    project store and resolves the sentence in the `decision` domain."""
    if not checkpoint_memory.nestor_available():
        raise EntryError(
            "Nestor is unavailable, and the Forge cannot start a build that never "
            "asked (the-forge-shape.md §11). Install it: pip install nestor-meaning."
        )
    from nestor import answer, cascade  # type: ignore[import-not-found]
    from nestor.sqlite_store import SqliteStore  # type: ignore[import-not-found]

    db = paths.project_nestor(project_id)
    db.parent.mkdir(parents=True, exist_ok=True)
    cascade.set_ledger_path(paths.project_nestor_ledger(project_id))
    store = SqliteStore(str(db))
    return answer.resolve(store, sentence, domain="decision")


def _major_from_chosen(chosen: str, known: list[str]) -> str | None:
    """A prior seal's canonical string is `label` or `label: rationale`; the
    label is one of the majors that were on offer. Longest prefix wins."""
    c = chosen.strip()
    for m in sorted(known, key=len, reverse=True):
        if c == m or c.startswith(m + ":") or c.startswith(m + " "):
            return m
    return None


def open_bite(
    sentence: str,
    *,
    project_id: str,
    builder_id: str,
    responder: checkpoint.Responder,
    root: Path = checkpoint_memory.DEFAULT_CHECKPOINT_ROOT,
    box: BoxLookup | None = None,
    recognize_threshold: float = checkpoint.DEFAULT_RECOGNIZE_THRESHOLD,
    table: list[majors.Row] | None = None,
) -> Entry:
    if not isinstance(sentence, str) or not sentence.strip():
        raise EntryError("an empty sentence is not a bite")
    e = Entry(sentence=sentence.strip(), project_id=project_id, builder_id=builder_id)

    # 1 — Nestor, first, or refuse.
    r = _ask_project_nestor(project_id, e.sentence)
    if r.get("verified"):
        e.answer = r.get("canonical")
        e.tiers["nestor"] = f"sealed (confidence {r.get('confidence', 0):.2f}, verifier {r.get('verifier', '')!r})"
    else:
        n = len(r.get("candidates") or [])
        e.tiers["nestor"] = "pending" + (f" ({n} unsealed candidate{'s' if n != 1 else ''})" if n else "")

    # 2 — the box.
    e.hits = majors.scan(e.sentence, table=table)
    e.majors = {m: [h.source for h in hs] for m, hs in majors.majors_for(e.hits).items()}
    box = box or NoBox()
    e.candidates = list(box.lookup(e.hits))
    e.tiers["box"] = (f"{box.name}: {len(e.candidates)} candidate(s)" if e.candidates
                      else f"{box.name}: nothing")

    # 3 — remote. Not built. Say so.
    e.tiers["remote"] = "not_attempted (not built)"

    if e.answer is not None:
        e.tiers["scan"] = "skipped: the project store already holds a sealed answer"
        e.major = _major_from_chosen(e.answer, list(e.majors)) or None
        return e

    # — the scan, and the first real decision through the router.
    if not e.hits:
        e.tiers["scan"] = "no keyword matched the table"
        return e
    ask = majors.ambiguous_majors(e.hits)
    if not ask:
        e.major = next(iter(e.majors))
        e.tiers["scan"] = f"one major: {e.major} (unambiguous)"
        return e

    options = tuple(
        checkpoint.Option(label=m, tradeoff="; ".join(dict.fromkeys(h.reason for h in hs)))
        for m, hs in majors.majors_for(e.hits).items()
    )
    decision = checkpoint.Decision(
        decision_type=DECISION_TYPE_MAJOR,
        surface=f"'{e.sentence}' could be {', '.join(ask)} — which major?",
        options=options,
        recommended=None,
    )
    outcome = checkpoint.run_checkpoint(
        decision, builder_id=builder_id, responder=responder, root=root,
        recognize_threshold=recognize_threshold,
    )
    e.decision_outcome = outcome
    e.major = _major_from_chosen(outcome.chosen, ask)
    e.tiers["scan"] = f"{len(ask)} majors → checkpoint band {outcome.band}" + (
        f", chose {e.major}" if e.major else f", chose {outcome.chosen!r} (not a major on offer)")
    return e


# ── CLI (dev shape, like the sibling modules) ───────────────────────────────

class _PickResponder:
    """Non-interactive: confirm yes; choose `--choose LABEL` (or the first
    option) with `--why`."""

    def __init__(self, choose: str | None, why: str):
        self._choose, self._why = choose, why

    def confirm(self, prompt: str) -> bool:
        print(f"[confirm] {prompt}\n[confirm] -> yes", file=sys.stderr)
        return True

    def choose(self, decision: checkpoint.Decision) -> checkpoint.ChoiceResult:
        print(f"[choose] {decision.surface}", file=sys.stderr)
        for o in decision.options:
            print(f"  - {o.label}: {o.tradeoff}", file=sys.stderr)
        label = self._choose or decision.options[0].label
        print(f"[choose] -> {label}", file=sys.stderr)
        return checkpoint.ChoiceResult(chosen_label=label, rationale=self._why)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="entry.py", description="open a bite: Nestor first, then the scan")
    p.add_argument("sentence")
    p.add_argument("--project", required=True, dest="project_id")
    p.add_argument("--builder", required=True, dest="builder_id")
    p.add_argument("--root", default=str(checkpoint_memory.DEFAULT_CHECKPOINT_ROOT))
    p.add_argument("--choose", default=None, help="the major to pick if asked (default: first)")
    p.add_argument("--why", default="picked at the command line", help="the rationale, if asked")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        e = open_bite(a.sentence, project_id=a.project_id, builder_id=a.builder_id,
                      responder=_PickResponder(a.choose, a.why), root=Path(a.root))
    except EntryError as err:
        print(f"REFUSED: {err}", file=sys.stderr)
        return 2
    except checkpoint_memory.CheckpointMemoryError as err:
        # Memory refused the seal — e.g. a per-verifier keyring with no key for
        # this builder. Nestor is right to refuse; say so in one line, not a
        # traceback, and name the fix the way Nestor's own message does.
        print(f"REFUSED by memory: {err}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(e.to_dict(), indent=2, default=str))
    else:
        for tier, what in e.tiers.items():
            print(f"{tier:7} {what}")
        print(f"major   {e.major or '(none)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
