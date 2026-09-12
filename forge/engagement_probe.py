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

from . import checkpoint_engagement, friction_floor

__all__ = ["CORPUS", "decompose", "probe", "summary", "main"]

# The floor a rationale must clear to escape the rubber-stamp flag, and the
# ceiling above which checkpoint_schedule.grade pushes the review interval OUT.
# Both imported/named from their owners rather than restated (the audit that
# caught two coincidental `0.34` literals applies here too).
FLOOR = checkpoint_engagement.RUBBER_STAMP_FLOOR  # 0.34
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
    {
        "id": "argparse-default",
        "kind": "not_a_decision",
        "context": CONTEXT_MAJOR,
        "note": "forge/entry.py --why default; reached the ledger on 2026-09-07",
        "text": "picked at the command line",
    },
    {
        "id": "argparse-default-sealed",
        "kind": "not_a_decision",
        "context": CONTEXT_MAJOR,
        "note": "the canonical form it was sealed as, per the-positional-default.md",
        "text": "web: picked at the command line",
    },
    {
        "id": "empty",
        "kind": "not_a_decision",
        "context": CONTEXT_DATES,
        "note": "picked an option, explained nothing",
        "text": "",
    },
    {
        "id": "echo",
        "kind": "not_a_decision",
        "context": CONTEXT_DATES,
        "note": "the prompt read back",
        "text": "when a picture gets a date, where does the date go",
    },
    # ── human-typed wave-throughs ───────────────────────────────────────────
    {"id": "assent-bare", "kind": "rubber_stamp", "context": CONTEXT_DATES, "text": "yes"},
    {
        "id": "assent-polite",
        "kind": "rubber_stamp",
        "context": CONTEXT_DATES,
        "text": "sounds good",
    },
    {
        "id": "assent-deferential",
        "kind": "rubber_stamp",
        "context": CONTEXT_DATES,
        "text": "whatever you think is best",
    },
    # ── real reasoning ──────────────────────────────────────────────────────
    {
        "id": "real-plain",
        "kind": "real",
        "context": CONTEXT_DATES,
        "note": "substantive, names the tradeoff, uses no pushback vocabulary",
        "text": (
            "the originals are already correct and a sidecar drifts the moment "
            "anyone re-exports, so we lose nothing by writing in place and gain "
            "one less thing to keep in sync"
        ),
    },
    {
        "id": "real-with-cues",
        "kind": "real",
        "context": CONTEXT_DATES,
        "note": "the same argument, rephrased with contrast markers",
        "text": (
            "however, I disagree with the recommendation: the dates are already "
            "correct, whereas a sidecar drifts on re-export"
        ),
    },
    {
        "id": "real-question",
        "kind": "real",
        "context": CONTEXT_DATES,
        "note": "engagement expressed as a question rather than a claim",
        "text": "but what happens when someone re-exports? does the sidecar survive that?",
    },
    {
        "id": "real-short",
        "kind": "real",
        "context": CONTEXT_DATES,
        "note": "a genuine one-line reason — the case the gate's docstring says it "
        "may misread, and names as the intended bias",
        "text": "exif, because the date has to travel with the file",
    },
    # ── the control: an off-topic non-sequitur ──────────────────────────────
    {
        "id": "non-sequitur",
        "kind": "not_a_decision",
        "context": CONTEXT_DATES,
        "note": "CONTROL — says nothing about the decision. Maximum novelty by "
        "construction; scores what irrelevance is worth.",
        "text": "the kettle is on and the cat needs feeding",
    },
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
        d.update(id=row["id"], kind=row["kind"], text=row["text"], note=row.get("note", ""))
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


# ── separability: could ANY reweighting of these four terms work? ───────────


def _feature_vector(text: str, context: str) -> list[float]:
    """The four terms `friction_score` combines, BEFORE weighting — the raw
    feature space. `decompose` reports the weighted contributions; this reports
    the inputs, which is what the question below is about."""
    d = decompose(text, context)
    low = text.lower()
    toks = set(friction_floor._WORD.findall(low))
    pushback_n = len(friction_floor._PUSHBACK & toks)
    grounding_n = len(d["grounding_hits"])
    return [
        min(1.0, pushback_n / 2),
        min(1.0, grounding_n / 2),
        min(1.0, d["unechoed_fraction"] * 1.5),
        1.0 if "?" in text else 0.0,
    ]


def separability(corpus: tuple[dict, ...] = CORPUS) -> dict:
    """Is the corpus linearly separable in `friction_score`'s four features?

    This is the question behind remedy 2 in
    docs/design/the-forge-engagement-defect.md — "wrap rather than re-vendor,
    reweight the terms for our subject." Reweighting is exactly a choice of
    linear coefficients, so if the labels are not linearly separable in these
    features, NO reweighting can work and the remedy is dead without anyone
    needing to try one.

    Two things are reported. **Collisions** are the decisive part: rows with
    identical feature vectors and opposite labels. A collision cannot be fixed
    by any function of these features at all, linear or otherwise — the
    distinction is simply not encoded. The **perceptron** is the general check,
    and it converges if and only if the classes are linearly separable.

    Deterministic: fixed corpus, fixed learning rate, zero init, no randomness."""
    rows = []
    for r in corpus:
        f = _feature_vector(r["text"], r["context"])
        rows.append(
            {"id": r["id"], "kind": r["kind"], "features": f, "should_pass": r["kind"] == "real"}
        )

    # ── collisions ──────────────────────────────────────────────────────────
    by_vec: dict[tuple, list[dict]] = {}
    for r in rows:
        by_vec.setdefault(tuple(r["features"]), []).append(r)
    collisions = [
        {
            "features": list(v),
            "ids": [x["id"] for x in group],
            "labels": sorted({x["kind"] for x in group}),
        }
        for v, group in by_vec.items()
        if len({x["should_pass"] for x in group}) > 1
    ]

    # ── perceptron: converges iff linearly separable ─────────────────────────
    w = [0.0] * 4
    bias = 0.0
    lr = 0.05
    epochs_run = 0
    separable = False
    for epoch in range(1, _PERCEPTRON_EPOCHS + 1):
        epochs_run = epoch
        errors = 0
        for r in rows:
            score = sum(wi * fi for wi, fi in zip(w, r["features"])) + bias
            if (score > 0) != r["should_pass"]:
                sign = 1.0 if r["should_pass"] else -1.0
                w = [wi + lr * sign * fi for wi, fi in zip(w, r["features"])]
                bias += lr * sign
                errors += 1
        if errors == 0:
            separable = True
            break

    return {
        "rows": rows,
        "collisions": collisions,
        "linearly_separable": separable,
        "epochs": epochs_run,
        "weights": [round(x, 4) for x in w] if separable else None,
        "verdict": (
            "reweighting cannot fix this: the classes are not linearly separable "
            "in friction_score's four features, so no choice of coefficients "
            "separates them"
            if not separable
            else "the classes ARE linearly separable — a reweighting exists; "
            "revisit remedy 2 in the-forge-engagement-defect.md"
        ),
    }


# Perceptron convergence is bounded by (R/margin)² updates. With 12 points whose
# features all lie in [0,1], a separable arrangement converges in the low
# hundreds; 20k epochs is ~240k updates, several orders of margin. Larger values
# only make the suite slower without making the verdict any more certain.
_PERCEPTRON_EPOCHS = 20_000
_FEATURE_NAMES = ("pushback", "grounding", "novelty", "question")


def _render_separability(s: dict) -> str:
    w = max(len(r["id"]) for r in s["rows"])
    out = [
        "could any reweighting of friction_score's terms separate these?",
        "",
        f"{'id':<{w}}  {'label':<14} "
        + " ".join(f"{n:>9}" for n in _FEATURE_NAMES)
        + "  should_pass",
        f"{'-' * w}  {'-' * 14} " + " ".join("-" * 9 for _ in _FEATURE_NAMES) + "  -----------",
    ]
    for r in s["rows"]:
        out.append(
            f"{r['id']:<{w}}  {r['kind']:<14} "
            + " ".join(f"{v:>9.2f}" for v in r["features"])
            + f"  {r['should_pass']}"
        )
    out.append("")
    if s["collisions"]:
        out.append("IDENTICAL FEATURE VECTORS, OPPOSITE LABELS — no function of")
        out.append("these features can separate these rows, reweighted or not:")
        for c in s["collisions"]:
            vec = ", ".join(f"{n}={v:.2f}" for n, v in zip(_FEATURE_NAMES, c["features"]))
            out.append(f"  [{vec}]")
            out.append(f"    {', '.join(c['ids'])}   ({' vs '.join(c['labels'])})")
        out.append("")
    out.append(f"linearly separable : {s['linearly_separable']} (perceptron, {s['epochs']} epochs)")
    out.append("")
    out.append(s["verdict"])
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="engagement_probe.py",
        description="what the engagement gate actually rewards — read-only",
    )
    p.add_argument(
        "--separability",
        action="store_true",
        help="ask whether ANY reweighting of the four terms could "
        "separate the corpus (remedy 2 in the defect paper)",
    )
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.separability:
        sep = separability()
        print(json.dumps(sep, indent=2, sort_keys=True) if args.json else _render_separability(sep))
        # Exit 1 while reweighting cannot rescue the scorer — the same
        # gateable-rather-than-remembered posture as the default mode.
        return 0 if sep["linearly_separable"] else 1
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
