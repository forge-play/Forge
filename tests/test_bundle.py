"""forge/bundle.py — the export side of the store pull: a checkout carries a
bundle at a ledger head, and never a database.

`cut` needs Nestor and skips without it; `check` and `find_databases` run on
the base install.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from forge import bundle, checkpoint_memory, paths

_HAS_NESTOR = checkpoint_memory.nestor_available()
_needs_nestor = pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")

PROJECT = "demo-workshop"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path / "forge-home"))
    return tmp_path


def _make_store(project_id: str):
    from nestor import cascade
    from nestor.decision import DecisionMemory
    from nestor.sqlite_store import SqliteStore
    db = paths.project_nestor(project_id)
    db.parent.mkdir(parents=True, exist_ok=True)
    cascade.set_ledger_path(paths.project_nestor_ledger(project_id))
    store = SqliteStore(str(db))
    mem = DecisionMemory(store)
    a = mem.propose("What is the first bite?", "the question that produces a major", origin="t")
    b = mem.propose("Which major?", "cli", rationale="it renames files", origin="t")
    mem.propose_edge(b["id"], a["id"], "refines", reason="t")
    return store


# ── base install ───────────────────────────────────────────────────────────

def test_the_layout_names(tmp_path):
    assert bundle.BUNDLE_DIR == ".forge" and bundle.BUNDLE_NAME == "bundle.json" and bundle.HEAD_NAME == "HEAD"


def test_find_databases_sees_every_shape_and_skips_git(tmp_path):
    (tmp_path / ".git" / "x").mkdir(parents=True)
    (tmp_path / ".git" / "x" / "nestor.db").write_text("no")
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "nestor.db").write_text("no")
    (tmp_path / "b.sqlite3").write_text("no")
    (tmp_path / "c.SQLITE").write_text("no")
    (tmp_path / "fine.json").write_text("{}")
    assert bundle.find_databases(tmp_path) == ["a/nestor.db", "b.sqlite3", "c.SQLITE"]
    assert bundle.find_databases(tmp_path / "nope") == []


def test_check_on_an_empty_checkout_names_what_is_missing(tmp_path):
    c = bundle.check(tmp_path)
    assert not c.ok
    assert c.problems == ["missing .forge/HEAD", "missing .forge/bundle.json"]
    assert c.digest_recomputed == "not_checked"


def test_check_flags_a_database_even_when_the_files_agree(tmp_path):
    out = tmp_path / ".forge"
    out.mkdir()
    (out / "HEAD").write_text(json.dumps({"head": "abc", "digest": "d"}))
    (out / "bundle.json").write_text(json.dumps({"digest": "d", "pairs": []}))
    (tmp_path / "nestor.db").write_text("no")
    c = bundle.check(tmp_path)
    assert not c.ok and c.databases == ["nestor.db"]
    assert c.problems[0] == "database in the checkout: nestor.db"


# ── with Nestor ────────────────────────────────────────────────────────────

@_needs_nestor
def test_cut_writes_the_bundle_and_the_head_and_check_holds(home):
    from nestor import ledger
    _make_store(PROJECT)
    repo = home / "workshop"
    repo.mkdir()
    c = bundle.cut(PROJECT, repo, now=datetime(2026, 9, 3, tzinfo=timezone.utc))
    assert c.bundle_path == repo / ".forge" / "bundle.json" and c.head_path == repo / ".forge" / "HEAD"
    assert c.head == ledger.head(str(paths.project_nestor_ledger(PROJECT)))
    assert c.counts["pairs"] == 2 and c.counts["sealed"] == 0, "drafts only cross"

    head = json.loads(c.head_path.read_text())
    b = json.loads(c.bundle_path.read_text())
    assert head["digest"] == b["digest"] == c.digest
    assert head["project_id"] == PROJECT and head["cut_by"] == "forge.bundle"
    assert head["store"] == "paths.project_nestor('demo-workshop')"
    assert str(paths.home()) not in c.head_path.read_text(), "no box path in the repo"
    assert b["counts"]["sealed"] == 0 and "ledger" in b, "shape travels; the chain rides along for audit"
    assert bundle.find_databases(repo) == []

    chk = bundle.check(repo)
    assert chk.ok and chk.problems == [] and chk.digest_recomputed == "ok"
    assert chk.head["head"] == c.head


@_needs_nestor
def test_a_tampered_bundle_fails_the_check(home):
    _make_store(PROJECT)
    repo = home / "workshop"
    repo.mkdir()
    bundle.cut(PROJECT, repo)
    p = repo / ".forge" / "bundle.json"
    b = json.loads(p.read_text())
    b["pairs"][0]["target_text"] = "something a human never said"
    p.write_text(json.dumps(b))
    chk = bundle.check(repo)
    assert not chk.ok and chk.digest_recomputed == "mismatch"
    assert any("does not recompute" in x for x in chk.problems)


@_needs_nestor
def test_cut_refuses_without_a_store_and_with_a_database_in_the_checkout(home):
    repo = home / "workshop"
    repo.mkdir()
    with pytest.raises(bundle.BundleError, match="no project store"):
        bundle.cut(PROJECT, repo)
    _make_store(PROJECT)
    (repo / "nestor.db").write_text("no")
    with pytest.raises(bundle.BundleError, match="never contains a Nestor database"):
        bundle.cut(PROJECT, repo)
    assert not (repo / ".forge").exists(), "a refusal writes nothing"


@_needs_nestor
def test_cut_refuses_a_broken_ledger(home):
    _make_store(PROJECT)
    lp = paths.project_nestor_ledger(PROJECT)
    if lp.exists() and lp.read_text().strip():
        lines = lp.read_text().splitlines()
        lines[-1] = lines[-1].replace('"', "'", 1)  # break the chain's last line
        lp.write_text("\n".join(lines) + "\n")
        repo = home / "workshop"
        repo.mkdir()
        with pytest.raises(bundle.BundleError, match="does not verify"):
            bundle.cut(PROJECT, repo)
    else:
        pytest.skip("no ledger entries were written by propose on this Nestor; nothing to break")


@_needs_nestor
def test_a_second_cut_moves_the_head_with_the_ledger(home):
    from nestor import ledger
    from nestor.decision import DecisionMemory
    from nestor.sqlite_store import SqliteStore
    store = _make_store(PROJECT)
    repo = home / "workshop"
    repo.mkdir()
    first = bundle.cut(PROJECT, repo)
    DecisionMemory(store).propose("A third question?", "yes", origin="t")
    second = bundle.cut(PROJECT, repo)
    assert second.counts["pairs"] == 3 and second.digest != first.digest
    assert second.head == ledger.head(str(paths.project_nestor_ledger(PROJECT)))
    assert bundle.check(repo).ok
