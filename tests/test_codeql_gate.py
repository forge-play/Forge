"""tools/codeql_gate.py — the gate half of .github/workflows/codeql.yml, built
on 2026-09-12 when the workflow's first run showed the repository has CodeQL
default setup enabled and GitHub refusing a workflow's SARIF upload because of
it. The workflow now analyzes with `upload: never` and this script reads the
SARIF it wrote; so the script is the thing that makes the check a gate, and a
gate that has never been shown to fail has not been shown to gate. Every
refusal is planted here against a sandbox SARIF: a result, a result whose
level comes from its rule, two runs, a missing file, a file that is not
SARIF, and a SARIF that analyzed nothing. The wiring — that the workflow
really runs this script after the analysis — is held in
tests/test_release_wiring.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_TOOL = _REPO / "tools" / "codeql_gate.py"
sys.path.insert(0, str(_REPO / "tools"))

import codeql_gate as cg  # noqa: E402  (tools/ is not a package)


def _result(rule: str, uri: str, line: int, text: str, level: str | None = "error") -> dict:
    res = {
        "ruleId": rule,
        "message": {"text": text},
        "locations": [
            {"physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": line}}}
        ],
    }
    if level is not None:
        res["level"] = level
    return res


def _sarif(*runs: list[dict], rules: list[dict] | None = None) -> dict:
    return {
        "version": "2.1.0",
        "runs": [
            {"tool": {"driver": {"name": "CodeQL", "rules": rules or []}}, "results": results}
            for results in runs
        ],
    }


def _write(tmp_path: Path, payload, name: str = "python.sarif") -> Path:
    p = tmp_path / name
    p.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
    return p


# ── clean ────────────────────────────────────────────────────────────────────


def test_a_sarif_with_no_results_is_clean(tmp_path):
    assert cg.problems(_write(tmp_path, _sarif([]))) == []


# ── the plants: the gate must be able to fail ────────────────────────────────


def test_a_planted_result_fires_naming_file_line_rule_level_and_message(tmp_path):
    sarif = _sarif(
        [_result("py/sql-injection", "forge/entry.py", 42, "This query depends on\nuser input.")]
    )
    (line,) = cg.problems(_write(tmp_path, sarif))
    assert line == "forge/entry.py:42: py/sql-injection (error): This query depends on", line


def test_a_planted_result_without_its_own_level_takes_the_rules_default(tmp_path):
    """CodeQL leaves `level` off a result when the rule's defaultConfiguration
    carries it; a gate that read only the result would print nothing useful.
    And a result with neither is SARIF's default, `warning`, not a crash."""
    rules = [{"id": "py/clear-text-logging", "defaultConfiguration": {"level": "warning"}}]
    sarif = _sarif(
        [
            _result("py/clear-text-logging", "forge/a.py", 1, "logged", level=None),
            _result("py/unknown", "forge/b.py", 2, "no rule entry", level=None),
        ],
        rules=rules,
    )
    got = cg.problems(_write(tmp_path, sarif))
    assert got == [
        "forge/a.py:1: py/clear-text-logging (warning): logged",
        "forge/b.py:2: py/unknown (warning): no rule entry",
    ], got


def test_planted_results_in_two_runs_are_both_reported(tmp_path):
    sarif = _sarif(
        [_result("actions/missing-permissions", ".github/workflows/x.yml", 3, "no permissions")],
        [_result("py/x", "tools/y.py", 9, "y")],
    )
    got = cg.problems(_write(tmp_path, sarif))
    assert (
        len(got) == 2
        and got[0].startswith(".github/workflows/x.yml:3")
        and got[1].startswith("tools/y.py:9")
    ), got


def test_a_planted_result_with_no_location_still_fires(tmp_path):
    sarif = _sarif([{"ruleId": "py/nowhere", "message": {"text": "m"}, "level": "note"}])
    assert cg.problems(_write(tmp_path, sarif)) == ["<no location>: py/nowhere (note): m"]


def test_a_missing_sarif_fires(tmp_path):
    """Planted: the analyze step wrote nothing. An absent file must not read
    as 'no findings' — it is the loudest way an analysis can have not run."""
    (line,) = cg.problems(tmp_path / "python.sarif")
    assert "no SARIF file was written" in line and "python.sarif" in line, line


def test_a_file_that_is_not_sarif_fires(tmp_path):
    (line,) = cg.problems(_write(tmp_path, "{not json"))
    assert "not readable as SARIF" in line, line


def test_a_sarif_that_analyzed_nothing_fires(tmp_path):
    """Planted: valid JSON, no runs. A SARIF with nothing in it is not a clean
    analysis, it is no analysis."""
    (line,) = cg.problems(_write(tmp_path, {"version": "2.1.0", "runs": []}))
    assert "no runs" in line, line
    (line,) = cg.problems(_write(tmp_path, [], name="list.sarif"))
    assert "no runs" in line, line


def test_the_plants_exercise_the_same_reader_the_cli_runs():
    """`main` reads through `problems`; the plants above call `problems`. Pin
    that so a refactor cannot leave the CLI on one reader and the plants on
    another."""
    assert "problems" in cg.main.__code__.co_names


# ── the CLI: what CI actually runs ───────────────────────────────────────────


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_TOOL), *args], capture_output=True, text=True)


def test_the_cli_exits_non_zero_annotating_every_planted_result(tmp_path):
    sarif = _sarif([_result("py/a", "a.py", 1, "one"), _result("py/b", "b.py", 2, "two")])
    r = _run(str(_write(tmp_path, sarif)))
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "::error::codeql: a.py:1: py/a (error): one" in r.stdout, r.stdout
    assert "::error::codeql: b.py:2: py/b (error): two" in r.stdout, r.stdout
    assert "2 result(s)" in r.stderr, r.stderr


def test_the_cli_exits_zero_on_a_clean_sarif(tmp_path):
    r = _run(str(_write(tmp_path, _sarif([]))))
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "no results" in r.stdout
