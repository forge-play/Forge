#!/usr/bin/env python3
"""forge/card_table.py — Willow's add-on cards as rows for the keyword scan
(the-join.md, thread 1: the catalogue is the table).

The keyword table (`forge/keywords.toml`) has eleven rows that know kinds of
thing: site, app, cli, api. A Willow card is the same row in another spelling:

    keyword   the add-on's name ("coming-up", and "coming up" as it is said)
    aliases   the lines of Willow's `ui/search-words.txt` that point at it —
              "due = coming, deadline, renewals" makes "due" an alias of
              coming-up and of renewals
    major     the add-on itself
    reason    the card's one line
    caps      its promises: writes, network, needs, and whether it is built

This module reads a Willow checkout and renders every card — built, under
`adapters/stdlib/` and `adapters/deps/`, or still an idea in
`adapters/planned.json` — as a `majors.Row`. `majors.scan` does not change; it
runs over a bigger table, and a sentence that names a job several add-ons do
yields one hit per add-on, which is the condition that means ASK.

What a row is NOT: a ranking. "Close to what you said" is BM25 over the cards,
Willow's `pile-rank`, and it stays on the Willow side. A row here is an exact,
word-boundary match the person can read and argue with, the way the keyword
table is — add an alias line when a real sentence missed, argue one when it
mapped wrong.

Two lists below are deliberately arguable, like the table's rows. `NOT_BY_NAME`
holds add-ons whose name is an ordinary word of speech ("all", "again",
"said"): they are reached by alias only, never by name, or every sentence
would name them. `PLAIN_PARTS` holds the parts of a hyphenated name that name
nothing on their own ("check" in "claim-check"), so an alias word reaches a
card by a part only when the part means something.

Refusals: a path that is not a Willow checkout (no `adapters/`), a card header
that does not parse, a planned entry without a name and a line — each raises
`CardTableError` at load. A broken catalogue is not an empty one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import majors

__all__ = [
    "Card",
    "CardTableError",
    "NOT_BY_NAME",
    "PLAIN_PARTS",
    "read_cards",
    "read_aliases",
    "rows",
    "load",
]


class CardTableError(Exception):
    """The checkout cannot be read as a catalogue. Raised at load, never
    swallowed."""


@dataclass(frozen=True)
class Card:
    """One add-on as its card's header says it, or one planned entry."""

    name: str
    line: str
    section: str
    where: str  # the card's path inside the checkout, or adapters/planned.json
    built: bool
    writes: str = ""
    network: str = ""
    needs: str = ""
    uses: str = ""

    @property
    def spellings(self) -> tuple[str, ...]:
        """How the name is written and how it is said: "coming-up", "coming up"."""
        said = self.name.replace("-", " ")
        return (self.name,) if said == self.name else (self.name, said)

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(self.name.split("-"))


#: Add-ons named by an ordinary word of speech. Reached by alias only.
NOT_BY_NAME = frozenset(
    "across again all capture changed export gaps history hosts ids live pins pipe"
    " plain print profile rules said scan serve stack stale start text words".split()
)

#: Parts of a hyphenated name that name nothing on their own.
PLAIN_PARTS = frozenset(
    "and audit card cards check drill file files first for in list log on out pin the to up".split()
)

_HEADER = re.compile(r"\A<!-- willow-addon\n(.*?)\n-->\n", re.S)
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _header(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise CardTableError(f"cannot read the card at {path}: {e}") from e
    m = _HEADER.match(text)
    if not m:
        raise CardTableError(f"{path}: no willow-addon header")
    out: dict[str, str] = {}
    for ln in m.group(1).splitlines():
        key, sep, value = ln.partition(":")
        if not sep or not key.strip():
            raise CardTableError(f"{path}: a header line is not `key: value`: {ln!r}")
        out[key.strip()] = value.strip()
    if not out.get("line"):
        raise CardTableError(f"{path}: the card has no `line`")
    return out


def read_cards(willow: Path | str) -> list[Card]:
    """Every card in the checkout, built ones first, then the ideas, each
    list by name. The checkout must hold `adapters/`."""
    root = Path(willow)
    adapters = root / "adapters"
    if not adapters.is_dir():
        raise CardTableError(f"{root} is not a Willow checkout: no adapters/ folder")
    cards: list[Card] = []
    for kind in ("stdlib", "deps"):
        base = adapters / kind
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            card = folder / "README.md"
            if not card.is_file():
                continue
            if not _NAME.match(folder.name):
                raise CardTableError(f"{card}: {folder.name!r} is not an add-on name")
            h = _header(card)
            cards.append(
                Card(
                    name=folder.name,
                    line=h["line"],
                    section=h.get("section", ""),
                    where=str(card.relative_to(root)),
                    built=True,
                    writes=h.get("writes", ""),
                    network=h.get("network", ""),
                    needs=h.get("needs", ""),
                    uses=h.get("uses", ""),
                )
            )
    built = {c.name for c in cards}
    planned = adapters / "planned.json"
    if planned.is_file():
        try:
            entries = json.loads(planned.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise CardTableError(f"cannot read {planned}: {e}") from e
        if not isinstance(entries, list):
            raise CardTableError(f"{planned}: not a list of entries")
        for i, p in enumerate(entries):
            if not isinstance(p, dict) or not p.get("name") or not p.get("line"):
                raise CardTableError(f"{planned}: entry {i} has no name and line")
            if not _NAME.match(p["name"]):
                raise CardTableError(f"{planned}: {p['name']!r} is not an add-on name")
            if p["name"] in built:
                raise CardTableError(f"{planned}: {p['name']} is built and still planned")
            cards.append(
                Card(
                    name=p["name"],
                    line=str(p["line"]),
                    section=str(p.get("section", "")),
                    where=str(planned.relative_to(root)),
                    built=False,
                    writes=str(p.get("writes", "")),
                    network=str(p.get("network", "")),
                    needs=str(p.get("needs", "")),
                )
            )
    return sorted(cards, key=lambda c: (not c.built, c.name))


def read_aliases(willow: Path | str) -> dict[str, tuple[str, ...]]:
    """`ui/search-words.txt`: one of the person's words, then the cards' words
    for it, in the kernel's words-list format (`due = coming, renewals`).
    Absent, the table has names and no aliases, which is said by the empty
    dict, not by an error: a checkout without the UI is still a catalogue."""
    f = Path(willow) / "ui" / "search-words.txt"
    if not f.is_file():
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for n, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        word, sep, rest = ln.partition("=")
        word = word.strip().lower()
        if not sep or not word:
            raise CardTableError(f"{f}:{n}: not `word = words`: {raw!r}")
        targets = tuple(t.strip().lower() for t in rest.split(",") if t.strip())
        if not targets:
            raise CardTableError(f"{f}:{n}: {word!r} stands for nothing")
        out[word] = targets
    return out


def _reaches(target: str, card: Card) -> bool:
    """Whether an alias target names this card: its whole name, or a part of
    it that means something on its own."""
    if target == card.name:
        return True
    return any(len(p) >= 3 and p not in PLAIN_PARTS and p == target for p in card.parts)


def rows(cards: list[Card], aliases: dict[str, tuple[str, ...]]) -> list[majors.Row]:
    """One `majors.Row` per card, in the cards' order. A card named by an
    ordinary word (`NOT_BY_NAME`) is keyed by its first alias instead, and
    left out when nothing points at it."""
    out: list[majors.Row] = []
    for c in cards:
        said = sorted(w for w, ts in aliases.items() if any(_reaches(t, c) for t in ts))
        if c.name in NOT_BY_NAME:
            if not said:
                continue
            keyword, rest = said[0], tuple(said[1:])
        else:
            keyword, rest = c.name, tuple(dict.fromkeys((*c.spellings[1:], *said)))
        caps = [
            f"writes:{c.writes or '?'}",
            f"network:{c.network or '?'}",
            "built" if c.built else "idea",
        ]
        if c.needs:
            caps.append(f"needs:{c.needs}")
        if c.section:
            caps.append(f"section:{c.section}")
        out.append(
            majors.Row(keyword=keyword, major=c.name, reason=c.line, aliases=rest, caps=tuple(caps))
        )
    return out


def load(willow: Path | str) -> list[majors.Row]:
    """The catalogue as a table: `rows(read_cards(w), read_aliases(w))`."""
    return rows(read_cards(willow), read_aliases(willow))
