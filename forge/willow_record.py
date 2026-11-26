#!/usr/bin/env python3
"""forge/willow_record.py — the person's record, asked and proposed to
through the kernel (the-join.md, thread 3: one record).

A willow box is the person's own record: a hash chain of what was asked, what
was suggested, and what they sealed with their key. The Forge never reads
that key and never checks a seal itself. It asks the kernel, through the one
verb that serves a sealed answer only after proving it under the key:

    python kernel.py bite --box BOX "the words"
    {"state": "sealed", "answer": "...", "by": "proposal:<sha256>"}

and it hands the kernel what the maker answered, through the one verb that
holds a suggestion at the door until the person seals it:

    python kernel.py propose --box BOX --file ONE-LINE.jsonl
    pass  proposal:<sha256>  waiting on your seal

Three questions the Forge puts to a record, the `RecordLookup` protocol:

    has_sealed(decision_type)   the bite for the words a decision is proposed
                                under, `question(dt)`: "forge decision
                                willow-email". Sealed → the option the person
                                chose; else None.
    stack_for(sentence)         the bite for the sentence itself. A sealed
                                stack → its text; else None.
    propose(...)                a decision the maker just answered, as one
                                proposal under `question(dt)`, citing nothing,
                                in the same shape Willow's `forge` add-on
                                writes. Returns the proposal's subject. The
                                engine proposes; it never seals (CONST-0-2).
                                `kept` is what the fork showed and what its
                                proposer held (`offered`, `recommended`,
                                `confidence`, `blind`, `rank`, ...), on the
                                same row as the pick, so that once the person
                                seals it the row is a scored outcome with
                                nothing to join.

Every question is a row on the person's record, the engine's included: that
is the kernel's rule ("every step is written to a tamper-evident log"), not a
side effect to hide. A record that refuses — not a box, a chain that doesn't
verify, a proposal the door turns back — is `WillowRecordError`, and the
caller refuses with it rather than reading past a break.

The kernel serves the FIRST seal that stands for a question's words, so a
decision sealed once is the answer until the person sets it aside (Willow's
planned `retire`); a later proposal for the same words is on the record,
waiting, and is not what `has_sealed` returns.

`decision_type(word)` is how both sides name a fork: the word the person said
that reached several add-ons, in the Forge's calibration-key charset, under
the `willow-` prefix. Willow's add-on imports it from here so the two never
drift.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "Deferred",
    "Sealed",
    "RecordLookup",
    "WillowRecord",
    "WillowRecordError",
    "decision_type",
    "question",
    "not_now_question",
    "DECISION_PATH",
    "NOT_NOW",
    "NOT_NOW_PATH",
]

#: where a decision is proposed, inside the box's `written/`
DECISION_PATH = "forge/decisions/{}.json"
#: what a fork left for later says it chose, and where it is proposed: not
#: deciding is a decision, kept under its own question so the fork's own stays
#: open for the pick to come
NOT_NOW = "not-now"
NOT_NOW_PATH = "forge/not-now/{}.json"


class WillowRecordError(Exception):
    """The record refused: not a box, a chain that doesn't verify, a sealed
    answer that isn't the shape a decision has, or a proposal the door turned
    back."""


def decision_type(word: str) -> str:
    """The fork's calibration key: the word said, in the Forge's charset."""
    return "willow-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", word).strip("-")


def question(decision_type: str) -> str:
    """The words a decision is proposed and asked under."""
    return f"forge decision {decision_type}"


def not_now_question(decision_type: str) -> str:
    """The words a fork left for later is proposed and asked under: never the
    decision's own, so sealing a not-now leaves the decision unanswered."""
    return f"forge not now {decision_type}"


@dataclass(frozen=True)
class Sealed:
    decision_type: str
    chosen: str
    word: str
    subject: str  # the proposal the seal names, `proposal:<sha256>`
    #: the other picks, when the person took more than one at this fork:
    #: `chosen` is the first of them, and these the rest, in their order
    also: tuple[str, ...] = ()


@dataclass(frozen=True)
class Deferred:
    """A fork the person sealed as not now: left undecided on purpose."""

    decision_type: str
    why: str
    subject: str


@runtime_checkable
class RecordLookup(Protocol):
    """Tier 0 of the entry and the first word in the checkpoint: the person's
    own record, under their key, asked through the kernel."""

    name: str

    def stack_for(self, sentence: str) -> str | None: ...

    def has_sealed(self, decision_type: str) -> Sealed | None: ...

    def propose(
        self,
        decision_type: str,
        chosen: str,
        *,
        over: list[str],
        why: str,
        surface: str = "",
        word: str | None = None,
        kept: dict | None = None,
    ) -> str: ...


class WillowRecord:
    """A box, asked through its kernel. `kernel` is the path of `kernel.py`;
    `box` the record's folder."""

    def __init__(self, kernel: Path | str, box: Path | str):
        self.kernel = Path(kernel)
        self.box = Path(box)
        self.name = f"willow record at {self.box}"

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        got = subprocess.run(
            [sys.executable, str(self.kernel), *argv[:1], "--box", str(self.box), *argv[1:]],
            capture_output=True,
            text=True,
        )
        if got.returncode == 2:
            raise WillowRecordError((got.stderr or got.stdout).strip() or "the kernel refused")
        return got

    def ask(self, words: str) -> dict | None:
        """The kernel's answer when the person sealed one for these words,
        else None. Exit 2 from the kernel is a refusal, raised."""
        got = self._run("bite", words)
        line = (got.stdout.strip().splitlines() or [""])[-1]
        try:
            doc = json.loads(line)
        except ValueError as e:
            raise WillowRecordError(f"the kernel's answer is not JSON: {line[:80]!r}") from e
        return doc if isinstance(doc, dict) and doc.get("state") == "sealed" else None

    def has_sealed(self, dt: str) -> Sealed | None:
        doc = self.ask(question(dt))
        if doc is None:
            return None
        try:
            data = json.loads(doc.get("answer", ""))
            chosen, word = data["chose"], data["word"]
        except (ValueError, KeyError, TypeError) as e:
            raise WillowRecordError(
                f"the sealed answer for {question(dt)!r} is not a decision: {e}"
            ) from e
        if not isinstance(chosen, str) or not isinstance(word, str):
            raise WillowRecordError(f"the sealed answer for {question(dt)!r} is not a decision")
        also = data.get("also") or []
        also = tuple(n for n in also if isinstance(n, str)) if isinstance(also, list) else ()
        return Sealed(decision_type=dt, chosen=chosen, word=word,
                      subject=str(doc.get("by", "")), also=also)  # fmt: skip

    def has_deferred(self, dt: str) -> Deferred | None:
        """The not-now the person sealed for this fork, else None."""
        doc = self.ask(not_now_question(dt))
        if doc is None:
            return None
        try:
            data = json.loads(doc.get("answer", ""))
            chosen = data["chose"]
        except (ValueError, KeyError, TypeError) as e:
            raise WillowRecordError(
                f"the sealed answer for {not_now_question(dt)!r} is not a not-now: {e}"
            ) from e
        if chosen != NOT_NOW:
            raise WillowRecordError(
                f"the sealed answer for {not_now_question(dt)!r} is not a not-now"
            )
        return Deferred(
            decision_type=dt, why=str(data.get("why", "")), subject=str(doc.get("by", ""))
        )

    def stack_for(self, sentence: str) -> str | None:
        doc = self.ask(sentence)
        return None if doc is None else str(doc.get("answer", ""))

    def propose(
        self,
        dt: str,
        chosen: str,
        *,
        over: list[str],
        why: str,
        surface: str = "",
        word: str | None = None,
        kept: dict | None = None,
        also: list[str] | None = None,
    ) -> str:
        """One proposal under `question(dt)`: the bite first, so the door has
        a question to hold it to, then the line. Returns the subject the
        person will seal or decline. The line's shape is the add-on's, so
        either side reads what the other wrote. `kept` rides on the same row
        and never replaces a field named here. `also` is the other picks
        when the person took more than one at this fork; said only then, so
        one pick reads as it always has."""
        self._run("bite", question(dt))
        data = {
            **(kept or {}),
            "word": word if word is not None else dt,
            "decision_type": dt,
            "chose": chosen,
            "over": list(over),
            "why": why,
            "surface": surface,
        }
        taken = [chosen]
        if also:
            data["also"] = [n for n in also if n != chosen]
            taken += data["also"]
        return self._proposed({
            "path": DECISION_PATH.format(dt),
            "data": json.dumps(data, sort_keys=True, ensure_ascii=False),
            "cites": [],
            "claim": f"for {dt!r}: {' and '.join(taken)} over {', '.join(over) or 'nothing'}; {why or 'no reason given'}",
        })  # fmt: skip

    def propose_not_now(
        self,
        dt: str,
        *,
        why: str = "",
        word: str | None = None,
        shown: list[str] | None = None,
        kept: dict | None = None,
    ) -> str:
        """A fork left for later, as its own proposal under
        `not_now_question(dt)`: sealed, it says the person chose not to decide
        yet, and the fork's own question stays open. `shown` is what they were
        shown, in the order they saw it. Returns the subject."""
        self._run("bite", not_now_question(dt))
        data = {
            **(kept or {}),
            "word": word if word is not None else dt,
            "decision_type": dt,
            "chose": NOT_NOW,
            "why": why,
            "shown": list(shown or []),
        }
        return self._proposed({
            "path": NOT_NOW_PATH.format(dt),
            "data": json.dumps(data, sort_keys=True, ensure_ascii=False),
            "cites": [],
            "claim": f"for {dt!r}: not now; {why or 'no reason given'}",
        })  # fmt: skip

    def _proposed(self, prop: dict) -> str:
        """One line through the door; the subject it passed under."""
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "proposal.jsonl"
            f.write_text(json.dumps(prop, ensure_ascii=False) + "\n", encoding="utf-8")
            got = self._run("propose", "--file", str(f))
        said = (got.stdout.strip().splitlines() or [""])[-1]
        if not said.startswith("pass ") or len(said.split()) < 2:
            raise WillowRecordError(f"the door turned the proposal back: {said[:120]}")
        return said.split()[1]
