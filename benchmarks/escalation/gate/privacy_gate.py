#!/usr/bin/env python3
"""Privacy gate for the escalation benchmark files (stdlib only).

Scans every file under ``benchmarks/escalation/`` and exits non-zero when any of
these is found:

* an email address or a phone number;
* a token-shaped string (hex or base64 run of 32+ characters, or a well-known
  key prefix for a code host, a payment API or a cloud provider);
* an absolute path (a Unix home directory, a macOS user directory, a drive
  letter path) or a file URI;
* a non-UTF-8 or binary file, a symlink, or an archive extension;
* a non-ASCII character in a JSON key or in an ``id`` value, or an invisible
  format character anywhere;
* a term from an optional deny-list file (``--denylist PATH`` or the
  ``ESCALATION_GATE_DENYLIST`` environment variable). The list is read at run
  time, is never committed, and its terms are never printed;
* a file that is not in the allowed layout, or a file count, line count or
  sha256 that differs from ``manifest.json``.

A violation is reported by class and location only; the matched text is never
echoed, so a failing run cannot leak the thing it found.

Exit codes: 0 clean, 1 violations found, 2 usage error.

``--write-manifest`` regenerates ``manifest.json`` from the tree and exits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_NAME = "manifest.json"
DATA_DIRS = ("catalog", "fixtures")
ALLOWED_OTHER = {
    "README.md",
    MANIFEST_NAME,
    "gate/privacy_gate.py",
    "runner.py",
    "aggregate.py",
    "socket_backend.py",
    "kaggle_export.py",
    "kaggle_rows.py",
    "kaggle_stage.py",
    "kaggle/route_task.py",
    "kaggle/classify_task.py",
    "kaggle/judge_task.py",
    "kaggle/ground_task.py",
}
PROMPT_DIR = "prompts"
SKIP_DIRS = {"__pycache__"}
DENYLIST_ENV = "ESCALATION_GATE_DENYLIST"

ARCHIVE_EXTS = {
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".zst",
    ".7z",
    ".rar",
    ".whl",
    ".jar",
    ".egg",
    ".pyc",
    ".pkl",
    ".pickle",
    ".db",
    ".sqlite",
    ".parquet",
    ".ipynb",
}

# The path markers are assembled from pieces so this file does not trip its own scan.
PATH_MARKERS = {
    "abs-path": ["/ho" + "me/", "/us" + "ers/", "/ro" + "ot/"],
    "file-uri": ["file:" + "//"],
}
DRIVE_PATH = re.compile(r"(?<![A-Za-z])[A-Za-z]:\\")

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(
    r"(?<![\w.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{3,4}(?![\w])"
    r"|(?<![\w.])\+\d{8,15}(?![\w])"
)
HEX_RUN = re.compile(r"[0-9a-fA-F]{32,}")
BASE64_RUN = re.compile(r"[A-Za-z0-9+/=_-]{32,}")
KEY_PREFIXES = re.compile(
    r"\bghp_[A-Za-z0-9]{8,}|\bgho_[A-Za-z0-9]{8,}|\bgithub_pat_[A-Za-z0-9_]{8,}"
    r"|\bsk-[A-Za-z0-9_-]{8,}|\bAKIA[0-9A-Z]{8,}|\bxox[bpa]-[A-Za-z0-9-]{8,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY"
)
SHA_VALUE = re.compile(r'("sha256"\s*:\s*")[0-9a-f]{64}(")')
SAFE_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")


def _mixed_base64(run: str) -> bool:
    """A base64-looking run has upper, lower and a digit; a long path or word does not."""
    return (
        any(c.isupper() for c in run)
        and any(c.islower() for c in run)
        and any(c.isdigit() for c in run)
    )


def text_findings(text: str) -> set[str]:
    """Classes of leak found in one piece of text."""
    found: set[str] = set()
    low = text.lower()
    for cls, markers in PATH_MARKERS.items():
        if any(m in low for m in markers):
            found.add(cls)
    if DRIVE_PATH.search(text):
        found.add("abs-path")
    if EMAIL.search(text):
        found.add("email")
    if PHONE.search(text):
        found.add("phone")
    if HEX_RUN.search(text):
        found.add("token")
    if KEY_PREFIXES.search(text):
        found.add("token")
    if any(_mixed_base64(m.group(0)) for m in BASE64_RUN.finditer(text)):
        found.add("token")
    if any(unicodedata.category(c) == "Cf" for c in text):
        found.add("invisible-char")
    return found


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def load_denylist(path: str | None) -> list[str]:
    """Terms from the deny-list file; blank lines and ``#`` comments are ignored."""
    if not path:
        return []
    terms = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            term = raw.strip()
            if term and not term.startswith("#"):
                terms.append(_fold(term))
    return terms


def _walk_json(node, path=""):
    """Yield (kind, key_or_value, location) for every key and string in a JSON value."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield "key", key, path
            if key == "sha256" and isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
                continue
            yield from _walk_json(value, f"{path}.{key}")
            if key == "id" and isinstance(value, str):
                yield "id", value, path
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk_json(value, f"{path}[{i}]")
    elif isinstance(node, str):
        yield "string", node, path


def iter_files(root: Path):
    for p in sorted(root.rglob("*")):
        rel_parts = p.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if p.is_dir() and not p.is_symlink():
            continue
        yield p, "/".join(rel_parts)


def is_allowed(rel: str) -> bool:
    """Whether a path belongs in the layout: data files, listed scripts, prompt texts."""
    parts = rel.split("/")
    if parts[0] in DATA_DIRS or rel in ALLOWED_OTHER:
        return True
    return len(parts) == 2 and parts[0] == PROMPT_DIR and parts[1].endswith(".txt")


def scan_file(path: Path, rel: str, denylist: list[str]) -> set[tuple[str, str]]:
    """Return {(class, location)} for one file."""
    out: set[tuple[str, str]] = set()
    if path.is_symlink():
        return {("symlink", rel)}
    if path.suffix.lower() in ARCHIVE_EXTS:
        out.add(("archive-extension", rel))
    data = path.read_bytes()
    if b"\x00" in data:
        out.add(("binary", rel))
        return out
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        out.add(("not-utf8", rel))
        return out

    if path.suffix == ".py" and not text.isascii():
        out.add(("non-ascii-source", rel))

    scan_text = SHA_VALUE.sub(r"\1\2", text) if rel == MANIFEST_NAME else text
    for lineno, line in enumerate(scan_text.splitlines(), 1):
        for cls in text_findings(line):
            out.add((cls, f"{rel}:{lineno}"))
        folded = _fold(line)
        if any(term in folded for term in denylist):
            out.add(("denylist", f"{rel}:{lineno}"))

    if path.suffix in {".json", ".jsonl"}:
        docs = text.splitlines() if path.suffix == ".jsonl" else [text]
        for lineno, doc in enumerate(docs, 1):
            if not doc.strip():
                continue
            where = f"{rel}:{lineno}" if path.suffix == ".jsonl" else rel
            try:
                value = json.loads(doc)
            except json.JSONDecodeError:
                out.add(("invalid-json", where))
                continue
            for kind, item, _loc in _walk_json(value):
                if kind == "key":
                    if not item.isascii() or not SAFE_KEY.match(item):
                        out.add(("confusable-key", where))
                elif kind == "id":
                    if not item.isascii() or not SAFE_KEY.match(item):
                        out.add(("confusable-id", where))
                else:
                    for cls in text_findings(item):
                        out.add((cls, where))
                    folded = _fold(item)
                    if any(term in folded for term in denylist):
                        out.add(("denylist", where))
    return out


def file_facts(path: Path) -> dict:
    data = path.read_bytes()
    return {"lines": data.count(b"\n"), "sha256": hashlib.sha256(data).hexdigest()}


def data_files(root: Path) -> dict[str, Path]:
    return {rel: p for p, rel in iter_files(root) if rel.split("/")[0] in DATA_DIRS}


def build_manifest(root: Path) -> dict:
    entries = []
    for rel, p in sorted(data_files(root).items()):
        entries.append({"path": rel, **file_facts(p)})
    return {"file_count": len(entries), "files": entries}


def check_manifest(root: Path) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    mpath = root / MANIFEST_NAME
    if not mpath.is_file():
        return {("manifest-missing", MANIFEST_NAME)}
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        listed = {e["path"]: e for e in manifest["files"]}
        declared = manifest["file_count"]
    except (json.JSONDecodeError, KeyError, TypeError, UnicodeDecodeError):
        return {("manifest-malformed", MANIFEST_NAME)}
    actual = data_files(root)
    if declared != len(listed) or len(listed) != len(actual):
        out.add(("manifest-file-count", MANIFEST_NAME))
    for rel in sorted(set(actual) - set(listed)):
        out.add(("manifest-unlisted-file", rel))
    for rel in sorted(set(listed) - set(actual)):
        out.add(("manifest-missing-file", rel))
    for rel in sorted(set(actual) & set(listed)):
        facts = file_facts(actual[rel])
        if listed[rel].get("sha256") != facts["sha256"]:
            out.add(("manifest-sha-mismatch", rel))
        if listed[rel].get("lines") != facts["lines"]:
            out.add(("manifest-line-mismatch", rel))
    return out


def run(root: Path, denylist_path: str | None) -> tuple[int, list[str]]:
    denylist = load_denylist(denylist_path)
    findings: set[tuple[str, str]] = set()
    scanned = 0
    for path, rel in iter_files(root):
        scanned += 1
        if not is_allowed(rel):
            findings.add(("unexpected-file", rel))
        findings |= scan_file(path, rel, denylist)
    findings |= check_manifest(root)
    lines = [f"FAIL {cls} {loc}" for cls, loc in sorted(findings)]
    note = "deny-list applied" if denylist_path else "no deny-list given"
    if findings:
        lines.append(f"privacy gate: {len(findings)} violation(s) in {scanned} file(s) ({note})")
        return 1, lines
    lines.append(f"privacy gate: OK, {scanned} file(s) scanned ({note})")
    return 0, lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(ROOT), help="directory to scan")
    ap.add_argument("--denylist", default=None, help="optional deny-list file, one term per line")
    ap.add_argument("--write-manifest", action="store_true", help="regenerate manifest.json")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"privacy gate: not a directory: {root}", file=sys.stderr)
        return 2
    if args.write_manifest:
        (root / MANIFEST_NAME).write_text(
            json.dumps(build_manifest(root), indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"wrote {MANIFEST_NAME}")
        return 0
    denylist = args.denylist or os.environ.get(DENYLIST_ENV) or None
    if denylist and not Path(denylist).is_file():
        print("privacy gate: the deny-list file was named but cannot be read", file=sys.stderr)
        return 2
    code, lines = run(root, denylist)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
