"""Tests for forge/checkpoint_schedule.py — the FSRS-backed (soft dependency)
spaced-repetition scheduler for checkpoint reviews.

Covers: `grade()`'s outcome->rating map (pure, no `fsrs` needed), `record_review`
under both real FSRS and the fixed-interval fallback (mirroring the soft-Nestor
technique `tests/test_checkpoint_calibration.py` uses for `nestor`, applied here
to `fsrs`), `is_due`/`due_at`, and the `review`/`due` CLI subcommands.
"""
from __future__ import annotations

import contextlib
import json
import sys
from datetime import datetime, timedelta, timezone

import pytest

from forge import checkpoint_schedule as sched

BUILDER_A = "a" * 32
PAIR_1 = "pair-1"

_HAS_FSRS = sched.fsrs_available()
_needs_fsrs = pytest.mark.skipif(not _HAS_FSRS, reason="fsrs not installed in this environment")


# ── fsrs-blocking helper, mirroring tests/test_checkpoint_calibration.py's
#    _nestor_blocked technique but for `fsrs` — see checkpoint_schedule.py's
#    own "Caches SUCCESS only" note: the module-level `_fsrs_cache` must be
#    reset to None too, or a prior successful import just gets replayed. ──

@contextlib.contextmanager
def _fsrs_blocked():
    saved_modules = {name: mod for name, mod in sys.modules.items()
                      if name == "fsrs" or name.startswith("fsrs.")}
    for name in saved_modules:
        del sys.modules[name]
    saved_cache = sched._fsrs_cache
    sched._fsrs_cache = None

    class _BlockFsrs:
        def find_spec(self, name, path, target=None):
            if name == "fsrs" or name.startswith("fsrs."):
                raise ImportError(f"blocked for test: {name}")
            return None

    finder = _BlockFsrs()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sched._fsrs_cache = saved_cache
        sys.modules.update(saved_modules)


# ── grade() — pure, does not touch fsrs at all ───────────────────────────────

def test_grade_held_with_no_engagement_is_good():
    assert sched.grade(sched.OUTCOME_HELD) == sched._RATING_GOOD


def test_grade_regressed_is_always_again():
    assert sched.grade(sched.OUTCOME_REGRESSED) == sched._RATING_AGAIN


def test_grade_regressed_ignores_engagement():
    # a regression is Again regardless of how hard the maker thought about it
    assert sched.grade(sched.OUTCOME_REGRESSED, engagement=0.99) == sched._RATING_AGAIN
    assert sched.grade(sched.OUTCOME_REGRESSED, engagement=0.01) == sched._RATING_AGAIN


def test_grade_held_below_rubber_stamp_floor_is_hard():
    thin = sched._HARD_MAX_ENGAGEMENT - 0.01
    assert thin >= 0.0
    assert sched.grade(sched.OUTCOME_HELD, engagement=thin) == sched._RATING_HARD


def test_grade_held_above_easy_floor_is_easy():
    strong = sched._EASY_MIN_ENGAGEMENT + 0.01
    assert strong <= 1.0
    assert sched.grade(sched.OUTCOME_HELD, engagement=strong) == sched._RATING_EASY


def test_grade_held_in_the_middle_band_is_good():
    mid = (sched._HARD_MAX_ENGAGEMENT + sched._EASY_MIN_ENGAGEMENT) / 2
    assert sched.grade(sched.OUTCOME_HELD, engagement=mid) == sched._RATING_GOOD


def test_grade_unknown_outcome_raises():
    with pytest.raises(sched.ScheduleError):
        sched.grade("neither-held-nor-regressed")


def test_grade_is_independent_of_fsrs_availability():
    """grade() never calls `_fsrs()` — it must return the same thing whether
    or not the `fsrs` package can be imported."""
    with _fsrs_blocked():
        assert sched.fsrs_available() is False
        assert sched.grade(sched.OUTCOME_HELD) == sched._RATING_GOOD
        assert sched.grade(sched.OUTCOME_REGRESSED) == sched._RATING_AGAIN


# ── fsrs_available() ─────────────────────────────────────────────────────────

def test_fsrs_available_is_a_bool():
    assert isinstance(sched.fsrs_available(), bool)


def test_fsrs_available_is_false_when_blocked():
    with _fsrs_blocked():
        assert sched.fsrs_available() is False
    # back to whatever this environment genuinely has, in this same process —
    # `True` only where fsrs is installed. Asserting `True` outright made this
    # test a hidden `fsrs` requirement on a soft dependency (it failed on every
    # box without fsrs while the README promised the suite stays green).
    assert sched.fsrs_available() is _HAS_FSRS


# ── record_review(): the fixed-interval fallback (deterministic, no fsrs) ───

def test_fallback_first_held_review_uses_base_interval():
    with _fsrs_blocked():
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        card = sched.record_review(None, sched.OUTCOME_HELD, now)
    assert card["kind"] == "fixed"
    assert card["interval_days"] == sched.FIXED_BASE_INTERVAL_DAYS
    assert card["due"] == (now + timedelta(days=sched.FIXED_BASE_INTERVAL_DAYS)).isoformat()


def test_fallback_second_held_review_doubles_the_interval():
    with _fsrs_blocked():
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        first = sched.record_review(None, sched.OUTCOME_HELD, now)
        second = sched.record_review(first, sched.OUTCOME_HELD, now + timedelta(days=1))
    assert second["interval_days"] == sched.FIXED_BASE_INTERVAL_DAYS * 2


def test_fallback_interval_is_capped_at_the_max():
    with _fsrs_blocked():
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        card = {"kind": "fixed", "interval_days": sched.FIXED_MAX_INTERVAL_DAYS, "due": now.isoformat()}
        grown = sched.record_review(card, sched.OUTCOME_HELD, now)
    assert grown["interval_days"] == sched.FIXED_MAX_INTERVAL_DAYS


def test_fallback_regression_resets_to_base_interval_regardless_of_prior():
    with _fsrs_blocked():
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        grown = {"kind": "fixed", "interval_days": 30.0, "due": now.isoformat()}
        card = sched.record_review(grown, sched.OUTCOME_REGRESSED, now)
    assert card["interval_days"] == sched.FIXED_BASE_INTERVAL_DAYS


def test_fallback_a_prior_fsrs_card_is_not_trusted_as_a_fixed_one():
    """`record_review` starts a fresh fixed card rather than reading
    `interval_days` off a blob the OTHER scheduler kind wrote."""
    with _fsrs_blocked():
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fsrs_shaped_prior = {"kind": "fsrs", "card": {}, "due": now.isoformat()}
        card = sched.record_review(fsrs_shaped_prior, sched.OUTCOME_HELD, now)
    assert card["kind"] == "fixed"
    assert card["interval_days"] == sched.FIXED_BASE_INTERVAL_DAYS


def test_fallback_raises_on_bad_outcome_before_producing_a_card():
    with _fsrs_blocked():
        with pytest.raises(sched.ScheduleError):
            sched.record_review(None, "sideways", datetime.now(timezone.utc))


# ── record_review(): real fsrs ───────────────────────────────────────────────

@_needs_fsrs
def test_real_fsrs_first_held_review_produces_an_fsrs_card():
    now = datetime.now(timezone.utc)
    card = sched.record_review(None, sched.OUTCOME_HELD, now)
    assert card["kind"] == "fsrs"
    assert "due" in card
    assert datetime.fromisoformat(card["due"]) > now


@_needs_fsrs
def test_real_fsrs_round_trips_a_prior_card_across_two_reviews():
    now = datetime.now(timezone.utc)
    first = sched.record_review(None, sched.OUTCOME_HELD, now)
    second = sched.record_review(first, sched.OUTCOME_HELD, now + timedelta(minutes=20))
    assert second["kind"] == "fsrs"
    assert datetime.fromisoformat(second["due"]) > datetime.fromisoformat(first["due"])


@_needs_fsrs
def test_real_fsrs_a_regression_is_a_lapse():
    now = datetime.now(timezone.utc)
    held = sched.record_review(None, sched.OUTCOME_HELD, now)
    review_time = now + timedelta(minutes=20)
    lapsed = sched.record_review(held, sched.OUTCOME_REGRESSED, review_time)
    assert lapsed["kind"] == "fsrs"
    # a fresh schedule was computed off the regression, relative to when it
    # was reviewed — not a copy of the held card's own due
    assert datetime.fromisoformat(lapsed["due"]) > review_time
    assert lapsed["due"] != held["due"]


@_needs_fsrs
def test_real_fsrs_an_unparseable_prior_card_starts_fresh_not_crashing():
    now = datetime.now(timezone.utc)
    garbage_prior = {"kind": "fsrs", "card": {"not": "a real card"}, "due": now.isoformat()}
    card = sched.record_review(garbage_prior, sched.OUTCOME_HELD, now)
    assert card["kind"] == "fsrs"


# ── is_due() / due_at() ──────────────────────────────────────────────────────

def test_is_due_true_when_now_is_past_due():
    card = {"due": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()}
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert sched.is_due(card, now) is True


def test_is_due_true_exactly_at_due():
    due = datetime(2026, 1, 1, tzinfo=timezone.utc)
    card = {"due": due.isoformat()}
    assert sched.is_due(card, due) is True


def test_is_due_false_before_due():
    card = {"due": datetime(2026, 1, 2, tzinfo=timezone.utc).isoformat()}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert sched.is_due(card, now) is False


def test_is_due_returns_a_bool_not_a_datetime():
    card = {"due": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()}
    result = sched.is_due(card, datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert isinstance(result, bool)


def test_due_at_raises_on_missing_due_field():
    with pytest.raises(sched.ScheduleError):
        sched.due_at({})


def test_due_at_raises_on_unparseable_due_field():
    with pytest.raises(sched.ScheduleError):
        sched.due_at({"due": "not-a-timestamp"})


# ── save_card / load_card sidecar round trip (fixture for the CLI tests) ────

def test_save_and_load_card_round_trips(tmp_path):
    card = {"kind": "fixed", "interval_days": 1.0, "due": "2026-01-02T00:00:00+00:00"}
    sched.save_card(BUILDER_A, PAIR_1, card, root=tmp_path)
    assert sched.load_card(BUILDER_A, PAIR_1, root=tmp_path) == card


def test_load_card_is_none_when_never_reviewed(tmp_path):
    assert sched.load_card(BUILDER_A, PAIR_1, root=tmp_path) is None


def test_save_card_rejects_empty_card_id(tmp_path):
    with pytest.raises(sched.ScheduleError):
        sched.save_card(BUILDER_A, "", {"due": "x"}, root=tmp_path)


def test_schedule_path_rejects_a_bad_builder_id(tmp_path):
    with pytest.raises(sched.ScheduleError):
        sched.schedule_path("../escape", root=tmp_path)


# ── CLI: argument parsing ────────────────────────────────────────────────────

def test_build_parser_parses_review_subcommand():
    args = sched.build_parser().parse_args(
        ["review", BUILDER_A, PAIR_1, "--outcome", "held"]
    )
    assert args.command == "review"
    assert args.builder_id == BUILDER_A
    assert args.pair_id == PAIR_1
    assert args.outcome == sched.OUTCOME_HELD
    assert args.root == str(sched.DEFAULT_CHECKPOINT_ROOT)
    assert args.func is sched._cmd_review


def test_build_parser_parses_due_subcommand():
    args = sched.build_parser().parse_args(["due", BUILDER_A, PAIR_1])
    assert args.command == "due"
    assert args.builder_id == BUILDER_A
    assert args.pair_id == PAIR_1
    assert args.func is sched._cmd_due


def test_build_parser_review_requires_a_valid_outcome_choice():
    with pytest.raises(SystemExit):
        sched.build_parser().parse_args(
            ["review", BUILDER_A, PAIR_1, "--outcome", "sideways"]
        )


def test_build_parser_requires_a_subcommand():
    with pytest.raises(SystemExit):
        sched.build_parser().parse_args([])


def test_build_parser_root_is_overridable():
    # --root lives on the TOP-LEVEL parser (added before the subparsers), so
    # it must precede the subcommand, not follow it.
    args = sched.build_parser().parse_args(
        ["--root", "/tmp/somewhere", "review", BUILDER_A, PAIR_1, "--outcome", "held"]
    )
    assert args.root == "/tmp/somewhere"


# ── CLI: end-to-end (fixed fallback, so timing is deterministic) ────────────

def test_cli_review_then_due_reports_not_yet_due(tmp_path, capsys):
    with _fsrs_blocked():
        rc = sched.main(["--root", str(tmp_path), "review", BUILDER_A, PAIR_1, "--outcome", "held"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["kind"] == "fixed"
        assert out["fsrs"] is False

        rc_due = sched.main(["--root", str(tmp_path), "due", BUILDER_A, PAIR_1])
        # a fresh 1-day-out fixed interval is not due yet — _cmd_due's own
        # "0 if due else 2" convention
        assert rc_due == 2
        due_out = json.loads(capsys.readouterr().out)
        assert due_out["is_due"] is False


def test_cli_due_with_no_prior_review_refuses_on_stderr(tmp_path, capsys):
    rc = sched.main(["--root", str(tmp_path), "due", BUILDER_A, "never-reviewed"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "never reviewed" in captured.err


def test_cli_review_persists_the_card_for_a_later_due_check(tmp_path):
    with _fsrs_blocked():
        sched.main(["--root", str(tmp_path), "review", BUILDER_A, PAIR_1, "--outcome", "held"])
    card = sched.load_card(BUILDER_A, PAIR_1, root=tmp_path)
    assert card is not None
    assert card["kind"] == "fixed"
