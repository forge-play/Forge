"""demo/the_first_bite.py runs the loop it describes.

Runs the demo as a subprocess (`--json --pace off`, so the content is what a
person sees, silently) with the fleet keyring unset and FORGE_HOME sandboxed
by the demo itself, then reads the facts it emits beside the friction log.
Beats 1 and 11 must report no friction when Nestor is installed; without it
they must say so as MISSING, honestly, rather than crash.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from forge import checkpoint_memory

_REPO = Path(__file__).resolve().parents[1]
_DEMO = _REPO / "demo" / "the_first_bite.py"
_HAS_NESTOR = checkpoint_memory.nestor_available()


def _run() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("NESTOR_")}
    env["FORGE_HOME"] = ""  # the demo sets its own, inside the playground
    r = subprocess.run([sys.executable, str(_DEMO), "--json", "--pace", "off"],
                       capture_output=True, text=True, cwd=str(_REPO), env=env, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def log() -> dict:
    return _run()


def test_the_demo_still_emits_the_friction_log_shape(log):
    assert set(log) >= {"origin", "missing", "friction", "facts"}
    assert log["origin"] == "fixture:first-bite"
    for x in log["missing"] + log["friction"]:
        assert set(x) == {"beat", "kind", "what", "expected", "actual", "fix"}


@pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")
def test_beat_1_runs_the_entry_and_logs_no_friction(log):
    assert not [x for x in log["missing"] + log["friction"] if x["beat"] == 1], log["missing"]
    e = log["facts"]["entry"]
    assert e["major"] == "metadata tool" and e["band"] == "socratic"
    assert e["tiers"]["nestor"].startswith("pending")
    assert e["tiers"]["remote"].startswith("not_attempted")


@pytest.mark.skipif(not _HAS_NESTOR, reason="nestor not installed")
def test_beat_11_calls_the_ledger_with_ground_truth(log):
    assert not [x for x in log["missing"] + log["friction"] if x["beat"] == 11], log["missing"]
    c = log["facts"]["calibration"]
    assert c["claim"] == "where-the-dates-live: maker picks sidecar json"
    assert c["confidence"] == 0.8 and c["outcome"] is False
    assert c["resolved"] == 1 and c["hit_rate"] == 0.0
    assert c["sealed"] is True


@pytest.mark.skipif(_HAS_NESTOR, reason="only meaningful without nestor")
def test_without_nestor_the_entry_refuses_but_the_loop_still_learns(log):
    """Found by CI's no-extras leg (rudi193-cmd/Forge#18): the first cut of this test expected
    beat 11 to be MISSING too. It is not. The entry refuses without Nestor (a
    build that never asked cannot start), but the build loop runs run_checkpoint
    on its soft-Nestor path — full Socratic, decided UNSEALED — and the
    calibration ledger is a SOIL store that needs no Nestor at all. So the
    prediction is recorded and resolved either way; only the seal is missing.
    The project Nestor's own draft on the entry said as much: "run_checkpoint
    may run Socratic without memory because a fresh decision is still a decision."
    """
    missing = {x["beat"]: x["what"] for x in log["missing"]}
    assert 1 in missing and "Nestor" in missing[1], missing
    assert missing.get(11) == "the decision was made but not sealed", missing
    assert "refused" in log["facts"]["entry"]
    c = log["facts"]["calibration"]
    assert c["outcome"] is False and c["resolved"] == 1
    assert c["sealed"] is False, "without memory the decision is made, not sealed — and the demo must say so"


def test_the_demo_never_writes_outside_its_playground(tmp_path):
    """FORGE_HOME is set by the demo to a directory under its own tmp, which is
    removed on exit; a real ~/.forge must not gain a `rally-dates` project."""
    real = Path.home() / ".forge" / "projects" / "rally-dates"
    assert not real.exists(), f"the demo leaked into {real}"
