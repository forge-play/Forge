@markdownai v1.0

# The session entry: willow-mcp's session start on the Forge's shape

> **Status: proposal.** Nothing here is built. Written 2026-09-23 by the
> Vishwakarma seat after the operator suggested that session start in
> willow-mcp could take the Forge's shape.
>
> **Prior art, read before code:** `forge/entry.py` (`open_bite`, `BoxLookup`,
> `NoBox`, the tier strings); `forge/deposit.py` (`ProposeOnly`, the `ci`
> domain); `the-forge-shape.md` §3 and §11; `the-two-stores.md`. willow-mcp:
> `src/willow_mcp/dispatch.py` (`session_enter`, `session_handoff_write`,
> `latest_project_handoff`); `src/willow_mcp/server.py` (the `session_enter`
> tool, which builds `orientation`); `src/willow_mcp/blockers.py`.

## What exists

**The dependency is already in place.** willow-mcp lists
`forge-play>=0.1.0,<1.0.0` as a hard runtime dependency (`pyproject.toml`,
under `dependencies`, not an extra). Only four small pieces of the Forge are
used: `human_loop`, `friction_floor` and `model_egress` are re-exported under
their old import paths, and `meter.py` calls `forge.model_egress.is_local_host`.
Nothing in willow-mcp calls `forge.entry`, the checkpoint router, `deposit`,
`bundle` or `store_diff`. The engine is installed but its main parts are unused.

**What session start does today.** `session_enter` resolves the entry mode
(human, orchestrator or dispatch) and binds a session record. The tool wrapper
in `server.py` then builds `orientation`:

- `records`: five standing collections (`stack`, `pm/portfolio`,
  `pm/milestones`, `pa/commitments`, `governance/flags`), each read or replaced
  by `{"error": "alias_not_configured"}` or a denial;
- `latest_handoff`: the newest `session_handoff-*.md` for this seat and
  project, returned as the whole file;
- `orient` and `frank`: whether `ORIENT.md` and `FRANK` exist;
- `blockers`: what this seat cannot do right now (attestation, egress lease,
  consent, worker);
- for the orchestrator only: pending envelope proposals, auto-propose
  discards, desk attention.

It already follows one of the Forge's rules. Orientation "must never be the
reason entry fails" (`server.py`, the `blockers` block), and `blockers.collect`
reports a failed check as an item instead of raising.

**What a session on 2026-09-23 actually saw.** All five `records` came back
`alias_not_configured`. The handoff was a 15-day-old narrative whose
`## Next bite` section held the real work: seal one pair, fix a paper that does
not render, decide an open remedy. Nothing at entry could say whether any of it
had been done since. The blocker list was right: the egress lease had expired
on 2026-09-03, and "no lease" is a current fact, not stale data.

## What "the Forge's shape" means here, and what it does not

`open_bite` cannot be the session entry as it stands. It turns one sentence
into a major. A session is not choosing a major, and forcing it through the
keyword scan would record decisions nobody made. That is the fault
`the-positional-default.md` exists to prevent.

The shape that carries over is four rules the entry already keeps:

1. **Ask the store first, and say which source answered.** Every source
   reports a state, and no source is silent.
2. **Absence is a value.** `not consulted`, `none`, `could not read` and
   `not_attempted (not built)` are each distinct from empty success.
3. **A decision this human already made is confirmed, not asked again.** This
   runs through the checkpoint router, keyed by decision type.
4. **The work closes with a deposit, propose-only,** into a store the next
   entry reads, and the lineage runs through Nestor rather than prose.

Rules 1 and 2 only report and change nothing. Rule 4 writes drafts and never
seals. Rule 3 decides on the human's behalf, so it carries the Forge's two
known defects with it (see *Held*).

## Proposal

### Phase 1: tiers at session start (willow-mcp only, report-only)

`orientation` gains a `tiers` block. Each source is reported in one fixed
vocabulary, following the Grove's INVARIANTS §8 and the entry's own states:

| State | Meaning | Today's equivalent |
|---|---|---|
| `populated` | read, and holds something | a `records` value with rows |
| `empty` | read, and holds nothing | a `records` value `[]` |
| `unconfigured` | this seat has no route to it | `alias_not_configured` |
| `denied` | a route exists and the gate refused | `_collection_denied` |
| `unreachable` | tried, and it failed | an exception swallowed by `except: pass` |
| `not_attempted` | not built, or skipped on purpose | nothing (absent) |

The existing keys stay, so no caller breaks. `tiers` is added beside them.
The one behaviour change is that swallowed exceptions in the orientation
builders become `unreachable` rows with the error class, instead of
disappearing. A seat can then tell "nothing is pending" from "the count
failed". That is the same gap the auto-propose discards counter was added to
close.

**Forge side:** one small module, `forge.tiers`, exports the state
vocabulary and a frozen `Tier(name, state, detail)`. `Entry.tiers` keeps its
`dict[str, str]` for compatibility and gains a structured twin. willow-mcp
imports the type from the dependency it already has, so the vocabulary has
one home, not two copies that drift.

### Phase 2: next bites as rows, not prose

`session_handoff_write` gains an optional structured `next_bites` list beside
the free-text `next_bite`. Each item is deposited as a **draft**, stamped with
session, seat and project, the way `deposit.py` stamps CI rows. On the next
`session_enter`, a `next_bites` tier lists the open items, each with its
state (still open, resolved, superseded), instead of handing back the whole
file.

The handoff file is still written. It is the narrative, and it stays the
human-readable record.

### The Nestor question, settled by keeping two doors

`forge.entry` refuses outright without Nestor ("an entry that never asked
has nothing to be honest about", §11). willow-mcp carries Nestor only as the
`nestor` extra, with a floor of 0.7.0 against the Forge's 0.20.2.

An earlier conversation offered two options: make Nestor a hard dependency
of willow-mcp, or soften the entry. **This paper takes neither.** The bite
refusal is right for a bite and stays. Session entry is a different door, and
willow-mcp's existing rule (orientation never fails entry) is right for it.
With Nestor absent, the Phase 2 tier reports `unreachable: nestor not
installed` and the session enters. Nothing in the Forge changes, and no
dependency moves.

@constraint severity=critical
Session entry never refuses on an orientation source. A source that cannot be read is reported as a tier state; it never blocks the session.

@constraint severity=critical
The Forge never imports willow-mcp. Everything in this paper is willow-mcp calling the Forge, or a Forge type willow-mcp imports.

@constraint severity=high
Session deposits are drafts. No session verb seals, and no session tier reports a draft as verified.

### The other half: Willow supplies the box

`open_bite`'s box tier is a `BoxLookup` protocol with a default of `NoBox`
("the real lookup ... lives on the willow side; this is the seam it plugs
into", `entry.py`). willow-mcp can supply that implementation over what it
already indexes: the app catalog, the knowledge base and `store_search_all`.
The dependency direction holds, because the Forge defines the protocol and
Willow implements it. This does not touch sessions, but it is the same seam
from the other side, and it is what turns `box: no box wired: nothing` into
an answer.

## Held

**Phase 3, the checkpoint router at session start** (rule 3), is held on two
measured defects:

- **Band selection ignores calibration.** Two simulated makers 100 points
  apart take identical band trajectories, and a maker wrong on every decision
  still has 83.3% of decisions auto-applied (`the-forge-pedagogy.md` §5,
  pinned by `tests/test_band_probe.py`). Letting sessions skip a question on
  that basis would spread the defect to every seat.
- **Seals are not verified on the entry's path.** The entry cannot run with
  the fleet keyring loaded, and `by_human` is structurally false.
  `seal_signatures_verified()` reports this but does not fix it. "You
  already answered this" would rest on seals that nothing checks.

Phase 3 waits until both are closed, not until one is.

## Open

Settled rows are kept, struck: a question closed by an answer is evidence of
how it was answered.

| # | Question | State | Answer / waiting on |
|---|---|---|---|
| 1 | ~~**Where do next bites live?** A Nestor pair is question → answer, and a next bite is an open task, not an answer. willow-mcp's gaps (`gap_log` / `gap_resolve`) already have an open → resolved lifecycle, and commitments do not fit (they are calendar events).~~ | settled | Operator, 2026-09-23: "both, with a gap per bite and a pair only when a bite is decided." Phase 2 writes a gap per next bite; a pair is proposed only when a bite turns into a decision. |
| 2 | **Project name ↔ project id.** Three identities that do not meet. A willow session's project is an explicit name (`Forge`), or else the workspace basename plus an 8-hex digest of the resolved path (`project_context`, `dispatch.py`). The engine's own store is `forge-engine`, chosen by hand. A workshop derives its id from the repo name. | in discussion | operator |
| 3 | **Which SOIL?** `forge.human_loop` writes its own SOIL under `~/.forge`, and Willow has its own. | direction given, shape open | Operator, 2026-09-23: "~/.forge should be for the session, and then it gets promoted to the willow soil (or kb) still uncertain about this shape." So `~/.forge` is the working layer and Willow's SOIL or KB is where it is promoted to. Still open: what triggers the promotion, and SOIL vs KB. |
| 4 | ~~**Seat vs project scope.** Should a next bite written by one seat surface to another seat entering the same project?~~ | settled | Operator, 2026-09-23: yes. The `next_bites` tier is keyed by project, not by seat; each row still names the seat that wrote it. |
| 5 | ~~Phase 1's change from swallowed exceptions to `unreachable` could surface noise that was silent before.~~ | settled | Operator, 2026-09-23: agreed, "not really a question." A Phase 1 step, not an open item: measure on one seat before it applies everywhere. |
