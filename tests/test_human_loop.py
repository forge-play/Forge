"""Tests for forge/human_loop.py — the human-in-the-loop primitives (attention
queue + attestation record), vendored from willow-mcp and adopted under
checkpoint (docs/design/the-forge-human-loop.md, D-HL-1/D-HL-2). Exercised
directly against `forge.soil_store.FilesystemSoilStore` + `tmp_path`, the
same injected-store pattern `tests/test_checkpoint_governance.py` uses one
layer up (through `checkpoint_governance`'s wrapper).

NOTE on `resolve()` and unknown `item_id`: upstream returns
`{"error": "unknown_item", "item_id": item_id}` rather than raising — the
Forge keeps this byte-for-byte (vendor_sync_check enforces it). Callers must
check for the error dict; only invalid *status* values raise HumanLoopError.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from forge import human_loop
from forge.soil_store import FilesystemSoilStore

BUILDER_A = "a" * 32


@pytest.fixture
def store(tmp_path):
    return FilesystemSoilStore(BUILDER_A, root=tmp_path)


# ── enqueue() ────────────────────────────────────────────────────────────────

def test_enqueue_creates_an_item_with_the_expected_fields(store):
    item = human_loop.enqueue(
        store,
        kind="consent",
        title="Ship the login redesign?",
        source_agent="vishwakarma",
        summary="Needs a human yes/no before promotion",
        priority="high",
        source_ref="pair-42",
        assignee="rudi",
    )
    assert item["kind"] == "consent"
    assert item["title"] == "Ship the login redesign?"
    assert item["summary"] == "Needs a human yes/no before promotion"
    assert item["priority"] == "high"
    assert item["status"] == human_loop.QUEUE_OPEN
    assert item["source_agent"] == "vishwakarma"
    assert item["source_ref"] == "pair-42"
    assert item["assignee"] == "rudi"
    assert item["resolved_by"] == ""
    assert item["resolved_at"] == ""
    assert item["note"] == ""
    assert isinstance(item["id"], str) and item["id"]
    # created_at is a real ISO-8601 timestamp
    datetime.fromisoformat(item["created_at"])


def test_enqueue_defaults_priority_to_normal(store):
    item = human_loop.enqueue(store, kind="review", title="t", source_agent="a")
    assert item["priority"] == "normal"


def test_enqueue_persists_to_the_store(store):
    item = human_loop.enqueue(store, kind="review", title="t", source_agent="a")
    assert store.get(human_loop.QUEUE_COLLECTION, item["id"]) == item


def test_enqueue_rejects_an_unknown_kind(store):
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.enqueue(store, kind="not-a-real-kind", title="t", source_agent="a")


def test_enqueue_rejects_an_empty_title(store):
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.enqueue(store, kind="review", title="   ", source_agent="a")


def test_enqueue_rejects_an_unknown_priority(store):
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.enqueue(store, kind="review", title="t", source_agent="a", priority="urgentish")


# ── resolve() ────────────────────────────────────────────────────────────────

def test_resolve_updates_status_resolved_by_and_resolved_at(store):
    item = human_loop.enqueue(store, kind="review", title="t", source_agent="a")
    assert item["resolved_by"] == ""

    resolved = human_loop.resolve(store, item["id"], resolved_by="rudi", note="looks good")
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == "rudi"
    assert resolved["note"] == "looks good"
    assert resolved["resolved_at"] != ""
    datetime.fromisoformat(resolved["resolved_at"])
    # everything else about the item is preserved
    assert resolved["id"] == item["id"]
    assert resolved["title"] == item["title"]
    assert resolved["kind"] == item["kind"]


def test_resolve_persists_the_update(store):
    item = human_loop.enqueue(store, kind="review", title="t", source_agent="a")
    human_loop.resolve(store, item["id"], resolved_by="rudi")
    stored = store.get(human_loop.QUEUE_COLLECTION, item["id"])
    assert stored["status"] == "resolved"
    assert stored["resolved_by"] == "rudi"


def test_resolve_supports_dismissed_and_acknowledged(store):
    item = human_loop.enqueue(store, kind="consent", title="t", source_agent="a")
    dismissed = human_loop.resolve(store, item["id"], resolved_by="rudi", status="dismissed")
    assert dismissed["status"] == "dismissed"

    item2 = human_loop.enqueue(store, kind="overload", title="t2", source_agent="a")
    ack = human_loop.resolve(store, item2["id"], resolved_by="rudi", status="acknowledged")
    assert ack["status"] == "acknowledged"


def test_resolve_rejects_an_unknown_status(store):
    item = human_loop.enqueue(store, kind="review", title="t", source_agent="a")
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.resolve(store, item["id"], resolved_by="rudi", status="approved")


def test_resolve_returns_error_dict_for_unknown_item_id(store):
    result = human_loop.resolve(store, "never-enqueued-id", resolved_by="rudi")
    assert result == {"error": "unknown_item", "item_id": "never-enqueued-id"}


def test_resolve_returns_error_dict_when_queue_has_other_items(store):
    human_loop.enqueue(store, kind="review", title="t1", source_agent="a")
    human_loop.enqueue(store, kind="consent", title="t2", source_agent="a")
    result = human_loop.resolve(store, "still-unknown", resolved_by="rudi")
    assert result == {"error": "unknown_item", "item_id": "still-unknown"}


def test_queue_stats_counts_by_status(store):
    a = human_loop.enqueue(store, kind="review", title="a", source_agent="x")
    b = human_loop.enqueue(store, kind="review", title="b", source_agent="x")
    human_loop.resolve(store, a["id"], resolved_by="rudi", status="dismissed")
    stats = human_loop.queue_stats(store)
    assert stats.get(human_loop.QUEUE_OPEN, 0) == 1
    assert stats.get("dismissed", 0) == 1
    assert stats.get("resolved", 0) == 0


# ── list_queue() ─────────────────────────────────────────────────────────────

def test_list_queue_defaults_to_open_only(store):
    open_item = human_loop.enqueue(store, kind="review", title="open one", source_agent="a")
    closed_item = human_loop.enqueue(store, kind="review", title="closed one", source_agent="a")
    human_loop.resolve(store, closed_item["id"], resolved_by="rudi")

    open_items = human_loop.list_queue(store)
    ids = {i["id"] for i in open_items}
    assert open_item["id"] in ids
    assert closed_item["id"] not in ids


def test_list_queue_filters_by_status(store):
    a = human_loop.enqueue(store, kind="review", title="a", source_agent="x")
    b = human_loop.enqueue(store, kind="review", title="b", source_agent="x")
    human_loop.resolve(store, a["id"], resolved_by="rudi", status="dismissed")

    dismissed = human_loop.list_queue(store, status="dismissed")
    assert {i["id"] for i in dismissed} == {a["id"]}

    still_open = human_loop.list_queue(store, status=human_loop.QUEUE_OPEN)
    assert {i["id"] for i in still_open} == {b["id"]}


def test_list_queue_filters_by_kind(store):
    c = human_loop.enqueue(store, kind="consent", title="c", source_agent="x")
    r = human_loop.enqueue(store, kind="review", title="r", source_agent="x")

    consents = human_loop.list_queue(store, status="", kind="consent")
    assert {i["id"] for i in consents} == {c["id"]}

    reviews = human_loop.list_queue(store, status="", kind="review")
    assert {i["id"] for i in reviews} == {r["id"]}


def test_list_queue_combines_status_and_kind_filters(store):
    target = human_loop.enqueue(store, kind="consent", title="target", source_agent="x")
    other_kind = human_loop.enqueue(store, kind="review", title="other kind", source_agent="x")
    same_kind_resolved = human_loop.enqueue(store, kind="consent", title="resolved", source_agent="x")
    human_loop.resolve(store, same_kind_resolved["id"], resolved_by="rudi")

    matched = human_loop.list_queue(store, status=human_loop.QUEUE_OPEN, kind="consent")
    assert {i["id"] for i in matched} == {target["id"]}
    assert other_kind["id"] not in {i["id"] for i in matched}
    assert same_kind_resolved["id"] not in {i["id"] for i in matched}


def test_list_queue_empty_status_means_all_statuses(store):
    open_item = human_loop.enqueue(store, kind="review", title="open", source_agent="x")
    closed_item = human_loop.enqueue(store, kind="review", title="closed", source_agent="x")
    human_loop.resolve(store, closed_item["id"], resolved_by="rudi")

    everything = human_loop.list_queue(store, status="")
    assert {i["id"] for i in everything} == {open_item["id"], closed_item["id"]}


def test_list_queue_respects_limit(store):
    for n in range(5):
        human_loop.enqueue(store, kind="review", title=f"t{n}", source_agent="x")
    assert len(human_loop.list_queue(store, limit=2)) == 2


def test_list_queue_newest_first(store):
    first = human_loop.enqueue(store, kind="review", title="first", source_agent="x")
    second = human_loop.enqueue(store, kind="review", title="second", source_agent="x")
    rows = human_loop.list_queue(store, status="")
    assert [r["id"] for r in rows[:2]] == [second["id"], first["id"]]


# ── create_attestation() ─────────────────────────────────────────────────────

def test_create_attestation_has_the_expected_fields(store):
    rec = human_loop.create_attestation(
        store,
        subject_id="pair-99",
        attested_by=BUILDER_A,
        by_human=True,
        subject_type="knowledge_atom",
        statement="I reviewed this and it holds",
        evidence_ref="ledger:abc123",
        context={"channel": "review"},
    )
    assert rec["subject_id"] == "pair-99"
    assert rec["subject_type"] == "knowledge_atom"
    assert rec["status"] == "attested"
    assert rec["attested_by"] == BUILDER_A
    assert rec["by_human"] is True
    assert rec["statement"] == "I reviewed this and it holds"
    assert rec["evidence_ref"] == "ledger:abc123"
    assert rec["context"] == {"channel": "review"}
    assert isinstance(rec["id"], str) and rec["id"]
    datetime.fromisoformat(rec["created_at"])


def test_create_attestation_by_human_is_not_forgeable_as_free_text(store):
    """`attested_by`/`by_human` come from the CALLER's supplied identity
    fields, not from anything the store or a subject_id could inject —
    the anti-forgery property the module docstring names."""
    rec = human_loop.create_attestation(
        store, subject_id="p1", attested_by="an-agent", by_human=False,
    )
    assert rec["by_human"] is False
    assert rec["attested_by"] == "an-agent"


def test_create_attestation_persists_to_the_store(store):
    rec = human_loop.create_attestation(store, subject_id="p1", attested_by=BUILDER_A, by_human=True)
    assert store.get(human_loop.ATTEST_COLLECTION, rec["id"]) == rec


def test_create_attestation_rejects_empty_subject_id(store):
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.create_attestation(store, subject_id="  ", attested_by=BUILDER_A, by_human=True)


def test_create_attestation_rejects_unknown_subject_type(store):
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.create_attestation(
            store, subject_id="p1", attested_by=BUILDER_A, by_human=True, subject_type="not-a-type",
        )


def test_create_attestation_rejects_unknown_status(store):
    with pytest.raises(human_loop.HumanLoopError):
        human_loop.create_attestation(
            store, subject_id="p1", attested_by=BUILDER_A, by_human=True, status="not-a-status",
        )


# ── has_attestation() / list_attestations() — the require_human gate ────────

def test_has_attestation_requires_human_when_asked(store):
    human_loop.create_attestation(store, subject_id="p1", attested_by="agent", by_human=False)
    assert human_loop.has_attestation(store, subject_id="p1") is True
    assert human_loop.has_attestation(store, subject_id="p1", require_human=True) is False

    human_loop.create_attestation(store, subject_id="p1", attested_by="rudi", by_human=True)
    assert human_loop.has_attestation(store, subject_id="p1", require_human=True) is True


def test_has_attestation_false_for_unknown_subject(store):
    assert human_loop.has_attestation(store, subject_id="never-seen") is False


def test_has_attestation_false_when_only_rejected(store):
    human_loop.create_attestation(
        store, subject_id="p1", attested_by="rudi", by_human=True, status="rejected",
    )
    assert human_loop.has_attestation(store, subject_id="p1") is False
