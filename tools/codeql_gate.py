#!/usr/bin/env python3
"""Fail on any result in a CodeQL SARIF file. The gate half of
.github/workflows/codeql.yml.

WHY THIS EXISTS
---------------
This repository has CodeQL *default setup* enabled — the GitHub-managed
configuration under Settings → Code security, which an organisation policy can
switch on for every eligible repository. GitHub refuses SARIF uploaded by a
workflow while default setup is on ("CodeQL analyses from advanced
configurations cannot be processed when the default setup is enabled"), which
is how codeql.yml's first run (#29, 2026-09-12) went red with both analyses
clean: the queries ran, the upload was rejected, the check said failure.

Two ways out. Turn default setup off — a repository setting, not a workflow
change, and the policy that turned it on can turn it on again — or stop
depending on the upload. This is the second. codeql.yml runs the queries with
`upload: never` and writes the SARIF to disk; this script reads that file and
exits non-zero naming every result. The check is then a gate on findings
whatever the setting says, default setup's own scan still populates the
Security tab, and a green here means the tree is clean rather than that an
upload was accepted.

WHAT A RESULT IS
----------------
SARIF `runs[].results[]`, one per alert. Each is reported as
`<file>:<line>: <rule id> (<level>): <message>`; the level is the result's own,
else the rule's default, else SARIF's default of `warning`. Every result counts
— a `note` the queries chose to raise is still a thing they raised. A missing
file, a file that is not SARIF, or a SARIF with no runs is also a failure: an
analysis that produced nothing to read has not said the tree is clean.

USAGE
-----
    python tools/codeql_gate.py PATH.sarif    # exit 1 naming every result
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def findings(sarif: dict) -> list[str]:
    """One line per result in `sarif`, across every run."""
    out: list[str] = []
    for run in sarif.get("runs") or []:
        driver = (run.get("tool") or {}).get("driver") or {}
        rules = {r.get("id"): r for r in driver.get("rules") or []}
        for result in run.get("results") or []:
            rule_id = result.get("ruleId") or "<no rule id>"
            level = (
                result.get("level")
                or ((rules.get(rule_id) or {}).get("defaultConfiguration") or {}).get("level")
                or "warning"
            )
            where = "<no location>"
            for loc in result.get("locations") or []:
                physical = loc.get("physicalLocation") or {}
                uri = (physical.get("artifactLocation") or {}).get("uri")
                if uri:
                    line = (physical.get("region") or {}).get("startLine")
                    where = f"{uri}:{line}" if line else uri
                    break
            text = ((result.get("message") or {}).get("text") or "").strip()
            first_line = text.splitlines()[0] if text else "<no message>"
            out.append(f"{where}: {rule_id} ({level}): {first_line}")
    return out


def problems(path: Path) -> list[str]:
    """Every reason `path` does not say the tree is clean: the file is
    missing, is not SARIF, analyzed nothing, or holds results."""
    if not path.is_file():
        return [
            f"{path}: no SARIF file was written — an analysis that produced no "
            "results file has not said the tree is clean"
        ]
    try:
        sarif = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"{path}: not readable as SARIF ({exc})"]
    if not isinstance(sarif, dict) or not sarif.get("runs"):
        return [f"{path}: SARIF has no runs — nothing was analyzed"]
    return findings(sarif)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sarif", help="the SARIF file the analyze step wrote")
    args = parser.parse_args(argv)
    path = Path(args.sarif)
    found = problems(path)
    for line in found:
        # A workflow command, so each result is an annotation on the run.
        print(f"::error::codeql: {line}")
    if found:
        print(f"codeql gate: {len(found)} result(s) in {path}", file=sys.stderr)
        return 1
    print(f"codeql gate: no results in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
