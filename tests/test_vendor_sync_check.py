"""tools/vendor_sync_check.py — the drift guard tests/test_no_reach_back.py and
tests/test_human_loop.py went on citing after it had been retired (a9ee4c2,
2026-09-02: the old one diffed against a willow-mcp checkout on disk and
skipped without one), rebuilt as a manifest of hashes under
G2-vendor-pins-forge on 2026-09-12.

Two different things are proven here, on purpose:

* The REAL manifest holds against the REAL tree (`test_every_real_pin_holds`).
  That is the guard itself: it fails the day someone edits
  forge/friction_floor.py's body in Forge alone (willow-mcp pins that exact
  hash), or changes tools/changelog_dedup.py's body without recording the
  fleet event in tools/vendor_manifest.json.
* The checker CAN fail. A pin that has never been shown to break has not been
  shown to check anything, so a sandbox manifest plants a one-byte drift, a
  missing file and a vanished `body_from` line, and the same `drifts()` the
  real test calls must name each one with the origin to re-sync from.

The sandbox is a fake repo under `tmp_path` with its own manifest, so nothing
here touches the real pins; the real pins are read once, by the first test.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_TOOL = _REPO / "tools" / "vendor_sync_check.py"
sys.path.insert(0, str(_REPO / "tools"))

import vendor_sync_check as vsc  # noqa: E402  (tools/ is not a package)

_HEADER = "# ── home ──\n# a header comment a repo may correct without moving the body\n"
_BODY_FIRST_LINE = '"""example — the pinned body starts here."""'
_BODY = _BODY_FIRST_LINE + "\nimport re\n\nFLAG = re.I\n"
_ORIGIN = "willow-memory/willow-gate:src/willow_gate/example.py"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pin(path: str, sha: str, origin: str = _ORIGIN, body_from: str | None = None) -> dict:
    return {"path": path, "origin": origin, "body_from": body_from,
            "sha256": sha, "note": "sandbox"}


def _sandbox(tmp_path: Path, files: dict[str, str], pins: list[dict]) -> tuple[Path, Path]:
    """A fake repo: `files` written under `root`, `pins` as its manifest."""
    root = tmp_path / "repo"
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    manifest = root / "tools" / "vendor_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"pins": pins}, indent=1), encoding="utf-8")
    return manifest, root


# ── the guard ────────────────────────────────────────────────────────────────


def test_every_real_pin_holds():
    """The real manifest against the real tree. If this fails, read the
    message: it names the file, the origin, and whether the fix is a re-sync
    or a recorded decision (`python tools/vendor_sync_check.py --print`)."""
    assert vsc.drifts() == []


def test_the_real_manifest_pins_what_the_repo_says_it_vendors():
    """tests/test_no_reach_back.py names three vendored modules and the
    changelog tool is the fleet's canonical copy; every one must be pinned,
    and a pin must be a real file with a full SHA-256."""
    pins = json.loads(vsc.MANIFEST.read_text(encoding="utf-8"))["pins"]
    paths = {p["path"] for p in pins}
    assert {"forge/friction_floor.py", "forge/human_loop.py",
            "forge/model_egress.py", "tools/changelog_dedup.py"} <= paths
    for pin in pins:
        assert (_REPO / pin["path"]).is_file(), pin["path"]
        assert len(pin["sha256"]) == 64 and int(pin["sha256"], 16) >= 0, pin["path"]
        assert pin["origin"] == "self" or ":" in pin["origin"], (
            f"{pin['path']}: origin must be `self` or `<org/repo>:<path>`"
        )
        assert pin["note"].strip(), f"{pin['path']}: a pin without a note is a number nobody decided"


# ── the sandbox: a matching pin passes ───────────────────────────────────────


def test_a_matching_whole_file_pin_passes(tmp_path):
    text = _HEADER + _BODY
    manifest, root = _sandbox(tmp_path, {"pkg/example.py": text},
                              [_pin("pkg/example.py", _sha(text))])
    assert vsc.drifts(manifest, root) == []


def test_a_body_pin_lets_the_header_above_it_change(tmp_path):
    """The reason `body_from` exists: #25 corrected friction_floor.py's header
    comment without moving the docstring-through-EOF bytes willow-mcp hashes.
    A body pin must hold across a header edit, and only the body counts."""
    pin = _pin("pkg/example.py", _sha(_BODY), body_from=_BODY_FIRST_LINE)
    manifest, root = _sandbox(tmp_path, {"pkg/example.py": _HEADER + _BODY}, [pin])
    assert vsc.drifts(manifest, root) == []

    (root / "pkg" / "example.py").write_text(
        "# a rewritten header, twice as long\n# with a second line\n" + _BODY,
        encoding="utf-8")
    assert vsc.drifts(manifest, root) == [], "a header edit above the body is not drift"


# ── the plants: the checker must be able to fail ─────────────────────────────


def test_a_one_byte_drift_fires_and_names_the_origin(tmp_path):
    """Planted: `re.I` becomes `re.X` — one byte, no line count change, the
    kind of edit a diff reviewer waves through. The drift must be reported
    with the file, both hashes, and the origin to re-sync from."""
    pin = _pin("pkg/example.py", _sha(_BODY), body_from=_BODY_FIRST_LINE)
    manifest, root = _sandbox(tmp_path, {"pkg/example.py": _HEADER + _BODY}, [pin])
    drifted = _BODY.replace("FLAG = re.I", "FLAG = re.X")
    assert len(drifted) == len(_BODY), "the plant is meant to be exactly one byte"
    (root / "pkg" / "example.py").write_text(_HEADER + drifted, encoding="utf-8")

    problems = vsc.drifts(manifest, root)
    assert len(problems) == 1, problems
    (line,) = problems
    assert line.startswith("pkg/example.py: ")
    assert _sha(_BODY) in line and _sha(drifted) in line, line
    assert f"re-sync from {_ORIGIN}" in line, line
    assert "update the manifest with the decision" in line, line


def test_a_missing_file_fires(tmp_path):
    """Planted: the pinned file is gone. A deleted vendored module is the
    loudest possible drift and must not read as 'nothing to check'."""
    manifest, root = _sandbox(tmp_path, {}, [_pin("pkg/gone.py", _sha(_BODY))])
    problems = vsc.drifts(manifest, root)
    assert len(problems) == 1 and problems[0].startswith("pkg/gone.py: file is missing"), problems
    assert _ORIGIN in problems[0]


def test_a_vanished_body_from_line_fires(tmp_path):
    """Planted: the line the pin starts from no longer exists (someone edited
    the docstring's first line). There is no body to hash, and silently
    hashing the whole file instead would report a drift for the wrong
    reason — it must say the anchor is gone."""
    pin = _pin("pkg/example.py", _sha(_BODY), body_from=_BODY_FIRST_LINE)
    manifest, root = _sandbox(tmp_path, {"pkg/example.py": _HEADER + _BODY}, [pin])
    (root / "pkg" / "example.py").write_text(
        _HEADER + _BODY.replace(_BODY_FIRST_LINE, '"""renamed first line."""'),
        encoding="utf-8")
    (line,) = vsc.drifts(manifest, root)
    assert "no line reads" in line and _BODY_FIRST_LINE in line, line


def test_a_self_origin_drift_says_it_is_a_fleet_event(tmp_path):
    """Planted on a `self` pin: this repo is the canonical home, so "re-sync
    from self" would be nonsense. The advice must be the decision, not a
    re-sync, and must say the consumers have to hear about it."""
    manifest, root = _sandbox(tmp_path, {"tools/canon.py": _BODY},
                              [_pin("tools/canon.py", _sha(_BODY + "\n"), origin="self")])
    (line,) = vsc.drifts(manifest, root)
    assert "re-sync" not in line and "fleet event" in line and "--print" in line, line


def test_the_plant_is_the_same_checker_the_real_test_runs():
    """The plants above call `vsc.drifts`; the guard calls `vsc.drifts`. Pin
    that identity so a refactor cannot leave the plants proving one function
    and the guard trusting another."""
    assert test_every_real_pin_holds.__code__.co_names[:2] == ("vsc", "drifts")


# ── the CLI: what CI actually runs ───────────────────────────────────────────


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_TOOL), *args],
                          capture_output=True, text=True)


def test_the_cli_exits_non_zero_naming_every_drift(tmp_path):
    """Two planted drifts, one run: both named on stderr, exit 1. A checker
    that stopped at the first drift would make a three-file re-sync three
    CI rounds."""
    manifest, root = _sandbox(
        tmp_path,
        {"a.py": "a\n", "b.py": "b\n"},
        [_pin("a.py", _sha("A\n")), _pin("b.py", _sha("b\n")), _pin("c.py", _sha("c\n"))],
    )
    r = _run("--manifest", str(manifest), "--root", str(root))
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert "vendor drift: a.py:" in r.stderr and "vendor drift: c.py:" in r.stderr, r.stderr
    assert "b.py" not in r.stderr, "a holding pin must not be reported"


def test_print_shows_the_current_hash_for_each_pin(tmp_path):
    """`--print` is how a deliberate update becomes one command: the output
    is the hash to paste, beside the path, in manifest order, exit 0 even
    while the pins are stale."""
    manifest, root = _sandbox(tmp_path, {"a.py": "a\n", "b.py": "b\n"},
                              [_pin("a.py", "0" * 64), _pin("b.py", _sha("b\n"))])
    r = _run("--print", "--manifest", str(manifest), "--root", str(root))
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    expected = [_sha("a\n") + "  a.py", _sha("b\n") + "  b.py"]
    assert r.stdout.splitlines() == expected, r.stdout


def test_the_default_run_is_the_real_manifest_and_passes():
    r = _run()
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert "vendor pins hold" in r.stdout


def test_ci_runs_the_checker_as_its_own_step():
    """The step in .github/workflows/tests.yml is what makes this a gate
    rather than a script someone may remember. Held by name so a workflow
    trim cannot drop it silently."""
    yaml = pytest.importorskip("yaml", reason="PyYAML needed to read the workflow")
    wf = yaml.safe_load((_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8"))
    runs = [str(step.get("run", "")) for job in wf["jobs"].values()
            for step in job.get("steps", [])]
    assert any("tools/vendor_sync_check.py" in run for run in runs), runs
