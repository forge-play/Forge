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
     With the answer comes its age: `tiers["deposit"]` names the store's
     newest CI row and how old it is, or `none` (the-forge-shape.md §12,
     rule 3 — a stale answer reported as current turns "nobody asked" into
     "the box says no").
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
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from . import checkpoint, checkpoint_memory, deposit, majors, paths, store_diff

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
    tiers: dict[str, str] = field(default_factory=dict)          # nestor / deposit / main / box / remote / scan
    decision_outcome: checkpoint.CheckpointOutcome | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["hits"] = [h.__dict__ for h in self.hits]
        d["decision_outcome"] = asdict(self.decision_outcome) if self.decision_outcome else None
        return d


def _ask_project_nestor(project_id: str, sentence: str) -> tuple[dict, object]:
    """Tier 1. Refuses if Nestor is not importable. Opens (creating) the
    project store and resolves the sentence in the `decision` domain. Returns
    the resolution and the open store, so the deposit's age can be read from
    the same store without opening it twice."""
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
    return answer.resolve(store, sentence, domain="decision"), store


def _deposit_tier(store: object) -> str:
    """Rule 3's second question, reported with the answer, never silently:
    how old is the store's last CI knowledge. `none` is an honest empty —
    a store that was never deposited into says so, and a build reads that
    as "nobody asked", not "the box says green"."""
    age = deposit.deposit_age(store)
    if age is None:
        return "none: no CI row in the project store"
    states = ", ".join(f"{k} {v}" for k, v in sorted(age["states"].items())) or "no runs parsed"
    return (f"{deposit.human_age(age['age_seconds'])} old: "
            f"{age['repo']}@{age['sha'][:12]} ({states})")


MAIN_ENV = "FORGE_MAIN_NESTOR"


def _main_tier(store: object, main: str | Path | None) -> str:
    """The third tier: how far the project store is from the main one
    (docs/design/the-store-diff.md). `main` is a nestor.db path or an
    exported bundle; falls back to $FORGE_MAIN_NESTOR. Never blocks. Three
    states, none of them silent: the four counts; `not consulted` when no
    main store was named; `could not read main` with the reason."""
    target = main if main is not None else os.environ.get(MAIN_ENV, "")
    if not target:
        return f"not consulted (no main store given; set {MAIN_ENV} or pass main=)"
    try:
        d = store_diff.diff(store, target)
    except Exception as err:  # noqa: BLE001 — every failure is a state, reported, never clean
        return f"could not read main {Path(str(target)).name}: {type(err).__name__}: {str(err)[:80]}"
    return store_diff.summary(d)


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
    main: str | Path | None = None,
) -> Entry:
    if not isinstance(sentence, str) or not sentence.strip():
        raise EntryError("an empty sentence is not a bite")
    e = Entry(sentence=sentence.strip(), project_id=project_id, builder_id=builder_id)

    # 1 — Nestor, first, or refuse.
    r, store = _ask_project_nestor(project_id, e.sentence)
    if r.get("verified"):
        e.answer = r.get("canonical")
        # The qualification is not decoration. A sealed row is trusted through
        # `is_verified_seal`, which degrades to a bare `status == 'sealed'`
        # test when no key is configured — and a builder id absent from the
        # keyring is refused outright, so every real run of this entry is the
        # unconfigured case. Reporting "sealed" without saying whether anyone
        # could check the signature is how "nobody verified this" reads as
        # "the box says yes" (docs/design/the-positional-default.md, gap 3).
        e.tiers["nestor"] = (
            f"sealed (confidence {r.get('confidence', 0):.2f}, "
            f"verifier {r.get('verifier', '')!r})"
            + ("" if checkpoint_memory.seal_signatures_verified()
               else " — SIGNATURES NOT VERIFIED (no seal key or keyring; "
                    "any 'sealed' row is trusted)"))
    else:
        n = len(r.get("candidates") or [])
        e.tiers["nestor"] = "pending" + (f" ({n} unsealed candidate{'s' if n != 1 else ''})" if n else "")
    # 1b — was the answer current? The store's last CI knowledge, with its age.
    e.tiers["deposit"] = _deposit_tier(store)
    # 1c — how far is this store from the main one? Four counts, or "not consulted".
    e.tiers["main"] = _main_tier(store, main)

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
    # `project` rides through to the sealed row's `origin` (the-two-stores.md).
    # The checkpoint memory is per-builder and cross-project — that is what
    # `has_sealed` needs — so the project is a field on the row, never part of
    # the domain key. It is what makes "the decisions taken in THIS workshop" a
    # filter rather than a guess about which rows belong to the repository
    # being exported.
    outcome = checkpoint.run_checkpoint(
        decision, builder_id=builder_id, responder=responder, root=root,
        recognize_threshold=recognize_threshold, project=project_id,
    )
    e.decision_outcome = outcome
    e.major = _major_from_chosen(outcome.chosen, ask)
    e.tiers["scan"] = f"{len(ask)} majors → checkpoint band {outcome.band}" + (
        f", chose {e.major}" if e.major else f", chose {outcome.chosen!r} (not a major on offer)")
    # An auto or recognize band means a prior sealed row answered instead of the
    # maker. Say whether that row's signature was checkable, for the same reason
    # the nestor tier does.
    if outcome.matched_band is not None and not checkpoint_memory.seal_signatures_verified():
        e.tiers["scan"] += " — prior seal's SIGNATURE NOT VERIFIED"
    return e


# ── CLI (dev shape, like the sibling modules) ───────────────────────────────

class _PickResponder:
    """Non-interactive: confirm yes; choose `--choose LABEL` (or the first
    option) with `--why`.

    `why=None` means the maker gave no rationale, and this responder does NOT
    invent one. It seals an empty rationale, which `checkpoint._engagement_fields`
    scores 0.0 and flags `rubber_stamp=True` — "the loudest rubber-stamp there
    is," which is exactly what a choice nobody explained should read as.

    Until 2026-09-07 `--why` defaulted to the string `"picked at the command
    line"`. That is argparse help text, not a reason, and it reached the ledger
    as a sealed rationale (docs/design/the-positional-default.md). Worse, it
    scored 0.350 against a 0.34 floor — clearing it on a homonym, since `line`
    is in the friction scorer's grounding lexicon as in *file, line* — so the
    one rationale in the system that is definitionally not a decision was the
    one the engagement gate never flagged, and it graded `Good`, pushing the
    review interval OUT (docs/design/the-forge-engagement-defect.md §1).
    A rationale nobody typed is not one."""

    def __init__(self, choose: str | None, why: str | None):
        self._choose, self._why = choose, why or ""

    def confirm(self, prompt: str) -> bool:
        print(f"[confirm] {prompt}\n[confirm] -> yes", file=sys.stderr)
        return True

    def choose(self, decision: checkpoint.Decision) -> checkpoint.ChoiceResult:
        print(f"[choose] {decision.surface}", file=sys.stderr)
        for o in decision.options:
            print(f"  - {o.label}: {o.tradeoff}", file=sys.stderr)
        # ── the positional default, refused ──────────────────────────────────
        # This line used to read `self._choose or decision.options[0].label`,
        # and that `or` is the whole of docs/design/the-positional-default.md:
        # on the first sentence anyone typed at the engine outside a test, three
        # majors were offered, index zero was taken, and it was sealed at
        # confidence 1.0 and reported as success. Nobody decided that.
        #
        # The entry already knows how to refuse — Nestor absent is an outright
        # EntryError. Both are the same condition, *the engine does not know*,
        # and only one of them was treated as such. The rule is not "ask a human
        # every time"; it is that not knowing must not be recorded as knowing.
        #
        # Raised from `choose`, this lands BEFORE `_seal_socratic_answer` seals
        # anything: `_full_socratic` calls the responder first and `cm.seal`
        # only with what it returns. So no row and no attestation is written.
        if self._choose is None and len(decision.options) > 1:
            raise EntryError(
                f"{decision.surface} — and no --choose was given. "
                f"A default chosen by list position is not a decision, and "
                f"nothing derived from one may be sealed "
                f"(docs/design/the-positional-default.md). Re-run with "
                f"--choose {decision.options[0].label!r} (or another of: "
                f"{', '.join(o.label for o in decision.options)})."
            )
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
    p.add_argument("--why", default=None,
                   help="the rationale, if asked. No default: a rationale nobody "
                        "typed is not one, and an absent one seals empty and flags "
                        "as a rubber-stamp rather than passing as a reason.")
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
