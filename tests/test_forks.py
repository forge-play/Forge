"""forge/forks.py: which forks are blind, the order a blind fork's cards are
shown in, and the confidence stated from blind picks alone."""

from __future__ import annotations

import hashlib

from forge import forks


def test_one_fork_in_five_is_blind_by_its_key_alone():
    keys = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(2000)]
    share = sum(forks.is_blind(k) for k in keys) / len(keys)
    assert 0.17 < share < 0.23
    assert all(forks.is_blind(k) == forks.is_blind(k) for k in keys[:50])  # nothing kept


def test_the_hashes_are_the_ones_a_record_was_made_with():
    """Unchanged from the card these rules came from: the blind test is the
    SHA-256 of "blind KEY", its first eight hex digits mod five."""
    key = hashlib.sha256(b"read my email").hexdigest()
    expect = int(hashlib.sha256(f"blind {key}".encode()).hexdigest()[:8], 16) % 5 == 0
    assert forks.is_blind(key) is expect
    names = ["mail", "apple-mail", "eml"]
    by_hash = sorted(names, key=lambda n: hashlib.sha256(f"shown {key} {n}".encode()).hexdigest())
    assert forks.shown_order(key, names) == by_hash


def test_a_blind_forks_order_is_its_own_and_the_same_each_time():
    names = [f"card-{i}" for i in range(8)]
    shown = forks.shown_order("k", names)
    assert sorted(shown) == sorted(names) and shown == forks.shown_order("k", list(reversed(names)))
    assert any(forks.shown_order(k, names) != names for k in ("a", "b", "c"))


def test_no_confidence_before_five_blind_picks_or_under_one_half():
    assert forks.stated_confidence(4, 4) is None  # four settled: not yet measured
    assert forks.stated_confidence(2, 5) is None  # 3/7 is under one half
    assert forks.stated_confidence(3, 6) == 0.5  # 4/8: one half, stated
    assert forks.stated_confidence(5, 5) == 0.86  # never a certainty
    assert forks.stated_confidence(500, 500) == forks.CEILING


def test_every_stated_confidence_is_in_the_range_calibration_bins():
    from forge import calibration

    for n in range(forks.MEASURED, 40):
        for k in range(n + 1):
            c = forks.stated_confidence(k, n)
            if c is not None:
                assert calibration.BIN_EDGES[0] <= c <= forks.CEILING < calibration.BIN_EDGES[-1]
