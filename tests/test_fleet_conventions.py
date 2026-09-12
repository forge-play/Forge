"""This tree is held to the fleet's published conventions (G2-conventions-forge,
fleet plan decision 4).

The rules are READ from the published document and never restated here: a
rule that lived in each repo's own test file would drift one repo at a time,
which is how every incident the document's `sources` names happened. The
document is willow-reconciler's `reconciler conventions --json`, and the
reconciler is its one home.

**How the document gets here: vendored, not imported.** The alternative was
a test extra on `willow-reconciler` and `from reconciler.conventions import
conventions`. tests/test_no_reach_back.py's rule is that the Forge never
imports willow-mcp — Willow depends on the Forge, and the reverse is a
cycle. The reconciler is not willow-mcp: it is a stdlib-only, read-only tool
under the same org that does not depend on forge-play, and a *test-time*
import of it would be neither a cycle nor the forbidden direction. So (a)
was allowed. (b) still wins on this repo's own terms: the no-extras CI leg
(`pip install -e . pytest pyyaml`, then the same suite) must stay green with
nothing else installed, and a rule set that needs a network install to be
read is held on one leg, not both. So `tests/fleet_conventions.json` is the
document saved verbatim (willow-reconciler 0.6.0, `reconciler conventions
--json`, byte for byte, trailing newline included), pinned below by SHA-256
naming that version, and compared to the live package whenever `reconciler`
happens to be importable — which it is on a developer's machine that has it
and is not in CI. tools/vendor_manifest.json (#26) carries the same pin
under origin `willow-memory/willow-reconciler:reconciler conventions --json`,
so tools/vendor_sync_check.py names this document beside every other
vendored body; a test below holds the two pins to the same number.

**Read against this tree, three things are true today and each test says
which:** release-please.yml arms auto-merge, so pr-title.yml is required
(present); the config's hidden set is exactly the published one; the two
reasoning comments are present — at the config's TOP level, beside
`$comment-versioning`, not inside `packages["."]` as the reconciler's own
consumer test looks for them, and the rule ("in the config file itself") is
met either way, so the checker here looks at both levels and plants both.
No pile exists here (no `docs/ideas.md`, the reconciler's `--doc` default,
nor an IDEAS.md), so the pile rule is vacuous and the test says so rather than
xfailing a file that is not required yet. CONTRIBUTING.md did not exist; it
does now, and names the exact command tests.yml runs.

Every scan helper below is planted in this file, per tests/test_scans_fire.py
(#26); the pins are hash comparisons the meta-scan cannot see and are proven
by their own plant.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The published document, saved verbatim, and what it was saved from.
DOCUMENT = REPO_ROOT / "tests" / "fleet_conventions.json"
DOCUMENT_SOURCE = "willow-reconciler 0.6.0, `reconciler conventions --json`"
DOCUMENT_SHA256 = "8c2ba122a7100141200d8c76ad086339f984446ab7e90dd9c27a092dbf7f5335"
SCHEMA = "willow-fleet-conventions/1"

RULES: dict = json.loads(DOCUMENT.read_text(encoding="utf-8"))

RELEASE_PLEASE = ".github/workflows/release-please.yml"
RELEASE_CONFIG = "release-please-config.json"
CONTRIBUTING = "CONTRIBUTING.md"
#: The fleet's pile path (the reconciler's `--doc` default). This repo keeps
#: no pile at this path or any other; see the vacuous test below.
PILE = "docs/ideas.md"
ARMS_AUTOMERGE = "gh pr merge --auto"
#: The exact command CONTRIBUTING.md names and .github/workflows/tests.yml runs.
TEST_COMMAND = "python -m pytest tests/ -q"


# ── the document itself ─────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_saved_document_is_the_published_one_by_hash():
    """The pin. A re-save from a newer reconciler changes this hash on
    purpose; an edit by hand changes it by accident. Either way the number
    here and the version it names move together, or this fails."""
    assert _sha256(DOCUMENT) == DOCUMENT_SHA256, (
        f"tests/fleet_conventions.json no longer hashes to what was saved from "
        f"{DOCUMENT_SOURCE}; re-save it from `reconciler conventions --json` "
        f"and update DOCUMENT_SHA256 and DOCUMENT_SOURCE together"
    )
    assert RULES["schema"] == SCHEMA


def test_the_pin_catches_a_planted_one_byte_edit(tmp_path):
    """Planted: the saved document with one byte changed must not hash to
    the pin. A pin that has never been shown to break has not been shown to
    check anything."""
    edited = tmp_path / "fleet_conventions.json"
    text = DOCUMENT.read_text(encoding="utf-8")
    edited_text = text.replace('"ci",', '"cx",', 1)
    assert edited_text != text, "the plant must actually change a byte"
    assert len(edited_text) == len(text), "and only a byte, not the length"
    edited.write_text(edited_text, encoding="utf-8")
    assert _sha256(edited) != DOCUMENT_SHA256
    assert _sha256(DOCUMENT) == DOCUMENT_SHA256, "and the real one still does"


def test_the_manifest_pins_the_same_document_to_the_same_hash():
    """tools/vendor_manifest.json is where every vendored body's pin lives
    (tools/vendor_sync_check.py runs it in CI); this file's pin must be the
    same number, or one of the two is stale. Held here, not only by the
    checker, so a re-save that updates one and forgets the other fails on
    the test that names both."""
    manifest = json.loads(
        (REPO_ROOT / "tools" / "vendor_manifest.json").read_text(encoding="utf-8")
    )
    entries = [p for p in manifest["pins"] if p["path"] == "tests/fleet_conventions.json"]
    assert len(entries) == 1, "the conventions document must be pinned exactly once"
    (entry,) = entries
    assert entry["sha256"] == DOCUMENT_SHA256, (
        "the manifest and DOCUMENT_SHA256 disagree; update both together "
        f"(manifest {entry['sha256'][:12]}…, test {DOCUMENT_SHA256[:12]}…)"
    )
    assert entry["origin"] == "willow-memory/willow-reconciler:reconciler conventions --json"
    assert entry["body_from"] is None, "the whole file is the document; nothing above it to skip"


def test_the_saved_document_matches_the_live_package_when_it_is_installed():
    """The optional live check: on a machine that has the reconciler
    installed, the vendored copy must equal what the package publishes. Not
    in CI (the package is not a dependency, see the module docstring), so
    this skips there and runs wherever a developer has it."""
    conventions_mod = pytest.importorskip(
        "reconciler.conventions", reason="willow-reconciler is not installed here"
    )
    assert conventions_mod.conventions() == RULES, (
        "the installed reconciler publishes a different document than "
        f"tests/fleet_conventions.json ({DOCUMENT_SOURCE}); re-save and re-pin"
    )


# ── the checks, each read from RULES ────────────────────────────────────────


def _arms_automerge(root: Path) -> bool:
    workflow = root / RELEASE_PLEASE
    return workflow.exists() and ARMS_AUTOMERGE in workflow.read_text(encoding="utf-8")


def _missing_when_armed(root: Path, required: list[str]) -> list[str]:
    if not _arms_automerge(root):
        return []
    return [f for f in required if not (root / f).exists()]


def _config_hidden_types(config_text: str) -> set[str]:
    sections = json.loads(config_text)["packages"]["."]["changelog-sections"]
    return {s["type"] for s in sections if s.get("hidden")}


def _config_missing_comments(config_text: str, required: list[str]) -> list[str]:
    """The required reasoning comments absent from the config. The rule is
    "in the config file itself"; the reconciler's own consumer test looks
    inside `packages["."]`, this repo keeps them at the top level beside
    `$comment-versioning`, and both are the config file, so both count."""
    document = json.loads(config_text)
    package = document["packages"]["."]
    return [c for c in required if c not in document and c not in package]


def _missing_when_pile_exists(root: Path, required: list[str]) -> list[str]:
    if not (root / PILE).exists():
        return []
    return [f for f in required if not (root / f).exists()]


def _names_test_command(contributing_text: str) -> bool:
    return TEST_COMMAND in contributing_text


def test_pr_title_guard_is_present_wherever_automerge_is_armed():
    assert _arms_automerge(REPO_ROOT), (
        f"{RELEASE_PLEASE} no longer arms auto-merge; if that is deliberate, the "
        "rule below becomes vacuous and this assertion is the one to revisit"
    )
    assert (
        _missing_when_armed(REPO_ROOT, RULES["required_when_release_please_arms_automerge"]) == []
    )


def test_the_configs_hidden_set_equals_the_published_set():
    text = (REPO_ROOT / RELEASE_CONFIG).read_text(encoding="utf-8")
    assert _config_hidden_types(text) == set(RULES["hidden_types"]), RULES["sources"][
        "hidden_types"
    ]


def test_the_config_carries_every_required_reasoning_comment():
    text = (REPO_ROOT / RELEASE_CONFIG).read_text(encoding="utf-8")
    assert _config_missing_comments(text, RULES["required_config_comments"]) == [], RULES[
        "sources"
    ]["required_config_comments"]


def test_contributing_names_the_test_command():
    assert RULES["contributing_must_name_test_command"] is True
    assert (REPO_ROOT / CONTRIBUTING).exists(), (
        "CONTRIBUTING.md is gone; " + RULES["sources"]["contributing_must_name_test_command"]
    )
    assert _names_test_command((REPO_ROOT / CONTRIBUTING).read_text(encoding="utf-8")), (
        f"CONTRIBUTING.md must name {TEST_COMMAND!r} verbatim — "
        + RULES["sources"]["contributing_must_name_test_command"]
    )


def test_trailers_workflow_is_present_because_a_pile_exists():
    """Until E3-piles (fleet plan Wave 3, 2026-09-12) this repo kept no pile
    and this test asserted the rule was vacuous. It keeps one now at the
    fleet's path, so `required_when_pile_exists` (trailers.yml running
    `reconciler verify` in CI) is live: a pile whose trailers nothing
    verifies is a pile that can carry a dangling join key forever."""
    assert (REPO_ROOT / PILE).exists(), (
        "docs/ideas.md is gone; " + RULES["sources"]["required_when_pile_exists"]
    )
    assert _missing_when_pile_exists(REPO_ROOT, RULES["required_when_pile_exists"]) == [], RULES[
        "sources"
    ]["required_when_pile_exists"]


# ── the plants ──────────────────────────────────────────────────────────────


def _tree(tmp_path: Path, label: str, *, arms: bool, files: tuple[str, ...] = ()) -> Path:
    root = tmp_path / label
    (root / ".github" / "workflows").mkdir(parents=True)
    body = "jobs:\n  release-please:\n    steps:\n      - run: |\n"
    body += f'          {ARMS_AUTOMERGE} "$pr"\n' if arms else "          gh pr list\n"
    (root / RELEASE_PLEASE).write_text(body, encoding="utf-8")
    for f in files:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("# planted\n", encoding="utf-8")
    return root


def test_the_armed_tree_check_fires_on_a_planted_tree_missing_the_guard(tmp_path):
    required = RULES["required_when_release_please_arms_automerge"]
    assert _missing_when_armed(_tree(tmp_path, "bare", arms=True), required) == required
    assert (
        _missing_when_armed(_tree(tmp_path, "guarded", arms=True, files=tuple(required)), required)
        == []
    )
    assert _missing_when_armed(_tree(tmp_path, "manual", arms=False), required) == []


def test_the_hidden_set_check_catches_a_planted_config_that_unhides_ci():
    """Planted: a config that lists `ci` un-hidden — jeles v0.4.1's exact
    mistake — and carries one required comment inside the package and none
    at the top level. The hidden set must read as three, not four, and the
    missing comment must be the one that is missing."""
    planted = json.dumps(
        {
            "packages": {
                ".": {
                    "changelog-sections": [
                        {"type": "feat", "section": "Added"},
                        {"type": "docs", "section": "Docs", "hidden": True},
                        {"type": "test", "section": "Tests", "hidden": True},
                        {"type": "ci", "section": "CI"},
                        {"type": "chore", "section": "Chores", "hidden": True},
                    ],
                    "$comment-what-cuts-a-release": "kept",
                }
            }
        }
    )
    assert _config_hidden_types(planted) == {"chore", "docs", "test"}
    assert _config_missing_comments(planted, RULES["required_config_comments"]) == [
        "$comment-hidden-rule"
    ]


def test_the_comment_check_catches_a_top_level_comment_and_a_missing_one():
    """Planted: the shape this repo actually uses — both comments at the top
    level, none in the package — must clear; with one of them removed, that
    one must be reported. Both levels count, and absence at both is absence."""
    required = RULES["required_config_comments"]
    top_level = json.dumps(
        {
            "packages": {".": {"changelog-sections": []}},
            **{c: "kept" for c in required},
        }
    )
    assert _config_missing_comments(top_level, required) == []
    one_gone = json.dumps(
        {
            "packages": {".": {"changelog-sections": []}},
            required[0]: "kept",
        }
    )
    assert _config_missing_comments(one_gone, required) == required[1:]


def test_the_pile_check_fires_on_a_planted_tree_with_a_pile_and_no_verify_gate(tmp_path):
    required = RULES["required_when_pile_exists"]
    with_pile = _tree(tmp_path, "pile", arms=False, files=(PILE,))
    assert _missing_when_pile_exists(with_pile, required) == required
    gated = _tree(tmp_path, "gated", arms=False, files=(PILE, *required))
    assert _missing_when_pile_exists(gated, required) == []


def test_the_contributing_check_catches_a_planted_contributing_without_the_command():
    assert not _names_test_command("# Contributing\n\nRun the tests before pushing.\n")
    assert not _names_test_command("Run `pytest` before pushing.\n"), (
        "the bare word is not the command; the rule wants something a PR can quote"
    )
    assert _names_test_command(f"```sh\n{TEST_COMMAND}\n```\n")
