#!/usr/bin/env python3
"""tools/store_diff.py — how far is a project store from the main one?

    python tools/store_diff.py --project-id forge-engine --main ~/.nestor/keep/nestor.db
    python tools/store_diff.py --project-id forge-engine --main main-decision-2026-09-03.json --json

Four sets, all reads: verified upstream (seals that should come home), proposed
here (what the pull carries up), conflicts (surfaced, never resolved here), and
retired here but sealed there. Writes nothing. Exit 1 when there is a conflict,
so a hook can gate on it; 0 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge import paths, store_diff  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project-id", required=True)
    ap.add_argument("--main", required=True, help="the main store: a nestor.db path or an exported bundle .json")
    ap.add_argument("--domain", default=store_diff.DEFAULT_DOMAIN)
    ap.add_argument("--repo-root", default=None,
                    help="a workshop checkout; --main may not lie inside it (a checkout never holds a database)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    from nestor.sqlite_store import SqliteStore  # type: ignore[import-not-found]
    db = paths.project_nestor(a.project_id)
    if not db.exists():
        print(f"no project store for {a.project_id!r} at {db}", file=sys.stderr)
        return 1
    try:
        d = store_diff.diff(SqliteStore(str(db)), a.main, domain=a.domain, forbid_under=a.repo_root)
    except store_diff.MainUnreadable as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(d.to_dict(), indent=2, sort_keys=True))
    else:
        print(store_diff.summary(d))
        for x in d.verified_upstream[:20]:
            print(f"  behind   {x['question'][:90]}  (sealed by {x['main_verifier']})")
        for x in d.proposed_here[:20]:
            print(f"  ahead    {x['question'][:90]}")
        for c in d.conflicts:
            print(f"  CONFLICT {c['question'][:90]}  [{c['kind']}]\n           here:  {c['here']['answer'][:80]}\n           there: {c['there']['answer'][:80]}")
        for x in d.retired_here_sealed_there:
            print(f"  retired  {x['question'][:90]}  (sealed there by {x['main_verifier']})")
    return 1 if d.conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
