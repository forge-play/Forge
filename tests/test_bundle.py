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


def _box_path_leaks(path) -> bool:
    """True if the file at `path` names the operator's box — `paths.home()`,
    the one string a cut must never carry into a repository."""
    return str(paths.home()) in path.read_text(encoding="utf-8")


def test_the_box_path_scan_catches_a_planted_leak(home):
    """Planted: a file that names the box, beside one that names only the
    project. Factored out of the cut test on 2026-09-12 when the meta-scan
    (tests/test_scans_fire.py) reported its inline read-and-`not in` as a
    scan with nothing to plant."""
    leaky = home / "leaky.json"
    leaky.write_text(f'{{"store": "{paths.home()}/x.sqlite"}}', encoding="utf-8")
    clean = home / "clean.json"
    clean.write_text('{"store": "paths.project_nestor(\'demo\')"}', encoding="utf-8")
    assert _box_path_leaks(leaky)
    assert not _box_path_leaks(clean)


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


def test_a_fresh_checkout_is_uncut_not_failed(tmp_path):
    """A workshop instantiated a minute ago has no ledger head to cut from,
    so it has neither file. That is `uncut`, and it is not a failure — a new
    workshop that is red for doing nothing wrong teaches its maker to ignore
    red."""
    c = bundle.check(tmp_path)
    assert c.state == "uncut"
    assert c.ok and c.problems == []
    assert c.digest_recomputed == "not_checked"
    assert c.to_dict()["state"] == "uncut"


def test_a_half_pair_is_still_a_failure(tmp_path):
    """Only *neither* file is uncut. One present and the other missing is a
    checkout that cut a bundle and lost half of it."""
    out = tmp_path / ".forge"
    out.mkdir()
    (out / "HEAD").write_text(json.dumps({"head": "abc", "digest": "d"}))
    c = bundle.check(tmp_path)
    assert c.state == "failed" and not c.ok
    assert c.problems == ["missing .forge/bundle.json"]

    (out / "HEAD").unlink()
    (out / "bundle.json").write_text(json.dumps({"digest": "d", "pairs": []}))
    c = bundle.check(tmp_path)
    assert c.state == "failed" and not c.ok
    assert c.problems == ["missing .forge/HEAD"]


def test_uncut_does_not_excuse_a_database_in_the_checkout(tmp_path):
    """The workshop rule does not care how far along the workshop is."""
    (tmp_path / "nestor.db").write_text("no")
    c = bundle.check(tmp_path)
    assert c.state == "failed" and not c.ok
    assert c.problems == ["database in the checkout: nestor.db"]


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
    assert not _box_path_leaks(c.head_path), "no box path in the repo"
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


# ── the command line ───────────────────────────────────────────────────────
# The CLI lives in forge/bundle.py, not tools/, because tools/ is not in the
# wheel. These tests are the ones that would have caught that: they exercise
# what a maker who ran `pip install forge-play` actually has.

def test_the_console_script_is_declared_so_a_pip_install_can_invoke_it():
    """`tools/store_export.py` is not installed by the wheel. Without a
    declared entry point a workshop has the library and no command, and step
    6 of the-forge-workshop.md is unreachable from a real install."""
    from importlib.metadata import entry_points
    scripts = {e.name: e.value for e in entry_points(group="console_scripts")}
    assert scripts.get("forge-export") == "forge.bundle:main", (
        "forge-export is not installed; reinstall the package after changing "
        "[project.scripts]"
    )


def test_the_cli_reports_uncut_and_exits_zero(tmp_path, capsys):
    rc = bundle.main(["--repo-root", str(tmp_path), "--check"])
    out = capsys.readouterr().out
    assert rc == 0, "a fresh workshop must not fail its own CI"
    assert "uncut" in out and "not a failure" in out


def test_the_cli_reports_a_half_pair_as_failed_and_exits_one(tmp_path, capsys):
    out_dir = tmp_path / ".forge"
    out_dir.mkdir()
    (out_dir / "HEAD").write_text(json.dumps({"head": "abc", "digest": "d"}))
    rc = bundle.main(["--repo-root", str(tmp_path), "--check"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAILED" in out and "missing .forge/bundle.json" in out


def test_the_cli_json_carries_the_state(tmp_path, capsys):
    rc = bundle.main(["--repo-root", str(tmp_path), "--check", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0 and payload["state"] == "uncut" and payload["ok"] is True


def test_the_cli_refuses_a_cut_with_no_project_id(tmp_path):
    with pytest.raises(SystemExit) as e:
        bundle.main(["--repo-root", str(tmp_path)])
    assert e.value.code == 2


@_needs_nestor
def test_the_cli_cuts_and_then_checks_clean(home, tmp_path, capsys):
    _make_store(PROJECT)
    repo = tmp_path / "checkout"
    repo.mkdir()
    assert bundle.main(["--project-id", PROJECT, "--repo-root", str(repo)]) == 0
    assert "cut " + PROJECT in capsys.readouterr().out
    assert bundle.main(["--repo-root", str(repo), "--check"]) == 0
    assert "ok" in capsys.readouterr().out
    assert bundle.check(repo).state == "ok"
