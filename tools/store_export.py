#!/usr/bin/env python3
"""tools/store_export.py — cut a workshop's bundle into its checkout, or check one.

The export side of the store pull (docs/design/the-store-pull.md) and the
workshop rule (docs/design/the-forge-workshop.md): the live store stays home,
the repo carries `.forge/bundle.json` and `.forge/HEAD`.

    python tools/store_export.py --project-id my-workshop --repo-root .          # cut
    python tools/store_export.py --repo-root . --check                           # check
    python tools/store_export.py --project-id my-workshop --repo-root . --json   # cut, JSON out

Exit 0 when the cut succeeds or the check holds; 1 on a refusal or a failed
check, with the reasons printed. Writes nothing to the store, ever.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge import bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo-root", required=True, help="the workshop checkout")
    ap.add_argument("--project-id", help="the per-project Nestor to cut from (required unless --check)")
    ap.add_argument("--check", action="store_true", help="re-read .forge/HEAD and .forge/bundle.json and report")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if a.check:
        c = bundle.check(a.repo_root)
        if a.json:
            print(json.dumps(c.to_dict(), indent=2, sort_keys=True))
        else:
            print("ok" if c.ok else "FAILED")
            for p in c.problems:
                print(f"  - {p}")
            if c.head:
                print(f"  head {c.head.get('head', '')[:16]}  digest {c.head.get('digest', '')[:16]}  "
                      f"cut {c.head.get('cut_at', '')}  recomputed: {c.digest_recomputed}")
        return 0 if c.ok else 1

    if not a.project_id:
        ap.error("--project-id is required to cut")
    try:
        c = bundle.cut(a.project_id, a.repo_root)
    except bundle.BundleError as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(c.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"cut {a.project_id} at head {c.head[:16]}  digest {c.digest[:16]}  "
              f"pairs {c.counts.get('pairs', 0)} sealed {c.counts.get('sealed', 0)}")
        print(f"  {c.bundle_path}\n  {c.head_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
