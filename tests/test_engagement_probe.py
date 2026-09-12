"""forge/engagement_probe.py — what the engagement gate actually rewards.

The probe is a measurement, so these tests pin the measurement rather than the
prose about it. If the scorer is ever fixed upstream, these fail loudly and the
defect paper needs rewriting — which is the correct way for a finding to expire.
"""

from __future__ import annotations

from forge import checkpoint_engagement
from forge import engagement_probe as ep


def test_the_argparse_default_clears_the_rubber_stamp_floor():
    """The finding the probe exists for: a string typed by nobody reads as
    engagement. Not asserted as a magic number — asserted against the floor it
    has to clear, which is the thing that matters."""
    d = ep.decompose("picked at the command line", ep.CONTEXT_MAJOR)
    assert d["score"] >= ep.FLOOR
    assert d["rubber_stamp"] is False
    assert d["grade"] == "Good", "so it pushed the review interval OUT"


def test_it_clears_the_floor_on_a_homonym():
    """Why it clears: `line` is in the grounding lexicon as in *file, line* — a
    code location — and "command line" collides with it. Strike the accidental
    token and the same phrase is flagged, which is the whole diagnosis."""
    d = ep.decompose("picked at the command line", ep.CONTEXT_MAJOR)
    assert "line" in d["grounding_hits"]
    without = ep.decompose("picked at the command prompt", ep.CONTEXT_MAJOR)
    assert without["score"] < ep.FLOOR and without["rubber_stamp"] is True


def test_a_substantive_rationale_is_read_as_thin():
    """The error in the other direction, and the one that costs a real maker."""
    row = next(r for r in ep.CORPUS if r["id"] == "real-plain")
    d = ep.decompose(row["text"], row["context"])
    assert d["rubber_stamp"] is True
    assert d["grade"] == "Hard (sooner)"


def test_the_same_argument_with_contrast_markers_scores_three_times_higher():
    """What the scorer is actually keyed on: disagreement vocabulary."""
    plain = next(r for r in ep.CORPUS if r["id"] == "real-plain")
    cues = next(r for r in ep.CORPUS if r["id"] == "real-with-cues")
    s_plain = ep.decompose(plain["text"], plain["context"])["score"]
    s_cues = ep.decompose(cues["text"], cues["context"])["score"]
    assert s_cues > s_plain
    assert ep.decompose(cues["text"], cues["context"])["dominant"] == "pushback"


def test_irrelevance_alone_does_not_clear_the_floor():
    """The control that stops an over-reading. Novelty is maximal for a
    non-sequitur too, so novelty is not what rescues the argparse default —
    the homonym is."""
    row = next(r for r in ep.CORPUS if r["id"] == "non-sequitur")
    d = ep.decompose(row["text"], row["context"])
    assert d["unechoed_fraction"] == 1.0
    assert d["rubber_stamp"] is True


def test_the_decomposition_reconstructs_the_authoritative_score():
    """The probe's own honesty check: the terms are a MODEL of the scorer, and
    a model that has drifted must say so rather than report attribution."""
    for r in ep.CORPUS:
        d = ep.decompose(r["text"], r["context"])
        assert d["reconstructed"], f"{r['id']}: decomposition no longer sums to the score"
        assert d["score"] == checkpoint_engagement.engagement_score(r["text"], r["context"])


def test_the_probe_exits_nonzero_while_a_non_decision_reads_as_engagement():
    assert ep.main([]) == 1


# ── separability: the evidence that killed remedy 2 ─────────────────────────


def test_reweighting_cannot_separate_the_corpus():
    """Remedy 2 in the-forge-engagement-defect.md was "reweight the terms for
    our subject". Reweighting IS a choice of linear coefficients, so this is
    decidable rather than arguable — and the answer is no."""
    s = ep.separability()
    assert s["linearly_separable"] is False
    assert s["epochs"] == ep._PERCEPTRON_EPOCHS, "the perceptron ran to exhaustion"


def test_the_collisions_are_the_decisive_part():
    """A collision is stronger than non-separability: identical feature vectors
    with opposite labels cannot be told apart by ANY function of these features,
    linear or not. "yes" and a thirty-word argument are the same point."""
    s = ep.separability()
    assert s["collisions"], "the finding rests on these"
    groups = {frozenset(c["ids"]) for c in s["collisions"]}
    assert any({"assent-bare", "real-plain"} <= g for g in groups), (
        "'yes' and a substantive rationale must be shown as the same point"
    )
    assert any({"argparse-default", "real-short"} <= g for g in groups), (
        "argparse's default and a genuine one-liner must be shown as the same point"
    )


def test_separability_mode_exits_nonzero_and_is_deterministic():
    assert ep.main(["--separability"]) == 1
    assert ep.separability() == ep.separability(), "no randomness in the verdict"
