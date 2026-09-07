#!/usr/bin/env python3
"""forge/engagement_probe.py — what does the engagement gate actually reward?

    "A gate that blocked a seal on a low score would be exactly the
    frictionless-in-reverse coercion the friction primitive refuses to become."
                                        (checkpoint_engagement.py, bite 3)

`checkpoint_engagement` scores a maker's rationale and `checkpoint_schedule
.grade` turns that score into an FSRS rating: below `RUBBER_STAMP_FLOOR` grades
`Hard` (resurface sooner), above `_EASY_MIN_ENGAGEMENT` grades `Easy` (push it
out). So the scorer moves review dates on real decisions. This module measures
what it is actually keyed on, and it exists because the answer is not what the
gate's own docstring implies.

**What this is.** A read-only probe over a fixed corpus of labelled rationales.
It writes nothing, calls no model, and touches no store. It reports, per row,
the authoritative `checkpoint_engagement.engagement_score` and a DECOMPOSITION
of that score into `friction_score`'s four terms, so a reader can see which term
carried it.

**Reuse, not reimplementation (rule 11).** The score is always
`checkpoint_engagement.engagement_score` — never recomputed here. The
decomposition reuses `friction_floor`'s OWN lexicons and helpers by import
(`_PUSHBACK`, `_GROUNDING`, `_content`), never a restated copy, so a lexicon
edit upstream changes this probe's attribution automatically. `forge/
friction_floor.py` is byte-for-byte with willow-gate's original and willow-mcp
hashes it as a drift guard — nothing here edits it, and nothing here should.

The decomposition is a MODEL of the scorer, and `decompose()` checks itself: if
the reconstructed total drifts from the authoritative score, the row is flagged
`reconstructed=False` rather than silently reported as attribution. A probe that
lied about the thing it was probing would be worse than no probe.

Usage:
    python -m forge.engagement_probe            # the table
    python -m forge.engagement_probe --json     # machine-readable

Exit 1 when any rationale labelled `not_a_decision` scores at or above
`RUBBER_STAMP_FLOOR` — i.e. when a string nobody typed as a reason is not being
read as a rubber-stamp. That is the condition this probe was written to catch,
so a hook can gate on it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import checkpoint_engagement, friction_floor

__all__ = ["Row", "CORPUS", "decompose", "probe", "summary", "main"]

# The floor a rationale must clear to escape the rubber-stamp flag, and the
# ceiling above which checkpoint_schedule.grade pushes the review interval OUT.
# Both imported/named from their owners rather than restated (the audit that
# caught two coincidental `0.34` literals applies here too).
FLOOR = checkpoint_engagement.RUBBER_STAMP_FLOOR          # 0.34
EASY_MIN = 0.66  # checkpoint_schedule._EASY_MIN_ENGAGEMENT (private; see note)

# `_EASY_MIN_ENGAGEMENT` is module-private in checkpoint_schedule and is
# documented there as "this module's own" constant with no engagement-side
# equivalent, so it is named here rather than imported through the private
# surface. If it moves, this probe's `grade` column is wrong and nothing will
# say so — the one drift risk in this file, recorded rather than hidden.


# ── the corpus ──────────────────────────────────────────────────────────────
#
# `kind` is the LABEL — what a human would say this rationale is — and it is
# the only judgment in this file. Everything else is measured.
#
#   not_a_decision : nobody typed this as a reason; it is a default, an echo,
#                    or silence. It MUST read as a rubber-stamp.
#   rubber_stamp   : a human typed it, and it is still a wave-through.
#   real           : a grounded rationale naming a tradeoff. It must NOT read
#                    as a rubber-stamp.

CONTEXT_MAJOR = (
    "'is source-trail a tool or an app that lives in willow-grove' "
    "could be web, mobile, desktop — which major?"
)
CONTEXT_DATES = "When a picture gets a date, where does the date go?"

CORPUS: tuple[dict, ...] = (
    # ── the one that started this: argparse's own --why default ─────────────
    {"id": "argparse-default", "kind": "not_a_decision", "context": CONTEXT_MAJOR,
     "note": "forge/entry.py --why default; reached the ledger on 2026-09-07",
     "text": "picked at the command line"},
    {"id": "argparse-default-sealed", "kind": "not_a_decision", "context": CONTEXT_MAJOR,
     "note": "the canonical form it was sealed as, per the-positional-default.md",
     "text": "web: picked at the command line"},
    {"id": "empty", "kind": "not_a_decision", "context": CONTEXT_DATES,
     "note": "picked an option, explained nothing",
     "text": ""},
    {"id": "echo", "kind": "not_a_decision", "context": CONTEXT_DATES,
     "note": "the prompt read back",
     "text": "when a picture gets a date, where does the date go"},

    # ── human-typed wave-throughs ───────────────────────────────────────────
    {"id": "assent-bare", "kind": "rubber_stamp", "context": CONTEXT_DATES,
     "text": "yes"},
    {"id": "assent-polite", "kind": "rubber_stamp", "context": CONTEXT_DATES,
     "text": "sounds good"},
    {"id": "assent-deferential", "kind": "rubber_stamp", "context": CONTEXT_DATES,
     "text": "whatever you think is best"},

    # ── real reasoning ──────────────────────────────────────────────────────
    {"id": "real-plain", "kind": "real", "context": CONTEXT_DATES,
     "note": "substantive, names the tradeoff, uses no pushback vocabulary",
     "text": ("the originals are already correct and a sidecar drifts the moment "
              "anyone re-exports, so we lose nothing by writing in place and gain "
              "one less thing to keep in sync")},
    {"id": "real-with-cues", "kind": "real", "context": CONTEXT_DATES,
     "note": "the same argument, rephrased with contrast markers",
     "text": ("however, I disagree with the recommendation: the dates are already "
              "correct, whereas a sidecar drifts on re-export")},
    {"id": "real-question", "kind": "real", "context": CONTEXT_DATES,
     "note": "engagement expressed as a question rather than a claim",
     "text": "but what happens when someone re-exports? does the sidecar survive that?"},
    {"id": "real-short", "kind": "real", "context": CONTEXT_DATES,
     "note": "a genuine one-line reason — the case the gate's docstring says it "
             "may misread, and names as the intended bias",
     "text": "exif, because the date has to travel with the file"},

    # ── the control: an off-topic non-sequitur ──────────────────────────────
    {"id": "non-sequitur", "kind": "not_a_decision", "context": CONTEXT_DATES,
     "note": "CONTROL — says nothing about the decision. Maximum novelty by "
             "construction; scores what irrelevance is worth.",
     "text": "the kettle is on and the cat needs feeding"},
)


# ── decomposition ───────────────────────────────────────────────────────────

def decompose(text: str, context: str) -> dict:
    """The authoritative score, plus which of `friction_score`'s four terms
    produced it.

    The total is ALWAYS `checkpoint_engagement.engagement_score` — the terms
    are an attribution model, and `reconstructed` reports whether they actually
    add up to it (tolerance 1e-9). A False there means `friction_score` changed
    and this decomposition is stale; trust `score`, not the terms."""
    score = checkpoint_engagement.engagement_score(text, context)

    low = text.lower()
    toks = set(friction_floor._WORD.findall(low))
    pushback_hits = sorted(friction_floor._PUSHBACK & toks)
    grounding_hits = sorted(friction_floor._GROUNDING & toks)

    grounding_n = len(grounding_hits)
    extras = []
    if re.search(r"\d", text):
        grounding_n += 1
        extras.append("digit")
    if re.search(r"[/(){}=]|```|\.py|::", text):
        grounding_n += 1
        extras.append("code-punctuation")

    a_words = friction_floor._content(text)
    u_words = friction_floor._content(context)
    novelty = len(a_words - u_words) / max(1, len(a_words))
    question = 1.0 if "?" in text else 0.0

    terms = {
        "pushback": 0.40 * min(1.0, len(pushback_hits) / 2),
        "grounding": 0.30 * min(1.0, grounding_n / 2),
        "novelty": 0.20 * min(1.0, novelty * 1.5),
        "question": 0.10 * question,
    }
    total = max(0.0, min(1.0, sum(terms.values())))

    return {
        "score": score,
        "terms": terms,
        "dominant": max(terms, key=lambda k: terms[k]) if any(terms.values()) else "",
        "pushback_hits": pushback_hits,
        "grounding_hits": grounding_hits + extras,
        "unechoed_fraction": novelty,
        "reconstructed": abs(total - score) < 1e-9,
        "rubber_stamp": checkpoint_engagement.is_rubber_stamp(text, context),
        "grade": _grade_name(score),
    }


def _grade_name(score: float) -> str:
    """What `checkpoint_schedule.grade` would return for a HELD review at this
    engagement — the review-interval consequence, which is the reason the score
    matters at all."""
    if score < FLOOR:
        return "Hard (sooner)"
    if score > EASY_MIN:
        return "Easy (later)"
    return "Good"


# ── the probe ───────────────────────────────────────────────────────────────

def probe(corpus: tuple[dict, ...] = CORPUS) -> list[dict]:
    """Score every corpus row. Read-only; no store, no model, no clock."""
    out = []
    for row in corpus:
        d = decompose(row["text"], row["context"])
        d.update(id=row["id"], kind=row["kind"], text=row["text"],
                 note=row.get("note", ""))
        # The label's expectation, and whether the scorer met it.
        d["expected_rubber_stamp"] = row["kind"] in ("not_a_decision", "rubber_stamp")
        d["agrees_with_label"] = d["rubber_stamp"] == d["expected_rubber_stamp"]
        out.append(d)
    return out


def summary(rows: list[dict]) -> dict:
    """Counts a reader should not have to tally by hand."""
    missed = [r for r in rows if r["kind"] == "not_a_decision" and not r["rubber_stamp"]]
    false_thin = [r for r in rows if r["kind"] == "real" and r["rubber_stamp"]]
    return {
        "n": len(rows),
        "floor": FLOOR,
        "easy_min": EASY_MIN,
        "agree_with_label": sum(1 for r in rows if r["agrees_with_label"]),
        "not_a_decision_unflagged": [r["id"] for r in missed],
        "real_read_as_thin": [r["id"] for r in false_thin],
        "decomposition_stale": [r["id"] for r in rows if not r["reconstructed"]],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def _render(rows: list[dict], s: dict) -> str:
    w = max(len(r["id"]) for r in rows)
    out = [
        f"engagement gate — what it rewards      floor={s['floor']}  easy_min={s['easy_min']}",
        "",
        f"{'id':<{w}}  {'label':<14} {'score':>6}  {'grade':<13} {'carried by':<10} flag",
        f"{'-' * w}  {'-' * 14} {'-' * 6}  {'-' * 13} {'-' * 10} ----",
    ]
    for r in rows:
        mark = " " if r["agrees_with_label"] else "!"
        out.append(
            f"{r['id']:<{w}}  {r['kind']:<14} {r['score']:>6.3f}  "
            f"{r['grade']:<13} {r['dominant']:<10} "
            f"{'stamp' if r['rubber_stamp'] else '-':<5}{mark}"
        )
    out += ["", f"agrees with label: {s['agree_with_label']}/{s['n']}"]
    if s["not_a_decision_unflagged"]:
        out.append("")
        out.append("NOT A DECISION, YET NOT FLAGGED — these grade Good or better,")
        out.append("so they push the review interval OUT:")
        for r in rows:
            if r["id"] in s["not_a_decision_unflagged"]:
                by = ", ".join(f"{k}={v:.2f}" for k, v in r["terms"].items() if v)
                out.append(f"  {r['id']}: {r['score']:.3f}  ({by})")
                if r["grounding_hits"]:
                    out.append(f"    grounding tokens: {r['grounding_hits']}")
                out.append(f"    unechoed fraction: {r['unechoed_fraction']:.2f}")
    if s["real_read_as_thin"]:
        out.append("")
        out.append(f"REAL, READ AS THIN: {', '.join(s['real_read_as_thin'])}")
    if s["decomposition_stale"]:
        out.append("")
        out.append(f"DECOMPOSITION STALE (friction_score changed): {s['decomposition_stale']}")
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="engagement_probe.py",
        description="what the engagement gate actually rewards — read-only")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = probe()
    s = summary(rows)
    if args.json:
        print(json.dumps({"summary": s, "rows": rows}, indent=2, sort_keys=True))
    else:
        print(_render(rows, s))
    # Exit 1 while a string nobody typed as a reason reads as engagement.
    return 1 if s["not_a_decision_unflagged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
