"""forge/forks.py — the rules a fork is asked and scored by, so that every
maker that shows a person a fork keeps the same honesty.

A fork is a choice put to the person: the cards a search found for what they
said, the first of them recommended. Two things make what they pick worth
learning from:

- **Some forks are blind.** One in `BLIND_EVERY` is shown with no
  recommendation, its cards in an order of their own (`shown_order`), so a
  pick made there says what the person wanted, not how often they went with
  what they were told. Which forks are blind is decided by the hash of the
  fork's key alone (`is_blind`): every maker asked about the same words
  agrees, and nothing is kept to decide it.
- **A confidence is stated only from blind picks, and only toward what is
  believed.** Of the blind forks settled on one matcher, the search's first
  was taken k of n times; the confidence is `(k+1)/(n+2)` (Laplace's rule of
  succession, so five of five is 0.86 and never a certainty), capped at
  0.99, and none is stated before `MEASURED` are settled or when it falls
  under one half (the house convention: claims are stated in the direction
  believed, so confidence lives in [0.5, 0.99], as `calibration` bins it).

`key` is what names the fork: for Willow's `forge` card, the kernel's
bite key of the person's sentence (the SHA-256 of its words in order), so a
question retyped in another case is the same fork. The hashes are SHA-256 of
`"blind {key}"` and `"shown {key} {name}"`, unchanged from the card these
rules came from, so a record made before they moved here reads the same.

Pure stdlib, no I/O.
"""

from __future__ import annotations

import hashlib

__all__ = ["BLIND_EVERY", "MEASURED", "is_blind", "shown_order", "stated_confidence"]

#: one fork in this many is blind
BLIND_EVERY = 5
#: blind picks settled before a confidence is stated
MEASURED = 5
#: the most a stated confidence can be: never a certainty
CEILING = 0.99


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def is_blind(key: str, every: int = BLIND_EVERY) -> bool:
    """Whether the fork named by `key` is shown blind: by its hash alone."""
    return int(_h(f"blind {key}")[:8], 16) % every == 0


def shown_order(key: str, names: list[str]) -> list[str]:
    """A blind fork's cards in the order they are shown: by the hash of the
    fork's key and each name, the same every time it is asked, and nothing of
    the search's order."""
    return sorted(names, key=lambda n: _h(f"shown {key} {n}"))


def stated_confidence(k: int, n: int, measured: int = MEASURED) -> float | None:
    """The confidence to state when the search's first was taken `k` of `n`
    blind forks: `(k+1)/(n+2)` to two places, at most `CEILING`; None before
    `measured` are settled, or when it would fall under one half."""
    if n < measured or 2 * k < n:  # (k+1)/(n+2) < 1/2 exactly when 2k < n
        return None
    return min(round((k + 1) / (n + 2), 2), CEILING)
