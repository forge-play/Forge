"""G2-meta-scans-forge — the meta-scan: every AST/grep-guard helper this suite
carries has been shown to catch something, by a test that *calls it*.

*A scan that has never fired has not been shown to check anything* is this
repo's own rule (tests/test_changelog_dedup_docstring.py's docstring says it
in so many words, and tests/test_vendor_sync_check.py's plants follow it).
This file is that rule turned into a test that reads the *other* test files:
it finds every module-level helper in ``tests/`` that is shaped like a
violation-scanner and asserts that some planted-violation test in the *same
file* runs that helper — directly, or through another helper it calls.

This file is not a fresh design. It is homestead-ledger's
`tests/test_scans_fire.py` (itself the sibling drift sweeps' meta-scan,
copied for its shape), ported here on 2026-09-12 and re-grounded against this
repo's own test files. The discovery rule and the plant rule below are
homestead's, verified here rather than re-derived, because a meta-scan that
disagreed between repos about what counts as "planted" would be exactly the
kind of drift this sweep exists to close.

**What its first run here found**, closed in the same commit rather than
allow-listed: three module-level scans no plant had ever called —
tests/test_no_reach_back.py's `_imports_of` (the no-reach-back invariant's
whole reader; every file it scanned was clean, so it had never reported
anything), tests/test_changelog_dedup_docstring.py's `_module_docstring`
(its plant fed the matcher a string and skipped the reader), and
tests/test_release_wiring.py's `_names_a_non_suppressed_credential` (had
cleared real steps, never refused one) — and three scans written inline in a
test body with nothing to name and nothing to plant: tests/test_deposit.py's
covenant check on forge/deposit.py's source, tests/test_release_wiring.py's
AST read of pr-title.yml's `PACKAGED` tuple, and tests/test_bundle.py's "no
box path in the repo" check on the HEAD file a cut writes. Each now has a
helper and a plant in its own file, and the real-tree tests at the end of
this file hold two of those files as the worked examples.

**Discovery is structural, not a naming convention.** A rule that only
matched a leading underscore or a stem list would miss a public
`check_payload_reach(...)` (an AST-walking scan spelled the way a helper
meant to be imported is spelled) and a grep-shaped `forbidden_word_hits(path)`
that reads a file and asks `"payload" in text` with no `ast` and no matching
stem at all — both are planted below, alongside the real thing. So the rule
is what a scan *does*:

* it parses or walks source (`ast.parse`, `ast.walk`), **or**
* it matches text with a pattern (`re.search`/`findall`/`finditer`/`match`/
  `fullmatch`/`compile`, or a module-level compiled pattern's `.search(…)`),
  **or**
* it reads a file's text (`.read_text()`/`.read_bytes()`) *and* asks a
  membership question of it (`x in text`, `x not in parts`) — the grep shape
  with no regex in it, which tests/test_deposit.py's `_covenant_breaches` and
  tests/test_bundle.py's `_box_path_leaks` both are, **or**
* it walks a **module-level list of forbidden words** and asks membership of
  each — `[word for word in _COVENANT_WORDS if word in body]`. Homestead's
  first draft missed this shape entirely, and there it was the whole
  enforcement of one decision; here `_covenant_breaches` is that shape too.
  The rule is narrow on purpose — the iteration must be over a module-level
  *collection* constant and the body must ask an `in` question — because
  "references a constant and says `in` somewhere" reports ordinary tests, and
  a meta-scan that cries wolf gets an allowlist bolted to it and stops
  meaning anything, **or**
* it filters a list the *caller* handed it by membership of each item —
  the same grep with the word list hoisted to the call site.

The name stems and the `_is_` prefix are kept on top of that, not instead of
it: they still catch helpers that hand their work to a caller. Discovery is a
union, so it is strictly wider than either half alone.

**Having a plant means a plant test calls the scan.** A test called
`test_the_guard_fires` that never touches the guard has not fired it — the
word in a test's name is not the evidence. A helper counts as planted only
when a `test_*` function whose name or docstring carries `plant`, `fires` or
`catches` reaches it — through the module's own helpers as well as directly,
so a plant that calls a wrapper has exercised the parser underneath it too.
Both halves are planted below: the name-only plant test (a counter-example
that must still be reported) and the call-through-a-helper case (which must
not).

**Honest about what it still cannot see.** A helper that reaches `ast.parse`
through an alias (`from ast import parse as p`), one that shells out to
`grep`, or one whose whole check is a comparison of two already-read strings
with no membership test and no pattern, is outside the rule above. Closing
those needs an interpreter, not a reader; this scan is the AST-grep half, not
a promise that it sees everything a scan could be shaped like. One such case
is named rather than hidden: tests/test_vendor_sync_check.py's guard is a
hash comparison (`vsc.drifts() == []`) — no membership, no pattern, no AST —
so this file cannot see it, and that file carries its own plants for the
same reason this one carries its own.
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

#: Word-stems the repo's own scan helpers already use, split on "_" so
#: `_record_synced_offenders`-style names (offenders is the *last* word) and
#: `_reads_a_jsonl_path_with_bare_json_loads`-style names (reads is the
#: *first*) both match without over-firing on unrelated names.
_NAME_TOKENS = frozenset(
    {"scan", "scans", "reads", "calls", "offenders", "uses", "check", "checks", "guard", "guards"}
)

#: The convention this repo actually uses for "this scan was shown to fire on
#: a planted violation" — read off the real test names, not guessed. The word
#: is necessary; calling the scan is what makes it count.
_PLANT_NAME_WORDS = ("plant", "fires", "catches")

#: In a *docstring*, only "plant" counts. "fires" and "catches" are ordinary
#: prose about the thing under test — tests/test_release_wiring.py's
#: docstrings say "no tag workflow fires, nothing publishes", about GitHub's
#: event suppression and not about a plant at all, and in homestead exactly
#: that sentence was clearing a credential scan that had no plant (audit,
#: 2026-09-11). A word that common in a repo's own subject matter cannot
#: also be its evidence of a plant.
_PLANT_DOC_WORDS = ("plant",)

#: Pattern-matching methods. Matched on the attribute name alone, so both
#: `re.search(...)` and a module-level `_STRIKE_RE.finditer(...)` count — a
#: compiled pattern is the same scan with the compile hoisted.
_MATCH_CALLS = frozenset({"search", "findall", "finditer", "match", "fullmatch", "compile"})

#: Reading a file's text through `pathlib`. The grep half of a grep-shaped
#: scan, in the spelling this suite reaches for first.
_TEXT_READS = frozenset({"read_text", "read_bytes"})

#: The same read through an already-open handle — `open(p).read()` and the
#: `with open(p) as f: f.read()` spelling of it. A rule that knew only
#: `_TEXT_READS` cleared those, which was never a documented boundary — only
#: a spelling it had not been shown (homestead audit, 2026-09-11).
_HANDLE_READS = frozenset({"read", "readlines", "readline"})

#: Wrappers a read may be decoded or normalised through before the
#: membership question is asked — `p.read_bytes().decode()` is the same read
#: of the same file, and the text it yields is the text actually read.
_TEXT_WRAPPERS = frozenset({"decode", "strip", "lower", "upper", "casefold"})

#: Reading a module's source without naming a path. `inspect.getsource(obj)`
#: returns the real file's text; tests/test_deposit.py reads
#: `Path(deposit.__file__)` instead, but the `getsource` spelling is one
#: keystroke away and was invisible to homestead's first draft.
_SOURCE_READS = frozenset({"getsource", "getsourcelines"})


def _is_open_call(expr: ast.AST) -> bool:
    """A builtin `open(...)`, however its mode and encoding are spelled."""
    return isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "open"


def _open_handles(node: ast.AST) -> frozenset[str]:
    """Every local name bound to an `open(...)` — `with open(p) as f` and
    `f = open(p)` alike — so `f.read()` is recognised as the file read it
    is."""
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.withitem) and _is_open_call(sub.context_expr):
            if isinstance(sub.optional_vars, ast.Name):
                names.add(sub.optional_vars.id)
        elif isinstance(sub, ast.Assign) and _is_open_call(sub.value):
            names.update(t.id for t in sub.targets if isinstance(t, ast.Name))
    return frozenset(names)


def _is_read_call(expr: ast.AST, handles: frozenset[str] = frozenset()) -> bool:
    """True if `expr` itself reads a real file's text — `.read_text()`/
    `.read_bytes()`, `open(...).read()` or an open handle's `.read()`, or
    `inspect.getsource(...)` — through any number of decoding wrappers."""
    if not isinstance(expr, ast.Call) or not isinstance(expr.func, ast.Attribute):
        return False
    attr = expr.func.attr
    if attr in _TEXT_READS or attr in _SOURCE_READS:
        return True
    if attr in _HANDLE_READS:
        return _is_open_call(expr.func.value) or (
            isinstance(expr.func.value, ast.Name) and expr.func.value.id in handles
        )
    if attr in _TEXT_WRAPPERS:
        return _is_read_call(expr.func.value, handles)
    return False


def _calls_in(node: ast.AST):
    """Every `Call` anywhere inside `node`."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            yield sub


def _walks_source(node: ast.AST) -> bool:
    """True if the body calls `ast.parse(...)` or `ast.walk(...)` — the shape
    of a scan that reads source rather than trusting an already-parsed tree."""
    return any(
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "ast"
        and call.func.attr in ("parse", "walk")
        for call in _calls_in(node)
    )


def _matches_text(node: ast.AST) -> bool:
    """True if the body runs a pattern over text — `re.search(...)`, a
    compiled pattern's `.finditer(...)`, or a bare `compile(...)`."""
    for call in _calls_in(node):
        if isinstance(call.func, ast.Attribute) and call.func.attr in _MATCH_CALLS:
            return True
        if isinstance(call.func, ast.Name) and call.func.id == "compile":
            return True
    return False


def _reads_file_text(node: ast.AST) -> bool:
    """True if the body reads a file's text itself, in any of the spellings
    `_is_read_call` knows."""
    handles = _open_handles(node)
    return any(_is_read_call(call, handles) for call in _calls_in(node))


def _tests_membership(node: ast.AST) -> bool:
    """True if the body asks `x in y` / `x not in y` anywhere — the grep
    question, once the text is in hand."""
    return any(
        isinstance(sub, ast.Compare) and any(isinstance(op, (ast.In, ast.NotIn)) for op in sub.ops)
        for sub in ast.walk(node)
    )


def _module_collection_constants(tree: ast.Module) -> frozenset[str]:
    """Every module-level `ALL_CAPS` name bound to a collection literal (or to
    `frozenset(...)`/`set(...)`/`tuple(...)`/`list(...)`) — the shape a
    forbidden-word list is written in, in this repo and its siblings."""
    found: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id.isupper()):
                continue
            value = node.value
            if isinstance(value, (ast.Set, ast.List, ast.Tuple)) or (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in ("frozenset", "set", "tuple", "list")
            ):
                found.add(target.id)
    return frozenset(found)


def _scans_a_word_list(node: ast.AST, constants: frozenset[str]) -> bool:
    """True if the body iterates one of `constants` and asks a membership
    question inside that iteration — the forbidden-word-list scan."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.For):
            iterables, body = [sub.iter], sub.body
        elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            iterables, body = [g.iter for g in sub.generators], [sub]
        else:
            continue
        if not any(isinstance(it, ast.Name) and it.id in constants for it in iterables):
            continue
        if any(_tests_membership(part) for part in body):
            return True
    return False


def _decorator_name(dec: ast.AST) -> str:
    """A decorator's own terminal name: `pytest.fixture` -> "fixture",
    `pytest.mark.usefixtures(...)` -> "usefixtures"."""
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Attribute):
        return dec.attr
    if isinstance(dec, ast.Name):
        return dec.id
    return ""


def _filters_by_membership(node: ast.AST) -> bool:
    """True if the body loops over something and keeps the items that are
    (or are not) *in* something else — `[term for term in terms if term in
    haystack]`.

    `_scans_a_word_list` above wants the iterable to be a module-level
    constant, which is right for a helper owning its own forbidden list. A
    helper handed the terms as an argument is the same grep with the list
    hoisted to the caller (homestead's shared `terms_found`, twenty-one call
    sites, matched none of the four earlier shapes — audit, 2026-09-11).
    Narrow the same way: the membership question must be asked *of the loop
    variable itself*, so iterating a table and asserting something about a
    result is still not a scan.
    """
    for sub in ast.walk(node):
        if isinstance(sub, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            targets = {gen.target.id for gen in sub.generators if isinstance(gen.target, ast.Name)}
            conditions = [cond for gen in sub.generators for cond in gen.ifs]
        elif isinstance(sub, ast.For) and isinstance(sub.target, ast.Name):
            targets, conditions = {sub.target.id}, list(sub.body)
        else:
            continue
        for condition in conditions:
            for inner in ast.walk(condition):
                if (
                    isinstance(inner, ast.Compare)
                    and any(isinstance(op, (ast.In, ast.NotIn)) for op in inner.ops)
                    and isinstance(inner.left, ast.Name)
                    and inner.left.id in targets
                ):
                    return True
    return False


def _is_fixture(node: ast.FunctionDef) -> bool:
    """`@pytest.fixture` — setup, not a scan, whatever it reads.

    Matched on the decorator's *own terminal name*, not on the word
    "fixture" appearing anywhere in its dump: `@pytest.mark.usefixtures(...)`
    carries that word and is not a fixture, and reading it as one silently
    exempted the whole decorated test from both halves of this file
    (homestead audit, 2026-09-11).
    """
    return any(_decorator_name(dec) == "fixture" for dec in node.decorator_list)


def _is_scan_helper(node: ast.FunctionDef, constants: frozenset[str] = frozenset()) -> bool:
    """A module-level helper counts as a scan/guard if it is shaped like one
    (walks source, matches a pattern, reads a file and asks a membership
    question of it, walks a module-level word list asking membership of
    each, or filters the caller's list by membership) or its name carries
    one of the repo's own stems.

    Deliberately *not* conditioned on a leading underscore: a public
    `check_changelog_claim` is the same scan with a different name.
    """
    name = node.name
    if name.startswith("test_") or name.startswith("__"):
        return False
    if _is_fixture(node):
        return False
    if name.startswith("_is_"):
        return True
    if _NAME_TOKENS & set(name.strip("_").split("_")):
        return True
    return (
        _walks_source(node)
        or _matches_text(node)
        or (_reads_file_text(node) and _tests_membership(node))
        or _scans_a_word_list(node, constants)
        or _filters_by_membership(node)
    )


def _is_plant_test(node: ast.FunctionDef) -> bool:
    """True if `node` is a planted-violation test by this repo's convention:
    a plant word in its name, or the narrower "plant" in its docstring."""
    name = node.name.lower()
    doc = (ast.get_docstring(node) or "").lower()
    return any(word in name for word in _PLANT_NAME_WORDS) or any(
        word in doc for word in _PLANT_DOC_WORDS
    )


def _module_helpers(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Every module-level, non-test function in one tests module, by name."""
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("test_")
    }


def _scan_helpers(source: str) -> list[str]:
    """Every module-level scan-helper function name in one tests module."""
    tree = ast.parse(source)
    constants = _module_collection_constants(tree)
    return sorted(
        name for name, node in _module_helpers(tree).items() if _is_scan_helper(node, constants)
    )


def _direct_calls(node: ast.AST, known: dict[str, ast.FunctionDef]) -> set[str]:
    """The module's own helpers this node calls by bare name."""
    return {
        call.func.id
        for call in _calls_in(node)
        if isinstance(call.func, ast.Name) and call.func.id in known
    }


def _helpers_the_plants_exercise(source: str) -> set[str]:
    """Every helper reachable from a planted-violation test in this module.

    A test counts as a plant test when its **name** carries one of
    `_PLANT_NAME_WORDS`, or its docstring carries one of the narrower
    `_PLANT_DOC_WORDS`; from there the reach is transitive through the
    module's own helpers, because a plant that calls a wrapper has exercised
    the helper underneath it just as surely as if it had called it by hand.
    """
    tree = ast.parse(source)
    helpers = _module_helpers(tree)
    reached: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
            continue
        if not _is_plant_test(node):
            continue
        pending = list(_direct_calls(node, helpers))
        while pending:
            name = pending.pop()
            if name in reached:
                continue
            reached.add(name)
            pending.extend(_direct_calls(helpers[name], helpers))
    return reached


def _unplanted_scan_helpers(source: str) -> list[str]:
    """The scan helpers in one tests module that no planted-violation test in
    the same module ever calls."""
    exercised = _helpers_the_plants_exercise(source)
    return [name for name in _scan_helpers(source) if name not in exercised]


#: A shared scan module, if this repo ever grows one. Homestead keeps helpers
#: three or more test modules call in `tests/_scans.py`; it is not a
#: `test_*.py` file, so it holds no plant tests of its own and the same-file
#: rule above cannot reach it — while `_global_scan_helper_names()` below
#: would happily use its helpers to *clear* inline scans elsewhere. A helper
#: that can excuse a test and can never be made to fire is the exact
#: asymmetry this file exists to forbid, so the shared module is swept too,
#: against plants anywhere in `tests/`. This repo has no such module today
#: (every scan helper lives beside its plant); the sweep is kept, planted
#: against a fake one, so the day it appears it is already held.
SHARED_SCANS = TESTS_DIR / "_scans.py"


def _import_aliases(tree: ast.Module) -> dict[str, str]:
    """`from tests._scans import terms_found as tf` -> `{"tf": "terms_found"}`,
    for imports anywhere in the module, function bodies included."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    aliases[alias.asname] = alias.name
    return aliases


def _called_names(node: ast.AST, aliases: dict[str, str]) -> set[str]:
    """Every name `node` calls: bare (resolved through `aliases`) or through
    an attribute — `helper(...)`, `tf(...)`, `module.helper(...)` are one
    delegation by three routes."""
    names: set[str] = set()
    for call in _calls_in(node):
        if isinstance(call.func, ast.Name):
            names.add(aliases.get(call.func.id, call.func.id))
        elif isinstance(call.func, ast.Attribute):
            names.add(call.func.attr)
    return names


def _names_the_plants_call(source: str) -> frozenset[str]:
    """Every name a planted-violation test in this module calls — directly,
    or through the module's own helpers, whichever module actually defines
    the name it calls."""
    tree = ast.parse(source)
    helpers = _module_helpers(tree)
    aliases = _import_aliases(tree)
    called: set[str] = set()
    walked: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("test_")):
            continue
        if not _is_plant_test(node):
            continue
        called |= _called_names(node, aliases)
        pending = list(_direct_calls(node, helpers))
        while pending:
            name = pending.pop()
            if name in walked:
                continue
            walked.add(name)
            called |= _called_names(helpers[name], aliases)
            pending.extend(_direct_calls(helpers[name], helpers))
    return frozenset(called)


def _unplanted_shared_scan_helpers(shared: Path = SHARED_SCANS) -> list[str]:
    """The scan helpers in the shared module that no planted-violation test
    anywhere in `tests/` ever calls. Cross-module by construction: the
    shared module has no plant tests of its own, and the plant that proves a
    shared helper belongs with the caller that relies on it. Empty when
    there is no shared module."""
    if not shared.exists():
        return []
    exercised: set[str] = set()
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == "test_scans_fire.py":
            continue
        exercised |= _names_the_plants_call(path.read_text(encoding="utf-8"))
    return [
        name for name in _scan_helpers(shared.read_text(encoding="utf-8")) if name not in exercised
    ]


def _offenders() -> list[str]:
    """Every tests/*.py file that defines a scan helper no plant test in the
    same file calls — and the shared module, if any, whose helpers are held
    to a plant anywhere in `tests/`."""
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == "test_scans_fire.py":
            continue  # this file's own helpers are proven below, not here
        unplanted = _unplanted_scan_helpers(path.read_text(encoding="utf-8"))
        if unplanted:
            offenders.append(f"{path.name}: {unplanted}")
    shared_unplanted = _unplanted_shared_scan_helpers()
    if shared_unplanted:
        offenders.append(f"{SHARED_SCANS.name}: {shared_unplanted}")
    return offenders


def test_every_scan_helper_has_a_planted_violation_test():
    """The house rule, run for real: no `tests/*.py` file may carry an
    AST/grep-guard helper that no planted-violation test in the same file
    actually runs."""
    offenders = _offenders()
    assert not offenders, (
        "these test files define a scan helper (it walks source, matches a "
        "pattern, or reads a file and asks a membership question of it — or "
        f"its name carries one of {sorted(_NAME_TOKENS)}) that no test naming "
        "plant/fires/catches ever calls — a scan that has never fired has not "
        f"been shown to check anything: {offenders}"
    )


# ── the discovery half, planted twice: AST-shaped and grep-shaped ────────────


def _write(tmp_path: Path, name: str, body: str) -> str:
    """A fake tests module on disk, read back the way `_offenders()` reads a
    real one."""
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path.read_text(encoding="utf-8")


def test_the_meta_scan_finds_an_ast_shaped_scan_whatever_it_is_named(tmp_path):
    """Planted: a scan that walks `ast` under a **public** name. A rule that
    required a leading underscore would miss `check_payload_reach` — the same
    scan, spelled the way a helper meant to be imported is spelled — and its
    missing plant would go unreported. (This repo's
    `check_changelog_claim` is public for exactly that reason.)"""
    source = _write(
        tmp_path,
        "test_planted_ast_shaped_scan.py",
        "import ast\n"
        "\n"
        "def check_payload_reach(source):\n"
        "    return [n for n in ast.walk(ast.parse(source))\n"
        "            if isinstance(n, ast.Attribute) and n.attr == 'payload']\n"
        "\n"
        "def test_nothing_reaches_a_payload():\n"
        "    assert not check_payload_reach('x = 1\\n')\n",
    )

    assert _scan_helpers(source) == ["check_payload_reach"], (
        "an ast.parse/ast.walk scan must be found under any name, public or "
        f"private; got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["check_payload_reach"], (
        "and with no planted-violation test in the file it must be reported"
    )


def test_the_meta_scan_finds_a_grep_shaped_scan(tmp_path):
    """Planted: a scan with no `ast` in it at all — `path.read_text()` and an
    `in`. The repo has this shape already (tests/test_bundle.py's
    `_box_path_leaks`), and a discovery rule that only knew about `ast`
    would clear a file whose only guard is this shape."""
    source = _write(
        tmp_path,
        "test_planted_grep_shaped_scan.py",
        "def forbidden_word_hits(path):\n"
        "    return 'payload' in path.read_text(encoding='utf-8')\n"
        "\n"
        "def test_no_module_says_payload(tmp_path):\n"
        "    probe = tmp_path / 'm.py'\n"
        "    probe.write_text('x = 1\\n', encoding='utf-8')\n"
        "    assert not forbidden_word_hits(probe)\n",
    )

    assert _scan_helpers(source) == ["forbidden_word_hits"], (
        "a read_text()+`in` scan is a scan; the name carries none of the "
        f"repo's stems, which is the point. Got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["forbidden_word_hits"]


def test_a_fixture_is_not_mistaken_for_a_scan(tmp_path):
    """The other side of the same honesty: `@pytest.fixture` setup that reads
    a file must not be reported, or the meta-scan cries wolf on every suite
    that stages a tmp home."""
    source = _write(
        tmp_path,
        "test_planted_fixture_only.py",
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def home(tmp_path):\n"
        "    (tmp_path / 'seed').write_text('x', encoding='utf-8')\n"
        "    return 'seed' in (tmp_path / 'seed').read_text(encoding='utf-8')\n"
        "\n"
        "def test_it(home):\n"
        "    assert home\n",
    )
    assert _scan_helpers(source) == []


# ── the plant half: naming a test "fires" is not having fired ────────────────


def test_the_plant_check_requires_the_plant_test_to_call_the_scan(tmp_path):
    """The counter-example, planted. A file whose only "plant" is a test
    *named* `test_the_scan_fires` and whose body never touches the scan must
    still be reported — a plant word in a name is not a plant."""
    source = _write(
        tmp_path,
        "test_planted_name_only_plant.py",
        "import ast\n"
        "\n"
        "def _payload_reaches(tree):\n"
        "    return [n for n in ast.walk(tree)\n"
        "            if isinstance(n, ast.Attribute) and n.attr == 'payload']\n"
        "\n"
        "def test_the_scan_fires_on_a_planted_violation():\n"
        "    '''Says it plants. Plants nothing.'''\n"
        "    assert True\n",
    )

    assert _scan_helpers(source) == ["_payload_reaches"]
    assert _unplanted_scan_helpers(source) == ["_payload_reaches"], (
        "a plant test that never calls the scan has not fired it; the word in "
        "the test's name is not the evidence"
    )


def test_a_plant_that_calls_the_scan_through_a_helper_clears_it(tmp_path):
    """And not over-strict: a real plant might call a wrapper rather than the
    parser underneath it — tests/test_no_reach_back.py's plant calls
    `_forbidden_imports`, which calls `_imports_of`. Reaching a helper
    through another helper is having exercised it, so neither may be
    reported."""
    source = _write(
        tmp_path,
        "test_planted_indirect_plant.py",
        "import ast\n"
        "\n"
        "def _payload_reaches(tree):\n"
        "    return [n for n in ast.walk(tree)\n"
        "            if isinstance(n, ast.Attribute) and n.attr == 'payload']\n"
        "\n"
        "def _offenders_in(source):\n"
        "    return _payload_reaches(ast.parse(source))\n"
        "\n"
        "def test_the_scan_catches_a_planted_reach():\n"
        "    assert _offenders_in('y = r.payload\\n')\n",
    )

    assert _scan_helpers(source) == ["_offenders_in", "_payload_reaches"]
    assert _unplanted_scan_helpers(source) == [], (
        "both the wrapper and the helper it calls were exercised by the plant"
    )


def test_the_plant_check_does_not_fire_on_a_real_guarded_file():
    """The whole thing against a real file of this repo's:
    tests/test_no_reach_back.py defines the AST reader (`_imports_of`) and
    plants it through its filter (`_forbidden_imports`), so the meta-scan
    must clear it — or it would be crying wolf on the very file this bite
    planted first. The filter itself is *not* a scan by the rule: it asks
    `n == r or n.startswith(...)` of names already read, never an `in`, never
    a pattern, never a file — the first draft of this test expected it to be
    counted, and the rule was right not to. The plant reaches the reader
    through it all the same."""
    source = (TESTS_DIR / "test_no_reach_back.py").read_text(encoding="utf-8")
    assert _scan_helpers(source) == ["_imports_of"], (
        "test_no_reach_back.py is expected to define exactly this scan helper"
    )
    assert "_forbidden_imports" in _helpers_the_plants_exercise(source)
    assert _unplanted_scan_helpers(source) == []


# ── the two shapes homestead's first draft could not see ────────────────────


def test_the_meta_scan_finds_a_regex_shaped_scan(tmp_path):
    """Planted: the third shape. A scan whose whole body is a module-level
    compiled pattern run over text — no `ast`, no `read_text`, and a name
    (`banned_spellings`) carrying none of the repo's stems.
    tests/test_changelog_dedup_docstring.py's `check_changelog_claim` is this
    shape (its name carries `check`, which would also have caught it; the
    pattern rule is what catches the one that does not)."""
    source = _write(
        tmp_path,
        "test_planted_regex_shaped_scan.py",
        "import re\n"
        "\n"
        "_BANNED = re.compile(r'innerHTML')\n"
        "\n"
        "def banned_spellings(page):\n"
        "    return _BANNED.findall(page)\n"
        "\n"
        "def test_the_page_builds_no_markup():\n"
        "    assert not banned_spellings('x')\n",
    )

    assert _scan_helpers(source) == ["banned_spellings"], (
        f"a compiled-pattern scan is a scan; got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["banned_spellings"]


def test_the_meta_scan_finds_a_forbidden_word_list_scan(tmp_path):
    """Planted: the fourth shape. A helper that walks a module-level word
    list asking membership of text its caller hands it — it reads no file,
    compiles no pattern, parses no source, and its name carries no stem, so
    the first three rules all clear it. In homestead that was one decision's
    entire enforcement, unseen."""
    source = _write(
        tmp_path,
        "test_planted_word_list_scan.py",
        "FORBIDDEN_PHRASES = ('official form', 'you should file')\n"
        "\n"
        "def phrase_hits(text):\n"
        "    return [p for p in FORBIDDEN_PHRASES if p in text]\n"
        "\n"
        "def test_the_package_says_none_of_them():\n"
        "    assert not phrase_hits('a maker keeps their own rationale')\n",
    )

    assert _scan_helpers(source) == ["phrase_hits"], (
        "a scan that walks a module-level word list asking membership of each "
        f"is a scan; got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["phrase_hits"]


def test_the_word_list_rule_does_not_fire_on_ordinary_constant_use(tmp_path):
    """The control the narrow rule exists for. A behaviour test that iterates
    a module-level table and asserts membership of a *result* is not a scan,
    and a rule loose enough to call it one reports the parametrised tables
    all over this suite and gets itself allowlisted into silence."""
    source = _write(
        tmp_path,
        "test_planted_ordinary_constant_use.py",
        "BANDS = ('auto', 'recognize')\n"
        "\n"
        "def detect(rows):\n"
        "    return rows[0]\n"
        "\n"
        "def test_every_band_round_trips():\n"
        "    for b in BANDS:\n"
        "        assert b in ('auto', 'recognize', 'socratic')\n",
    )
    assert _scan_helpers(source) == []


def test_the_meta_scan_finds_a_scan_handed_its_word_list_by_the_caller(tmp_path):
    """Planted: the fifth shape. `terms_found(haystack, terms)` walks the
    *caller's* list asking membership of each — no module-level constant, no
    regex, no read, no stem in its name — so all four earlier rules clear it
    (homestead's shared helper, twenty-one call sites, matched none of them
    — audit, 2026-09-11)."""
    source = _write(
        tmp_path,
        "test_planted_caller_word_list.py",
        "def terms_found(haystack, terms):\n"
        "    return [term for term in terms if term in haystack]\n"
        "\n"
        "def test_the_log_carries_none_of_them():\n"
        "    assert not terms_found('a reference only', ('1234',))\n",
    )
    assert _scan_helpers(source) == ["terms_found"], (
        "a helper that filters the caller's terms by membership is a scan; "
        f"got {_scan_helpers(source)}"
    )
    assert _unplanted_scan_helpers(source) == ["terms_found"]


def test_the_caller_word_list_rule_does_not_fire_on_an_ordinary_filter(tmp_path):
    """The control the narrow half exists for: the membership question must
    be asked *of the loop variable itself*. A helper that filters rows by a
    field, or builds a list from a table, is ordinary code and a rule loose
    enough to report it gets an allow-list bolted on and stops meaning
    anything."""
    source = _write(
        tmp_path,
        "test_planted_ordinary_filter.py",
        "KNOWN = ('auto', 'socratic')\n"
        "\n"
        "def due_rows(rows):\n"
        "    return [row for row in rows if row[1] in KNOWN]\n"
        "\n"
        "def test_it():\n"
        "    assert due_rows([]) == []\n",
    )
    assert _scan_helpers(source) == []


def test_a_plant_reaches_a_shared_helper_through_an_import_alias(tmp_path):
    """The shared module's proof is cross-module, so the reach has to follow
    the routes a cross-module call actually takes: a bare name, an attribute
    (`module.helper(...)`), and the `import ... as` alias a caller may bind
    it to. A rule that only matched the bare original name would read this
    plant as calling nothing. (Fake modules: this repo has no `tests/_scans`
    yet; nothing here is imported, only parsed.)"""
    source = _write(
        tmp_path,
        "test_planted_aliased_plant.py",
        "from tests._scans import terms_found as tf\n"
        "from tests import _scans\n"
        "\n"
        "def test_the_shared_scan_catches_a_planted_leak():\n"
        "    assert tf('a line naming 1234', ('1234',)) == ['1234']\n"
        "    assert _scans.other_helper('x') == []\n",
    )
    reached = _names_the_plants_call(source)
    assert "terms_found" in reached, "an aliased call is still a call"
    assert "other_helper" in reached, "and so is `module.helper(...)`"

    quiet = _write(
        tmp_path,
        "test_planted_quiet_plant.py",
        "from tests._scans import terms_found as tf\n"
        "\n"
        "def test_the_shared_scan_catches_a_planted_leak():\n"
        "    assert True\n",
    )
    assert _names_the_plants_call(quiet) == frozenset(), (
        "importing a helper is not calling it; the plant word in the name is "
        "not the evidence here either"
    )


def test_the_shared_module_sweep_fires_on_a_planted_unreached_helper(tmp_path):
    """This repo has no shared scan module today, so the sweep must be
    vacuously clean against the real tree — and it must not be *only*
    vacuous: planted, a fake shared module with one helper no plant in
    `tests/` calls must be reported, and one every real plant reaches would
    not be. `_unplanted_shared_scan_helpers` takes the module path for
    exactly this."""
    assert not SHARED_SCANS.exists(), (
        "a tests/_scans.py appeared: keep this test, and know the sweep now "
        "holds it against plants anywhere in tests/"
    )
    assert _unplanted_shared_scan_helpers() == []

    fake = tmp_path / "_scans.py"
    fake.write_text(
        "def terms_found(haystack, terms):\n"
        "    return [term for term in terms if term in haystack]\n"
        "\n"
        "def nobody_calls_this(path):\n"
        "    return 'x' in path.read_text(encoding='utf-8')\n",
        encoding="utf-8",
    )
    reported = _unplanted_shared_scan_helpers(fake)
    assert "nobody_calls_this" in reported, reported
    assert "terms_found" in reported, (
        "no real plant in this repo's tests/ calls a `terms_found` either; "
        "the day one does, this line is the one to change"
    )


# ── the plant rule: "fires" in prose is not evidence of a plant ─────────────


def test_a_docstring_saying_fires_about_something_else_does_not_clear_a_scan(tmp_path):
    """The counter-example homestead found live, and this repo has the same
    sentence: tests/test_release_wiring.py's docstrings say "no tag workflow
    fires" — prose about GitHub's event suppression, not about a plant. Only
    "plant" counts in a docstring; "fires" and "catches" count in a test's
    name, where they are deliberate."""
    source = _write(
        tmp_path,
        "test_planted_prose_fires.py",
        "import ast\n"
        "\n"
        "def _reaches(tree):\n"
        "    return [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)]\n"
        "\n"
        "def test_the_workflow_publishes():\n"
        "    '''No tag workflow fires, so nothing publishes and nothing catches it.'''\n"
        "    assert _reaches(ast.parse('a.b\\n'))\n",
    )

    assert _scan_helpers(source) == ["_reaches"]
    assert _unplanted_scan_helpers(source) == ["_reaches"], (
        "prose using the word 'fires' is not a plant; the scan is still "
        "unproven and must still be reported"
    )


def test_a_docstring_that_says_planted_does_clear_the_scan(tmp_path):
    """And the other side, so the tightening cannot be a blanket refusal: a
    test whose name carries no plant word but whose docstring says it plants,
    and which calls the scan, has fired it."""
    source = _write(
        tmp_path,
        "test_planted_docstring_plant.py",
        "import ast\n"
        "\n"
        "def _reaches(tree):\n"
        "    return [n for n in ast.walk(tree) if isinstance(n, ast.Attribute)]\n"
        "\n"
        "def test_a_reach_is_reported():\n"
        "    '''Planted: a module that does reach an attribute.'''\n"
        "    assert _reaches(ast.parse('a.b\\n'))\n",
    )
    assert _scan_helpers(source) == ["_reaches"]
    assert _unplanted_scan_helpers(source) == []


# ── the inline half: a scan written directly in a test's own body ───────────
#
# Everything above reads *module-level helpers*. A guard written inline, in a
# test's own body, with nothing to name and nothing to plant, is invisible to
# it — and this repo had three on 2026-09-12: tests/test_deposit.py's
# covenant check read forge/deposit.py and asked `word not in body` in the
# test itself; tests/test_release_wiring.py's pr-title test parsed the
# workflow's embedded Python and walked the tree with `isinstance(n,
# ast.Assign)` inline; tests/test_bundle.py's cut test asked `str(home) not
# in head.read_text()` of the file it had just written. All three are
# factored out and planted now. This half closes the gap for the next one: it
# walks every `test_*` function's own body for the same shapes the
# module-helper half already knows, holds it to the same "reads a file, not a
# string it built" requirement, and clears a test that delegates to a scan
# helper already defined (and already required to be planted) somewhere in
# `tests/` — recognized by name, whichever module actually owns it, since
# `from tests.test_x import _helper` and a bare call to a same-file helper
# are the same delegation by a different route.
#
# "Asks a membership question of it" is held to the text actually read, not
# to anything built from it: a name bound directly to a `.read_text()`/
# `.read_bytes()` call (one level, no chain through `json.loads` or the
# like) counts; a dict key or a `Path.parents` check several steps removed
# does not. Loosening that would also catch `"version" in pyproject["project"]`
# and every `_yaml(...)["jobs"]` assertion in tests/test_release_wiring.py,
# which have nothing to do with scanning a tree, and a rule that cries wolf
# on those gets an allowlist bolted onto it and stops meaning anything.


#: String operations that narrow text without turning it into something
#: else: `source.split('"""', 2)[2]` is still the file's own text (that is
#: exactly how `_covenant_breaches` carves off a docstring), and a membership
#: question of it is still a question of the tree. The list is deliberately
#: all `str`/`bytes` methods — `json.loads(...)` is a bare call to a *name*,
#: not one of these, so a dict built from a read is still several steps
#: removed and still not a scan.
_TEXT_SLICERS = _TEXT_WRAPPERS | frozenset(
    {
        "split",
        "rsplit",
        "splitlines",
        "partition",
        "rpartition",
        "replace",
        "lstrip",
        "rstrip",
        "removeprefix",
        "removesuffix",
    }
)


def _text_root(expr: ast.AST) -> ast.AST:
    """Peel subscripts and `_TEXT_SLICERS` calls off `expr` and return what
    the text ultimately came from."""
    while True:
        if isinstance(expr, ast.Subscript):
            expr = expr.value
        elif (
            isinstance(expr, ast.Call)
            and isinstance(expr.func, ast.Attribute)
            and expr.func.attr in _TEXT_SLICERS
        ):
            expr = expr.func.value
        else:
            return expr


def _direct_text_names(func: ast.FunctionDef) -> frozenset[str]:
    """Local names holding the text of a file this function read — bound
    straight from the read, or from a slice of one such name through
    `_TEXT_SLICERS` alone. Nothing that turns the text into another kind of
    object (`json.loads`, `tomllib.loads`, a `Path.parents`) is traced, so
    `"version" in pyproject["project"]` stays the ordinary assertion it is."""
    handles = _open_handles(func)
    names: set[str] = set()
    assigns = [
        (
            [t.id for t in node.targets if isinstance(t, ast.Name)],
            _text_root(node.value),
        )
        for node in ast.walk(func)
        if isinstance(node, ast.Assign)
    ]
    for _ in range(len(assigns) + 1):  # to a fixed point; each pass adds ≥1 or stops
        grew = False
        for targets, root in assigns:
            if not targets or set(targets) <= names:
                continue
            if _is_read_call(root, handles) or (isinstance(root, ast.Name) and root.id in names):
                names.update(targets)
                grew = True
        if not grew:
            break
    return frozenset(names)


def _is_text_source(expr: ast.AST, direct_names: frozenset[str], handles: frozenset[str]) -> bool:
    root = _text_root(expr)
    return _is_read_call(root, handles) or (isinstance(root, ast.Name) and root.id in direct_names)


def _membership_on_read_text(node: ast.FunctionDef) -> bool:
    """A membership test whose text side is a file read — directly, or
    through a name `_direct_text_names` traces back to one."""
    direct_names = _direct_text_names(node)
    handles = _open_handles(node)
    for sub in ast.walk(node):
        if isinstance(sub, ast.Compare) and any(
            isinstance(op, (ast.In, ast.NotIn)) for op in sub.ops
        ):
            if any(
                _is_text_source(operand, direct_names, handles)
                for operand in (sub.left, *sub.comparators)
            ):
                return True
    return False


def _isinstance_against_ast_type(node: ast.AST) -> bool:
    """True if the body itself calls `isinstance(x, ast.SomeType)` (or a
    tuple containing one) — the direct judgment of a source walk, as against
    a test that merely calls `ast.parse()` and hands the tree to a scan
    helper already defined (and already planted) elsewhere."""
    for call in _calls_in(node):
        if isinstance(call.func, ast.Name) and call.func.id == "isinstance" and len(call.args) == 2:
            type_arg = call.args[1]
            candidates = type_arg.elts if isinstance(type_arg, ast.Tuple) else [type_arg]
            for candidate in candidates:
                if (
                    isinstance(candidate, ast.Attribute)
                    and isinstance(candidate.value, ast.Name)
                    and candidate.value.id == "ast"
                ):
                    return True
    return False


def _global_scan_helper_names() -> frozenset[str]:
    """Every scan-helper name defined anywhere in `tests/` — every
    `test_*.py` file (this one excluded — its own helpers are proven above,
    not by this rule) plus the shared module, if there is one. A test that
    calls one of these by name — bare, or through `module.helper(...)` — is
    delegating to a helper the module-helper half already holds to its own
    plant, wherever that helper actually lives."""
    names: set[str] = set()
    paths = sorted(TESTS_DIR.glob("test_*.py"))
    if SHARED_SCANS.exists():
        paths.append(SHARED_SCANS)
    for path in paths:
        if path.name == "test_scans_fire.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _module_collection_constants(tree)
        for name, fn in _module_helpers(tree).items():
            if _is_scan_helper(fn, constants):
                names.add(name)
    return frozenset(names)


def _imported_names(tree: ast.Module) -> frozenset[str]:
    """Every name this module binds with `from ... import name` (or `as`),
    anywhere — function-body imports included, which is how a test most
    often reaches another module's scan helper."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return frozenset(names)


def _calls_any_by_name(
    node: ast.AST, bare: frozenset[str], attrs: frozenset[str] | None = None
) -> bool:
    """True if `node` delegates to a known scan helper: a bare call to one of
    `bare`, or `module.helper(...)` for one of `attrs`.

    The two sets differ on purpose. An attribute call names the module it
    comes from, so matching the attribute alone is safe. A *bare* name is
    only that helper if this module actually has it — imported, or defined
    here — otherwise a local function that happens to share a name with some
    other module's scan helper would clear every inline scan beside it
    (homestead audit, 2026-09-11).
    """
    attrs = bare if attrs is None else attrs
    for call in _calls_in(node):
        if isinstance(call.func, ast.Name) and call.func.id in bare:
            return True
        if isinstance(call.func, ast.Attribute) and call.func.attr in attrs:
            return True
    return False


def _resolvable_helpers(source: str, global_helpers: frozenset[str]) -> frozenset[str]:
    """The known scan helpers this module can reach by a *bare* name: the
    ones it imports, and the ones it defines itself."""
    tree = ast.parse(source)
    return global_helpers & (_imported_names(tree) | frozenset(_scan_helpers(source)))


def _is_inline_scan(
    node: ast.AST,
    global_helpers: frozenset[str],
    bare_helpers: frozenset[str] | None = None,
) -> bool:
    """A test body counts as an inline scan when it reads a real file and,
    in its own body — not by calling a scan helper `tests/` already defines
    somewhere — walks source and judges it directly (`ast.parse`/`ast.walk`
    plus an `isinstance` against an `ast.*` type), matches a pattern, or asks
    a membership question of the text it read.

    **Delegation clears the whole test, deliberately.** A test that calls a
    known scan helper is not reported even if it also asks its own `in`
    question of the text it read, because that second question is typically
    the fixture precondition of the first — "the file really does carry the
    thing I am about to plant" — and a stricter rule would push those
    preconditions out of sight. The cost is real and named: an unplanted
    inline `in` hidden behind a delegated call is not seen.
    """
    if not (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ):
        return False
    if _is_fixture(node):
        return False
    if not _reads_file_text(node):
        return False  # not reading a real file — a string the test built
    bare = global_helpers if bare_helpers is None else bare_helpers
    if _calls_any_by_name(node, bare, global_helpers):
        return False  # delegates to a helper already held to its own plant
    return (
        (_walks_source(node) and _isinstance_against_ast_type(node))
        or _matches_text(node)
        or _membership_on_read_text(node)
    )


def _test_functions(tree: ast.Module):
    """Every test function in a module, by the name a failure would report
    it as: module-level `def test_*`/`async def test_*`, and the methods of
    a `class Test*` — a rule that read only `tree.body` could never see a
    scan in one."""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for method in node.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{node.name}::{method.name}", method


def _inline_scan_tests(source: str, global_helpers: frozenset[str]) -> list[str]:
    """Every test function in one tests module whose own body is itself a
    scan by the rule above."""
    tree = ast.parse(source)
    bare = _resolvable_helpers(source, global_helpers)
    return sorted(
        name for name, node in _test_functions(tree) if _is_inline_scan(node, global_helpers, bare)
    )


def _inline_scan_offenders() -> list[str]:
    """Every `file::test_name` in `tests/*.py` whose own body is itself an
    unfactored scan."""
    global_helpers = _global_scan_helper_names()
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == "test_scans_fire.py":
            continue
        for name in _inline_scan_tests(path.read_text(encoding="utf-8"), global_helpers):
            offenders.append(f"{path.name}::{name}")
    return offenders


def test_no_test_body_is_itself_a_scan():
    """The inline half of the house rule: a guard written directly in a
    test's body, with no helper to name and plant, is invisible to the scan
    above and can never be shown to fire. Every `tests/*.py` test must
    either not be a scan by the shapes above, or delegate to a scan helper
    `tests/` already defines and plants — in the same file, another test
    module, or a shared module."""
    offenders = _inline_scan_offenders()
    assert not offenders, (
        "these tests are themselves a scan (reads a real file, then walks "
        "its source and judges it, matches a pattern, or asks a membership "
        "question of the text) with no scan helper behind them anywhere in "
        f"tests/, so the scan has never been planted: {offenders}"
    )


def test_the_inline_scan_check_finds_a_scan_written_directly_in_a_test_body(tmp_path):
    """Planted: a test file whose only guard is written inline — `ast.parse`
    plus a direct `isinstance` walk, on a file the test actually reads (via
    `tmp_path`, not a string built in place) — the shape
    tests/test_release_wiring.py's pr-title test had before this bite
    factored it out. No helper exists anywhere for it to delegate to, so it
    must be reported."""
    target = tmp_path / "target.py"
    target.write_text("import banned\n", encoding="utf-8")
    source = _write(
        tmp_path,
        "test_planted_inline_scan.py",
        "import ast\n"
        "from pathlib import Path\n"
        f"TARGET = Path({str(target)!r})\n"
        "\n"
        "def test_no_banned_import_at_module_scope():\n"
        "    tree = ast.parse(TARGET.read_text('utf-8'))\n"
        "    for node in tree.body:\n"
        "        if isinstance(node, ast.Import):\n"
        "            assert 'banned' not in {a.name for a in node.names}\n",
    )
    assert _inline_scan_tests(source, frozenset()) == ["test_no_banned_import_at_module_scope"]


def test_the_inline_scan_check_knows_every_spelling_of_reading_a_real_file(tmp_path):
    """Planted, one per spelling homestead's first pass did not know.
    `read_text` was the only read it recognised, so the same scan written
    with the builtin `open`, with a `with` block, through
    `read_bytes().decode()`, or through `inspect.getsource` was cleared —
    not by a documented rule, just by a spelling it had not been shown."""
    spellings = {
        "open_chain": "    text = open('x', encoding='utf-8').read()\n",
        "open_with": (
            "    with open('x', encoding='utf-8') as handle:\n        text = handle.read()\n"
        ),
        "read_bytes_decode": "    text = Path('x').read_bytes().decode()\n",
        "getsource": "    text = inspect.getsource(Path)\n",
    }
    for label, read in spellings.items():
        source = _write(
            tmp_path,
            f"test_planted_read_{label}.py",
            "import inspect\n"
            "from pathlib import Path\n"
            "\n"
            "def test_no_banned_word():\n"
            f"{read}"
            "    assert 'banned' not in text\n",
        )
        assert _inline_scan_tests(source, frozenset()) == ["test_no_banned_word"], (
            f"reading a real file via {label} is reading a real file"
        )


def test_the_inline_scan_check_follows_a_slice_of_the_text_but_not_a_parse_of_it(tmp_path):
    """The boundary the one-level rule draws, planted both ways. A `.split()`
    of the text read is still that text — tests/test_deposit.py's covenant
    check carves the docstring off with exactly `src.split('\"\"\"', 2)[2]`,
    and was this shape inline before this bite — but a dict `json.loads`
    built from it is another kind of object, and asking membership of *that*
    is the ordinary assertion this rule must not cry wolf on."""
    sliced = _write(
        tmp_path,
        "test_planted_sliced_text.py",
        "from pathlib import Path\n"
        "\n"
        "def test_the_body_names_no_seal():\n"
        "    source = Path('x').read_text(encoding='utf-8')\n"
        '    body = source.split(\'"""\', 2)[2]\n'
        "    assert 'seal(' not in body\n",
    )
    assert _inline_scan_tests(sliced, frozenset()) == ["test_the_body_names_no_seal"]

    parsed = _write(
        tmp_path,
        "test_planted_parsed_text.py",
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "def test_the_document_declares_a_version():\n"
        "    loaded = json.loads(Path('x').read_text(encoding='utf-8'))\n"
        "    assert 'version' in loaded['project']\n",
    )
    assert _inline_scan_tests(parsed, frozenset()) == [], (
        "a dict parsed out of the text is not the text; a rule that reported "
        "this gets an allow-list bolted to it and stops meaning anything"
    )


def test_the_inline_scan_check_does_not_fire_on_a_string_the_test_built(tmp_path):
    """Planted: a test that matches a pattern, but only against a string
    literal it built itself — no `.read_text()`/`.read_bytes()` anywhere.
    Not a scan of the tree, so it must not be reported."""
    source = _write(
        tmp_path,
        "test_planted_string_literal_match.py",
        "import re\n"
        "\n"
        "def test_the_greeting_has_no_banned_word():\n"
        "    assert not re.search(r'banned', 'a maker keeps their own rationale')\n",
    )
    assert _inline_scan_tests(source, frozenset()) == []


def test_the_inline_scan_check_does_not_fire_on_a_fixture(tmp_path):
    """The other honesty check, held against the inline half too: a fixture
    that reads a file and asks membership of it is setup, not a scan, and
    must not be reported."""
    source = _write(
        tmp_path,
        "test_planted_inline_fixture.py",
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def home(tmp_path):\n"
        "    (tmp_path / 'seed').write_text('x', encoding='utf-8')\n"
        "    return 'seed' in (tmp_path / 'seed').read_text(encoding='utf-8')\n"
        "\n"
        "def test_it(home):\n"
        "    assert home\n",
    )
    assert _inline_scan_tests(source, frozenset()) == []


def test_a_usefixtures_marker_does_not_exempt_a_test_from_either_half(tmp_path):
    """Planted: the exemption that was not one. `@pytest.mark.usefixtures`
    carries the word "fixture", and a rule that looked for that word
    anywhere in the decorator cleared every test wearing it. The marker must
    not exempt; a real `@pytest.fixture` beside it still must."""
    marked = _write(
        tmp_path,
        "test_planted_usefixtures.py",
        "import pytest\n"
        "from pathlib import Path\n"
        "\n"
        "@pytest.mark.usefixtures('_home')\n"
        "def test_no_banned_word():\n"
        "    text = Path('x').read_text(encoding='utf-8')\n"
        "    assert 'banned' not in text\n",
    )
    assert _inline_scan_tests(marked, frozenset()) == ["test_no_banned_word"], (
        "a usefixtures marker is not a fixture and must not exempt the test"
    )

    real = _write(
        tmp_path,
        "test_planted_real_fixture.py",
        "import pytest\n"
        "from pathlib import Path\n"
        "\n"
        "@pytest.fixture(autouse=True)\n"
        "def staged():\n"
        "    return 'banned' in Path('x').read_text(encoding='utf-8')\n",
    )
    assert _scan_helpers(real) == [], "a real @pytest.fixture is still setup"


def test_the_inline_scan_check_clears_a_test_that_delegates_to_a_known_helper(tmp_path):
    """And not over-strict: a test that reads a real file and calls a scan
    helper already known to `tests/` (wherever it actually lives — bare name
    or `module.helper(...)`) is delegating, not scanning inline, so it must
    not be reported even though it still reads a real file and still asks a
    membership question of the result."""
    target = tmp_path / "target.py"
    target.write_text("import willow_mcp\n", encoding="utf-8")
    source = _write(
        tmp_path,
        "test_planted_delegating_test.py",
        "from pathlib import Path\n"
        f"TARGET = Path({str(target)!r})\n"
        "\n"
        "from tests.test_no_reach_back import _imports_of\n"
        "\n"
        "def test_the_module_does_not_import_willow_mcp():\n"
        "    imported = _imports_of(TARGET)\n"
        "    assert 'willow_mcp' not in imported\n",
    )
    assert _inline_scan_tests(source, frozenset({"_imports_of"})) == []


def test_the_inline_scan_check_reads_class_methods_and_async_tests_too(tmp_path):
    """Planted: the two shapes a `tree.body`-only walk cannot see. This
    suite has no test classes today; homestead had eight, so a scan in a
    method was never reportable there, and an `async def test_*` would be
    the same blind spot the day one is written here."""
    in_a_class = _write(
        tmp_path,
        "test_planted_class_scan.py",
        "from pathlib import Path\n"
        "\n"
        "class TestTheTree:\n"
        "    def test_no_banned_word(self):\n"
        "        text = Path('x').read_text(encoding='utf-8')\n"
        "        assert 'banned' not in text\n",
    )
    assert _inline_scan_tests(in_a_class, frozenset()) == ["TestTheTree::test_no_banned_word"], (
        "a scan in a test class's method is still a scan, and is named as one"
    )

    awaited = _write(
        tmp_path,
        "test_planted_async_scan.py",
        "from pathlib import Path\n"
        "\n"
        "async def test_no_banned_word():\n"
        "    text = Path('x').read_text(encoding='utf-8')\n"
        "    assert 'banned' not in text\n",
    )
    assert _inline_scan_tests(awaited, frozenset()) == ["test_no_banned_word"]


def test_delegating_clears_a_test_that_also_asks_its_own_question(tmp_path):
    """The boundary this rule draws, pinned rather than left to be
    rediscovered: a test that calls a known scan helper is cleared *whole*,
    including an `in` of its own on the same text — the `in` beside the
    delegated call is the precondition that keeps a plant honest ("the
    fixture really does carry the thing I am about to change"), and
    reporting those would push preconditions out of sight for no gain."""
    source = _write(
        tmp_path,
        "test_planted_delegate_and_check.py",
        "from pathlib import Path\n"
        "from tests.test_deposit import _covenant_breaches\n"
        "\n"
        "def test_the_planted_word_is_reported():\n"
        "    source = Path('x').read_text(encoding='utf-8')\n"
        "    assert 'sign_seal' in source\n"
        "    assert _covenant_breaches(Path('x'))\n",
    )
    assert _inline_scan_tests(source, frozenset({"_covenant_breaches"})) == []
    assert _inline_scan_tests(source, frozenset()) == ["test_the_planted_word_is_reported"], (
        "and with no helper behind it, the same body is an inline scan"
    )


def test_a_local_function_sharing_a_helpers_name_does_not_clear_a_scan(tmp_path):
    """Planted: the shadow. Delegation is recognised by *name*, across the
    whole of `tests/`, so a module with a local function that happens to
    share a scan helper's name would have every inline scan beside it
    cleared by a call to something else entirely. A bare name only counts
    when this module imports it or defines it."""
    shadow = _write(
        tmp_path,
        "test_planted_shadowed_helper.py",
        "from pathlib import Path\n"
        "\n"
        "def _assigned_literal(text):\n"
        "    return text\n"
        "\n"
        "def test_no_banned_word():\n"
        "    text = Path('x').read_text(encoding='utf-8')\n"
        "    assert _assigned_literal(text)\n"
        "    assert 'banned' not in text\n",
    )
    assert _inline_scan_tests(shadow, frozenset({"_assigned_literal"})) == [
        "test_no_banned_word"
    ], "a local `_assigned_literal` is not test_release_wiring's `_assigned_literal`"

    imported = _write(
        tmp_path,
        "test_planted_imported_helper.py",
        "from pathlib import Path\n"
        "from tests.test_release_wiring import _assigned_literal\n"
        "\n"
        "def test_no_banned_word():\n"
        "    text = Path('x').read_text(encoding='utf-8')\n"
        "    assert _assigned_literal(text)\n"
        "    assert 'banned' not in text\n",
    )
    assert _inline_scan_tests(imported, frozenset({"_assigned_literal"})) == [], (
        "and the same call, of the helper this module really imported, is "
        "the delegation it looks like"
    )


def test_the_inline_scan_check_does_not_fire_on_the_real_tree():
    """The whole thing against a real file of this repo's:
    tests/test_deposit.py carried an inline covenant scan and now delegates
    to its own `_covenant_breaches`, planted in the same file — so the check
    must clear it, or it would be crying wolf on the very fix it exists to
    require. And the fix was needed: the body that test had before the
    factoring, reconstructed here in its exact shape (read, carve off the
    docstring with `split`, ask `not in` of the remainder), must be reported
    even with every real helper in `tests/` known — it called none of them."""
    global_helpers = _global_scan_helper_names()
    assert "_covenant_breaches" in global_helpers
    source = (TESTS_DIR / "test_deposit.py").read_text(encoding="utf-8")
    assert _inline_scan_tests(source, global_helpers) == []

    before_the_factoring = (
        "from pathlib import Path\n"
        "\n"
        "def test_the_module_never_names_seal_or_a_keyring():\n"
        "    src = Path('forge/deposit.py').read_text(encoding='utf-8')\n"
        '    body = src.split(\'"""\', 2)[2]  # below the module docstring\n'
        "    for word in ('seal(', 'seal_edge(', 'keyring'):\n"
        "        assert word not in body, f'{word!r} appears in forge/deposit.py'\n"
    )
    assert _inline_scan_tests(before_the_factoring, global_helpers) == [
        "test_the_module_never_names_seal_or_a_keyring"
    ], "the shape this repo carried until 2026-09-12 is an inline scan"
