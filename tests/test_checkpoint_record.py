"""forge/checkpoint.py with the person's record wired in (the-join.md,
thread 3): the record is asked first, a standing seal is a confirm and
nothing else, and every answer the maker gives or confirms is proposed onto
the record to wait on their seal. The record here is a stand-in; the real
one is `forge.willow_record.WillowRecord`, tested in its own file."""

from __future__ import annotations

import pytest

from forge import checkpoint, willow_record
from tests.test_checkpoint import (
    AUTH_OPTIONS,
    BUILDER_A,
    DECISION_TYPE,
    ORIGINAL_SURFACE,
    REWORDED_SURFACE,
    ChoiceResult,
    Decision,
    ScriptedResponder,
    _needs_nestor,
    _seal_original_auth_decision,
)

pytestmark = pytest.mark.filterwarnings("ignore:NESTOR_SEAL_KEY not set.*:RuntimeWarning")


class FakeRecord:
    name = "fake record"

    def __init__(self, sealed=None, refuse=None, refuse_propose=None):
        self.sealed, self.refuse, self.refuse_propose = sealed or {}, refuse, refuse_propose
        self.asked: list[str] = []
        self.proposed: list[dict] = []

    def stack_for(self, sentence):
        return None

    def has_sealed(self, dt):
        if self.refuse:
            raise willow_record.WillowRecordError(self.refuse)
        self.asked.append(dt)
        chosen = self.sealed.get(dt)
        return willow_record.Sealed(dt, chosen, dt, "proposal:" + "cd" * 32) if chosen else None

    def propose(self, dt, chosen, *, over, why, surface="", word=None):
        if self.refuse_propose:
            raise willow_record.WillowRecordError(self.refuse_propose)
        self.proposed.append(
            {"dt": dt, "chosen": chosen, "over": over, "why": why, "surface": surface}
        )
        return "proposal:" + "ef" * 32


def decision() -> Decision:
    return Decision(decision_type=DECISION_TYPE, surface=ORIGINAL_SURFACE, options=AUTH_OPTIONS)


def test_the_record_is_a_record_lookup_too():
    assert isinstance(FakeRecord(), willow_record.RecordLookup)


@_needs_nestor
def test_a_standing_seal_on_the_record_is_a_confirm_and_touches_no_memory(tmp_path):
    rec = FakeRecord(sealed={DECISION_TYPE: "JWT bearer token"})
    responder = ScriptedResponder(confirm_answers=[True])
    out = checkpoint.run_checkpoint(
        decision(), builder_id=BUILDER_A, responder=responder, root=tmp_path, record=rec
    )
    assert out.band == "auto" and out.chosen == "JWT bearer token" and out.sealed is True
    assert out.matched_band == "auto" and out.match_confidence == 1.0
    assert out.record == "sealed 'JWT bearer token' (proposal:" + "cd" * 32 + "), confirmed"
    assert out.record_subject == "proposal:" + "cd" * 32
    assert out.rationale == "" and out.engagement is None and out.pair_id == ""
    assert "You sealed a" in responder.confirm_prompts[0] and not responder.choose_calls
    assert rec.proposed == [], "nothing to propose: the record already holds it"
    assert not any(tmp_path.iterdir()), "the engine's memory was never opened"


@_needs_nestor
def test_not_this_falls_through_to_memory_and_the_new_answer_is_proposed(tmp_path):
    rec = FakeRecord(sealed={DECISION_TYPE: "JWT bearer token"})
    responder = ScriptedResponder(
        confirm_answers=[False],
        choose_answers=[
            ChoiceResult(chosen_label="session cookie + CSRF", rationale="server state")
        ],
    )
    out = checkpoint.run_checkpoint(
        decision(), builder_id=BUILDER_A, responder=responder, root=tmp_path, record=rec
    )
    assert out.band == "socratic" and out.chosen == "session cookie + CSRF" and out.sealed is True
    assert out.matched_band is None, "the engine's own memory proposed nothing"
    assert (
        out.record
        == "sealed 'JWT bearer token', maker said not this; proposed proposal:" + "ef" * 32
    )
    assert out.record_subject == "proposal:" + "ef" * 32
    assert rec.proposed == [
        {
            "dt": DECISION_TYPE,
            "chosen": "session cookie + CSRF",
            "over": ["JWT bearer token"],
            "why": "server state",
            "surface": ORIGINAL_SURFACE,
        }
    ]


@_needs_nestor
def test_a_seal_for_an_option_not_on_offer_is_said_and_the_maker_is_asked(tmp_path):
    rec = FakeRecord(sealed={DECISION_TYPE: "magic link"})
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="JWT bearer token", rationale="stateless")]
    )
    out = checkpoint.run_checkpoint(
        decision(), builder_id=BUILDER_A, responder=responder, root=tmp_path, record=rec
    )
    assert out.band == "socratic" and not responder.confirm_prompts
    assert out.record.startswith("sealed 'magic link', not an option here; proposed ")
    assert rec.proposed[0]["chosen"] == "JWT bearer token"


@_needs_nestor
def test_nothing_sealed_is_said_and_a_deferral_is_proposed_with_its_reason(tmp_path):
    rec = FakeRecord()
    responder = ScriptedResponder(choose_answers=[ChoiceResult(deferred=True)])
    out = checkpoint.run_checkpoint(
        decision(), builder_id=BUILDER_A, responder=responder, root=tmp_path, record=rec
    )
    assert out.deferred and out.chosen == "session cookie + CSRF"
    assert out.record.startswith("nothing sealed; proposed ")
    assert rec.proposed[0]["why"].startswith("deferred: the maker reviewed the tradeoff")
    assert rec.asked == [DECISION_TYPE]


@_needs_nestor
def test_the_engines_own_auto_confirm_is_proposed_to_the_record_too(tmp_path):
    _seal_original_auth_decision(tmp_path)
    rec = FakeRecord()
    responder = ScriptedResponder(confirm_answers=[True])
    out = checkpoint.run_checkpoint(
        decision(), builder_id=BUILDER_A, responder=responder, root=tmp_path, record=rec
    )
    assert out.band == "auto" and out.matched_band == "auto" and out.pair_id
    assert out.record.startswith("nothing sealed; proposed ") and out.record_subject
    assert rec.proposed[0]["chosen"] == out.chosen and rec.proposed[0]["over"] == [
        "JWT bearer token"
    ]


@_needs_nestor
def test_a_recognized_confirm_is_proposed_under_the_rewording(tmp_path):
    _seal_original_auth_decision(tmp_path)
    rec = FakeRecord()
    responder = ScriptedResponder(confirm_answers=[True])
    out = checkpoint.run_checkpoint(
        Decision(decision_type=DECISION_TYPE, surface=REWORDED_SURFACE, options=AUTH_OPTIONS),
        builder_id=BUILDER_A,
        responder=responder,
        root=tmp_path,
        record=rec,
        recognize_threshold=0.5,
    )
    assert out.band == "recognize"
    assert rec.proposed[0]["surface"] == REWORDED_SURFACE and rec.proposed[0]["why"] == ""


@_needs_nestor
def test_defer_seal_still_proposes_to_the_record(tmp_path):
    rec = FakeRecord()
    responder = ScriptedResponder(
        choose_answers=[ChoiceResult(chosen_label="JWT bearer token", rationale="stateless")]
    )
    out = checkpoint.run_checkpoint(
        decision(),
        builder_id=BUILDER_A,
        responder=responder,
        root=tmp_path,
        record=rec,
        defer_seal=True,
    )
    assert out.drafted and not out.sealed and out.record_subject == "proposal:" + "ef" * 32


def test_the_record_can_answer_and_take_proposals_without_nestor(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint.checkpoint_memory, "nestor_available", lambda: False)
    rec = FakeRecord(sealed={DECISION_TYPE: "JWT bearer token"})
    out = checkpoint.run_checkpoint(
        decision(),
        builder_id=BUILDER_A,
        responder=ScriptedResponder(confirm_answers=[True]),
        root=tmp_path,
        record=rec,
    )
    assert out.band == "auto" and out.sealed is True and out.memory_available is False
    fresh = checkpoint.run_checkpoint(
        decision(),
        builder_id=BUILDER_A,
        responder=ScriptedResponder(
            confirm_answers=[False],
            choose_answers=[ChoiceResult(chosen_label="session cookie + CSRF", rationale="x")],
        ),
        root=tmp_path,
        record=rec,
    )
    assert fresh.band == "socratic" and fresh.memory_available is False and not fresh.sealed
    assert fresh.record_subject and rec.proposed[0]["chosen"] == "session cookie + CSRF"


def test_no_record_is_said_as_not_wired(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint.checkpoint_memory, "nestor_available", lambda: False)
    out = checkpoint.run_checkpoint(
        decision(),
        builder_id=BUILDER_A,
        responder=ScriptedResponder(choose_answers=[ChoiceResult(chosen_label="JWT bearer token")]),
        root=tmp_path,
    )
    assert out.record == "not wired" and out.record_subject == ""


def test_a_refusing_record_refuses_the_checkpoint(tmp_path):
    with pytest.raises(checkpoint.CheckpointError, match="the record refused: the chain is broken"):
        checkpoint.run_checkpoint(
            decision(),
            builder_id=BUILDER_A,
            responder=ScriptedResponder(),
            root=tmp_path,
            record=FakeRecord(refuse="the chain is broken"),
        )


def test_a_door_that_turns_the_proposal_back_refuses_after_the_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(checkpoint.checkpoint_memory, "nestor_available", lambda: False)
    with pytest.raises(checkpoint.CheckpointError, match="refused the proposal: a claim says why"):
        checkpoint.run_checkpoint(
            decision(),
            builder_id=BUILDER_A,
            responder=ScriptedResponder(
                choose_answers=[ChoiceResult(chosen_label="JWT bearer token")]
            ),
            root=tmp_path,
            record=FakeRecord(refuse_propose="a claim says why"),
        )
