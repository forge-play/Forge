"""tools/changelog_dedup.py's module docstring must not assert a stale fact
about whether this repository has a CHANGELOG.md.

Guards the mistake this file already made once: its docstring said "This
repository has no CHANGELOG.md" long after CHANGELOG.md existed here, tags
through v0.7.2 were cut, and nine `chore(master): release` commits were in the
history (corrected under T1-forge-canon, 2026-09-12). A scan that has never
fired has not been shown to check anything, so
`test_the_scan_catches_a_stale_claim_beside_a_real_changelog` below plants
that exact mistake — a docstring claiming no CHANGELOG.md, checked against
this repository's own, real CHANGELOG.md — and asserts the same checker used
against the real docstring catches it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_TOOL = _REPO / "tools" / "changelog_dedup.py"
_CHANGELOG = _REPO / "CHANGELOG.md"

# What the docstring says (or once said) about CHANGELOG.md's existence:
# "This repository has no CHANGELOG.md" / "repo has no CHANGELOG.md", etc.
# Anchored on "has no CHANGELOG.md" specifically — a future rewrite that drops
# the claim entirely, because the file will exist here from now on, leaves
# nothing for this pattern to match, which is fine: there is then nothing
# stale to catch. Past tense ("had no CHANGELOG.md", describing 2026-08-11)
# does not match, on purpose — that is history, not a live claim.
_CLAIMS_NO_CHANGELOG_RE = re.compile(r"\bhas no CHANGELOG\.md\b")


def _module_docstring(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    doc = ast.get_docstring(tree)
    assert doc, f"{path} has no module docstring to check"
    return doc


def check_changelog_claim(docstring: str, changelog_exists: bool) -> str | None:
    """None if the docstring's claim about CHANGELOG.md's existence matches
    the tree; otherwise a message describing the mismatch. This is the scan;
    both the real test below and its plant call this same function."""
    claims_missing = bool(_CLAIMS_NO_CHANGELOG_RE.search(docstring))
    if claims_missing and changelog_exists:
        return "the docstring says 'has no CHANGELOG.md' but CHANGELOG.md exists in this tree"
    return None


def test_the_docstrings_changelog_claim_matches_the_tree():
    """The real check: tools/changelog_dedup.py's docstring must not claim
    CHANGELOG.md is missing while CHANGELOG.md exists here."""
    doc = _module_docstring(_TOOL)
    problem = check_changelog_claim(doc, _CHANGELOG.exists())
    assert problem is None, (
        f"{problem} — update the docstring to say what is actually true "
        "(strike or date the old claim, per house style; never delete it "
        "silently)."
    )


def test_the_scan_catches_a_stale_claim_beside_a_real_changelog(tmp_path):
    """The plant. Without this, `check_changelog_claim` passing on the real
    file above would not prove it can ever fail — it could be a function that
    always returns None. Reconstruct the exact violation this repo shipped
    (the docstring sentence, verbatim), write it as a module's docstring, read
    it back through the same `_module_docstring` the real test uses (so the
    reader is planted too, not only the matcher — the meta-scan in
    tests/test_scans_fire.py found it unplanted on 2026-09-12), and check it
    against this repository's own real CHANGELOG.md, which does exist."""
    assert _CHANGELOG.exists(), (
        "this plant needs a real CHANGELOG.md in the tree to be meaningful; "
        "if this repo ever loses its CHANGELOG.md, the docstring claim would "
        "become true and this test's premise no longer holds"
    )
    stale_docstring = (
        "Rebuild the newest CHANGELOG section from the commits, dropping "
        "merge commits.\n\n"
        "IT HAS NOT HAPPENED HERE, AND CANNOT YET. This repository has no "
        "CHANGELOG.md. It carries tags v0.0.3 through v0.0.9, but no "
        "`chore(master): release` commit exists anywhere in its history."
    )
    stale_module = tmp_path / "changelog_dedup.py"
    stale_module.write_text('"""' + stale_docstring + '\n"""\n\nimport sys\n', encoding="utf-8")
    assert _module_docstring(stale_module) == stale_docstring
    problem = check_changelog_claim(_module_docstring(stale_module), _CHANGELOG.exists())
    assert problem is not None, (
        "the scan did not catch a docstring claiming 'no CHANGELOG.md' next "
        "to a real one — it has never been shown to check anything"
    )

    # And the honest-history phrasing this file's docstring now uses ("had no
    # CHANGELOG.md", describing 2026-08-11) must NOT trip the same check —
    # otherwise every future dating of an old claim breaks this test.
    honest_history = "As written (2026-08-11), this repository had no CHANGELOG.md."
    assert check_changelog_claim(honest_history, _CHANGELOG.exists()) is None
