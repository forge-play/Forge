"""forge/bundle.py — cut a project store's bundle at a ledger head, for the repo.

The workshop rule (docs/design/the-forge-workshop.md): the live Nestor
database stays home under `paths.project_nestor(<id>)`, and the repository
carries the exported bundle, which is shape and never content. This module
is the export side of the store pull: it writes two files into a checkout,

    .forge/bundle.json   Nestor's own bundle format (`nestor export`), with
                         the source ledger carried for audit
    .forge/HEAD          a small record: the ledger head the bundle was cut
                         at, the bundle's digest, counts, when, by what

and `check` re-reads them: the digest recomputes, the two files agree, and
the checkout holds no database. That last check is the constraint the paper
marks critical, and it is the one a template cannot enforce by layout alone.

Propose-only is not at issue here: nothing is written to the store. The
ledger is verified before the cut and the cut refuses a broken chain, because
a bundle cut at a head nothing vouches for is a bundle whose pin means nothing.

Nestor is imported lazily; its absence is a `BundleError`. The base install
can still run `check` on the two files without it (the digest recomputation
is Nestor's and is reported as `not_checked` when Nestor is absent, never as
clean).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths

__all__ = ["BUNDLE_DIR", "BUNDLE_NAME", "HEAD_NAME", "BundleError", "Cut", "Check",
           "cut", "check", "find_databases"]

#: Where a checkout keeps its bundle. A dot-directory at the repo root, so it
#: never collides with a package named `forge` and is visibly not code.
BUNDLE_DIR = ".forge"
BUNDLE_NAME = "bundle.json"
HEAD_NAME = "HEAD"

_CUT_BY = "forge.bundle"


class BundleError(Exception):
    """Refusals: no store, a broken ledger, Nestor absent, a database in the checkout."""


@dataclass(frozen=True)
class Cut:
    project_id: str
    head: str
    digest: str
    cut_at: str
    counts: dict[str, int]
    bundle_path: Path
    head_path: Path

    def to_dict(self) -> dict:
        return {"project_id": self.project_id, "head": self.head, "digest": self.digest,
                "cut_at": self.cut_at, "counts": dict(self.counts),
                "bundle": str(self.bundle_path), "HEAD": str(self.head_path)}


@dataclass
class Check:
    ok: bool
    problems: list[str] = field(default_factory=list)
    head: dict | None = None
    digest_recomputed: str = "not_checked"   # "ok" | "mismatch" | "not_checked" (Nestor absent)
    databases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "problems": list(self.problems), "head": self.head,
                "digest_recomputed": self.digest_recomputed, "databases": list(self.databases)}


def _nestor():
    try:
        from nestor import cascade, ledger, portable  # type: ignore[import-not-found]
        from nestor.sqlite_store import SqliteStore  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - the no-extras leg
        raise BundleError("Nestor is unavailable; there is no store to cut a bundle from. "
                          "Install it: pip install nestor-meaning.") from e
    return cascade, ledger, portable, SqliteStore


def find_databases(root: str | Path) -> list[str]:
    """Every file under `root` that looks like a Nestor database: named
    `nestor.db` or ending in `.db`, `.sqlite`, `.sqlite3`. `.git` is skipped.
    Paths are returned relative to `root`, sorted. The workshop rule says the
    list must be empty; this is how `check` knows."""
    root = Path(root)
    found: list[str] = []
    if not root.is_dir():
        return found
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        if p.is_file() and (p.name == "nestor.db" or p.suffix.lower() in (".db", ".sqlite", ".sqlite3")):
            found.append(str(p.relative_to(root)))
    return sorted(found)


def cut(project_id: str, repo_root: str | Path, *, now: datetime | None = None) -> Cut:
    """Export the project store to `<repo_root>/.forge/bundle.json` and write
    `.forge/HEAD` beside it. Refuses when the store does not exist, when the
    ledger chain does not verify, or when the checkout already holds a
    database (the cut would be putting a bundle beside the thing it exists
    to replace)."""
    cascade, ledger, portable, SqliteStore = _nestor()
    repo_root = Path(repo_root)
    db = paths.project_nestor(project_id)
    if not db.exists():
        raise BundleError(f"no project store for {project_id!r} at {db}; the entry creates it on first ask")
    dbs = find_databases(repo_root)
    if dbs:
        raise BundleError("a workshop checkout never contains a Nestor database; found: " + ", ".join(dbs))

    ledger_path = paths.project_nestor_ledger(project_id)
    cascade.set_ledger_path(ledger_path)
    ok, detail = ledger.verify(str(ledger_path))
    if not ok:
        raise BundleError(f"the project ledger does not verify; refusing to cut at a head nothing vouches for: {detail}")
    head = ledger.head(str(ledger_path))

    store = SqliteStore(str(db))
    bundle = portable.export_bundle(store, include_ledger=True)

    out = repo_root / BUNDLE_DIR
    out.mkdir(parents=True, exist_ok=True)
    bundle_path = out / BUNDLE_NAME
    head_path = out / HEAD_NAME
    bundle_path.write_text(json.dumps(bundle, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    cut_at = (now or datetime.now(timezone.utc)).isoformat()
    record = {
        "project_id": project_id,
        "head": head,
        "digest": bundle["digest"],
        "bundle": BUNDLE_NAME,
        "nestor_bundle": bundle.get("nestor_bundle"),
        "counts": dict(bundle.get("counts") or {}),
        "cut_at": cut_at,
        "cut_by": _CUT_BY,
        # The store is attested by name, never by path: a path would carry the
        # box's home directory into the repo, and the pull's `own_store` bound
        # is satisfied by the project id resolving under `paths.project_nestor`.
        "store": f"paths.project_nestor({project_id!r})",
    }
    head_path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return Cut(project_id=project_id, head=head, digest=bundle["digest"], cut_at=cut_at,
               counts=record["counts"], bundle_path=bundle_path, head_path=head_path)


def check(repo_root: str | Path) -> Check:
    """Re-read `.forge/HEAD` and `.forge/bundle.json` and say whether they
    hold together: both present and readable, digests equal, the bundle's
    digest recomputes (when Nestor is here to recompute it), and no database
    anywhere under `repo_root`. Never raises; every failure is a problem
    line, and `ok` is False if there is one."""
    repo_root = Path(repo_root)
    out = repo_root / BUNDLE_DIR
    c = Check(ok=True)
    c.databases = find_databases(repo_root)
    for d in c.databases:
        c.problems.append(f"database in the checkout: {d}")

    head_path, bundle_path = out / HEAD_NAME, out / BUNDLE_NAME
    head: dict | None = None
    bundle: dict | None = None
    for name, p in ((HEAD_NAME, head_path), (BUNDLE_NAME, bundle_path)):
        if not p.is_file():
            c.problems.append(f"missing {BUNDLE_DIR}/{name}")
            continue
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            c.problems.append(f"unreadable {BUNDLE_DIR}/{name}: {e}")
            continue
        if name == HEAD_NAME:
            head = loaded
        else:
            bundle = loaded
    c.head = head

    if head is not None and bundle is not None:
        if head.get("digest") != bundle.get("digest"):
            c.problems.append("HEAD.digest does not match bundle.digest")
        if not head.get("head"):
            c.problems.append("HEAD carries no ledger head")
        try:
            from nestor import portable  # type: ignore[import-not-found]
        except ImportError:
            c.digest_recomputed = "not_checked"
        else:
            ok, detail = portable.verify_bundle(bundle)
            c.digest_recomputed = "ok" if ok else "mismatch"
            if not ok:
                c.problems.append(f"bundle digest does not recompute: {detail}")

    c.ok = not c.problems
    return c
