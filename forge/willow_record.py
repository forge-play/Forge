#!/usr/bin/env python3
"""forge/willow_record.py — the person's record, asked through the kernel
(the-join.md, thread 3: one record).

A willow box is the person's own record: a hash chain of what was asked, what
was suggested, and what they sealed with their key. The Forge never reads
that key and never checks a seal itself. It asks the kernel, through the one
verb that serves a sealed answer only after proving it under the key:

    python kernel.py bite --box BOX "the words"
    {"state": "sealed", "answer": "...", "by": "proposal:<sha256>"}

Two questions the Forge puts to a record:

    has_sealed(decision_type)   the bite for the words Willow's `forge` add-on
                                proposes a decision under, `question(dt)`:
                                "forge decision willow-email". Sealed → the
                                option the person chose; else None.
    stack_for(sentence)         the bite for the sentence itself. A sealed
                                stack → its text; else None.

Every question is a row on the person's record, the engine's included: that
is the kernel's rule ("every step is written to a tamper-evident log"), not a
side effect to hide. A record that refuses — not a box, a chain that doesn't
verify — is `WillowRecordError`, and the entry refuses with it rather than
reading past a break.

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
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Sealed",
    "WillowRecord",
    "WillowRecordError",
    "decision_type",
    "question",
    "DECISION_PATH",
]

#: where the add-on proposes a decision, inside the box's `written/`
DECISION_PATH = "forge/decisions/{}.json"


class WillowRecordError(Exception):
    """The record refused the question: not a box, or a chain that doesn't
    verify, or a sealed answer that isn't the shape a decision has."""


def decision_type(word: str) -> str:
    """The fork's calibration key: the word said, in the Forge's charset."""
    return "willow-" + re.sub(r"[^A-Za-z0-9_.-]+", "-", word).strip("-")


def question(decision_type: str) -> str:
    """The words a decision is proposed and asked under."""
    return f"forge decision {decision_type}"


@dataclass(frozen=True)
class Sealed:
    decision_type: str
    chosen: str
    word: str
    subject: str  # the proposal the seal names, `proposal:<sha256>`


class WillowRecord:
    """A box, asked through its kernel. `kernel` is the path of `kernel.py`;
    `box` the record's folder."""

    def __init__(self, kernel: Path | str, box: Path | str):
        self.kernel = Path(kernel)
        self.box = Path(box)
        self.name = f"willow record at {self.box}"

    def ask(self, words: str) -> dict | None:
        """The kernel's answer when the person sealed one for these words,
        else None. Exit 2 from the kernel is a refusal, raised."""
        got = subprocess.run(
            [sys.executable, str(self.kernel), "bite", "--box", str(self.box), words],
            capture_output=True,
            text=True,
        )
        if got.returncode == 2:
            raise WillowRecordError((got.stderr or got.stdout).strip() or "the kernel refused")
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
        return Sealed(decision_type=dt, chosen=chosen, word=word, subject=str(doc.get("by", "")))

    def stack_for(self, sentence: str) -> str | None:
        doc = self.ask(sentence)
        return None if doc is None else str(doc.get("answer", ""))
