"""forge/build_loop.py — the forks resolved through memory, and the calibration
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
from forge.checkpoint import ChoiceResult, Decision

_needs_nestor = pytest.mark.skipif(not checkpoint_memory.nestor_available(), reason="nestor not installed")

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
        return ChoiceResult(chosen_label=label, rationale="the originals must never change; the club has been burned before")


def test_label_from_chosen_reads_both_shapes_and_refuses_the_rest():
    labels = ["sidecar json", "exif in place", "exif"]
    assert bl.label_from_chosen("sidecar json", labels) == "sidecar json"
    assert bl.label_from_chosen("exif in place: the originals travel", labels) == "exif in place"
    assert bl.label_from_chosen("exif: short", labels) == "exif"
    assert bl.label_from_chosen("something else entirely", labels) is None


def test_a_refused_extraction_cannot_be_resolved(tmp_path):
    plan = ps.validate({"app_name": "x", "entries": [{
        "kind": "fork", "decision_type": "one", "surface": "?", "options": [{"label": "only"}]}]})
    with pytest.raises(bl.BuildLoopError) as e:
        bl.resolve(plan, builder_id=BUILDER, responder=ScriptedResponder(), root=tmp_path / "cp")
    assert "at least two" in str(e.value)


@_needs_nestor
def test_the_stub_plan_resolves_to_itself_with_no_asks(tmp_path):
    plan = ps.validate({"app_name": "hello", "entries": [
        {"kind": "file_write", "dest_path": "README.md", "content": "# hello\n"}]})
    r = ScriptedResponder()
    res = bl.resolve(plan, builder_id=BUILDER, responder=r, root=tmp_path / "cp")
    assert res.plan == plan and res.outcomes == [] and res.predictions == []
    assert r.choose_calls == [] and r.confirm_prompts == []


@_needs_nestor
def test_a_fork_is_asked_answered_substituted_and_the_prediction_settled(tmp_path):
    root = tmp_path / "cp"
    plan = ps.load(FIXTURE)
    r = ScriptedResponder({"where-the-dates-live": "exif in place"})   # NOT the recommended
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
    bl.resolve(plan, builder_id=BUILDER, responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}), root=root)

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
    res = bl.resolve(ps.load(FIXTURE), builder_id=BUILDER,
                     responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}), root=root)
    assert res.predictions[0]["outcome"] is True
    assert calibration_ledger.scorecard(BUILDER, root=root)["summary"]["hit_rate"] == 1.0


@_needs_nestor
def test_a_fork_without_confidence_records_nothing(tmp_path):
    root = tmp_path / "cp"
    raw = json.loads(FIXTURE.read_text())
    raw["entries"][1]["confidence"] = None
    res = bl.resolve(ps.validate(raw), builder_id=BUILDER,
                     responder=ScriptedResponder({"where-the-dates-live": "sidecar json"}), root=root)
    assert res.predictions == []
    assert calibration_ledger.scorecard(BUILDER, root=root)["resolved"] == 0


@_needs_nestor
def test_conflicting_writes_keep_the_chosen_entry(tmp_path):
    plan = ps.validate({"app_name": "demo", "entries": [
        {"kind": "file_write", "dest_path": "app.py", "content": "print('a')\n"},
        {"kind": "file_write", "dest_path": "app.py", "content": "print('b')\n"},
    ]})
    res = bl.resolve(plan, builder_id=BUILDER, responder=ScriptedResponder({"conflicting-write": "entry 1"}),
                     root=tmp_path / "cp")
    assert [e.content for e in res.plan.entries] == ["print('b')\n"]


@_needs_nestor
def test_cli_resolves_and_prints_a_scorecard(tmp_path, capsys):
    root = str(tmp_path / "cp")
    rc = bl.main([str(FIXTURE), "--builder", BUILDER, "--root", root,
                  "--choose", "where-the-dates-live=exif in place", "--json"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["chosen"] == {"where-the-dates-live": "exif in place"}
    assert d["scorecard"]["resolved"] == 1 and d["predictions"][0]["outcome"] is False
    assert all(e["kind"] == "file_write" for e in d["plan"]["entries"])
