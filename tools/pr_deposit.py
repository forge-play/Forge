#!/usr/bin/env python3
"""tools/pr_deposit.py — write how CI went into a project's Nestor, propose-only.

Paper: docs/design/the-pr-time-deposit.md. Two ways in, one module underneath:

    --inbox DIR   shape C. Read willow-bot's webhook inbox
                  ($WILLOW_HOME/upstream_steward/webhook_inbox) and deposit every
                  sha it can key. No network. Items the bridge wrote without a
                  head_sha are reported, not guessed (gap 1d737ffa2595).
    --sha SHA     shape A, the backfill. Ask GitHub through `gh` for the runs at
                  SHA and the PR that merged it. This is egress; run it from a
                  hand that holds `gh`, never from a seat without a lease, and
                  never as a warrant recipe.

Every row lands as a draft in the `ci` domain of
`forge.paths.project_nestor(--project-id)`; every edge is unsigned. `--dry-run`
prints what would be written and writes nothing.

    python tools/pr_deposit.py --project-id forge-engine --inbox ~/.willow/upstream_steward/webhook_inbox
    python tools/pr_deposit.py --project-id forge-engine --repo forge-play/Forge --sha cc9aab1 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Runnable as a script from any interpreter that has Nestor: the repo root is
# one level up. Installed `forge-play` wins when present; this is the fallback.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forge import deposit, paths  # noqa: E402
from forge.deposit import Run  # noqa: E402


def _open_store(project_id: str):
    from nestor import cascade  # type: ignore[import-not-found]
    from nestor.sqlite_store import SqliteStore  # type: ignore[import-not-found]
    db = paths.project_nestor(project_id)
    db.parent.mkdir(parents=True, exist_ok=True)
    cascade.set_ledger_path(paths.project_nestor_ledger(project_id))
    return SqliteStore(str(db))


# ── shape A: gh ────────────────────────────────────────────────────────────

def _gh(args: list[str]) -> list | dict:
    """One `gh` call, JSON out. An unreadable answer is a COULD NOT RUN for the
    caller to record, never a silent empty; here it raises so the tool can
    say what it could not read."""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise deposit.DepositError(f"gh {' '.join(args[:3])} failed: {proc.stderr.strip()[:200]}")
    try:
        return json.loads(proc.stdout or "null")
    except ValueError as e:
        raise deposit.DepositError(f"gh returned unreadable JSON: {e}") from e


def runs_from_gh(repo: str, sha: str) -> list[Run]:
    rows = _gh(["run", "list", "--repo", repo, "--commit", sha,
                "--json", "name,status,conclusion,databaseId,url", "--limit", "100"])
    return [Run(name=str(r.get("name") or r.get("workflowName") or ""), status=str(r.get("status") or ""),
                conclusion=str(r.get("conclusion") or ""), run_id=str(r.get("databaseId") or ""),
                url=str(r.get("url") or "")) for r in (rows or [])]


def pr_from_gh(repo: str, sha: str) -> tuple[dict | None, str, str]:
    """(pr summary or None, text to scan for Decision: trailers, actor type).
    The actor is the merging user's `type` as GitHub asserts it, never a
    login (§13)."""
    prs = _gh(["pr", "list", "--repo", repo, "--state", "merged", "--search", sha,
               "--json", "number,title,mergedAt,body,mergedBy", "--limit", "1"])
    if not prs:
        return None, "", "User"
    pr = prs[0]
    text = pr.get("body") or ""
    commits = _gh(["pr", "view", str(pr["number"]), "--repo", repo, "--json", "commits"]) or {}
    for c in (commits.get("commits") or []):
        text += "\n" + (c.get("messageHeadline") or "") + "\n" + (c.get("messageBody") or "")
    merged_by = pr.get("mergedBy") or {}
    actor = "Bot" if str(merged_by.get("type") or "").lower() == "bot" or merged_by.get("is_bot") else "User"
    return ({"number": pr.get("number"), "title": pr.get("title", ""),
             "merged_at": (pr.get("mergedAt") or "")[:10]}, text, actor)


# ── the tool ───────────────────────────────────────────────────────────────

def _emit(obj: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, indent=2, sort_keys=True))
        return
    for k, v in obj.items():
        print(f"{k}: {v}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--project-id", required=True, help="the per-project Nestor (forge.paths.project_nestor)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--inbox", help="willow-bot's webhook inbox directory (shape C, no network)")
    src.add_argument("--sha", help="a commit sha to ask GitHub about through gh (shape A, backfill)")
    ap.add_argument("--repo", help="owner/name; required with --sha, taken from the item with --inbox")
    ap.add_argument("--actor-type", choices=("Bot", "User"), default=None,
                    help="override the actor type (default: the inbox item's sender_type, or gh's mergedBy.type)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written; write nothing")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    report: dict = {"project_id": a.project_id, "dry_run": a.dry_run, "deposits": [], "unkeyed": [], "skipped": 0}
    store = None if a.dry_run else _open_store(a.project_id)

    if a.inbox:
        read = deposit.read_inbox(a.inbox)
        report["unkeyed"] = read.unkeyed
        report["skipped"] = read.skipped
        for sha, runs in read.keyed.items():
            repo = a.repo or read.repo.get(sha, "")
            entry = {"repo": repo, "sha": sha, "runs": [(r.name, r.state) for r in runs]}
            try:
                if a.dry_run:
                    entry["would_write"] = deposit._commitment(runs)
                else:
                    d = deposit.deposit_ci(store, repo=repo, sha=sha, runs=runs,
                                           actor_type=a.actor_type or "Bot", via="webhook_inbox")
                    entry["deposit"] = d.to_dict()
            except deposit.DepositError as e:
                entry["refused"] = str(e)
            report["deposits"].append(entry)
    else:
        if not a.repo:
            ap.error("--repo is required with --sha")
        runs = runs_from_gh(a.repo, a.sha)
        pr, text, actor = pr_from_gh(a.repo, a.sha)
        refs = deposit.extract_decision_refs(text)
        entry = {"repo": a.repo, "sha": a.sha, "runs": [(r.name, r.state) for r in runs],
                 "pr": pr, "decision_refs": refs, "actor_type": a.actor_type or actor}
        try:
            if a.dry_run:
                entry["would_write"] = deposit._commitment(runs) if runs else "(nothing: no runs read)"
            else:
                d = deposit.deposit_ci(store, repo=a.repo, sha=a.sha, runs=runs, pr=pr,
                                       actor_type=a.actor_type or actor, via="gh")
                entry["deposit"] = d.to_dict()
                if refs:
                    entry["links"] = deposit.link_decisions(store, d.row["id"], refs).to_dict()
        except deposit.DepositError as e:
            entry["refused"] = str(e)
        report["deposits"].append(entry)

    _emit(report, a.json)
    refused = any("refused" in d for d in report["deposits"])
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
