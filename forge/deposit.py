"""forge/deposit.py — the PR-time deposit: how CI went, written into a project's
Nestor as drafts, and the edges that say which decisions a PR touched.

Paper: docs/design/the-pr-time-deposit.md. The walls this module is built
inside, restated so a reader does not have to open the paper:

- **Propose only.** `DecisionMemory.propose`, `propose_edge` and
  `memory.revise_draft` (draft over draft, history kept) are the only Nestor
  verbs called here. Nothing in this module can reach `seal`, `seal_edge`, or
  a keyring; a test pins that on the source text.
- **Its own domain.** A CI outcome is not a decision. Rows land in the `ci`
  domain so `decision check` and the entry's tier-1 ask never answer "has a
  human decided this?" with a workflow run.
- **Four states, by table.** `pass`, `fail`, `could_not_run`, `pending`. An
  unreadable or cancelled run is `could_not_run`, never clean; a run still in
  progress is `pending`, and the deposit refuses rather than record it.
- **An actor is a type, never a login.** The origin carries `actor=Bot` or
  `actor=User`; no login string is stored anywhere.
- **The model never touches it.** Which decisions a PR relates to is read by
  a regular expression from a `Decision:` trailer. An ambiguous or unmatched
  prefix is reported and skipped, never guessed.
- **No network.** This module takes a store and returns rows. Reading the
  bot's inbox is a directory read; asking GitHub is the tool's job
  (`tools/pr_deposit.py`), never this module's.

Nestor is imported lazily and its absence is a `DepositError`, the same
discipline as `forge/checkpoint_memory.py`: the base install runs without it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "DOMAIN", "STATES", "DepositError", "Run", "outcome_state",
    "extract_decision_refs", "deposit_ci", "link_decisions", "read_inbox",
    "newest_deposit", "deposit_age", "human_age",
]

#: The Nestor domain CI rows live in. Never `decision`.
DOMAIN = "ci"

#: The four coverage states, in the order the paper lists them.
STATES = ("pass", "fail", "could_not_run", "pending")

#: GitHub `conclusion` → state, for a run whose `status` is `completed`.
#: Anything not in this table is `could_not_run`: an unreadable run is never
#: clean.
_CONCLUSION_TO_STATE = {
    "success": "pass",
    "failure": "fail",
    "startup_failure": "fail",
}

#: A `Decision:` trailer: the key at the start of a line, then 8 or more hex
#: characters of a project-store pair id. Case-insensitive on the key only.
_DECISION_REF = re.compile(r"^\s*decision:\s*([0-9a-fA-F]{8,})\s*$", re.IGNORECASE | re.MULTILINE)

_ACTOR_TYPES = ("Bot", "User")


class DepositError(Exception):
    """Refusals: Nestor absent, a pending run, an unknown actor type, bad input."""


@dataclass(frozen=True)
class Run:
    """One workflow run at one sha, as GitHub reports it. `run_id` is the
    databaseId from `gh run list` or the check-run id from a webhook; `url`
    is the html_url. Both are strings so a webhook item and a `gh` row read
    the same."""
    name: str
    status: str
    conclusion: str
    run_id: str = ""
    url: str = ""

    @property
    def state(self) -> str:
        return outcome_state(self.status, self.conclusion)


def outcome_state(status: str | None, conclusion: str | None) -> str:
    """The table. `status` other than `completed` is `pending`; then the
    conclusion is looked up, and anything the table does not name is
    `could_not_run`."""
    if (status or "").lower() != "completed":
        return "pending"
    return _CONCLUSION_TO_STATE.get((conclusion or "").lower(), "could_not_run")


def extract_decision_refs(text: str) -> list[str]:
    """Every `Decision: <id-prefix>` trailer in `text`, lower-cased, in order,
    de-duplicated. A regular expression and nothing else: the model never
    names a decision."""
    seen: list[str] = []
    for m in _DECISION_REF.finditer(text or ""):
        ref = m.group(1).lower()
        if ref not in seen:
            seen.append(ref)
    return seen


# ── the store ──────────────────────────────────────────────────────────────

def _decision_memory(store: Any, domain: str) -> Any:
    try:
        from nestor.decision import DecisionMemory  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - exercised by the no-extras leg
        raise DepositError(
            "Nestor is unavailable; the deposit has nowhere to write. "
            "Install it: pip install nestor-meaning."
        ) from e
    return DecisionMemory(store, domain=domain)


def _rows(store: Any) -> list[dict]:
    """Every pair in the store. `memory_list` caps at 50 by default (handoff
    gap 6); always pass the limit. `memory_init` first: a fresh store has no
    pair table until something creates it, and a list before that is an
    error, not an empty."""
    store.memory_init()
    return list(store.memory_list(limit=1_000_000))


def _question(repo: str, sha: str) -> str:
    return f"How did CI go for {repo}@{sha}?"


def _commitment(runs: Iterable[Run]) -> str:
    parts = []
    for r in sorted(runs, key=lambda r: (r.name.lower(), r.run_id)):
        tail = f" (run {r.run_id})" if r.run_id else ""
        parts.append(f"{r.state}: {r.name} {r.conclusion or '-'}{tail}")
    return "; ".join(parts)


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).isoformat()


@dataclass
class Deposit:
    """What `deposit_ci` wrote. `row` is the live draft pair; `superseded` is
    the id of the row this one revised (a re-run at the same sha with a
    different outcome), if any; `unchanged` means the same outcome was already
    the live row and nothing was written; `states` counts the runs by state."""
    row: dict
    superseded: str | None
    states: dict[str, int] = field(default_factory=dict)
    unchanged: bool = False

    def to_dict(self) -> dict:
        return {"id": self.row["id"], "question": self.row["source_text"],
                "commitment": self.row["target_text"], "superseded": self.superseded,
                "unchanged": self.unchanged, "states": dict(self.states)}


def deposit_ci(store: Any, *, repo: str, sha: str, runs: Iterable[Run],
               pr: dict | None = None, actor_type: str, via: str,
               now: datetime | None = None) -> Deposit:
    """Propose one `ci` row for `repo@sha` from `runs`. A re-run with a
    different outcome revises the live draft (`nestor.memory.revise_draft`),
    keeping the old row as history; the same outcome again writes nothing.

    Refuses when any run is `pending` (come back when it is done), when
    `runs` is empty (nothing was read, and an empty deposit would read as
    clean), and when `actor_type` is not `Bot` or `User`.

    `pr`, when given, is `{"number": int, "title": str, "merged_at": str}` and
    becomes the row's reason. `via` names the tool or lane that produced the
    rows (`webhook_inbox`, `gh`), never a login.
    """
    runs = list(runs)
    if not runs:
        raise DepositError(f"no runs for {repo}@{sha}; nothing was read, so nothing is deposited")
    if actor_type not in _ACTOR_TYPES:
        raise DepositError(f"actor_type must be one of {_ACTOR_TYPES}, got {actor_type!r}")
    pending = [r.name for r in runs if r.state == "pending"]
    if pending:
        raise DepositError(f"{len(pending)} run(s) still pending at {repo}@{sha}: "
                           f"{', '.join(sorted(pending))}; deposit when they are done")
    if not repo or not sha:
        raise DepositError("repo and sha are required")

    states: dict[str, int] = {}
    for r in runs:
        states[r.state] = states.get(r.state, 0) + 1

    question = _question(repo, sha)
    commitment = _commitment(runs)
    live = [r for r in _rows(store)
            if r.get("source_lang") == DOMAIN and r.get("source_text") == question
            and not r.get("superseded_by")]

    reason = ""
    if pr:
        reason = f'PR #{pr.get("number")} "{pr.get("title", "")}" merged {pr.get("merged_at", "")}'.strip()
    origin = f"{repo}@{sha} actor={actor_type} via={via} at={_now_iso(now)}"

    mem = _decision_memory(store, DOMAIN)
    if not live:
        row = mem.propose(question, commitment, rationale=reason, origin=origin)
        return Deposit(row=row, superseded=None, states=states)

    old = live[0]
    if old.get("target_text") == commitment:
        # The same outcome deposited twice is one fact, not two rows.
        return Deposit(row=old, superseded=None, states=states, unchanged=True)

    # A re-run at the same sha with a different outcome: Nestor's draft→draft
    # verb. The old row keeps its text and reason and gains `superseded_by`;
    # `memory_lineage` walks the chain. No edge is proposed for this — an
    # edge relates two decisions, and this is one question answered again.
    from nestor import memory  # type: ignore[import-not-found]
    row = memory.revise_draft(question, commitment, DOMAIN, DOMAIN,
                              reason=(reason + " " if reason else "") + f"re-run via {via}",
                              origin=origin, store=store)
    return Deposit(row=row, superseded=old["id"], states=states)


@dataclass
class Links:
    linked: list[dict] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    ambiguous: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"linked": list(self.linked), "unmatched": list(self.unmatched),
                "ambiguous": list(self.ambiguous)}


def link_decisions(store: Any, row_id: str, refs: Iterable[str]) -> Links:
    """Propose `refines` edges from the CI row to each decision a `Decision:`
    trailer named. A prefix that matches no `decision` pair is reported under
    `unmatched`; one that matches several is reported under `ambiguous` with
    the candidates. Neither is guessed."""
    decisions = [r for r in _rows(store) if r.get("source_lang") == "decision"]
    out = Links()
    mem = _decision_memory(store, DOMAIN)
    for ref in refs:
        ref = ref.lower()
        hits = [r for r in decisions if r["id"].lower().startswith(ref)]
        if not hits:
            out.unmatched.append(ref)
            continue
        if len(hits) > 1:
            out.ambiguous.append({"ref": ref, "candidates": sorted(h["id"] for h in hits)})
            continue
        target = hits[0]
        edge = mem.propose_edge(row_id, target["id"], "refines",
                                reason=f"named by a Decision: trailer ({ref})")
        out.linked.append({"ref": ref, "decision": target["id"], "question": target["source_text"],
                           "edge": edge["id"]})
    return out


def newest_deposit(store: Any, repo: str | None = None) -> dict | None:
    """The newest live `ci` row, for `repo` or for any repo, or None. The read
    Rule 3's second question hangs off: how old is the store's last CI
    knowledge. Rows revised into history (`superseded_by` set) do not count;
    the live row is the store's current knowledge."""
    prefix = f"How did CI go for {repo}@" if repo else "How did CI go for "
    rows = [r for r in _rows(store)
            if r.get("source_lang") == DOMAIN and r.get("source_text", "").startswith(prefix)
            and not r.get("superseded_by")]
    if not rows:
        return None
    return max(rows, key=lambda r: r.get("created_at", ""))


_SHA_IN_QUESTION = re.compile(r"^How did CI go for (?P<repo>[^@\s]+)@(?P<sha>[0-9a-fA-F]+)\?$")


def _parse_when(s: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def deposit_age(store: Any, repo: str | None = None,
                now: datetime | None = None) -> dict | None:
    """Rule 3, second question: *was the answer current?* Returns None when
    the store holds no `ci` row, else `{"repo", "sha", "at", "age_seconds",
    "states"}` for the newest live row, where `states` counts the run states
    named in its commitment. `at` is the row's `created_at`; the deposit's
    own `at=` in the origin is the run's time and may differ. Never raises
    on a malformed row: an unreadable date is `age_seconds: None`."""
    row = newest_deposit(store, repo)
    if row is None:
        return None
    m = _SHA_IN_QUESTION.match(row.get("source_text", ""))
    when = _parse_when(row.get("created_at", ""))
    age = None
    if when is not None:
        age = max(0.0, ((now or datetime.now(timezone.utc)) - when).total_seconds())
    states: dict[str, int] = {}
    for part in (row.get("target_text") or "").split(";"):
        state = part.strip().split(":", 1)[0].strip()
        if state in STATES:
            states[state] = states.get(state, 0) + 1
    return {"repo": m.group("repo") if m else "", "sha": m.group("sha") if m else "",
            "at": row.get("created_at", ""), "age_seconds": age, "states": states}


def human_age(seconds: float | None) -> str:
    """`None` → "unknown age"; else the two largest units, `3d 4h`, `12m`, `0s`."""
    if seconds is None:
        return "unknown age"
    s = int(seconds)
    units = (("d", 86400), ("h", 3600), ("m", 60), ("s", 1))
    parts = []
    for name, size in units:
        if s >= size:
            parts.append(f"{s // size}{name}")
            s %= size
        if len(parts) == 2:
            break
    return " ".join(parts) or "0s"


# ── the bot's inbox (shape C) ──────────────────────────────────────────────

@dataclass
class InboxRead:
    """What `read_inbox` found. `keyed` maps a head sha to its runs; `unkeyed`
    holds check-run items that carry no sha and so cannot be deposited under
    any question — reported, never guessed at. `skipped` counts items that
    were not check runs."""
    keyed: dict[str, list[Run]] = field(default_factory=dict)
    unkeyed: list[dict] = field(default_factory=list)
    skipped: int = 0
    repo: dict[str, str] = field(default_factory=dict)
    #: sha -> the `sender_type` the bridge copied from the payload, verbatim
    #: ("Bot", "User", "Organization", or ""). Not mapped here; the caller
    #: decides what an unknown type means, and `deposit_ci` refuses anything
    #: but Bot or User.
    actor: dict[str, str] = field(default_factory=dict)


def read_inbox(inbox: str | Path) -> InboxRead:
    """Read willow-bot's webhook inbox (`integrations/fleet_bridge.py`): one
    JSON file per queued event. Only `kind == "check_run"` items are
    deposits. As of 2026-09-03 the bridge writes no `head_sha`; an item
    without one lands in `unkeyed` and the tool reports it, because a row
    that cannot name its sha would be filed under a question it cannot
    answer. A `sender_type` field, when present, is the actor type."""
    root = Path(inbox)
    out = InboxRead()
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.unkeyed.append({"file": path.name, "why": "unreadable"})
            continue
        if item.get("kind") != "check_run":
            out.skipped += 1
            continue
        sha = (item.get("head_sha") or "").strip()
        if not sha:
            out.unkeyed.append({"file": path.name, "why": "no head_sha",
                                "name": item.get("name"), "conclusion": item.get("conclusion")})
            continue
        run = Run(name=str(item.get("name") or ""), status=str(item.get("status") or "completed"),
                  conclusion=str(item.get("conclusion") or ""),
                  run_id=str(item.get("check_id") or item.get("id") or ""),
                  url=str(item.get("html_url") or ""))
        out.keyed.setdefault(sha, []).append(run)
        if item.get("repo"):
            out.repo[sha] = str(item["repo"])
        sender = str(item.get("sender_type") or "")
        if sender and sha not in out.actor:
            out.actor[sha] = sender
    return out
