#!/usr/bin/env python3
"""forge/card_box.py — the box, tier 2 of the entry, over Willow's catalogue
(the-join.md; idea 7: a real `BoxLookup` over the catalogue).

`forge/entry.py` asks three tiers in order — the project's memory, the box,
remote — and says which answered. Until now the box was `NoBox`: nothing, and
said so. This is the first real one. It holds a Willow checkout's cards as a
table (`forge/card_table.py`) and answers the entry's question the way the
seam asks it: given the scan's hits, what does the box already have?

    box = CardBox("/path/to/Willow")
    hits = box.scan("read my email and tell me when the boiler is due")
    box.lookup(hits)   → Candidate(mail, …, "what “email” usually means here"),
                         Candidate(apple-mail, …), Candidate(coming-up, …),
                         Candidate(renewals, …)
    box.forks(hits)    → {"email": ["mail", "apple-mail"],
                          "due": ["coming-up", "renewals"]}

`lookup` keeps the `BoxLookup` protocol as it is: hits in, candidates out, one
per add-on, first seen first. It ignores hits for majors it does not hold
(`web`, from the keyword table), so one hit list can carry both scans. `forks`
is the catalogue's own ambiguity: one word the person said, several add-ons it
reaches. That is a `Decision` with cards as options — the stack plan's job
(the-join.md, thread 2), not this module's; here it is only reported.

A candidate is a card, not a ranking: it was named, or an alias line names
it. An add-on still an idea is a candidate that says so. No model, no BM25,
no network; the checkout is only read.

Exit codes of the CLI, the Forge's today: 0 candidates found, 1 none, 2
refused (not a Willow checkout).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import card_table, majors
from .entry import Candidate
from .willow_record import decision_type

__all__ = ["CardBox", "decision_type"]


class CardBox:
    """Tier 2 over a Willow checkout's cards."""

    def __init__(self, willow: Path | str):
        self.willow = Path(willow)
        self.cards = card_table.read_cards(self.willow)
        self.rows = card_table.rows(self.cards, card_table.read_aliases(self.willow))
        self._by_name = {c.name: c for c in self.cards}
        built = sum(1 for c in self.cards if c.built)
        self.name = (
            f"willow cards at {self.willow} ({built} built, {len(self.cards) - built} ideas)"
        )

    def scan(self, sentence: str) -> list[majors.Hit]:
        """The keyword scan over the catalogue's rows. The entry runs this
        itself when given the rows as its `catalogue`; the CLI runs it here."""
        return majors.scan(sentence, table=self.rows)

    def _why(self, h: majors.Hit, card: card_table.Card) -> str:
        if h.matched in card.spellings:
            why = "you named it"
        else:
            why = f"what “{h.matched}” usually means here"
        return why if card.built else why + " (an idea, not built)"

    def lookup(self, hits: list[majors.Hit]) -> list[Candidate]:
        out: list[Candidate] = []
        seen: set[str] = set()
        for h in hits:
            card = self._by_name.get(h.target)
            if card is None or card.name in seen:
                continue
            seen.add(card.name)
            out.append(Candidate(name=card.name, where=card.where, why=self._why(h, card)))
        return out

    def forks(self, hits: list[majors.Hit]) -> dict[str, list[str]]:
        """One word the person said, several add-ons it reaches — in the
        order the words were said and the add-ons were hit."""
        by_word: dict[str, list[str]] = {}
        for h in hits:
            if h.target not in self._by_name:
                continue
            names = by_word.setdefault(h.matched, [])
            if h.target not in names:
                names.append(h.target)
        return {w: ns for w, ns in by_word.items() if len(ns) > 1}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="card_box.py", description="what Willow's catalogue already has for a sentence"
    )
    p.add_argument("sentence")
    p.add_argument("--willow", required=True, help="a Willow checkout (its adapters/ folder)")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        box = CardBox(a.willow)
    except card_table.CardTableError as err:
        print(f"REFUSED: {err}", file=sys.stderr)
        return 2
    hits = box.scan(a.sentence)
    found = box.lookup(hits)
    forks = box.forks(hits)
    if a.json:
        print(
            json.dumps(
                {
                    "box": box.name,
                    "candidates": [c.__dict__ for c in found],
                    "forks": forks,
                },
                indent=2,
            )
        )
    else:
        print(f"box     {box.name}")
        for c in found:
            print(f"cand    {c.name:<18} {c.why:<44} {c.where}")
        for word, names in forks.items():
            print(f"fork    “{word}” could be {', '.join(names)}")
        if not found:
            print("cand    (nothing named: no card or alias line matched)")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main())
