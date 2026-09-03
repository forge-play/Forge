"""forge/deposit.py — the PR-time deposit, propose-only, in its own domain.

The store-backed tests need Nestor and skip without it, like tests/test_entry.py.
The table, the regex and the inbox reader run on the base install.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from forge import checkpoint_memory, deposit
from forge.deposit import Run

_HAS_NESTOR = checkpoint_memory.nestor_available()
_needs_nestor = pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")

REPO = "forge-play/Forge"
SHA = "cc9aab19ba2502e14e331e20e699f634fb4cb1a2"


# ── the table ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,conclusion,state", [
    ("completed", "success", "pass"),
    ("completed", "failure", "fail"),
    ("completed", "startup_failure", "fail"),
    ("completed", "cancelled", "could_not_run"),
    ("completed", "timed_out", "could_not_run"),
    ("completed", "skipped", "could_not_run"),
    ("completed", "neutral", "could_not_run"),
    ("completed", "stale", "could_not_run"),
    ("completed", "", "could_not_run"),
    ("completed", None, "could_not_run"),
    ("completed", "something_new", "could_not_run"),
    ("in_progress", "", "pending"),
    ("queued", None, "pending"),
    (None, "success", "pending"),
])
def test_the_state_table(status, conclusion, state):
    assert deposit.outcome_state(status, conclusion) == state
    assert state in deposit.STATES


def test_four_states_and_could_not_run_is_never_clean():
    assert deposit.STATES == ("pass", "fail", "could_not_run", "pending")
    assert deposit.outcome_state("completed", "cancelled") != "pass"


# ── the trailer ────────────────────────────────────────────────────────────

def test_decision_trailer_is_read_by_rule():
    body = ("feat: the thing\n\nDecision: 2c2b2c3e\nsome prose\n"
            "decision: ABCDEF0123\nDecision: 2c2b2c3e\nDecision: short\nNot Decision: 12345678\n")
    assert deposit.extract_decision_refs(body) == ["2c2b2c3e", "abcdef0123"]
    assert deposit.extract_decision_refs("") == []
    assert deposit.extract_decision_refs("Decision:\n") == []


# ── the inbox (shape C) ────────────────────────────────────────────────────

def _item(tmp: Path, fname: str, **fields) -> None:
    (tmp / f"{fname}.json").write_text(json.dumps(fields), encoding="utf-8")


def test_inbox_reader_keys_on_head_sha_and_reports_the_rest(tmp_path):
    _item(tmp_path, "a", kind="check_run", head_sha=SHA, name="Tests", status="completed",
          conclusion="success", check_id=11, html_url="u1", repo=REPO)
    _item(tmp_path, "b", kind="check_run", head_sha=SHA, name="CodeQL", conclusion="cancelled", check_id=12)
    _item(tmp_path, "c", kind="check_run", name="Tests", conclusion="failure")  # the bridge today: no sha
    _item(tmp_path, "d", kind="pull_request", number=4)
    (tmp_path / "e.json").write_text("{not json", encoding="utf-8")
    r = deposit.read_inbox(tmp_path)
    assert set(r.keyed) == {SHA}
    assert sorted(x.name for x in r.keyed[SHA]) == ["CodeQL", "Tests"]
    assert [x.state for x in sorted(r.keyed[SHA], key=lambda x: x.name)] == ["could_not_run", "pass"]
    assert r.repo[SHA] == REPO
    assert [u["why"] for u in r.unkeyed] == ["no head_sha", "unreadable"]
    assert r.skipped == 1


def test_inbox_reader_on_a_missing_directory_is_empty_not_an_error(tmp_path):
    r = deposit.read_inbox(tmp_path / "nope")
    assert r.keyed == {} and r.unkeyed == [] and r.skipped == 0


# ── the store ──────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    if not _HAS_NESTOR:
        pytest.skip("nestor not installed")
    from nestor import cascade
    from nestor.sqlite_store import SqliteStore
    cascade.set_ledger_path(tmp_path / "ledger.jsonl")
    s = SqliteStore(str(tmp_path / "nestor.db"))
    s.memory_init()  # a project store is created by the entry's first ask; mirror that
    return s


RUNS = [Run("Tests", "completed", "success", "1", "u1"),
        Run("CodeQL", "completed", "success", "2", "u2"),
        Run("Release Please", "completed", "cancelled", "3", "u3")]


@_needs_nestor
def test_deposit_lands_as_a_draft_in_the_ci_domain(store):
    d = deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS,
                           pr={"number": 4, "title": "vendoring goes home", "merged_at": "2026-09-03"},
                           actor_type="Bot", via="webhook_inbox",
                           now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    row = d.row
    assert row["status"] == "draft"
    assert row["source_lang"] == "ci" and row["target_lang"] == "ci"
    assert row["source_text"] == f"How did CI go for {REPO}@{SHA}?"
    assert row["target_text"] == ("pass: CodeQL success (run 2); could_not_run: Release Please cancelled (run 3); "
                                  "pass: Tests success (run 1)")
    assert row["reason"].startswith('PR #4 "vendoring goes home" merged 2026-09-03')
    assert row["origin"] == f"{REPO}@{SHA} actor=Bot via=webhook_inbox at=2026-09-03T00:00:00+00:00"
    assert d.superseded is None
    assert d.states == {"pass": 2, "could_not_run": 1}
    assert "Bot" in row["origin"] and "[bot]" not in row["origin"], "a type, never a login"


@_needs_nestor
def test_the_decision_verbs_are_blind_to_ci_rows(store):
    from nestor.decision import DecisionMemory
    deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="User", via="gh")
    DecisionMemory(store)  # the decision domain, opened the way the entry opens it
    rows = store.memory_list(limit=1000)
    assert [r["source_lang"] for r in rows] == ["ci"], "one row, and it is not a decision"


@_needs_nestor
def test_a_rerun_supersedes_and_the_question_is_stable(store):
    first = deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="Bot", via="webhook_inbox")
    rerun = [Run("Tests", "completed", "failure", "9", "u9")]
    second = deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=rerun, actor_type="Bot", via="webhook_inbox")
    assert second.row["source_text"] == first.row["source_text"]
    assert second.row["id"] != first.row["id"]
    assert second.superseded == first.row["id"] and second.row["status"] == "draft"
    old = store.memory_get(first.row["id"])
    assert old["superseded_by"] == second.row["id"], "the old row went into history, not away"
    assert old["target_text"] == first.row["target_text"]
    assert [r["id"] for r in store.memory_lineage(second.row["id"])] == [first.row["id"]]
    assert store.memory_edges_from(second.row["id"]) == [], "a revision is lineage, not an edge"
    live = [r for r in store.memory_list(limit=100) if not r["superseded_by"]]
    assert [r["id"] for r in live] == [second.row["id"]]
    assert deposit.newest_deposit(store, REPO)["id"] == second.row["id"]
    # the same outcome again is one fact, not a third row
    third = deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=rerun, actor_type="Bot", via="gh")
    assert third.unchanged and third.row["id"] == second.row["id"]
    assert len(store.memory_list(limit=100)) == 2


@_needs_nestor
def test_a_pending_run_refuses_the_whole_deposit(store):
    with pytest.raises(deposit.DepositError, match="pending"):
        deposit.deposit_ci(store, repo=REPO, sha=SHA,
                           runs=RUNS + [Run("Nightly", "in_progress", "")],
                           actor_type="Bot", via="webhook_inbox")
    assert store.memory_list(limit=10) == []


@_needs_nestor
def test_empty_runs_and_bad_actor_refuse(store):
    with pytest.raises(deposit.DepositError, match="nothing was read"):
        deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=[], actor_type="Bot", via="gh")
    with pytest.raises(deposit.DepositError, match="actor_type"):
        deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="willows-bot[bot]", via="gh")


@_needs_nestor
def test_links_are_refines_edges_and_unmatched_or_ambiguous_refs_are_reported(store):
    from nestor.decision import DecisionMemory
    dm = DecisionMemory(store)
    a = dm.propose("Which domain holds a CI outcome?", "ci", origin="t")
    b = dm.propose("How is a conclusion mapped?", "by table", origin="t")
    d = deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="Bot", via="webhook_inbox")
    links = deposit.link_decisions(store, d.row["id"], [a["id"][:8].upper(), "ffffffff"])
    assert [l["decision"] for l in links.linked] == [a["id"]]
    assert links.unmatched == ["ffffffff"] and links.ambiguous == []
    edges = store.memory_edges_from(d.row["id"])
    assert [(e["kind"], e["dst_id"], e["edge_sig"]) for e in edges] == [("refines", a["id"], "")]
    assert b["id"] not in {e["dst_id"] for e in edges}


@_needs_nestor
def test_an_ambiguous_prefix_links_nothing(store, monkeypatch):
    """Two decisions sharing a prefix: the ref names both, so neither is linked."""
    d = deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="Bot", via="webhook_inbox")
    twins = [{"id": "abcdef01-1", "source_lang": "decision", "source_text": "one"},
             {"id": "abcdef01-2", "source_lang": "decision", "source_text": "two"}]
    monkeypatch.setattr(deposit, "_rows", lambda s: twins)
    links = deposit.link_decisions(store, d.row["id"], ["abcdef01"])
    assert links.linked == [] and links.unmatched == []
    assert links.ambiguous == [{"ref": "abcdef01", "candidates": ["abcdef01-1", "abcdef01-2"]}]
    assert store.memory_edges_from(d.row["id"]) == []


@_needs_nestor
def test_a_ci_row_never_answers_a_decision_check(store):
    """The whole reason for the domain split: the entry's tier-1 ask resolves
    in `decision`, and a CI row must not be there."""
    from nestor import answer
    deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="Bot", via="webhook_inbox")
    r = answer.resolve(store, f"How did CI go for {REPO}@{SHA}?", domain="decision")
    assert r.get("state") != "sealed" and r.get("verified") is not True


# ── the age (Rule 3, second question) ──────────────────────────────────────

def test_human_age_reads_two_units():
    assert deposit.human_age(None) == "unknown age"
    assert deposit.human_age(0) == "0s"
    assert deposit.human_age(59) == "59s"
    assert deposit.human_age(3600 * 27 + 60 * 5 + 3) == "1d 3h"
    assert deposit.human_age(60 * 12 + 30) == "12m 30s"


@_needs_nestor
def test_deposit_age_is_none_on_an_empty_store_and_reads_the_live_row(store):
    assert deposit.deposit_age(store) is None
    then = datetime(2026, 9, 3, 6, 0, tzinfo=timezone.utc)
    deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=RUNS, actor_type="Bot", via="webhook_inbox", now=then)
    age = deposit.deposit_age(store, now=then.replace(hour=9))
    assert age["repo"] == REPO and age["sha"] == SHA
    assert age["states"] == {"pass": 2, "could_not_run": 1}
    assert age["age_seconds"] is not None and age["age_seconds"] >= 0
    assert deposit.deposit_age(store, repo="other/repo") is None
    # a revision moves the live row; the age follows the live row, not history
    rerun = [Run("Tests", "completed", "failure", "9", "u9")]
    deposit.deposit_ci(store, repo=REPO, sha=SHA, runs=rerun, actor_type="Bot", via="gh")
    assert deposit.deposit_age(store)["states"] == {"fail": 1}


def test_inbox_reader_carries_the_sender_type_verbatim(tmp_path):
    _item(tmp_path, "a", kind="check_run", head_sha=SHA, name="Tests", conclusion="success", sender_type="Bot")
    _item(tmp_path, "b", kind="check_run", head_sha="f" * 40, name="Tests", conclusion="success",
          sender_type="Organization")
    _item(tmp_path, "c", kind="check_run", head_sha="e" * 40, name="Tests", conclusion="success")
    r = deposit.read_inbox(tmp_path)
    assert r.actor == {SHA: "Bot", "f" * 40: "Organization"}, "verbatim, unmapped; absent stays absent"


# ── the covenant, as a type ────────────────────────────────────────────────

@_needs_nestor
def test_the_only_nestor_surface_is_propose_only(store):
    """loki's finding: a live DecisionMemory carries seal and seal_edge, so a
    grep on the source was the only guard. Now the object the module holds
    cannot reach them at all."""
    mem = deposit._decision_memory(store, deposit.DOMAIN)
    assert isinstance(mem, deposit.ProposeOnly)
    public = {n for n in dir(mem) if not n.startswith("_")}
    assert public == {"propose", "propose_edge", "revise_draft", "domain"}
    for forbidden in ("seal", "seal_edge", "store", "reject_pair", "reject_match"):
        assert not hasattr(mem, forbidden), forbidden
    with pytest.raises(AttributeError):
        mem.seal  # noqa: B018
    with pytest.raises(AttributeError):
        setattr(mem, "seal", lambda *a, **k: None)  # __slots__: nothing can be bolted on


# ── the covenant, on the source ────────────────────────────────────────────

def test_the_module_never_names_seal_or_a_keyring():
    src = Path(deposit.__file__).read_text(encoding="utf-8")
    body = src.split('"""', 2)[2]  # below the module docstring
    for word in ("seal(", "seal_edge(", "keyring", "sign_seal", "NESTOR_SEAL_KEY"):
        assert word not in body, f"{word!r} appears in forge/deposit.py"
    assert "import requests" not in body and "urllib" not in body and "subprocess" not in body, \
        "the module opens no network and runs no command"
