"""Tests for forge/project_home.py and the workshop-root half of forge/paths.py
— Phase 1a of docs/design/the-workshop-surface-and-home.md, held to that
paper's testing recipe:

  1. ensure_project_home is idempotent and writes the starter README once.
  2. A refused open_bite creates no directory (the host calls it after).
  3. An invalid or empty project_id is refused.
  6. No Nestor database or `.forge/` appears under the project home.

`FORGE_WORKSHOP_ROOT` is pointed at tmp_path so nothing lands under the real
`~/Forge/workshop`; `FORGE_HOME` likewise, so the CLI tests' project store
lands in a tmp too.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge import _ids, checkpoint_memory, entry, paths, project_home

_HAS_NESTOR = checkpoint_memory.nestor_available()
_needs_nestor = pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")

PROJECT = "demo-project"


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    root = tmp_path / "workshop"
    monkeypatch.setenv("FORGE_WORKSHOP_ROOT", str(root))
    monkeypatch.setenv("FORGE_HOME", str(tmp_path / "forge-home"))
    return root


# ── paths: the resolver only computes ───────────────────────────────────────


def test_workshop_root_defaults_under_the_real_home(monkeypatch):
    monkeypatch.delenv("FORGE_WORKSHOP_ROOT", raising=False)
    assert paths.workshop_root() == Path.home() / "Forge" / "workshop"


def test_workshop_root_respects_the_override(workshop):
    assert paths.workshop_root() == workshop


def test_workshop_root_falls_back_when_the_override_is_empty(monkeypatch):
    monkeypatch.setenv("FORGE_WORKSHOP_ROOT", "")
    assert paths.workshop_root() == Path.home() / "Forge" / "workshop"


def test_project_home_is_under_the_workshop_root_and_does_not_touch_disk(workshop):
    p = paths.project_home(PROJECT)
    assert p == workshop / PROJECT
    assert not workshop.exists()


def test_project_home_applies_the_id_charset(workshop):
    with pytest.raises(_ids.PrincipalError):
        paths.project_home("../escape")


def test_the_three_locations_are_distinct(workshop):
    """The paper's rule: git checkout, `~/.forge`, and the workshop home are
    three places. The resolver must not put the home under the engine root."""
    home = paths.project_home(PROJECT)
    assert paths.home() not in home.parents
    assert paths.project_nestor(PROJECT).parent not in home.parents


# ── ensure_project_home ─────────────────────────────────────────────────────


def test_creates_the_folder_and_the_starter_readme(workshop):
    home = project_home.ensure_project_home(PROJECT)
    assert home == workshop / PROJECT
    assert home.is_dir()
    readme = home / project_home.README_NAME
    assert readme.is_file()
    text = readme.read_text(encoding="utf-8")
    assert text.startswith(f"# {PROJECT}\n")
    assert text == project_home.STARTER_README.format(project_id=PROJECT)


def test_idempotent_and_never_modifies_an_existing_home(workshop):
    home = project_home.ensure_project_home(PROJECT)
    readme = home / project_home.README_NAME
    readme.write_text("mine now\n", encoding="utf-8")
    (home / "notes.txt").write_text("keep\n", encoding="utf-8")

    again = project_home.ensure_project_home(PROJECT)
    assert again == home
    assert readme.read_text(encoding="utf-8") == "mine now\n"
    assert (home / "notes.txt").read_text(encoding="utf-8") == "keep\n"


def test_a_deleted_readme_is_not_rewritten(workshop):
    """'On first creation only' means only: a maker who removed the README
    made a decision, and the engine does not undo it on the next bite."""
    home = project_home.ensure_project_home(PROJECT)
    (home / project_home.README_NAME).unlink()
    project_home.ensure_project_home(PROJECT)
    assert not (home / project_home.README_NAME).exists()


@pytest.mark.parametrize("bad", ["", "../escape", "a/b", " ", "x" * 129])
def test_refuses_an_empty_or_invalid_id(workshop, bad):
    with pytest.raises(project_home.ProjectHomeError):
        project_home.ensure_project_home(bad)
    assert not workshop.exists()


def test_refuses_a_non_str_id(workshop):
    with pytest.raises(project_home.ProjectHomeError):
        project_home.ensure_project_home(None)  # type: ignore[arg-type]


def test_refuses_a_symlinked_home(workshop, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    workshop.mkdir(parents=True)
    (workshop / PROJECT).symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(project_home.ProjectHomeError):
        project_home.ensure_project_home(PROJECT)
    assert not (elsewhere / project_home.README_NAME).exists()


def test_refuses_a_home_that_is_a_file(workshop):
    workshop.mkdir(parents=True)
    (workshop / PROJECT).write_text("not a dir\n", encoding="utf-8")
    with pytest.raises(project_home.ProjectHomeError):
        project_home.ensure_project_home(PROJECT)


def test_no_engine_state_lands_under_the_home(workshop):
    """Recipe item 6: the home is maker workspace, never the store."""
    home = project_home.ensure_project_home(PROJECT)
    assert sorted(p.name for p in home.iterdir()) == [project_home.README_NAME]
    assert not (home / ".forge").exists()
    assert not list(home.rglob("nestor.db"))


# ── the host: after a successful bite, and only then ────────────────────────


def test_a_refused_bite_creates_no_home(workshop, monkeypatch, capsys):
    """Recipe item 2. Nestor absent is the entry's own refusal; the CLI
    returns 2 before the home step runs."""
    monkeypatch.setattr(entry.checkpoint_memory, "nestor_available", lambda: False)
    rc = entry.main(["a sentence", "--project", PROJECT, "--builder", "b" * 32])
    assert rc == 2
    assert "REFUSED" in capsys.readouterr().err
    assert not workshop.exists()


def test_an_empty_sentence_creates_no_home(workshop, capsys):
    rc = entry.main(["   ", "--project", PROJECT, "--builder", "b" * 32])
    assert rc == 2
    assert not workshop.exists()


@_needs_nestor
def test_a_successful_bite_reports_the_home_beside_the_tiers(workshop, tmp_path, capsys):
    rc = entry.main(
        [
            "a records tool for the rally",
            "--project",
            PROJECT,
            "--builder",
            "b" * 32,
            "--root",
            str(tmp_path / "checkpoints"),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    home = workshop / PROJECT
    assert f"home    {home}" in out
    assert (home / project_home.README_NAME).is_file()
    # Reported beside the tiers, not as one — a folder is not a source that
    # answered (the paper leaves `tiers["home"]` open; the host reports it).
    assert out.index("major   ") < out.index("home    ")


@_needs_nestor
def test_json_output_carries_the_home(workshop, tmp_path, capsys):
    import json

    rc = entry.main(
        [
            "a records tool for the rally",
            "--project",
            PROJECT,
            "--builder",
            "b" * 32,
            "--root",
            str(tmp_path / "checkpoints"),
            "--json",
        ]
    )
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["home"] == str(workshop / PROJECT)
    assert "home" not in d["tiers"]


@_needs_nestor
def test_a_home_that_cannot_be_made_is_reported_not_faked(workshop, tmp_path, capsys):
    """Honest absence: the bite already happened; the folder failing is a
    state the maker reads, not a clean success and not a retroactive refusal."""
    workshop.mkdir(parents=True)
    (workshop / PROJECT).write_text("in the way\n", encoding="utf-8")
    rc = entry.main(
        [
            "a records tool for the rally",
            "--project",
            PROJECT,
            "--builder",
            "b" * 32,
            "--root",
            str(tmp_path / "checkpoints"),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "home    could not create: ProjectHomeError" in out
