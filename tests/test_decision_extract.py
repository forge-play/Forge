"""forge/plan_shape.py + forge/decision_extract.py — noticing that a decision
is being made, by rule, over the plan's structure. No Nestor needed."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge import decision_extract as dx
from forge import plan_shape as ps

FIXTURE = Path(__file__).resolve().parents[1] / "demo" / "fixtures" / "fork_plan.json"

# The host's stub plan, exactly as apps/the-forge's hello_world_command emits it.
STUB_PLAN = {
    "app_name": "hello",
    "entries": [
        {"kind": "file_write", "dest_path": "README.md", "content": "# hello\n"},
        {"kind": "file_write", "dest_path": "app.py", "content": "print('hello from hello')", "executable": False},
    ],
}


def _fork(**over):
    f = {
        "kind": "fork", "decision_type": "auth-flow", "surface": "how do users sign in?",
        "options": [{"label": "session cookie", "tradeoff": "server state"},
                    {"label": "jwt", "tradeoff": "revocation is on you"}],
        "recommended": "session cookie", "confidence": 0.7,
        "resolves": {"session cookie": [{"kind": "file_write", "dest_path": "auth.py", "content": "# cookie\n"}],
                     "jwt": [{"kind": "file_write", "dest_path": "auth.py", "content": "# jwt\n"}]},
    }
    f.update(over)
    return f


def _plan(*entries):
    return {"app_name": "demo", "entries": list(entries)}


# ── plan_shape ───────────────────────────────────────────────────────────────

def test_the_hosts_stub_plan_is_a_valid_plan_with_no_forks():
    doc = ps.validate(STUB_PLAN)
    assert not doc.has_forks and len(doc.entries) == 2
    assert doc.to_dict()["entries"][0]["kind"] == "file_write"


def test_the_fixture_loads_and_round_trips():
    doc = ps.load(FIXTURE)
    assert [type(e).__name__ for e in doc.entries] == ["FileWrite", "Fork", "FileWrite"]
    assert ps.validate(doc.to_dict()) == doc


@pytest.mark.parametrize("bad,why", [
    ({"app_name": "../x", "entries": [STUB_PLAN["entries"][0]]}, "charset"),
    ({"app_name": "demo", "entries": []}, "no entries"),
    (_plan({"kind": "mystery"}), "unknown kind"),
    (_plan({"kind": "file_write", "content": "x"}), "dest_path"),
    (_plan(_fork(resolves={"jwt": [{"kind": "fork"}]})), "file_write"),
    ("not a plan", "object"),
])
def test_not_a_plan_is_refused(bad, why):
    with pytest.raises(ps.PlanShapeError) as e:
        ps.validate(bad)
    assert why in str(e.value)


def test_a_bad_fork_is_parsed_and_carries_its_problems():
    doc = ps.validate(_plan(_fork(options=[{"label": "only one"}], decision_type="has space",
                                  confidence=0.3, recommended="nope")))
    (_, fork), = doc.forks
    problems = fork.problems()
    assert any("option" in p for p in problems)
    assert any("decision_type" in p for p in problems)
    assert any("recommended" in p for p in problems)


def test_confidence_without_a_recommendation_is_a_problem():
    doc = ps.validate(_plan(_fork(recommended=None)))
    (_, fork), = doc.forks
    assert any("confidence in nothing" in p for p in fork.problems())


# ── decision_extract ─────────────────────────────────────────────────────────

def test_the_stub_plan_extracts_to_nothing_and_says_so():
    ex = dx.extract(ps.validate(STUB_PLAN))
    assert ex.items == [] and ex.refused == []
    assert ex.nothing_to_decide is True
    assert ex.to_dict()["nothing_to_decide"] is True


def test_a_fork_becomes_one_decision_in_plan_order():
    ex = dx.extract(ps.load(FIXTURE))
    assert len(ex.items) == 1 and ex.refused == []
    x = ex.items[0]
    assert x.origin == dx.ORIGIN_FORK and x.index == 1
    assert x.decision.decision_type == "where-the-dates-live"
    assert [o.label for o in x.decision.options] == ["sidecar json", "exif in place"]
    assert x.decision.recommended == "sidecar json" and x.confidence == 0.8


def test_two_forks_extract_in_order():
    ex = dx.extract(ps.validate(_plan(_fork(decision_type="first"), STUB_PLAN["entries"][0],
                                      _fork(decision_type="second"))))
    assert [x.decision.decision_type for x in ex.items] == ["first", "second"]
    assert [x.index for x in ex.items] == [0, 2]


def test_a_malformed_fork_is_refused_with_its_reason_not_dropped():
    ex = dx.extract(ps.validate(_plan(_fork(options=[{"label": "only one"}]))))
    assert ex.items == []
    assert len(ex.refused) == 1 and ex.refused[0].index == 0
    assert "at least two" in ex.refused[0].reason
    assert ex.nothing_to_decide is False, "a refusal is not 'nothing to decide'"


def test_conflicting_writes_become_a_decision():
    ex = dx.extract(ps.validate(_plan(
        {"kind": "file_write", "dest_path": "app.py", "content": "print('a')\n"},
        {"kind": "file_write", "dest_path": "README.md", "content": "# fine\n"},
        {"kind": "file_write", "dest_path": "app.py", "content": "print('b')\n"},
    )))
    assert len(ex.items) == 1
    x = ex.items[0]
    assert x.origin == dx.ORIGIN_CONFLICT and x.indices == (0, 2)
    assert x.decision.decision_type == dx.DECISION_TYPE_CONFLICT
    assert [o.label for o in x.decision.options] == ["entry 0", "entry 2"]
    assert "print('a')" in x.decision.options[0].tradeoff


class _Hit:
    def __init__(self, target, reason):
        self.target, self.reason = target, reason


class _Entry:
    sentence = "I got sum kol sites for app to spin"
    majors = {"web": ["site", "app"], "mobile": ["app"], "desktop": ["app"]}
    hits = [_Hit("web", "served"), _Hit("mobile", "an APK"), _Hit("desktop", "runs where you sit")]
    decision_outcome = None


def test_the_entrys_open_ambiguity_is_passed_through_as_r1():
    ex = dx.extract(ps.validate(STUB_PLAN), entry=_Entry())
    assert len(ex.items) == 1
    x = ex.items[0]
    assert x.origin == dx.ORIGIN_ENTRY and x.decision.decision_type == "major"
    assert [o.label for o in x.decision.options] == ["web", "mobile", "desktop"]
    assert x.decision.options[1].tradeoff == "an APK"


def test_an_entry_whose_major_was_already_decided_adds_nothing():
    e = _Entry()
    e.decision_outcome = object()
    assert dx.extract(ps.validate(STUB_PLAN), entry=e).nothing_to_decide


def test_cli_prints_the_extraction(capsys, tmp_path):
    p = tmp_path / "plan.json"
    p.write_text(json.dumps(STUB_PLAN))
    import subprocess, sys
    r = subprocess.run([sys.executable, "-m", "forge.decision_extract", str(p)], capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parents[1]))
    assert r.returncode == 0 and json.loads(r.stdout)["nothing_to_decide"] is True
