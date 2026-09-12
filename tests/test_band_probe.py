"""forge/band_probe.py — §5 of docs/design/the-forge-pedagogy.md, run.

The claim: the `auto` band keys on the engine's confidence and the store's fill,
never on the maker's demonstrated calibration. These pin the measurement so the
finding stops being an assertion and starts being a regression test — if a
future change makes band selection calibration-aware, `test_the_two_makers_take
_the_same_bands` fails, which is the correct way for this to break.
"""

from __future__ import annotations

import pytest

from forge import band_probe, checkpoint_memory

_needs_nestor = pytest.mark.skipif(
    not checkpoint_memory.nestor_available(), reason="nestor not installed"
)


@pytest.fixture
def root(tmp_path):
    return tmp_path / "checkpoints"


@_needs_nestor
def test_the_two_makers_are_maximally_apart_in_calibration(root):
    """The instrument's own contrast check. A null finding is only worth
    reporting if the probe could have seen the effect; this asserts the two
    makers really are the two extremes the ledger can express."""
    aligned = band_probe.run("aligned", rounds=3, root=root / "a")
    contrary = band_probe.run("contrary", rounds=3, root=root / "c")
    assert aligned["hit_rate"] == 1.0 and contrary["hit_rate"] == 0.0
    assert aligned["overconfidence"] == pytest.approx(band_probe.CONFIDENCE - 1.0)
    assert contrary["overconfidence"] == pytest.approx(band_probe.CONFIDENCE)


@_needs_nestor
def test_the_two_makers_take_the_same_bands(root):
    """§5, measured. Two makers 100pp apart in calibration take an IDENTICAL
    band trajectory, because `run_checkpoint` reads
    `checkpoint_memory.check(surface)` and nothing else — no calibration value
    is in scope at the branch."""
    aligned = band_probe.run("aligned", rounds=4, root=root / "a")
    contrary = band_probe.run("contrary", rounds=4, root=root / "c")
    assert aligned["band_counts"] == contrary["band_counts"]
    s = band_probe.summary({"aligned": aligned, "contrary": contrary})
    assert s["auto_rate_gap_pp"] == 0.0
    assert s["separable"] is False, "a gap below the sealed harness floor is not a finding"


@_needs_nestor
def test_a_maker_who_is_always_wrong_still_gets_auto_applied(root):
    """The consequence §5 actually cares about, stated as a number: being wrong
    every single time costs a maker nothing in how often the engine stops
    asking them."""
    contrary = band_probe.run("contrary", rounds=5, root=root / "c")
    assert contrary["hit_rate"] == 0.0
    assert contrary["auto_rate_pct"] > 50.0
    assert contrary["by_band"]["auto"]["hit_rate"] == 0.0, (
        "every auto-applied decision belonged to a maker who was wrong about it"
    )


@_needs_nestor
def test_the_auto_rate_rises_as_the_store_fills(root):
    """The other half of the claim: it is store fill that drives the band, and
    fill only ever grows. Round 1 has nothing sealed and is all socratic; every
    later round is auto."""
    r = band_probe.run("contrary", rounds=4, root=root / "c")
    first, rest = r["per_round"][0], r["per_round"][1:]
    assert first.get("auto", 0) == 0 and first.get("socratic", 0) > 0
    assert all(x.get("socratic", 0) == 0 and x.get("auto", 0) > 0 for x in rest)
