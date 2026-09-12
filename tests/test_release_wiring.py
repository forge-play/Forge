"""The release chain is three files that must agree, and every disagreement is silent.

    release-please-config.json     decides the tag name and what cuts a release
    .release-please-manifest.json  is the version it bumps from
    .github/workflows/release.yml  fires on a tag pattern and publishes

Nothing joins them up at runtime. A mismatch does not raise — it means a release
quietly does not happen, and this repo already has the scar: **v0.0.8 is tagged
but has never existed on PyPI.** The tag was cut on a commit whose version was
still 0.0.7, the build produced 0.0.7, and the only thing that noticed was PyPI
refusing a duplicate upload.

Ported from kartikeya (which ported it from willow-mcp, where a config mistake
would have tagged `willow-mcp-v2.2.0` while the publish workflow listened for
`v*`). The Forge's chain is copied from jeles — the fleet's fullest — with the
package name swapped; these tests are what make that copy checkable rather than
trusted. Like kartikeya, this repo has no second version file to keep in step.
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re
import tomllib  # stdlib from 3.11; this package requires >=3.11
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="PyYAML needed to read the workflows")

_REPO = Path(__file__).resolve().parents[1]
_CONFIG = _REPO / "release-please-config.json"
_MANIFEST = _REPO / ".release-please-manifest.json"
_RELEASE_WF = _REPO / ".github" / "workflows" / "release.yml"
_RP_WF = _REPO / ".github" / "workflows" / "release-please.yml"


def _json(p: Path) -> dict:
    return json.loads(p.read_text())


def _yaml(p: Path) -> dict:
    return yaml.safe_load(p.read_text())


def _package_config() -> dict:
    return _json(_CONFIG)["packages"]["."]


def test_the_tag_release_please_creates_matches_what_release_yml_listens_for():
    """With `include-component-in-tag` unset it defaults to *true* and the tag
    becomes `kartikeya-vX.Y.Z`, which `v*` does not match — so the tag is created
    and nothing publishes, with no error anywhere. Observed on willow-mcp#256."""
    cfg = _package_config()
    version = _json(_MANIFEST)["."]
    tag = (
        f"{cfg['package-name']}-v{version}"
        if cfg.get("include-component-in-tag", True)
        else f"v{version}"
    )

    # `on:` parses as the boolean True — PyYAML applies the YAML 1.1 rule.
    patterns = list(_yaml(_RELEASE_WF)[True]["push"]["tags"])
    assert any(fnmatch.fnmatch(tag, p) for p in patterns), (
        f"release-please would create the tag {tag!r}, which matches none of "
        f"release.yml's trigger patterns {patterns!r}. Nothing would publish, "
        f"and nothing would report an error."
    )


def test_the_version_has_exactly_one_source():
    """v0.0.8's direct cause: pyproject carried a hardcoded version that the tag
    disagreed with. It is `dynamic` now, and this keeps it that way — a literal
    here is a second copy, and a second copy is what drifts."""
    pyproject = tomllib.loads((_REPO / "pyproject.toml").read_text())
    assert "version" in (pyproject["project"].get("dynamic") or [])
    assert "version" not in pyproject["project"], (
        "a literal project.version is exactly what broke v0.0.8"
    )
    assert pyproject["tool"]["hatch"]["version"]["source"] == "vcs"
    assert not _package_config().get("extra-files"), (
        "nothing in this repo stores a version, so nothing needs bumping"
    )


# A credential whose events actually trigger workflows. Either form is
# acceptable; what is NOT acceptable is GITHUB_TOKEN, whose events GitHub
# suppresses — the release PR merges, no tag workflow fires, nothing publishes.
#
# Originally this pinned the literal RELEASE_PLEASE_TOKEN, which named the
# mechanism rather than the property. The willow-ci GitHub App satisfies the
# same property (an installation token is not GITHUB_TOKEN) and adds hourly
# expiry, so the assertion now accepts either and the prohibition below is
# unchanged. Widening this to accept GITHUB_TOKEN would give back the three
# releases jeles lost.
NON_SUPPRESSED_CREDENTIALS = (
    "RELEASE_PLEASE_TOKEN",  # fine-grained PAT (being retired)
    "steps.app-token.outputs.token",  # willow-ci App installation token
)


def _names_a_non_suppressed_credential(value: object) -> bool:
    text = str(value)
    return any(c in text for c in NON_SUPPRESSED_CREDENTIALS)


def test_the_credential_scan_catches_github_token_and_clears_the_app_token():
    """Planted both ways. A step whose only credential is GITHUB_TOKEN — the
    exact shape that lost jeles three releases — must read as suppressed;
    either accepted form must clear. Until 2026-09-12 this helper cleared
    real steps and had never been shown to refuse one (the meta-scan in
    tests/test_scans_fire.py found it unplanted)."""
    assert not _names_a_non_suppressed_credential({"token": "${{ secrets.GITHUB_TOKEN }}"})
    assert not _names_a_non_suppressed_credential(None)
    assert _names_a_non_suppressed_credential({"GH_TOKEN": "${{ steps.app-token.outputs.token }}"})
    assert _names_a_non_suppressed_credential("${{ secrets.RELEASE_PLEASE_TOKEN }}")


def test_release_automation_uses_a_non_suppressed_credential_everywhere():
    """A bot token silently produces no workflow runs: the release PR merges, no
    tag workflow fires, nothing publishes. jeles lost three releases to it."""
    steps = _yaml(_RP_WF)["jobs"]["release-please"]["steps"]
    used: set[str] = set()
    values: list[str] = []
    for step in steps:
        for value in list((step.get("env") or {}).values()) + list(
            (step.get("with") or {}).values()
        ):
            values.append(str(value))
            used.update(re.findall(r"secrets\.([A-Z_]+)", str(value)))
    assert any(_names_a_non_suppressed_credential(v) for v in values), (
        f"no non-suppressed credential anywhere in the job; secrets seen: {used}"
    )
    assert "GITHUB_TOKEN" not in used, (
        f"GITHUB_TOKEN's events do not trigger workflows; found {used}"
    )


def test_auto_merge_waits_for_ci_rather_than_merging_directly():
    """`--auto` is what makes the merge wait for the required checks. Falling
    back to a plain merge would publish off an unverified commit."""
    steps = _yaml(_RP_WF)["jobs"]["release-please"]["steps"]
    arming = [s for s in steps if "gh pr merge" in str(s.get("run", ""))]
    assert arming, "no step arms auto-merge on the release PR"
    for step in arming:
        for line in step["run"].splitlines():
            if "gh pr merge" in line and not line.strip().startswith("#"):
                assert "--auto" in line, f"merge without --auto: {line.strip()}"
                assert "--squash" not in line


def test_the_changelog_is_rebuilt_before_auto_merge_is_armed():
    """Order is the point: the correction must land on the release PR *before*
    auto-merge can take it, or the release ships wrong and is fixed afterwards.

    **Exercised for real since v0.2.0.** As written (2026-08-11) this repo had
    no CHANGELOG.md and no `chore(master): release` commit, so the tool
    no-opped and only the wiring could be asserted. The predicted duplication
    then happened on schedule and this step caught it unassisted: `git log --
    CHANGELOG.md` shows a `chore: rebuild the changelog section from the
    commits` commit on seven of the nine release PRs (v0.2.0 through v0.7.1),
    each dropping the merge-commit duplicate. This test still asserts the
    wiring only; the corrections themselves are that history (corrected
    2026-09-12, G2-vendor-pins-forge)."""
    steps = _yaml(_RP_WF)["jobs"]["release-please"]["steps"]
    names = [s.get("name") or str(s.get("uses", "")) for s in steps]

    def index_of(needle: str) -> int:
        hits = [i for i, n in enumerate(names) if needle in n]
        assert hits, f"no step matching {needle!r} in {names}"
        return hits[0]

    assert (
        index_of("actions/checkout")
        < index_of("release-please-action")
        < index_of("Rebuild the changelog")
        < index_of("Arm auto-merge")
    ), names

    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0, "needs full history for the range"
    assert checkout["with"]["fetch-tags"] is True, "needs tags to find the previous release"


def test_a_changelog_bail_does_not_block_the_release():
    """The bug willow-mcp shipped, carried here as a guard rather than repeated.
    Under `set -e`, exit 2 — the tool refusing a section it cannot model —
    skipped the auto-merge arming and stopped the release entirely. Trading a
    wrong changelog for no release at all is a bad deal."""
    steps = _yaml(_RP_WF)["jobs"]["release-please"]["steps"]
    step = next(s for s in steps if "Rebuild the changelog" in (s.get("name") or ""))
    assert "::warning::" in step["run"], "a bail must warn"
    assert 'status" = "2"' in step["run"], "exit 2 must be handled, not left to set -e"
    assert _names_a_non_suppressed_credential(step.get("env"))
    assert "GITHUB_TOKEN" not in str(step.get("env"))
    assert (_REPO / "tools" / "changelog_dedup.py").exists(), (
        "the workflow calls a script this repo does not ship"
    )


def _assigned_literal(source: str, name: str):
    """The literal bound to module-level `name` in `source`, read out of the
    AST rather than the text, so a comment that spells the same assignment
    for another repo is not what gets returned. StopIteration if unbound."""
    tree = ast.parse(source)
    return next(
        ast.literal_eval(n.value)
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == name
    )


def test_the_assignment_reader_catches_the_value_and_not_the_comment():
    """Planted: a body whose comment spells willow-mcp's PACKAGED and whose
    assignment spells this repo's. The reader must return the assignment and
    nothing the comment says; and an unbound name must not read as some
    other name's value. Factored out of the test below on 2026-09-12 when
    the meta-scan (tests/test_scans_fire.py) reported the inline AST walk as
    a scan with nothing to plant."""
    body = (
        "# willow-mcp: PACKAGED = ('src/willow_mcp/', 'pyproject.toml')\n"
        "OTHER = 1\n"
        "PACKAGED = ('forge/', 'pyproject.toml')\n"
    )
    assert _assigned_literal(body, "PACKAGED") == ("forge/", "pyproject.toml")
    assert _assigned_literal(body, "OTHER") == 1
    with pytest.raises(StopIteration):
        _assigned_literal(body, "MISSING")


def test_the_pr_title_check_guards_both_directions():
    """One direction stops a title inventing a release; the other stops a commit
    releasing something nobody installs. willow-mcp shipped 2.1.5 that way and
    jeles published v0.4.1 for a single `ci:` commit.

    The packaged path is the one thing in that workflow that must NOT be shared
    between repos — willow-mcp uses `src/willow_mcp/`, jeles a top-level
    `jeles/`. Read the *assigned value* out of the AST rather than searching the
    text: the comments there name the other repos' paths deliberately, and a
    substring check would flag its own explanation."""
    wf = _REPO / ".github" / "workflows" / "pr-title.yml"
    body = _yaml(wf)["jobs"]["title"]["steps"][-1]["run"].split("<<'PY'")[1].rsplit("PY", 1)[0]
    packaged = _assigned_literal(body, "PACKAGED")

    assert packaged == ("forge/", "pyproject.toml"), packaged
    pyproject = tomllib.loads((_REPO / "pyproject.toml").read_text())
    wheel = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"]
    assert wheel == ["forge"], f"packaged path disagrees with what the wheel ships: {wheel}"


def test_the_release_body_is_synced_after_the_release_is_created():
    """release-please writes the GitHub Release body from its own parse, not
    from CHANGELOG.md, so fixing the file leaves the release *page* wrong.
    willow-mcp's v2.1.4 page and jeles' v0.5.0 page both kept their duplicate
    after the file had been corrected.

    As written (2026-08-11) this had never run here — there was no CHANGELOG.md
    to publish from. It has run on every release since v0.5.0 (CHANGELOG.md
    exists, tags through v0.7.2). The wiring is still what is asserted here
    (corrected 2026-09-12, G2-vendor-pins-forge)."""
    steps = _yaml(_RP_WF)["jobs"]["release-please"]["steps"]
    names = [s.get("name") or str(s.get("uses", "")) for s in steps]

    def index_of(needle: str) -> int:
        hits = [i for i, n in enumerate(names) if needle in n]
        assert hits, f"no step matching {needle!r} in {names}"
        return hits[0]

    assert (
        index_of("release-please-action")
        < index_of("Make the GitHub Release body")
        < index_of("Arm auto-merge")
    ), names

    step = steps[index_of("Make the GitHub Release body")]
    run = step["run"]
    assert "--print-section" in run
    assert "gh release edit" in run
    assert "$GITHUB_SHA" in run, "must not depend on which branch the previous step left"
    assert "rstrip()" in run, "comparison must ignore trailing whitespace"
    assert _names_a_non_suppressed_credential(step.get("env"))
    assert "GITHUB_TOKEN" not in str(step.get("env"))


def test_print_section_refuses_when_there_is_no_changelog():
    """The ordering trap this repo uniquely has. `--print-section`'s stdout
    becomes a GitHub Release body, so falling through the "no CHANGELOG.md yet —
    nothing to rebuild" early return would publish that sentence as the release
    notes. It must exit non-zero instead, and the workflow then warns and leaves
    the release alone."""
    import subprocess
    import sys

    tool = _REPO / "tools" / "changelog_dedup.py"
    if (_REPO / "CHANGELOG.md").exists():
        pytest.skip("a changelog exists now — this guards the no-changelog state")
    r = subprocess.run(
        [sys.executable, str(tool), "--print-section", "0.0.9"],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stdout.strip() == "", f"printed something usable as a body: {r.stdout!r}"


def test_print_section_refuses_while_only_hand_written_history_exists():
    """The live successor to the no-CHANGELOG guard, and the same hazard.

    CHANGELOG.md now exists but contains only the hand-written v0.0.1-v0.0.9
    history, backfilled because those tags predate release-please. Those
    sections deliberately carry no `(…/compare/…)` link, which is how the tool
    tells generated sections from written ones.

    `--print-section`'s stdout becomes a GitHub Release body, so this must exit
    non-zero with an empty stdout rather than printing an explanatory sentence
    that would be published as release notes."""
    import subprocess
    import sys

    changelog = _REPO / "CHANGELOG.md"
    if not changelog.exists():
        pytest.skip("no changelog — the earlier guard covers that state")
    generated = [ln for ln in changelog.read_text().splitlines() if ln.startswith("## [")]
    if generated:
        pytest.skip("release-please has written a section — this guard is spent")

    r = subprocess.run(
        [sys.executable, str(_REPO / "tools" / "changelog_dedup.py"), "--print-section", "0.0.9"],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert r.stdout.strip() == "", f"printed something publishable: {r.stdout!r}"


def test_a_rebuild_leaves_the_hand_written_history_alone():
    """The claim the changelog header makes about this tool, checked rather than
    asserted: with no generated section present there is nothing to rebuild, and
    that is a clean no-op — not an error, and not a rewrite of the history."""
    import subprocess
    import sys

    changelog = _REPO / "CHANGELOG.md"
    if not changelog.exists() or [
        ln for ln in changelog.read_text().splitlines() if ln.startswith("## [")
    ]:
        pytest.skip("only meaningful while the file is hand-written history alone")

    before = changelog.read_text()
    r = subprocess.run(
        [sys.executable, str(_REPO / "tools" / "changelog_dedup.py")],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
    )
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert changelog.read_text() == before, "the hand-written history was modified"


def test_only_types_that_change_the_installed_package_cut_a_release():
    """Every un-hidden type releases on its own. jeles shipped v0.4.1 to PyPI
    for a `ci:` commit touching a workflow file — survivable when a human merges
    the release PR, not once auto-merge does."""
    sections = _package_config()["changelog-sections"]
    visible = {s["type"] for s in sections if not s.get("hidden")}
    assert visible == {"feat", "fix", "security", "perf", "refactor", "build", "deps"}, visible
    for t in ("docs", "test", "ci", "chore"):
        assert next(s for s in sections if s["type"] == t).get("hidden") is True


def test_a_breaking_change_below_1_0_cuts_1_0_0_rather_than_a_minor():
    """`bump-minor-pre-major` was true here and is now false — a policy change,
    so this test flipped with it.

    True kept a breaking change at a minor, so that reaching 1.0 stayed a
    decision someone makes. Dependents paid for it: a `<1.0.0` cap accepted
    every version this config could produce and therefore promised nothing.
    willow-mcp tried `kartikeya>=0.0.9,<0.1.0` to close that downstream and
    withdrew it — that cap would have expired on the very next `feat:`, which
    this config already documents as taking 0.0.9 to 0.1.0.

    The visible consequence: `feat:` still goes 0.0.9 -> 0.1.0, and a breaking
    change goes straight to 1.0.0. That jump is the point — the number then says
    what happened.
    """
    cfg = _package_config()
    assert cfg.get("bump-minor-pre-major") is False, (
        "true caps a breaking change at a minor, which makes a downstream "
        "`<1.0.0` cap meaningless. See willow-mcp docs/design/fleet-versioning.md"
    )
    assert cfg.get("bump-patch-for-minor-pre-major") is False, (
        "with this true, a feat would bump the patch instead of the minor"
    )
    assert _json(_MANIFEST)["."].startswith("0."), (
        "past 1.0 both flags are dead weight — `isPreMajor` gates them. Remove."
    )


def test_the_publish_job_uses_oidc_with_attestations():
    """Trusted Publishing (OIDC) with PEP 740 attestations enabled. No stored
    token, and attestations default to true — an explicit `false` or a leftover
    `password:` means the migration is incomplete."""
    job = _yaml(_RELEASE_WF)["jobs"]["publish"]
    perms = job.get("permissions") or {}
    assert perms.get("id-token") == "write", (
        "the publish job must request id-token: write for Trusted Publishing"
    )
    publish = job["steps"]
    step = next(s for s in publish if "pypi-publish" in str(s.get("uses", "")))
    with_ = step.get("with") or {}
    assert "password" not in with_, (
        "a stored token is not needed with Trusted Publishing — drop the password line"
    )
    assert with_.get("attestations") is not False, (
        "attestations are available with OIDC — do not disable them"
    )


def test_the_checkout_uses_a_non_suppressed_credential_so_pushes_are_not_gated():
    """`actions/checkout` persists whatever credential it used, and the changelog
    step's `git push` then uses it. `env: GH_TOKEN` only reaches the `gh` CLI.

    With the default GITHUB_TOKEN the commit is pushed as github-actions[bot],
    and the release PR's CI run comes back `action_required` — created, but held
    awaiting manual approval — so auto-merge waits on a check that never
    reports. Observed on the 2.2.0 release PR, which needed CI started by hand;
    release-please's own commit on the same branch was not gated, because it
    pushes with the PAT.

    This is the fourth way this fleet has been bitten by token attribution, so
    it gets a test rather than a comment."""
    steps = _yaml(_RP_WF)["jobs"]["release-please"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    token = str((checkout.get("with") or {}).get("token", ""))
    assert _names_a_non_suppressed_credential(token), (
        "checkout must carry a credential whose events trigger workflows — its "
        "credential is what the changelog step pushes with. "
        f"Got: {token!r}"
    )
    assert "GITHUB_TOKEN" not in token


# ── the pile and its gate (E3-trailers, fleet plan Wave 3, 2026-09-12) ──────
#
# docs/ideas.md is a numbered idea pile in willow-reconciler's form, and its
# numbers are permanent join keys: a commit carrying `Idea-Id: willow-ideas-NNN`
# is read as having LANDED item NNN ahead of every other signal. A pile with
# no `reconciler verify` in CI can therefore carry a dangling id forever — a
# confident, permanent wrong answer — so wherever the pile exists, the gate
# must too (the fleet convention `required_when_pile_exists`;
# tests/test_fleet_conventions.py holds the same rule from the published
# document, and this test holds the workflow's own wiring).

_PILE = _REPO / "docs" / "ideas.md"
_TRAILERS_WF = _REPO / ".github" / "workflows" / "trailers.yml"


def _pile_without_its_gate(root: Path) -> bool:
    """True if `root` keeps a numbered idea pile at the fleet's path and has no
    trailers.yml to verify the Idea-Id trailers that pile invites."""
    pile = root / "docs" / "ideas.md"
    gate = root / ".github" / "workflows" / "trailers.yml"
    return pile.exists() and not gate.exists()


def test_trailers_yml_exists_wherever_the_pile_does():
    assert _PILE.exists(), "the pile moved; docs/ideas.md is where the fleet's tooling reads it"
    assert not _pile_without_its_gate(_REPO), (
        "docs/ideas.md exists with no .github/workflows/trailers.yml to verify "
        "its Idea-Id trailers against it"
    )
    wf = _yaml(_TRAILERS_WF)
    steps = wf["jobs"]["verify-trailers"]["steps"]
    run = "\n".join(str(s.get("run", "")) for s in steps)
    assert "reconciler verify" in run and "docs/ideas.md" in run, run
    # `on:` parses as the boolean True — PyYAML applies the YAML 1.1 rule.
    assert wf[True]["pull_request"]["branches"] == ["master"], (
        "the gate must run on every PR to the default branch, which is master here"
    )
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0, (
        "verify walks the whole history; a shallow clone verifies only what it fetched"
    )


def test_the_pile_gate_check_fires_on_a_planted_pile_with_no_workflow(tmp_path):
    """Planted: a tree with a pile and no trailers.yml must be reported; the
    same tree with the workflow beside it, and a tree with no pile at all,
    must not. Without this, the check above passing on the real tree would
    not show `_pile_without_its_gate` can ever say True."""
    bare = tmp_path / "bare"
    (bare / "docs").mkdir(parents=True)
    (bare / "docs" / "ideas.md").write_text("1. an idea\n", encoding="utf-8")
    assert _pile_without_its_gate(bare)

    gated = tmp_path / "gated"
    (gated / "docs").mkdir(parents=True)
    (gated / "docs" / "ideas.md").write_text("1. an idea\n", encoding="utf-8")
    (gated / ".github" / "workflows").mkdir(parents=True)
    (gated / ".github" / "workflows" / "trailers.yml").write_text(
        "name: Trailers\n", encoding="utf-8"
    )
    assert not _pile_without_its_gate(gated)

    no_pile = tmp_path / "no_pile"
    no_pile.mkdir()
    assert not _pile_without_its_gate(no_pile), "no pile, nothing to gate"


# ── the fleet CI floor (decision 5: C4-tests-yml, C4-codeql, 2026-09-12) ─────
#
# tests.yml is held to the floor's shape by reading the file, never by
# restating it: the Linux matrix equals the Python classifiers pyproject.toml
# declares (a classifier CI never runs is a promise nobody checked; a matrix
# entry with no classifier is a version the package does not claim); the
# Windows job runs the floor and the ceiling of that list; the lint job pins
# ruff to one exact version and runs both `check` and `format --check`; the
# aggregate `test` job needs every other job, runs `if: always()`, and rejects
# any result that is not `success` — skipped and cancelled included, because a
# required check that goes green on a skipped leg protects nothing. codeql.yml
# analyzes python and actions. Each helper below is planted.

_TESTS_WF = _REPO / ".github" / "workflows" / "tests.yml"
_CODEQL_WF = _REPO / ".github" / "workflows" / "codeql.yml"
_PYPROJECT = _REPO / "pyproject.toml"
_CLASSIFIER_RE = re.compile(r"Programming Language :: Python :: (3\.\d+)\b")
_RUFF_PIN_RE = re.compile(r"\bruff==(\d+\.\d+\.\d+)\b")
_GATE = "test"


def _classifier_minors(pyproject_text: str) -> list[str]:
    """Every `Programming Language :: Python :: 3.X` classifier, in file order."""
    return _CLASSIFIER_RE.findall(pyproject_text)


def _matrix_versions(workflow: dict, job: str) -> list[str]:
    return [str(v) for v in workflow["jobs"][job]["strategy"]["matrix"]["python-version"]]


def _ruff_pin(workflow: dict) -> str | None:
    """The exact `ruff==X.Y.Z` the lint job installs, or None when it is
    unpinned (`pip install ruff`, `ruff>=…`) — an unpinned ruff is a ruff
    release reddening every open PR at once."""
    runs = "\n".join(str(s.get("run", "")) for s in workflow["jobs"]["lint"]["steps"])
    m = _RUFF_PIN_RE.search(runs)
    return m.group(1) if m else None


def _gate_problems(workflow: dict, gate: str = _GATE) -> list[str]:
    """Everything wrong with the aggregate job `gate`: absent, not
    `if: always()`, not needing every other job in the workflow, or not
    rejecting a non-success result. "Rejects" means the gate's own step text
    either reads `toJSON(needs)` and compares to `success`, or names all
    three of failure/cancelled/skipped in `contains(needs.*.result, …)`; a
    gate that only checks for `failure` passes on a skipped leg."""
    jobs = workflow["jobs"]
    if gate not in jobs:
        return [f"no `{gate}` job"]
    job = jobs[gate]
    problems: list[str] = []
    if str(job.get("if", "")).strip() != "always()":
        problems.append(
            f"`{gate}` is not `if: always()`, so a failed leg skips it "
            "and a skipped required check reads as passing"
        )
    needs = job.get("needs") or []
    needs = [needs] if isinstance(needs, str) else list(needs)
    missing = sorted(set(jobs) - {gate} - set(needs))
    if missing:
        problems.append(f"`{gate}` does not need {missing}")
    text = "\n".join(
        str(part)
        for step in job.get("steps", [])
        for part in (step.get("run", ""), step.get("if", ""), *(step.get("env") or {}).values())
    )
    explicit = "toJSON(needs)" in text and "success" in text
    triple = all(
        f"'{r}'" in text and "needs.*.result" in text for r in ("failure", "cancelled", "skipped")
    )
    if not (explicit or triple):
        problems.append(
            f"`{gate}` does not reject a skipped or cancelled leg — "
            "it must fail on any needed result that is not `success`"
        )
    return problems


def _codeql_languages(workflow: dict) -> set[str]:
    return {str(lang) for lang in workflow["jobs"]["analyze"]["strategy"]["matrix"]["language"]}


def test_the_linux_matrix_is_the_classifiers():
    classifiers = _classifier_minors(_PYPROJECT.read_text(encoding="utf-8"))
    assert classifiers, (
        "pyproject.toml declares no `Programming Language :: Python :: 3.X` classifier"
    )
    assert _matrix_versions(_yaml(_TESTS_WF), "test-matrix") == classifiers, (
        "tests.yml's Linux matrix must be exactly the Python classifiers pyproject.toml "
        "declares, in order — change both together"
    )


def test_the_windows_job_runs_the_floor_and_the_ceiling():
    classifiers = _classifier_minors(_PYPROJECT.read_text(encoding="utf-8"))
    by_minor = sorted(classifiers, key=lambda v: int(v.split(".")[1]))
    assert _matrix_versions(_yaml(_TESTS_WF), "windows") == [by_minor[0], by_minor[-1]]
    assert _yaml(_TESTS_WF)["jobs"]["windows"]["runs-on"].startswith("windows")


def test_ruff_is_pinned_to_an_exact_version():
    wf = _yaml(_TESTS_WF)
    assert _ruff_pin(wf) is not None, "the lint job must `pip install ruff==X.Y.Z`"
    runs = "\n".join(str(s.get("run", "")) for s in wf["jobs"]["lint"]["steps"])
    assert "ruff check" in runs and "ruff format --check" in runs


def test_the_aggregate_gate_needs_every_leg_and_rejects_a_skipped_one():
    assert _gate_problems(_yaml(_TESTS_WF)) == []


def test_codeql_analyzes_python_and_actions():
    assert _CODEQL_WF.exists(), "the floor's static-analysis half is missing"
    assert _codeql_languages(_yaml(_CODEQL_WF)) == {"python", "actions"}


def test_the_classifier_reader_catches_a_planted_mismatch():
    """Planted: a pyproject declaring 3.11 and 3.13, and a workflow whose
    matrix also runs 3.12 — the reader must return exactly the two declared
    minors so the equality above can fail on the third."""
    planted = (
        "classifiers = [\n"
        '    "Programming Language :: Python :: 3",\n'
        '    "Programming Language :: Python :: 3.11",\n'
        '    "Programming Language :: Python :: 3.13",\n'
        "]\n"
    )
    assert _classifier_minors(planted) == ["3.11", "3.13"], "the bare `3` is not a minor"
    workflow = {
        "jobs": {
            "test-matrix": {"strategy": {"matrix": {"python-version": ["3.11", "3.12", "3.13"]}}}
        }
    }
    assert _matrix_versions(workflow, "test-matrix") != _classifier_minors(planted)
    assert _classifier_minors("requires-python = '>=3.11'\n") == [], (
        "requires-python is not a classifier"
    )


def test_the_ruff_pin_check_catches_an_unpinned_install():
    """Planted: the three spellings of not pinning, and the one that is."""

    def lint(run: str) -> dict:
        return {"jobs": {"lint": {"steps": [{"run": run}]}}}

    assert _ruff_pin(lint("pip install ruff")) is None
    assert _ruff_pin(lint("pip install 'ruff>=0.5'")) is None
    assert _ruff_pin(lint("pip install ruff~=0.16")) is None
    assert _ruff_pin(lint("pip install ruff==0.16.7\nruff check .")) == "0.16.7"


def test_the_gate_check_fires_on_a_planted_gate_that_tolerates_a_skipped_leg():
    """Planted three ways, each the mistake a real workflow has shipped:
    a gate that checks only `failure` (so a skipped leg passes), a gate
    without `if: always()` (so a failed leg skips the gate itself), and a
    gate whose `needs` forgot a job. Then the shape this repo carries, which
    must clear."""

    def workflow(gate: dict) -> dict:
        return {"jobs": {"a": {}, "b": {}, "test": gate}}

    failure_only = workflow(
        {
            "needs": ["a", "b"],
            "if": "always()",
            "steps": [{"if": "${{ contains(needs.*.result, 'failure') }}", "run": "exit 1"}],
        }
    )
    assert any("skipped" in p for p in _gate_problems(failure_only)), _gate_problems(failure_only)

    not_always = workflow(
        {
            "needs": ["a", "b"],
            "steps": [{"env": {"NEEDS": "${{ toJSON(needs) }}"}, "run": 'assert r == "success"'}],
        }
    )
    assert any("always()" in p for p in _gate_problems(not_always)), _gate_problems(not_always)

    forgot_b = workflow(
        {
            "needs": ["a"],
            "if": "always()",
            "steps": [{"env": {"NEEDS": "${{ toJSON(needs) }}"}, "run": 'assert r == "success"'}],
        }
    )
    assert any("['b']" in p for p in _gate_problems(forgot_b)), _gate_problems(forgot_b)

    assert _gate_problems({"jobs": {"a": {}}}) == ["no `test` job"]

    explicit = workflow(
        {
            "needs": ["a", "b"],
            "if": "always()",
            "steps": [
                {"env": {"NEEDS": "${{ toJSON(needs) }}"}, "run": 'if r != "success": exit(1)'}
            ],
        }
    )
    assert _gate_problems(explicit) == []
    triple = workflow(
        {
            "needs": ["a", "b"],
            "if": "always()",
            "steps": [
                {
                    "if": "${{ contains(needs.*.result, 'failure') || "
                    "contains(needs.*.result, 'cancelled') || "
                    "contains(needs.*.result, 'skipped') }}",
                    "run": "exit 1",
                }
            ],
        }
    )
    assert _gate_problems(triple) == [], "the contains-triple is the other accepted spelling"
