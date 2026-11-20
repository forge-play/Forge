"""A simulated maker who sometimes defers to what they can see, and what the
ledger then says about the proposer, asked in view and asked blind.

The claim under forge 0.11's blind forks (and Willow's forge add-on's, #382):
a pick made with the recommendation in view measures how far the maker
follows it as much as how often the proposer is right; a blind pick measures
only the second. Argued until now; measured here, through the real
build_loop, checkpoint and calibration ledger, with nothing mocked but the
maker (Die-Namic's tests/person.py idea: a person at the keyboard who reads
what is asked and answers it).

The world, seeded so it is the same every run:

  * each fork has two options and one of them is right, which the maker knows;
  * the proposer recommends the right one with probability ACCURACY and
    states exactly that as its confidence: it is perfectly calibrated;
  * shown a recommendation, the maker takes it with probability DEFER, and
    otherwise takes the right one; asked blind, there is nothing to take, so
    they take the right one.

So in view the proposer's pick is taken DEFER + (1 - DEFER) * ACCURACY of the
time, and blind ACCURACY of the time. A ledger that scores in-view picks
calls a calibrated proposer underconfident by the maker's deference; one that
scores blind picks sees it as it is.
"""

from __future__ import annotations

import random

import pytest

from forge import build_loop as bl
from forge import calibration_ledger, checkpoint_memory
from forge import plan_shape as ps
from forge.checkpoint import ChoiceResult

pytestmark = pytest.mark.skipif(
    not checkpoint_memory.nestor_available(), reason="nestor not installed"
)

BUILDER = "d" * 32
SEED = 20261120
N = 300  # forks per arm: at 80 the seeded gap came out 0.10 against 0.20
ACCURACY = 0.6  # how often the proposer's pick is the right one, and what it says
DEFER = 0.5  # how often a maker who can see the pick takes it
IN_VIEW = DEFER + (1 - DEFER) * ACCURACY  # 0.8: what an in-view ledger sees
SLACK = 0.08  # about 2.8 standard errors of one hit rate at N = 300, 2.2 of the gap


class SimulatedMaker:
    """Knows the right option for each fork; follows a recommendation it can
    see DEFER of the time. Never defers outright (a deferral is voided since
    #52, and would only thin the sample)."""

    def __init__(self, right: dict[str, str], rng: random.Random):
        self.right, self.rng = right, rng
        self.saw_a_recommendation = 0

    def confirm(self, prompt):  # every fork is fresh: memory is never consulted twice
        return True

    def choose(self, d):
        if d.recommended is not None:
            self.saw_a_recommendation += 1
            if self.rng.random() < DEFER:
                return ChoiceResult(
                    chosen_label=d.recommended, rationale="it said so, and I went with it"
                )
        return ChoiceResult(
            chosen_label=self.right[d.decision_type], rationale="I know which one this is"
        )


def _world(arm: str, blind: bool, rng: random.Random) -> tuple[ps.PlanDoc, dict[str, str]]:
    entries, right = [], {}
    for i in range(N):
        dt = f"{arm}-{i:03d}"
        good, bad = rng.sample(["left", "right"], 2)
        right[dt] = good
        pick = good if rng.random() < ACCURACY else bad
        entries.append(
            {
                "kind": "fork",
                "decision_type": dt,
                "surface": f"which way for {dt}?",
                "options": [{"label": "left"}, {"label": "right"}],
                "recommended": pick,
                "confidence": ACCURACY,
                "blind": blind,
                "resolves": {},
            }
        )
    return ps.validate({"app_name": "study", "entries": entries}), right


@pytest.fixture(scope="module")
def ledger(tmp_path_factory):
    root = tmp_path_factory.mktemp("cp")
    rng = random.Random(SEED)
    makers = {}
    for arm, blind in (("view", False), ("blind", True)):
        plan, right = _world(arm, blind, rng)
        makers[arm] = SimulatedMaker(right, rng)
        bl.resolve(plan, builder_id=BUILDER, responder=makers[arm], root=root)
    card = calibration_ledger.scorecard(BUILDER, group_by="blind", root=root)
    return card, makers


def test_the_maker_saw_the_recommendation_only_in_view(ledger):
    _, makers = ledger
    assert makers["view"].saw_a_recommendation == N
    assert makers["blind"].saw_a_recommendation == 0


def test_every_pick_was_scored_and_none_voided_or_from_memory(ledger):
    card, _ = ledger
    assert card["resolved"] == 2 * N and card["void"] == 0 and card["from_memory"] == 0
    assert card["groups"]["True"]["n"] == N and card["groups"]["False"]["n"] == N


def test_blind_picks_recover_the_proposers_true_accuracy(ledger):
    card, _ = ledger
    s = card["groups"]["True"]["summary"]
    assert s["hit_rate"] == pytest.approx(ACCURACY, abs=SLACK)
    assert abs(s["overconfidence"]) <= SLACK, "a calibrated proposer reads as calibrated"


def test_in_view_picks_measure_the_makers_deference_too(ledger):
    card, _ = ledger
    s = card["groups"]["False"]["summary"]
    assert s["hit_rate"] == pytest.approx(IN_VIEW, abs=SLACK)
    assert s["overconfidence"] <= -(IN_VIEW - ACCURACY) + SLACK, (
        "the same calibrated proposer reads as underconfident by the maker's deference"
    )


def test_the_gap_between_them_is_the_deference(ledger):
    card, _ = ledger
    blind = card["groups"]["True"]["summary"]["hit_rate"]
    view = card["groups"]["False"]["summary"]["hit_rate"]
    assert view - blind == pytest.approx(IN_VIEW - ACCURACY, abs=SLACK)
    assert view > blind, "in view, the recommendation lifts its own hit rate"


def expected_brier(confidence: float, hit_rate: float) -> float:
    """A constant confidence's mean Brier score against a hit rate."""
    return hit_rate * (1 - confidence) ** 2 + (1 - hit_rate) * confidence**2


def test_in_view_the_brier_score_rewards_the_proposer_for_being_followed(ledger):
    """The same proposer, scored by Brier: 0.20 expected in view, 0.24 blind.
    Deference does not only hide how often it is right; it scores it better
    for being followed, which is the confident wrong answer the Forge is for
    refusing, reached from the other side."""
    card, _ = ledger
    view = card["groups"]["False"]["summary"]["brier"]
    blind = card["groups"]["True"]["summary"]["brier"]
    assert view == pytest.approx(expected_brier(ACCURACY, IN_VIEW), abs=0.03)
    assert blind == pytest.approx(expected_brier(ACCURACY, ACCURACY), abs=0.03)
    assert view < blind
