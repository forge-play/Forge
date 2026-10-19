"""`run_checkpoint(defer_seal=True)` — for a host that seals once, at the end of
its session (willow-bot's one script): an answer given mid-session is proposed
as a Nestor draft, never sealed, and never attested.

Each test attempts the forbidden act (a mid-session seal) and asserts it did
not happen; the last pins that the default still seals.
"""

from __future__ import annotations

import json

import pytest

from forge import checkpoint, checkpoint_memory, entry
from forge.checkpoint import ChoiceResult, Decision, Option

pytestmark = pytest.mark.filterwarnings("ignore:NESTOR_SEAL_KEY not set.*:RuntimeWarning")
_needs_nestor = pytest.mark.skipif(
    not checkpoint_memory.nestor_available(), reason="nestor not installed"
)

BUILDER = "c" * 32
DECISION = Decision(
    decision_type="schema-normalization-tradeoff",
    surface="Should the orders table be normalized or denormalized?",
    options=(Option("normalized", "cleaner writes"), Option("denormalized", "fast reporting")),
)
ORIGINAL = "How should the login form authenticate?"
REWORDED = "What auth should the sign-in form use?"
AUTH = Decision(
    decision_type="auth-flow-for-user-facing-form",
    surface=REWORDED,
    options=(Option("session cookie + CSRF", "server state"), Option("JWT", "stateless")),
)


class Responder:
    def __init__(self, choose=None, confirm=True):
        self._choose, self._confirm = choose, confirm

    def confirm(self, prompt: str) -> bool:
        return self._confirm

    def choose(self, decision: Decision) -> ChoiceResult:
        assert self._choose is not None, "asked to choose with nothing scripted"
        return ChoiceResult(chosen_label=self._choose, rationale="writes dominate here")


def _rows(decision_type, root):
    with checkpoint_memory.open_checkpoint_memory(BUILDER, decision_type, root=root) as cm:
        return list(cm._store.memory_candidates(cm.domain, cm.domain))


def _no_seal(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("sealed mid-session")

    monkeypatch.setattr(checkpoint_memory.CheckpointMemory, "seal", refuse)


@_needs_nestor
def test_a_fresh_answer_is_a_draft_not_a_seal(tmp_path, monkeypatch):
    root = tmp_path / "cp"
    _no_seal(monkeypatch)
    out = checkpoint.run_checkpoint(
        DECISION,
        builder_id=BUILDER,
        responder=Responder(choose="normalized"),
        root=root,
        defer_seal=True,
    )
    assert (out.band, out.sealed, out.drafted, out.attestation_id) == ("socratic", False, True, "")
    (row,) = _rows(DECISION.decision_type, root)
    assert (row["id"], row["status"]) == (out.pair_id, "draft")
    assert row["target_text"] == "normalized: writes dominate here"


@_needs_nestor
def test_a_recognized_answer_confirmed_is_a_draft_not_a_seal(tmp_path, monkeypatch):
    root = tmp_path / "cp"
    with checkpoint_memory.open_checkpoint_memory(BUILDER, AUTH.decision_type, root=root) as cm:
        cm.seal(ORIGINAL, "session cookie + CSRF")
    _no_seal(monkeypatch)
    out = checkpoint.run_checkpoint(
        AUTH, builder_id=BUILDER, responder=Responder(confirm=True), root=root, defer_seal=True
    )
    assert (out.band, out.sealed, out.drafted, out.attestation_id) == ("recognize", False, True, "")
    status = {r["source_text"]: r["status"] for r in _rows(AUTH.decision_type, root)}
    assert status == {ORIGINAL: "sealed", REWORDED: "draft"}


@_needs_nestor
def test_the_entry_passes_it_through_and_the_ledger_holds_no_seal(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path / "forge-home"))
    root = tmp_path / "cp"
    e = entry.open_bite(
        "I got sum kol sites for app to spin",
        project_id="demo-project",
        builder_id=BUILDER,
        responder=Responder(choose="web"),
        root=root,
        defer_seal=True,
    )
    assert e.decision_outcome.drafted is True and e.decision_outcome.sealed is False
    kinds = [
        json.loads(x)["kind"] for x in (root / "ledger.jsonl").read_text().splitlines() if x.strip()
    ]
    assert "entity_seal" not in kinds


@_needs_nestor
def test_the_default_still_seals_and_attests(tmp_path):
    root = tmp_path / "cp"
    out = checkpoint.run_checkpoint(
        DECISION, builder_id=BUILDER, responder=Responder(choose="normalized"), root=root
    )
    assert (out.sealed, out.drafted) == (True, False) and out.attestation_id
    (row,) = _rows(DECISION.decision_type, root)
    assert row["status"] == "sealed"
