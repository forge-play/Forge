#!/usr/bin/env python3
"""forge/majors.py — the keyword → major scan (the-forge-shape.md §3).

    "That is not a reasoning problem. It contains two keywords — `site` and
    `app` — and a regex finds both. They map to different majors: site → web;
    app → web, mobile, or desktop. Two candidates and no way to choose is a
    detectable condition with a scripted response: ask."

The table is `forge/keywords.toml` — a flat file somebody can read and argue
with. This module reads it and does the one operation: a span of text in,
hits out. Deterministic, model-free, word-boundary, case-insensitive.

**Two callers, one interface.** The Forge's entry (`forge/entry.py`) feeds it a
maker's opening sentence and ignores `path`/`anchor`. The corpus's prose lane
(willow-side) feeds it a document and needs them: "a claim without a resolvable
origin is not a claim." So the scan emits `(source, target, reason, path,
anchor)` — `Hit` — and the Forge discards the last two. Written for one caller,
the scan would acquire a sentence-shaped interface and be rewritten for the
second; written for both, the Forge gets its entry and the corpus gets its
missing lane from one component.

Refusals: a table that does not parse, or a row missing `keyword`/`major`/
`reason`, raises `MajorsError` at load — a broken table is not an empty one.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

__all__ = ["Hit", "Row", "MajorsError", "DEFAULT_TABLE", "load_table", "scan",
           "majors_for", "ambiguous_majors"]

DEFAULT_TABLE = Path(__file__).with_name("keywords.toml")


class MajorsError(Exception):
    """The table cannot be read as a table. Raised at load, never swallowed."""


@dataclass(frozen=True)
class Row:
    keyword: str
    major: str
    reason: str
    aliases: tuple[str, ...] = ()
    caps: tuple[str, ...] = ()

    @property
    def spellings(self) -> tuple[str, ...]:
        return (self.keyword, *self.aliases)


@dataclass(frozen=True)
class Hit:
    """One keyword found in a span of text, mapped to one major.

    `source` is the keyword as written in the table (not as spelled in the
    text — the alias that matched is `matched`), `target` the major, `reason`
    the table's argument for the row. `path` and `anchor` are the ORIGIN — the
    corpus caller's, passed through untouched; the Forge leaves them empty."""

    source: str
    target: str
    reason: str
    path: str = ""
    anchor: str = ""
    matched: str = ""
    caps: tuple[str, ...] = ()


_REQUIRED = ("keyword", "major", "reason")


def load_table(path: Path | str | None = None) -> list[Row]:
    """Read the table. Every row must carry keyword/major/reason; a row that
    does not is a refusal, not a skip."""
    p = Path(path) if path is not None else DEFAULT_TABLE
    try:
        doc = tomllib.loads(p.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise MajorsError(f"cannot read the keyword table at {p}: {e}") from e
    rows_raw = doc.get("map")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise MajorsError(f"{p}: no [[map]] rows")
    rows: list[Row] = []
    for i, r in enumerate(rows_raw):
        missing = [k for k in _REQUIRED if not isinstance(r.get(k), str) or not r[k].strip()]
        if missing:
            raise MajorsError(f"{p}: row {i} is missing {missing}")
        aliases = tuple(str(a) for a in (r.get("aliases") or []))
        caps = tuple(str(c) for c in (r.get("caps") or []))
        rows.append(Row(keyword=r["keyword"].strip().lower(), major=r["major"].strip(),
                        reason=r["reason"].strip(), aliases=tuple(a.strip().lower() for a in aliases),
                        caps=caps))
    return rows


def _pattern(spellings: Iterable[str]) -> re.Pattern[str]:
    alts = sorted({re.escape(s) for s in spellings if s}, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(alts) + r")(?![\w-])", re.IGNORECASE)


def scan(text: str, *, path: str = "", anchor: str = "",
         table: list[Row] | None = None) -> list[Hit]:
    """Every keyword in `text`, mapped to every major its row names. Order is
    by position in the text, then table order — deterministic for a given
    text and table. A span with no keyword yields `[]`, which is an honest
    answer, not a failure."""
    rows = table if table is not None else load_table()
    found: list[tuple[int, int, Hit]] = []
    for ti, row in enumerate(rows):
        m = _pattern(row.spellings).search(text)
        if not m:
            continue
        found.append((m.start(), ti, Hit(
            source=row.keyword, target=row.major, reason=row.reason,
            path=path, anchor=anchor, matched=m.group(1).lower(), caps=row.caps)))
    found.sort(key=lambda t: (t[0], t[1]))
    return [h for _, _, h in found]


def majors_for(hits: Iterable[Hit]) -> dict[str, list[Hit]]:
    """Majors named by the hits, each with the hits that named it, in first-
    seen order."""
    out: dict[str, list[Hit]] = {}
    for h in hits:
        out.setdefault(h.target, []).append(h)
    return out


def ambiguous_majors(hits: Iterable[Hit]) -> list[str]:
    """The majors, if there is more than one — the condition that means ASK.
    One major or none returns `[]`."""
    majors = list(majors_for(hits))
    return majors if len(majors) > 1 else []


if __name__ == "__main__":
    import argparse
    import json
    p = argparse.ArgumentParser(prog="majors.py", description="scan a span of text for keywords → majors")
    p.add_argument("text")
    p.add_argument("--table", default=None)
    p.add_argument("--path", default="")
    p.add_argument("--anchor", default="")
    a = p.parse_args()
    hits = scan(a.text, path=a.path, anchor=a.anchor, table=load_table(a.table) if a.table else None)
    print(json.dumps({
        "hits": [h.__dict__ for h in hits],
        "majors": {m: [h.source for h in hs] for m, hs in majors_for(hits).items()},
        "ask": ambiguous_majors(hits),
    }, indent=2))
