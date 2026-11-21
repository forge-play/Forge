"""forge/bl.py — the forks resolved through memory, and the calibration
ledger finally called from somewhere that is not its own tests.

Nestor-gated (the checkpoint router seals). The ScriptedResponder mirrors
tests/test_checkpoint.py's; `root` is a tmp checkpoint root that the ledger
shares.
"""

from __future__ import annotations

import json
import os
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


class DeferringResponder(ScriptedResponder):
    """ "I don't know, you choose", at every fork."""

    def choose(self, d):
        self.choose_calls.append(d)
        return ChoiceResult(deferred=True)


@_needs_nestor
def test_a_deferral_is_voided_not_scored_as_the_recommendation_picked(tmp_path):
    """The checkpoint takes the recommendation when the maker defers; scoring
    that as `chosen == recommended` was a hit the maker never made."""
    root = tmp_path / "cp"
    res = bl.resolve(
        ps.load(FIXTURE), builder_id=BUILDER, responder=DeferringResponder(), root=root
    )
    (o,) = res.outcomes
    assert o.deferred and res.chosen == {"where-the-dates-live": "sidecar json"}, (
        "the plan still gets the recommendation, as before"
    )
    (p,) = res.predictions
    assert p["outcome"] is None and p["void"] == bl.DEFERRED
    card = calibration_ledger.scorecard(BUILDER, root=root)
    assert card["resolved"] == 0 and card["void"] == 1 and card["pending"] == 0


def _blind_fixture() -> ps.PlanDoc:
    raw = json.loads(FIXTURE.read_text())
    raw["entries"][1]["blind"] = True
    return ps.validate(raw)


@_needs_nestor
def test_a_blind_fork_is_asked_without_its_recommendation_and_still_scored(tmp_path):
    root = tmp_path / "cp"
    r = ScriptedResponder({"where-the-dates-live": "sidecar json"})  # the hidden recommendation
    res = bl.resolve(_blind_fixture(), builder_id=BUILDER, responder=r, root=root)
    (asked,) = r.choose_calls
    assert asked.recommended is None, "the maker is never shown it"
    (p,) = res.predictions
    assert p["blind"] is True and p["outcome"] is True and p["confidence"] == 0.8
    card = calibration_ledger.scorecard(BUILDER, group_by="blind", root=root)
    assert card["resolved"] == 1 and list(card["groups"]) == ["True"]


@_needs_nestor
def test_a_deferral_on_a_blind_fork_cannot_fall_back_to_the_recommendation(tmp_path):
    root = tmp_path / "cp"
    plan = _blind_fixture()
    ((_, fork),) = plan.forks
    res = bl.resolve(plan, builder_id=BUILDER, responder=DeferringResponder(), root=root)
    assert res.chosen == {"where-the-dates-live": fork.shown[0].label}, (
        "the first option as asked, in the engine's order: not the proposer's pick by design"
    )
    (p,) = res.predictions
    assert p["outcome"] is None and p["void"] == bl.DEFERRED


@_needs_nestor
def test_in_view_and_blind_predictions_group_apart(tmp_path):
    root = tmp_path / "cp"
    bl.resolve(
        ps.load(FIXTURE),
        builder_id=BUILDER,
        responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}),
        root=root,
    )
    raw = json.loads(FIXTURE.read_text())
    raw["entries"][1].update(blind=True, decision_type="where-the-times-live")
    bl.resolve(
        ps.validate(raw),
        builder_id=BUILDER,
        responder=ScriptedResponder({"where-the-times-live": "exif in place"}),
        root=root,
    )
    groups = calibration_ledger.scorecard(BUILDER, group_by="blind", root=root)["groups"]
    assert groups["False"]["summary"]["hit_rate"] == 1.0, "in view: followed"
    assert groups["True"]["summary"]["hit_rate"] == 0.0, "blind: the proposer missed"


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


def _plan_with_one_fork(recommended=None, confidence=None, blind=False) -> ps.PlanDoc:
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
                    "blind": blind,
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


def test_a_fork_sealed_on_the_record_is_the_auto_band_and_nobody_is_asked(tmp_path):
    from tests.test_checkpoint_record import FakeRecord

    rec = FakeRecord(sealed={"willow-email": "mail"})
    responder = ScriptedResponder()
    res = bl.resolve(
        _plan_with_one_fork("mail", 0.8),
        builder_id=BUILDER,
        responder=responder,
        root=tmp_path,
        record=rec,
    )
    assert res.predictions == [], "their earlier seal agreeing with itself is no new pick"
    assert not any(tmp_path.iterdir()), "no ledger and no memory of the engine's own"
    assert res.chosen == {"willow-email": "mail"} and not responder.choose_calls
    assert len(responder.confirm_prompts) == 1 and "You sealed a" in responder.confirm_prompts[0]
    o = res.outcomes[0]
    assert o.band == "auto" and o.sealed and o.record.endswith(", confirmed")
    assert [e.dest_path for e in res.plan.entries] == ["steps/merkle.md", "steps/mail.md"]
    assert rec.proposed == []
    assert res.to_dict()["outcomes"][0]["record_subject"] == "proposal:" + "cd" * 32


def test_a_fresh_fork_is_proposed_with_its_prediction_on_the_same_row(tmp_path):
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
            "kept": {
                "kind": "fork",
                "offered": ["apple-mail", "mail"],
                "recommended": "mail",
                "confidence": 0.8,
                "blind": False,
                "rank": 1,
            },
        }
    ]
    assert res.outcomes[0].record.startswith("nothing sealed; proposed proposal:")
    assert res.outcomes[0].sealed is False
    assert res.predictions == [
        {
            "claim": "willow-email: maker picks mail",
            "confidence": 0.8,
            "blind": False,
            "on_record": "proposal:" + "ef" * 32,
        }
    ], "no outcome here: the row is scored once the person seals it"
    assert not any(tmp_path.iterdir()), "nothing went to a ledger of the engine's own"
    assert calibration_ledger.scorecard(BUILDER, root=tmp_path)["resolved"] == 0


def test_a_blind_fork_keeps_the_order_shown_and_the_recommendation_unsaid(tmp_path):
    from tests.test_checkpoint_record import FakeRecord

    rec = FakeRecord()
    plan = _plan_with_one_fork("mail", 0.7, blind=True)
    responder = ScriptedResponder({"willow-email": "mail"})
    res = bl.resolve(plan, builder_id=BUILDER, responder=responder, root=tmp_path, record=rec)
    asked = responder.choose_calls[0]
    assert asked.recommended is None, "blind: the maker was shown no recommendation"
    kept = rec.proposed[0]["kept"]
    assert kept["blind"] is True and kept["recommended"] is None
    assert kept["proposer_first"] == "mail" and kept["confidence"] == 0.7
    assert kept["offered"] == ["apple-mail", "mail"], "the proposer's order, as it wrote it"
    assert kept["shown"] == [o.label for o in asked.options], "and the order the maker saw"
    assert kept["rank"] == 2, "where the pick fell in the proposer's order"
    assert res.predictions[0]["blind"] is True


def test_a_fork_with_no_confidence_is_proposed_and_predicts_nothing(tmp_path):
    from tests.test_checkpoint_record import FakeRecord

    rec = FakeRecord()
    res = bl.resolve(
        _plan_with_one_fork(),
        builder_id=BUILDER,
        responder=ScriptedResponder({"willow-email": "mail"}),
        root=tmp_path,
        record=rec,
    )
    assert res.predictions == [], "a suggestion, not a claim: nothing to score"
    kept = rec.proposed[0]["kept"]
    assert kept["recommended"] is None and kept["confidence"] is None and kept["rank"] == 2


def test_a_deferral_on_the_record_is_kept_and_voided(tmp_path):
    from tests.test_checkpoint_record import FakeRecord

    class Defers(ScriptedResponder):
        def choose(self, d):
            self.choose_calls.append(d)
            return ChoiceResult(deferred=True)

    rec = FakeRecord()
    res = bl.resolve(
        _plan_with_one_fork("mail", 0.8),
        builder_id=BUILDER,
        responder=Defers(),
        root=tmp_path,
        record=rec,
    )
    assert res.chosen == {"willow-email": "mail"}, "handed back, so the recommendation is taken"
    assert rec.proposed[0]["kept"]["deferred"] is True
    assert res.predictions[0]["void"] == bl.DEFERRED, "taking it for them is not them picking it"


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
    assert "record: 1 proposed, waiting on your seal" in out.out and "scorecard" not in out.out
    assert not (tmp_path / "cp").exists(), "no store of the engine's own was opened"
    prop = json.loads((box / "proposed.jsonl").read_text(encoding="utf-8").splitlines()[0])
    data = json.loads(prop["data"])
    assert data["chose"] == "mail" and prop["claim"].endswith("mbox is what I have")
    assert data["offered"] == ["apple-mail", "mail"] and data["rank"] == 2
    assert data["word"] == "willow-email", "what rides with the pick replaces no field of its own"
    assert (box / "asked.log").read_text(encoding="utf-8").splitlines() == [
        "forge decision willow-email"
    ] * 2, "asked once for a seal, once by propose before the door; both are rows"


def test_cli_refuses_a_willow_without_a_box(tmp_path, capsys):
    f = tmp_path / "plan.json"
    f.write_text(json.dumps(_plan_with_one_fork().to_dict()))
    assert bl.main([str(f), "--builder", BUILDER, "--willow", str(tmp_path)]) == 2
    assert "--willow and --box go together" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("WILLOW_KERNEL"), reason="WILLOW_KERNEL names no kernel.py")
def test_against_a_real_kernel_the_loop_closes_on_one_record(tmp_path):
    """Asked, proposed with what was shown, sealed with the key, and the next
    build is the confirm: one record, and nothing of the engine's own."""
    import subprocess
    import sys

    from forge.willow_record import WillowRecord

    kernel = os.environ["WILLOW_KERNEL"]
    pile = tmp_path / "pile"
    pile.mkdir()
    (pile / "a.txt").write_text("nothing about email here\n")
    box, key, root = tmp_path / "box", tmp_path / "k.key", tmp_path / "cp"
    init = [sys.executable, kernel, "init", "--box", str(box), "--pile", str(pile), "--key", str(key)]  # fmt: skip
    assert subprocess.run(init, capture_output=True, check=False).returncode == 0
    rec = WillowRecord(Path(kernel), box)
    plan = _plan_with_one_fork("mail", 0.8)

    first = bl.resolve(
        plan,
        builder_id=BUILDER,
        responder=ScriptedResponder({"willow-email": "apple-mail"}),
        root=root,
        record=rec,
    )
    subject = first.predictions[0]["on_record"]
    row = json.loads(json.loads((box / "proposals" / (subject[9:] + ".json")).read_text())["data"])
    assert row["chose"] == "apple-mail" and row["offered"] == ["apple-mail", "mail"]
    assert (row["recommended"], row["confidence"], row["rank"]) == ("mail", 0.8, 1)

    seal = [sys.executable, kernel, "seal", "--box", str(box), subject]
    assert subprocess.run(seal, capture_output=True, check=False).returncode == 0
    again = ScriptedResponder()
    second = bl.resolve(plan, builder_id=BUILDER, responder=again, root=root, record=rec)
    assert second.outcomes[0].band == "auto" and second.chosen == {"willow-email": "apple-mail"}
    assert not again.choose_calls and second.predictions == []
    assert not root.exists(), "no store of the engine's own, before the seal or after"
