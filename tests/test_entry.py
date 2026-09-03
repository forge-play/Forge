"""forge/entry.py — Nestor first, then the scan, then the first real decision
through the checkpoint router.

Needs Nestor for everything but the refusal test (`checkpoint_memory
.nestor_available()` is the gate). `FORGE_HOME` is pointed at tmp_path so the
project store lands there, and the checkpoint root is a tmp too.
"""
from __future__ import annotations

import pytest

from forge import checkpoint, checkpoint_memory, entry, paths
from forge.checkpoint import ChoiceResult, Decision

_HAS_NESTOR = checkpoint_memory.nestor_available()
_needs_nestor = pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")

BUILDER = "b" * 32
PROJECT = "demo-project"
SENTENCE = "I got sum kol sites for app to spin"


class ScriptedResponder:
    def __init__(self, choose=None, confirm=True):
        self._choose = choose
        self._confirm = confirm
        self.choose_calls: list[Decision] = []
        self.confirm_prompts: list[str] = []

    def confirm(self, prompt: str) -> bool:
        self.confirm_prompts.append(prompt)
        return self._confirm

    def choose(self, decision: Decision) -> ChoiceResult:
        self.choose_calls.append(decision)
        assert self._choose is not None, "asked to choose with nothing scripted"
        return ChoiceResult(chosen_label=self._choose, rationale="because the rally has a website already")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("FORGE_HOME", str(tmp_path / "forge-home"))
    return tmp_path


def test_nestor_absent_is_a_refusal_not_a_degrade(home, monkeypatch):
    monkeypatch.setattr(entry.checkpoint_memory, "nestor_available", lambda: False)
    with pytest.raises(entry.EntryError) as e:
        entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                        responder=ScriptedResponder(), root=home / "cp")
    assert "never asked" in str(e.value)


def test_an_empty_sentence_is_not_a_bite(home):
    with pytest.raises(entry.EntryError):
        entry.open_bite("   ", project_id=PROJECT, builder_id=BUILDER,
                        responder=ScriptedResponder(), root=home / "cp")


def test_project_nestor_path_hangs_off_the_forge_home_and_checks_the_charset(home):
    p = paths.project_nestor(PROJECT)
    assert p == paths.home() / "projects" / PROJECT / "nestor" / "keep" / "nestor.db"
    assert paths.project_nestor_ledger(PROJECT) == p.with_name("ledger.jsonl")
    with pytest.raises(Exception):
        paths.project_nestor("../escape")


@_needs_nestor
def test_ambiguity_asks_once_then_confirms_without_asking(home):
    root = home / "cp"
    r1 = ScriptedResponder(choose="web")
    e1 = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER, responder=r1, root=root)
    assert e1.tiers["nestor"].startswith("pending")
    assert e1.tiers["box"].endswith("nothing")
    assert e1.tiers["remote"].startswith("not_attempted")
    assert set(e1.majors) == {"web", "mobile", "desktop"}
    assert len(r1.choose_calls) == 1, "three majors → one Socratic ask"
    asked = r1.choose_calls[0]
    assert asked.decision_type == entry.DECISION_TYPE_MAJOR
    assert {o.label for o in asked.options} == {"web", "mobile", "desktop"}
    assert e1.decision_outcome.band == "socratic" and e1.decision_outcome.sealed
    assert e1.major == "web"
    assert paths.project_nestor(PROJECT).exists(), "the project store was created on first ask"

    r2 = ScriptedResponder(choose=None)  # would fail if asked to choose
    e2 = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER, responder=r2, root=root)
    assert r2.choose_calls == [], "the second time, the maker is confirmed, not re-asked"
    assert r2.confirm_prompts, "…but they ARE confirmed (auto is never a silent commit)"
    assert e2.decision_outcome.band in ("auto", "recognize")
    assert e2.major == "web"


@_needs_nestor
def test_one_major_needs_no_decision(home):
    r = ScriptedResponder()
    e = entry.open_bite("a tiny cli that renames files", project_id=PROJECT, builder_id=BUILDER,
                        responder=r, root=home / "cp")
    assert e.major == "cli" and e.decision_outcome is None
    assert r.choose_calls == [] and r.confirm_prompts == []
    assert "unambiguous" in e.tiers["scan"]


@_needs_nestor
def test_no_keyword_is_an_honest_empty(home):
    e = entry.open_bite("hello there", project_id=PROJECT, builder_id=BUILDER,
                        responder=ScriptedResponder(), root=home / "cp")
    assert e.major is None and e.hits == [] and "no keyword" in e.tiers["scan"]


@_needs_nestor
def test_a_sealed_project_answer_short_circuits_the_scan(home):
    from nestor import memory
    from nestor.sqlite_store import SqliteStore

    db = paths.project_nestor(PROJECT)
    db.parent.mkdir(parents=True)
    store = SqliteStore(str(db))
    memory.add_pair(SENTENCE, "web: the rally already has a site", "decision", "decision",
                    status="sealed", verifier="rosalind", store=store)

    r = ScriptedResponder()
    e = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER, responder=r, root=home / "cp")
    assert e.tiers["nestor"].startswith("sealed")
    assert e.answer.startswith("web")
    assert e.major == "web" and e.decision_outcome is None
    assert r.choose_calls == [] and r.confirm_prompts == []
    assert "skipped" in e.tiers["scan"]


@_needs_nestor
def test_the_box_seam_is_consulted_and_named(home):
    class FakeBox:
        name = "fake catalog"

        def lookup(self, hits):
            return [entry.Candidate(name="rally-site", where="apps/rally-site", why="a site with the same keywords")]

    e = entry.open_bite("a site", project_id=PROJECT, builder_id=BUILDER,
                        responder=ScriptedResponder(), root=home / "cp", box=FakeBox())
    assert e.candidates and e.candidates[0].name == "rally-site"
    assert e.tiers["box"] == "fake catalog: 1 candidate(s)"


@_needs_nestor
def test_cli_asks_then_confirms(home, capsys):
    root = str(home / "cp")
    rc = entry.main([SENTENCE, "--project", PROJECT, "--builder", BUILDER, "--root", root,
                     "--choose", "mobile", "--json"])
    assert rc == 0
    import json
    d = json.loads(capsys.readouterr().out)
    assert d["major"] == "mobile" and d["decision_outcome"]["band"] == "socratic"
    rc = entry.main([SENTENCE, "--project", PROJECT, "--builder", BUILDER, "--root", root, "--json"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["major"] == "mobile" and d["decision_outcome"]["band"] in ("auto", "recognize")


def test_the_demo_finds_its_table():
    """demo/the_first_bite.py's beat 1 looks for forge/keywords.toml and logs
    friction if it is missing. It exists now."""
    from forge import majors
    assert majors.DEFAULT_TABLE.name == "keywords.toml" and majors.DEFAULT_TABLE.exists()
