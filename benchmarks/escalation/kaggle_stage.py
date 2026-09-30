#!/usr/bin/env python3
"""Stage the escalation prompts as a dataset, and refuse to stage a leak (stdlib only).

``stage`` builds an upload directory for ``kaggle datasets create``::

    <shape>.jsonl x4      the exported prompts (see kaggle_export.py)
    catalog/tools.json    the tool catalogue the route prompt is written against
    README.md             what the dataset is
    dataset-metadata.json the dataset's id, title and licence

and then runs every gate below over what it built. If any gate fails the staging
directory is deleted and nothing is left to upload. A failure names the class and the
location only; the matched text is never printed.

Gates:

* layout and count: exactly the files above, each shape's line count equal to the
  repo's ``manifest.json``, and the catalogue byte-identical to the manifest's sha256;
* the answer key: each prompt line has exactly the exported keys and no ``expected``,
  ``answerable`` or ``rationale`` anywhere;
* everything ``gate/privacy_gate.py`` checks: email, phone, token-shaped strings,
  absolute paths, file URIs, binary or archive files, non-UTF-8, invisible
  characters, confusable keys and ids, and the deny-list;
* store and vault identifiers (8 or 12 hex characters mixing digits and letters, UUIDs);
* Unicode lookalikes: a word that mixes Latin with Cyrillic or Greek, and a deny-list
  term that only matches after confusable letters are folded to Latin;
* compressed or binary payloads recognised by their leading bytes, whatever the name.

The deny-list (the operator's names, paths, hostnames) is read from a file given on the
command line. It must live outside every git tree, and so must the staging directory.
Neither is ever committed.

Usage: ``python kaggle_stage.py --out DIR --dataset-id OWNER/SLUG --denylist FILE``.
Exit codes: 0 staged, 1 a gate failed (staging deleted), 2 usage error.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import kaggle_export  # noqa: E402

BENCH = _HERE
SHAPES = kaggle_export.SHAPES
runner = kaggle_export.runner


def _load_gate(bench: Path):
    spec = importlib.util.spec_from_file_location(
        "escalation_privacy_gate", bench / "gate" / "privacy_gate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate(BENCH)

PROMPT_FILES = tuple(f"{shape}.jsonl" for shape in SHAPES)
CATALOG_FILE = "catalog/tools.json"
README_FILE = "README.md"
METADATA_FILE = "dataset-metadata.json"
EXPECTED_FILES = frozenset({*PROMPT_FILES, CATALOG_FILE, README_FILE, METADATA_FILE})
ANSWER_KEY_KEYS = frozenset({"expected", "answerable", "rationale"})
DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9-]*$")

README_TEXT = """# Escalation benchmark: prompts

Prompts for an escalation benchmark: does a model know when it cannot answer?

Every task has a refusal token, `ESCALATE`. In each of four job shapes (route,
classify, judge, ground) some items have had their answer removed, or come with text
that does not contain it. On those items `ESCALATE` is the only correct reply. Every
item is invented for this benchmark.

Each line of `<shape>.jsonl` is one JSON object:

- `id`: the item id
- `shape`: one of route, classify, judge, ground
- `messages`: a system message and a user message, exactly as sent to a model
- `schema`: the reply envelope the prompts ask for, `{answer, confidence}`

The answer key is not part of this dataset. `catalog/tools.json` is the list of
invented tools the route prompts are written against.
"""

# Confusable letters (Cyrillic and Greek) and the Latin letter each passes for.
_CONFUSABLE_PAIRS = (
    (0x0430, "a"),
    (0x0432, "b"),
    (0x0435, "e"),
    (0x043A, "k"),
    (0x043C, "m"),
    (0x043D, "h"),
    (0x043E, "o"),
    (0x0440, "p"),
    (0x0441, "c"),
    (0x0442, "t"),
    (0x0443, "y"),
    (0x0445, "x"),
    (0x0455, "s"),
    (0x0456, "i"),
    (0x0458, "j"),
    (0x04BB, "h"),
    (0x0501, "d"),
    (0x051B, "q"),
    (0x051D, "w"),
    (0x03B1, "a"),
    (0x03B5, "e"),
    (0x03B7, "n"),
    (0x03B9, "i"),
    (0x03BA, "k"),
    (0x03BD, "v"),
    (0x03BF, "o"),
    (0x03C1, "p"),
    (0x03C4, "t"),
    (0x03C5, "u"),
    (0x03C7, "x"),
    (0x03C9, "w"),
)
CONFUSABLES = {chr(code): latin for code, latin in _CONFUSABLE_PAIRS}
SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")
WORD = re.compile(r"\w+", re.UNICODE)
_LOWER_ID = r"(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])(?:[0-9a-f]{8}|[0-9a-f]{12})"
_UPPER_ID = r"(?=[0-9A-F]*[0-9])(?=[0-9A-F]*[A-F])(?:[0-9A-F]{8}|[0-9A-F]{12})"
STORE_ID = re.compile(rf"(?<![0-9A-Za-z])(?:{_LOWER_ID}|{_UPPER_ID})(?![0-9A-Za-z])")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
MAGIC = (
    b"\x1f\x8b",  # gzip
    b"PK\x03\x04",  # zip and its kin
    b"BZh",  # bzip2
    b"\xfd7zXZ\x00",  # xz
    b"\x28\xb5\x2f\xfd",  # zstd
    b"7z\xbc\xaf\x27\x1c",  # 7z
    b"Rar!",  # rar
    b"%PDF",  # pdf
    b"\x89PNG",  # png
    b"SQLite format 3",  # sqlite
)


def skeleton(text: str) -> str:
    """Fold a string so confusable letters, accents and invisible marks all vanish."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = "".join(c for c in folded if unicodedata.category(c) not in ("Mn", "Cf"))
    return "".join(CONFUSABLES.get(c, c) for c in kept)


def _script(char: str) -> str | None:
    try:
        first = unicodedata.name(char).split()[0]
    except ValueError:
        return None
    return first if first in SCRIPTS else None


def mixed_script(text: str) -> bool:
    """A single word that mixes Latin with Cyrillic or Greek letters."""
    for word in WORD.findall(text):
        scripts = {_script(c) for c in word if c.isalpha()} - {None}
        if len(scripts) > 1:
            return True
    return False


# --- build ---------------------------------------------------------------------


def dataset_metadata(dataset_id: str) -> dict:
    return {
        "title": "Escalation benchmark prompts",
        "id": dataset_id,
        "licenses": [{"name": "CC0-1.0"}],
    }


def build(out: Path, dataset_id: str, bench: Path = BENCH) -> None:
    """Write the staging directory. ``out`` must be outside git and empty or absent."""
    kaggle_export.write_export(out, bench)
    (out / "catalog").mkdir()
    shutil.copyfile(bench / "catalog" / "tools.json", out / CATALOG_FILE)
    (out / README_FILE).write_text(README_TEXT, encoding="utf-8", newline="\n")
    meta = json.dumps(dataset_metadata(dataset_id), indent=2) + "\n"
    (out / METADATA_FILE).write_text(meta, encoding="utf-8", newline="\n")


# --- gates ---------------------------------------------------------------------

Findings = set[tuple[str, str]]


def gate_layout(out: Path, bench: Path) -> Findings:
    """File set, line counts and catalogue digest against the repo's manifest."""
    found: Findings = set()
    actual = {rel: p for p, rel in gate.iter_files(out)}
    for rel in sorted(set(actual) - EXPECTED_FILES):
        found.add(("unexpected-file", rel))
    for rel in sorted(EXPECTED_FILES - set(actual)):
        found.add(("missing-file", rel))
    try:
        manifest = json.loads((bench / gate.MANIFEST_NAME).read_text(encoding="utf-8"))
        listed = {entry["path"]: entry for entry in manifest["files"]}
    except (OSError, ValueError, KeyError, TypeError):
        return found | {("manifest-malformed", gate.MANIFEST_NAME)}
    for shape in SHAPES:
        rel, want = f"{shape}.jsonl", listed.get(f"fixtures/{shape}.jsonl")
        if rel in actual and (
            want is None or actual[rel].read_bytes().count(b"\n") != want["lines"]
        ):
            found.add(("line-count-mismatch", rel))
    want = listed.get(CATALOG_FILE)
    if CATALOG_FILE in actual:
        digest = hashlib.sha256(actual[CATALOG_FILE].read_bytes()).hexdigest()
        if want is None or want.get("sha256") != digest:
            found.add(("catalog-sha-mismatch", CATALOG_FILE))
    return found


def gate_answer_key(out: Path) -> Findings:
    """Each prompt line carries exactly the exported keys and no answer-key field."""
    found: Findings = set()
    for name in PROMPT_FILES:
        path = out / name
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{name}:{lineno}"
            try:
                value = json.loads(line)
            except ValueError:
                found.add(("invalid-json", where))
                continue
            if not isinstance(value, dict) or tuple(sorted(value)) != kaggle_export.EXPORT_KEYS:
                found.add(("export-keys", where))
            keys = {k for kind, k, _ in gate._walk_json(value) if kind == "key"}
            if keys & ANSWER_KEY_KEYS:
                found.add(("answer-key", where))
    return found


def _texts(rel: str, path: Path, text: str):
    """(location, string): every raw line, then every decoded string in a JSON file.

    Decoding matters: a lookalike letter written as a JSON escape only shows up once
    the string is decoded.
    """
    lines = text.splitlines()
    for lineno, line in enumerate(lines, 1):
        yield f"{rel}:{lineno}", line
    if path.suffix == ".jsonl":
        docs = [(f"{rel}:{n}", line) for n, line in enumerate(lines, 1)]
    elif path.suffix == ".json":
        docs = [(rel, text)]
    else:
        docs = []
    for where, doc in docs:
        try:
            value = json.loads(doc)
        except ValueError:
            continue
        for _kind, item, _loc in gate._walk_json(value):
            yield where, item


def _privacy(path: Path, rel: str, denylist_terms: list[str]) -> Findings:
    """``privacy_gate.scan_file``, except that a dataset id of the form owner/slug is fine.

    The gate's id check allows no slash; the dataset metadata's ``id`` has one by design,
    so that one finding is dropped, and only when the id is plain lowercase ASCII.
    """
    found = gate.scan_file(path, rel, denylist_terms)
    if rel == METADATA_FILE and not path.is_symlink():
        try:
            ident = json.loads(path.read_text(encoding="utf-8")).get("id")
        except (OSError, ValueError, AttributeError):
            ident = None
        if isinstance(ident, str) and DATASET_ID.match(ident):
            found.discard(("confusable-id", rel))
    return found


def gate_content(out: Path, denylist_terms: list[str]) -> Findings:
    """The privacy gate per file, plus store ids, lookalikes and compressed payloads."""
    found: Findings = set()
    skeleton_terms = [skeleton(term) for term in denylist_terms]
    for path, rel in gate.iter_files(out):
        found |= _privacy(path, rel, denylist_terms)
        if path.is_symlink():
            continue
        data = path.read_bytes()
        if any(data.startswith(magic) for magic in MAGIC):
            found.add(("compressed-payload", rel))
            continue
        if b"\x00" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for where, item in _texts(rel, path, text):
            if STORE_ID.search(item) or UUID.search(item):
                found.add(("store-id", where))
            if mixed_script(item):
                found.add(("lookalike-script", where))
            flat = skeleton(item)
            if any(term in flat for term in skeleton_terms):
                found.add(("denylist-lookalike", where))
    return found


def run_gates(out: Path, denylist_path: Path, bench: Path = BENCH) -> tuple[int, list[str]]:
    terms = gate.load_denylist(str(denylist_path))
    findings = gate_layout(out, bench) | gate_answer_key(out) | gate_content(out, terms)
    lines = [f"FAIL {cls} {loc}" for cls, loc in sorted(findings)]
    files = sum(1 for _ in gate.iter_files(out))
    if findings:
        lines.append(f"stage gate: {len(findings)} violation(s) in {files} file(s)")
        return 1, lines
    lines.append(f"stage gate: OK, {files} file(s), {len(terms)} deny-list term(s) applied")
    return 0, lines


# --- stage ---------------------------------------------------------------------


def stage(
    out: Path, dataset_id: str, denylist_path: Path, bench: Path = BENCH
) -> tuple[int, list[str]]:
    """Build the staging directory and gate it; delete it again if a gate fails."""
    if not DATASET_ID.match(dataset_id):
        return 2, ["stage: --dataset-id must look like owner/slug (lowercase, digits, hyphens)"]
    if not denylist_path.is_file():
        return 2, ["stage: the deny-list file was named but cannot be read"]
    if kaggle_export.inside_git_tree(denylist_path):
        return 2, ["stage: the deny-list file must be outside every git tree"]
    if not gate.load_denylist(str(denylist_path)):
        return 2, ["stage: the deny-list file has no terms; an empty list proves nothing"]
    if kaggle_export.inside_git_tree(out):
        return 2, ["stage: the staging directory must be outside every git tree"]
    if out.exists() and any(out.iterdir()):
        return 2, ["stage: the staging directory must be empty or absent"]
    build(out, dataset_id, bench)
    code, lines = run_gates(out, denylist_path, bench)
    if code:
        shutil.rmtree(out)
        lines.append("stage: staging directory deleted; nothing to upload")
    return code, lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="staging directory (outside git)")
    ap.add_argument("--dataset-id", required=True, help="owner/slug for dataset-metadata.json")
    ap.add_argument("--denylist", required=True, type=Path, help="deny-list file (outside git)")
    ap.add_argument("--bench", type=Path, default=BENCH, help="benchmark directory override")
    args = ap.parse_args(argv)
    code, lines = stage(args.out, args.dataset_id, args.denylist, args.bench)
    print("\n".join(lines), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
