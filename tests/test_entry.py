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
def test_the_entry_reports_the_deposit_age_with_the_answer(home):
    """Rule 3's second question, the-forge-shape.md §12: report the age and
    the state with the answer, never silently. An empty store says `none`;
    after a deposit the tier names the sha, the states and an age."""
    from nestor.sqlite_store import SqliteStore
    from forge import deposit
    from forge.deposit import Run

    e = entry.open_bite("a tiny cli that renames files", project_id=PROJECT, builder_id=BUILDER,
                        responder=ScriptedResponder(), root=home / "cp")
    assert e.tiers["deposit"].startswith("none")
    assert list(e.tiers)[:2] == ["nestor", "deposit"], "asked, then how current the answer is"

    store = SqliteStore(str(paths.project_nestor(PROJECT)))
    deposit.deposit_ci(store, repo="forge-play/Forge", sha="cc9aab19ba2502e14e331e20e699f634fb4cb1a2",
                       runs=[Run("Tests", "completed", "success", "1"), Run("CodeQL", "completed", "cancelled", "2")],
                       actor_type="Bot", via="webhook_inbox")
    e2 = entry.open_bite("a tiny cli that renames files", project_id=PROJECT, builder_id=BUILDER,
                         responder=ScriptedResponder(), root=home / "cp")
    t = e2.tiers["deposit"]
    assert "forge-play/Forge@cc9aab19ba25" in t and "could_not_run 1" in t and "pass 1" in t
    assert t.endswith(")") and " old: " in t
    assert e2.tiers["nestor"].startswith("pending"), "a ci row never answers the decision ask"


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


# ── the --why default: a rationale nobody typed is not one ──────────────────
#
# docs/design/the-positional-default.md's @prompt: "the test that matters is a
# sentence with two or more majors and no --choose, run non-interactively." Its
# open-gaps table names the `--why` default as its own row. These are that row.
#
# A test asserting the *right* major was chosen would be testing the keyword
# table, not this.

def test_why_has_no_default():
    """`--why` must not fabricate a rationale. Until 2026-09-07 it defaulted to
    the string "picked at the command line", which reached the ledger as a
    sealed rationale and — scoring 0.350 against a 0.34 floor, on the homonym
    `line` — was the one rationale in the system the engagement gate never
    flagged (docs/design/the-forge-engagement-defect.md §1)."""
    a = entry.build_parser().parse_args(["s", "--project", "p", "--builder", "b"])
    assert a.why is None, "--why must have no default"


def test_pick_responder_does_not_invent_a_rationale():
    """With no --why, the CLI responder seals an EMPTY rationale rather than
    argparse's help text."""
    r = entry._PickResponder(choose="web", why=None)
    d = Decision(decision_type=entry.DECISION_TYPE_MAJOR,
                 surface="could be web, mobile, desktop — which major?",
                 options=[checkpoint.Option("web", "a site"),
                          checkpoint.Option("mobile", "an app")])
    assert r.choose(d).rationale == ""


@_needs_nestor
def test_no_rationale_is_the_loudest_rubber_stamp(home):
    """A major WAS chosen (--choose web) but no reason was given. The choice is
    recorded honestly: an empty rationale scores 0.0 and flags, per
    checkpoint._engagement_fields' "the loudest rubber-stamp there is".

    Before the --why fix the same run scored 0.350 and graded `Good`, which
    pushed the review interval OUT — the engine's least-considered decision was
    also the one it re-asked least often.

    (This used to run with `choose=None`; that path now refuses outright — see
    `test_an_ambiguous_major_with_no_choice_refuses` — so the rubber-stamp
    property is asserted where it still applies: a real pick, no reason.)"""
    out = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                          responder=entry._PickResponder(choose="web", why=None),
                          root=home / "cp").decision_outcome
    assert out.band == "socratic" and out.rationale == ""
    assert out.engagement == 0.0
    assert out.rubber_stamp is True, "an unexplained choice must read as a rubber-stamp"


# ── gap 1: an ambiguous major with no choice must refuse ────────────────────
#
# the-positional-default.md's @prompt, verbatim: "a sentence with two or more
# majors and no `--choose`, run non-interactively. Assert that nothing reaches
# `checkpoint_memory` — not an unsealed row, not an attestation. A test that
# asserts the *right* major was chosen is testing the table, not this."

@_needs_nestor
def test_an_ambiguous_major_with_no_choice_refuses(home):
    with pytest.raises(entry.EntryError) as e:
        entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                        responder=entry._PickResponder(choose=None, why=None),
                        root=home / "cp")
    msg = str(e.value)
    assert "list position is not a decision" in msg
    assert "--choose" in msg, "a refusal must say how to proceed"
    assert not msg.startswith("REFUSED"), \
        "main() already prefixes REFUSED: — carrying it here too printed it twice"


@_needs_nestor
def test_the_refusal_writes_nothing_to_memory(home):
    """The half that matters. A refusal that still left a row behind would be
    the same failure wearing an error message."""
    root = home / "cp"
    with pytest.raises(entry.EntryError):
        entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                        responder=entry._PickResponder(choose=None, why=None),
                        root=root)
    with checkpoint_memory.open_checkpoint_memory(
            BUILDER, entry.DECISION_TYPE_MAJOR, root=root) as cm:
        assert cm.has_sealed() is False, "nothing may be sealed from a non-decision"
        assert cm.check(
            f"'{SENTENCE}' could be web, mobile, desktop — which major?"
        )["canonical"] is None, "not even an unsealed row"

    # ...and no attestation, which is the other thing @prompt names.
    from forge import human_loop, soil_store
    store = soil_store.FilesystemSoilStore(BUILDER, root=root)
    assert human_loop.list_attestations(store) == []


@_needs_nestor
def test_one_unambiguous_major_still_needs_no_choice(home):
    """The refusal is about ambiguity, not about --choose being mandatory. One
    option is not a decision the maker has to make."""
    e = entry.open_bite("a tiny cli that renames files", project_id=PROJECT,
                        builder_id=BUILDER,
                        responder=entry._PickResponder(choose=None, why=None),
                        root=home / "cp")
    assert e.major == "cli" and e.decision_outcome is None


@_needs_nestor
def test_the_old_default_would_have_escaped_the_flag(home):
    """The regression this fix exists to prevent, pinned as an executable fact:
    the retired default string clears the rubber-stamp floor. If a future change
    makes this pass as thin, the --why default was not the whole problem — and
    the engagement defect paper's §1 needs revisiting, not deleting."""
    from forge import checkpoint_engagement
    surface = "could be web, mobile, desktop — which major?"
    assert checkpoint_engagement.engagement_score("picked at the command line", surface) >= \
        checkpoint_engagement.RUBBER_STAMP_FLOOR


# ── gap 3: a sealed row whose signature nobody could check ──────────────────

@_needs_nestor
def test_the_entry_says_when_a_seal_could_not_be_verified(home, monkeypatch):
    """`is_verified_seal` degrades to a bare `status == 'sealed'` test when no
    key is configured — Nestor warns about it at runtime — and a builder id
    absent from the keyring is refused outright, so every real run of the entry
    is the unconfigured case. Reporting "sealed" without that qualification is
    how "nobody verified this" reads as "the box says yes"."""
    monkeypatch.setattr(entry.checkpoint_memory, "seal_signatures_verified", lambda: False)
    root = home / "cp"
    e1 = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                         responder=entry._PickResponder(choose="web", why=None), root=root)
    assert e1.decision_outcome.band == "socratic"

    e2 = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                         responder=ScriptedResponder(choose=None), root=root)
    assert e2.decision_outcome.matched_band is not None, "a prior seal answered"
    assert "SIGNATURE NOT VERIFIED" in e2.tiers["scan"]


@_needs_nestor
def test_a_verifiable_seal_carries_no_warning(home, monkeypatch):
    """The qualification must be a report, not a permanent decoration — with
    signing configured it disappears."""
    monkeypatch.setattr(entry.checkpoint_memory, "seal_signatures_verified", lambda: True)
    root = home / "cp"
    entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                    responder=entry._PickResponder(choose="web", why=None), root=root)
    e2 = entry.open_bite(SENTENCE, project_id=PROJECT, builder_id=BUILDER,
                         responder=ScriptedResponder(choose=None), root=root)
    assert "NOT VERIFIED" not in e2.tiers["scan"]


def test_seal_signatures_verified_never_raises():
    """A probe that cannot answer says "not verified" rather than exploding —
    the same fail-loud-not-open posture as the rest of this module."""
    assert isinstance(checkpoint_memory.seal_signatures_verified(), bool)
