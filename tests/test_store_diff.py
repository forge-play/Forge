"""forge/store_diff.py — the four sets between a project store and the main one.

Needs Nestor for the store-backed cases; the bundle-shaped case runs on the
base install.
"""
from __future__ import annotations

import pytest

from forge import checkpoint_memory, entry, paths, store_diff

_HAS_NESTOR = checkpoint_memory.nestor_available()
_needs_nestor = pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")


def _store(path):
    from nestor.sqlite_store import SqliteStore
    s = SqliteStore(str(path))
    s.memory_init()
    return s


def _seal(store, q, a, verifier="rosalind"):
    from nestor import memory
    return memory.add_pair(q, a, "decision", "decision", status="sealed", verifier=verifier, store=store)


@pytest.fixture
def stores(tmp_path):
    if not _HAS_NESTOR:
        pytest.skip("nestor not installed")
    from nestor import cascade
    from nestor.decision import DecisionMemory
    cascade.set_ledger_path(tmp_path / "ledger.jsonl")
    proj = _store(tmp_path / "proj.db")
    main = _store(tmp_path / "main.db")
    pm = DecisionMemory(proj)
    # verified upstream: same answer, draft here, sealed there
    pm.propose("Which domain holds a CI outcome?", "ci", rationale="not a decision", origin="t")
    _seal(main, "Which domain holds a CI outcome?", "ci")
    # proposed here only
    pm.propose("Does the first bite get a keyword row?", "no", origin="t")
    # conflict: sealed there with a different answer
    pm.propose("Where does the deposit run?", "gh first", origin="t")
    _seal(main, "Where does the deposit run?", "the bot's inbox first")
    # agreed: sealed both, same answer
    _seal(proj, "What may a contribution be?", "shape, never content")
    _seal(main, "What may a contribution be?", "shape, never content")
    # retired here (supersedes edge from a newer row), sealed there
    old = pm.propose("Where is the project Nestor?", "~/.forge/nestor", origin="t")
    new = pm.propose("Where is the project Nestor? (moved)", "~/.forge/projects/<id>/nestor", origin="t")
    pm.propose_edge(new["id"], old["id"], "supersedes", reason="moved")
    _seal(main, "Where is the project Nestor?", "~/.forge/nestor")
    # main-only rows are not the project's business
    _seal(main, "Something the fleet decided", "elsewhere")
    return proj, main


@_needs_nestor
def test_the_four_sets(stores):
    proj, main = stores
    d = store_diff.diff(proj, main)
    assert [x["question"] for x in d.verified_upstream] == ["Which domain holds a CI outcome?"]
    assert d.verified_upstream[0]["main_verifier"] == "rosalind"
    assert {x["question"] for x in d.proposed_here} == {"Does the first bite get a keyword row?",
                                                         "Where is the project Nestor? (moved)"}
    assert [c["question"] for c in d.conflicts] == ["Where does the deposit run?"]
    assert d.conflicts[0]["kind"] == "sealed_there"
    assert d.conflicts[0]["here"]["answer"] == "gh first" and d.conflicts[0]["there"]["answer"] == "the bot's inbox first"
    assert [x["question"] for x in d.retired_here_sealed_there] == ["Where is the project Nestor?"]
    assert d.agreed == 1
    assert d.behind == 1 and d.ahead == 2
    assert d.project_live == 6 and d.main_live == 5
    s = store_diff.summary(d)
    assert s.startswith("behind 1 (sealed upstream), ahead 2 (proposed here), 1 conflict(s), 1 retired here but sealed there; 1 agreed")


@_needs_nestor
def test_main_as_a_bundle_reads_the_same(stores, tmp_path):
    import json
    from nestor import portable
    proj, main = stores
    b = portable.export_bundle(main, include_ledger=False)
    d_dict = store_diff.diff(proj, b)
    p = tmp_path / "main-bundle.json"
    p.write_text(json.dumps(b))
    d_path = store_diff.diff(proj, p)
    for d in (d_dict, d_path):
        assert d.behind == 1 and d.ahead == 2 and len(d.conflicts) == 1 and len(d.retired_here_sealed_there) == 1
    assert d_dict.main_source.startswith("bundle (digest") and d_path.main_source.startswith("bundle main-bundle.json")


@_needs_nestor
def test_diff_writes_nothing(stores, tmp_path):
    proj, main = stores
    before = (tmp_path / "ledger.jsonl").read_text() if (tmp_path / "ledger.jsonl").exists() else ""
    n_p, n_m = len(proj.memory_list(limit=1000)), len(main.memory_list(limit=1000))
    store_diff.diff(proj, main)
    after = (tmp_path / "ledger.jsonl").read_text() if (tmp_path / "ledger.jsonl").exists() else ""
    assert before == after and len(proj.memory_list(limit=1000)) == n_p and len(main.memory_list(limit=1000)) == n_m


def test_bundle_shaped_diff_needs_no_store_on_the_main_side():
    class FakeStore:
        def memory_init(self): pass
        def memory_list(self, limit=50):
            return [{"id": "p1", "source_text": "Q one?", "source_norm": "q one", "source_lang": "decision",
                     "target_lang": "decision", "target_text": "A", "status": "draft", "superseded_by": ""},
                    {"id": "p2", "source_text": "Q two?", "source_norm": "q two", "source_lang": "decision",
                     "target_lang": "decision", "target_text": "B", "status": "draft", "superseded_by": ""}]
    bundle = {"digest": "abc123def456", "pairs": [
        {"id": "m1", "source_text": "Q one?", "source_norm": "q one", "source_lang": "decision",
         "target_lang": "decision", "target_text": "A", "status": "sealed", "verifier": "sean"}]}
    d = store_diff.diff(FakeStore(), bundle)
    assert d.behind == 1 and d.ahead == 1 and d.conflicts == [] and d.agreed == 0


# ── the entry tier ──────────────────────────────────────────────────────────

class _Responder:
    def confirm(self, prompt): return True
    def choose(self, decision): raise AssertionError("not asked")


@_needs_nestor
def test_the_entry_reports_the_main_diff_or_says_it_was_not_consulted(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("FORGE_MAIN_NESTOR", raising=False)
    e = entry.open_bite("a tiny cli that renames files", project_id="p", builder_id="b" * 32,
                        responder=_Responder(), root=tmp_path / "cp")
    assert e.tiers["main"].startswith("not consulted")
    assert list(e.tiers)[:3] == ["nestor", "deposit", "main"]

    main = _store(tmp_path / "main.db")
    _seal(main, "a tiny cli that renames files", "cli: it renames files")
    monkeypatch.setenv("FORGE_MAIN_NESTOR", str(tmp_path / "main.db"))
    e2 = entry.open_bite("a tiny cli that renames files", project_id="p", builder_id="b" * 32,
                         responder=_Responder(), root=tmp_path / "cp")
    assert e2.tiers["main"].startswith("behind 0 (sealed upstream), ahead 0"), e2.tiers["main"]
    assert "main: store main.db" in e2.tiers["main"]
    e3 = entry.open_bite("a tiny cli that renames files", project_id="p", builder_id="b" * 32,
                         responder=_Responder(), root=tmp_path / "cp", main=tmp_path / "nope.json")
    assert e3.tiers["main"].startswith("could not read main"), e3.tiers["main"]
