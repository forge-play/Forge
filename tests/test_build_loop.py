"""forge/bl.py — the forks resolved through memory, and the calibration
ledger finally called from somewhere that is not its own tests.

Nestor-gated (the checkpoint router seals). The ScriptedResponder mirrors
tests/test_checkpoint.py's; `root` is a tmp checkpoint root that the ledger
shares.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge import build_loop as bl
from forge import calibration_ledger, checkpoint_memory
from forge import plan_shape as ps
from forge.checkpoint import ChoiceResult, Decision, Option

_needs_nestor = pytest.mark.skipif(
    not checkpoint_memory.nestor_available(), reason="nestor not installed"
)

FIXTURE = Path(__file__).resolve().parents[1] / "demo" / "fixtures" / "fork_plan.json"
BUILDER = "c" * 32


class ScriptedResponder:
    def __init__(self, picks: dict[str, str] | None = None):
        self._picks = picks or {}
        self.choose_calls: list[Decision] = []
        self.confirm_prompts: list[str] = []

    def confirm(self, prompt):
        self.confirm_prompts.append(prompt)
        return True

    def choose(self, d):
        self.choose_calls.append(d)
        label = self._picks[d.decision_type]
        return ChoiceResult(
            chosen_label=label,
            rationale="the originals must never change; the club has been burned before",
        )


def test_label_from_chosen_reads_both_shapes_and_refuses_the_rest():
    labels = ["sidecar json", "exif in place", "exif"]
    assert bl.label_from_chosen("sidecar json", labels) == "sidecar json"
    assert bl.label_from_chosen("exif in place: the originals travel", labels) == "exif in place"
    assert bl.label_from_chosen("exif: short", labels) == "exif"
    assert bl.label_from_chosen("something else entirely", labels) is None


def test_a_refused_extraction_cannot_be_resolved(tmp_path):
    plan = ps.validate(
        {
            "app_name": "x",
            "entries": [
                {
                    "kind": "fork",
                    "decision_type": "one",
                    "surface": "?",
                    "options": [{"label": "only"}],
                }
            ],
        }
    )
    with pytest.raises(bl.BuildLoopError) as e:
        bl.resolve(plan, builder_id=BUILDER, responder=ScriptedResponder(), root=tmp_path / "cp")
    assert "at least two" in str(e.value)


@_needs_nestor
def test_the_stub_plan_resolves_to_itself_with_no_asks(tmp_path):
    plan = ps.validate(
        {
            "app_name": "hello",
            "entries": [{"kind": "file_write", "dest_path": "README.md", "content": "# hello\n"}],
        }
    )
    r = ScriptedResponder()
    res = bl.resolve(plan, builder_id=BUILDER, responder=r, root=tmp_path / "cp")
    assert res.plan == plan and res.outcomes == [] and res.predictions == []
    assert r.choose_calls == [] and r.confirm_prompts == []


@_needs_nestor
def test_a_fork_is_asked_answered_substituted_and_the_prediction_settled(tmp_path):
    root = tmp_path / "cp"
    plan = ps.load(FIXTURE)
    r = ScriptedResponder({"where-the-dates-live": "exif in place"})  # NOT the recommended
    res = bl.resolve(plan, builder_id=BUILDER, responder=r, root=root)

    assert len(r.choose_calls) == 1
    (o,) = res.outcomes
    assert o.band == "socratic" and o.sealed
    assert res.chosen == {"where-the-dates-live": "exif in place"}

    # substituted: the fork is gone, its chosen branch is in its place, order kept
    kinds = [type(e).__name__ for e in res.plan.entries]
    assert kinds == ["FileWrite", "FileWrite", "FileWrite"] and not res.plan.has_forks
    assert res.plan.entries[1].dest_path == "dates.py" and "EXIF" in res.plan.entries[1].content

    # the calibration wire: recorded before, resolved after, against the maker's pick
    (p,) = res.predictions
    assert p["claim"] == "where-the-dates-live: maker picks sidecar json" and p["confidence"] == 0.8
    assert p["outcome"] is False, "the proposer said sidecar at 0.8; the maker picked exif"
    card = calibration_ledger.scorecard(BUILDER, root=root)
    assert card["resolved"] == 1 and card["pending"] == 0
    assert card["summary"]["hit_rate"] == 0.0


@_needs_nestor
def test_second_run_confirms_without_asking_and_does_not_reopen_the_prediction(tmp_path):
    root = tmp_path / "cp"
    plan = ps.load(FIXTURE)
    bl.resolve(
        plan,
        builder_id=BUILDER,
        responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}),
        root=root,
    )

    r2 = ScriptedResponder()  # would KeyError if asked to choose
    res2 = bl.resolve(plan, builder_id=BUILDER, responder=r2, root=root)
    assert r2.choose_calls == [] and r2.confirm_prompts, "confirmed, not re-asked"
    assert res2.outcomes[0].band in ("auto", "recognize")
    assert res2.chosen["where-the-dates-live"] == "sidecar json"
    assert res2.plan.entries[1].content.startswith("# writes <picture>.json")
    (p,) = res2.predictions
    assert p.get("already_settled") is True, "a settled prediction is history"
    assert calibration_ledger.scorecard(BUILDER, root=root)["resolved"] == 1


@_needs_nestor
def test_picking_the_recommendation_resolves_true(tmp_path):
    root = tmp_path / "cp"
    res = bl.resolve(
        ps.load(FIXTURE),
        builder_id=BUILDER,
        responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}),
        root=root,
    )
    assert res.predictions[0]["outcome"] is True
    assert calibration_ledger.scorecard(BUILDER, root=root)["summary"]["hit_rate"] == 1.0


@_needs_nestor
def test_a_fork_without_confidence_records_nothing(tmp_path):
    root = tmp_path / "cp"
    raw = json.loads(FIXTURE.read_text())
    raw["entries"][1]["confidence"] = None
    res = bl.resolve(
        ps.validate(raw),
        builder_id=BUILDER,
        responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}),
        root=root,
    )
    assert res.predictions == []
    assert calibration_ledger.scorecard(BUILDER, root=root)["resolved"] == 0


@_needs_nestor
def test_conflicting_writes_keep_the_chosen_entry(tmp_path):
    plan = ps.validate(
        {
            "app_name": "demo",
            "entries": [
                {"kind": "file_write", "dest_path": "app.py", "content": "print('a')\n"},
                {"kind": "file_write", "dest_path": "app.py", "content": "print('b')\n"},
            ],
        }
    )
    res = bl.resolve(
        plan,
        builder_id=BUILDER,
        responder=ScriptedResponder({"conflicting-write": "entry 1"}),
        root=tmp_path / "cp",
    )
    assert [e.content for e in res.plan.entries] == ["print('b')\n"]


@_needs_nestor
def test_cli_resolves_and_prints_a_scorecard(tmp_path, capsys):
    root = str(tmp_path / "cp")
    rc = bl.main(
        [
            str(FIXTURE),
            "--builder",
            BUILDER,
            "--root",
            root,
            "--choose",
            "where-the-dates-live=exif in place",
            "--json",
        ]
    )
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["chosen"] == {"where-the-dates-live": "exif in place"}
    assert d["scorecard"]["resolved"] == 1 and d["predictions"][0]["outcome"] is False
    assert all(e["kind"] == "file_write" for e in d["plan"]["entries"])


# ── the positional default, refused on this side too ────────────────────────


def test_a_fork_with_no_choose_refuses_rather_than_taking_index_zero():
    """build_loop's CLI responder had the same `or d.options[0].label` the
    entry's did (docs/design/the-positional-default.md). A fork is a decision by
    construction — resolving one by list position and sealing it is the exact
    failure the paper names."""
    r = bl._PickResponder(picks={}, why=None)
    d = Decision(
        decision_type="where-the-dates-live",
        surface="When a picture gets a date, where does the date go?",
        options=[
            Option("sidecar json", "the pictures stay untouched"),
            Option("exif in place", "the date travels with the picture"),
        ],
    )
    with pytest.raises(bl.BuildLoopError) as e:
        r.choose(d)
    assert "list position is not a decision" in str(e.value)
    assert "--choose 'where-the-dates-live=sidecar json'" in str(e.value), (
        "a refusal must say how to proceed"
    )


def test_a_named_pick_is_honoured():
    r = bl._PickResponder(picks={"where-the-dates-live": "exif in place"}, why=None)
    d = Decision(
        decision_type="where-the-dates-live",
        surface="where?",
        options=[Option("sidecar json", "a"), Option("exif in place", "b")],
    )
    assert r.choose(d).chosen_label == "exif in place"


def test_a_single_option_needs_no_pick():
    """The refusal is about ambiguity, not about --choose being mandatory."""
    r = bl._PickResponder(picks={}, why=None)
    d = Decision(decision_type="t", surface="s", options=[Option("only", "the one option")])
    assert r.choose(d).chosen_label == "only"


# ── the record wired in (the-join.md, thread 3; bite 5) ──────────────────────


def _plan_with_one_fork(recommended=None, confidence=None) -> ps.PlanDoc:
    return ps.validate(
        {
            "app_name": "willow-stack",
            "entries": [
                {
                    "kind": "file_write",
                    "dest_path": "steps/merkle.md",
                    "content": "- merkle -- --box {box}\n",
                },
                {
                    "kind": "fork",
                    "decision_type": "willow-email",
                    "surface": "“email” could be apple-mail, mail: which add-on?",
                    "options": [
                        {"label": "apple-mail", "tradeoff": "Apple Mail's .emlx"},
                        {"label": "mail", "tradeoff": ".eml and mbox"},
                    ],
                    "recommended": recommended,
                    "confidence": confidence,
                    "resolves": {
                        "apple-mail": [
                            {
                                "kind": "file_write",
                                "dest_path": "steps/apple-mail.md",
                                "content": "- apple-mail -- --box {box}\n",
                            }
                        ],
                        "mail": [
                            {
                                "kind": "file_write",
                                "dest_path": "steps/mail.md",
                                "content": "- mail -- --box {box}\n",
                            }
                        ],
                    },
                },
            ],
        }
    )


@_needs_nestor
def test_a_fork_sealed_on_the_record_is_the_auto_band_and_nobody_is_asked(tmp_path):
    from tests.test_checkpoint_record import FakeRecord

    rec = FakeRecord(sealed={"willow-email": "mail"})
    responder = ScriptedResponder()
    res = bl.resolve(
        _plan_with_one_fork(), builder_id=BUILDER, responder=responder, root=tmp_path, record=rec
    )
    assert res.chosen == {"willow-email": "mail"} and not responder.choose_calls
    assert len(responder.confirm_prompts) == 1 and "You sealed a" in responder.confirm_prompts[0]
    o = res.outcomes[0]
    assert o.band == "auto" and o.sealed and o.record.endswith(", confirmed")
    assert [e.dest_path for e in res.plan.entries] == ["steps/merkle.md", "steps/mail.md"]
    assert rec.proposed == []
    assert res.to_dict()["outcomes"][0]["record_subject"] == "proposal:" + "cd" * 32


@_needs_nestor
def test_a_fresh_fork_is_answered_and_proposed_onto_the_record(tmp_path):
    from tests.test_checkpoint_record import FakeRecord

    rec = FakeRecord()
    res = bl.resolve(
        _plan_with_one_fork("mail", 0.8),
        builder_id=BUILDER,
        responder=ScriptedResponder({"willow-email": "apple-mail"}),
        root=tmp_path,
        record=rec,
    )
    assert res.chosen == {"willow-email": "apple-mail"}
    assert rec.proposed == [
        {
            "dt": "willow-email",
            "chosen": "apple-mail",
            "over": ["mail"],
            "why": "the originals must never change; the club has been burned before",
            "surface": "“email” could be apple-mail, mail: which add-on?",
        }
    ]
    assert res.outcomes[0].record.startswith("nothing sealed; proposed proposal:")
    assert res.predictions[0]["outcome"] is False, "the maker did not pick the recommendation"


def test_the_plan_file_may_be_willows_suggest_envelope(tmp_path):
    plan = _plan_with_one_fork()
    f = tmp_path / "suggest.json"
    f.write_text(
        json.dumps(
            {"cards": {"built": 1, "ideas": 0}, "steps": [], "forks": {}, "plan": plan.to_dict()}
        )
    )
    assert bl.load_plan(f).to_dict() == plan.to_dict()
    g = tmp_path / "nothing.json"
    g.write_text(json.dumps({"cards": {}, "steps": [], "forks": {}, "plan": None}))
    with pytest.raises(ps.PlanShapeError, match="holds no plan"):
        bl.load_plan(g)
    h = tmp_path / "bare.json"
    h.write_text(json.dumps(plan.to_dict()))
    assert bl.load_plan(h).to_dict() == plan.to_dict()


@_needs_nestor
def test_cli_with_a_willow_and_a_box_asks_the_record_and_proposes_to_it(tmp_path, capsys):
    from tests.test_willow_record import FAKE

    willow = tmp_path / "Willow"
    willow.mkdir()
    (willow / "kernel.py").write_text(FAKE)
    box = tmp_path / "box"
    box.mkdir()
    (box / "kernel.json").write_text("{}")
    (box / "answers.json").write_text("{}")
    f = tmp_path / "plan.json"
    f.write_text(json.dumps(_plan_with_one_fork().to_dict()))
    rc = bl.main(
        [
            str(f),
            "--builder",
            BUILDER,
            "--root",
            str(tmp_path / "cp"),
            "--choose",
            "willow-email=mail",
            "--why",
            "mbox is what I have",
            "--willow",
            str(willow),
            "--box",
            str(box),
        ]
    )
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert (
        "willow-email             band socratic  → mail  record: nothing sealed; proposed proposal:"
        in out.out
    )
    prop = json.loads((box / "proposed.jsonl").read_text().splitlines()[0])
    assert json.loads(prop["data"])["chose"] == "mail" and prop["claim"].endswith(
        "mbox is what I have"
    )
    assert (box / "asked.log").read_text().splitlines() == ["forge decision willow-email"] * 2, (
        "asked once for a seal, once by propose before the door; both are rows"
    )


def test_cli_refuses_a_willow_without_a_box(tmp_path, capsys):
    f = tmp_path / "plan.json"
    f.write_text(json.dumps(_plan_with_one_fork().to_dict()))
    assert bl.main([str(f), "--builder", BUILDER, "--willow", str(tmp_path)]) == 2
    assert "--willow and --box go together" in capsys.readouterr().err
