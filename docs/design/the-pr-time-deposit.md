@markdownai v1.0

# The PR-time deposit — paper before code

> **Prior art, read before code:** `forge-play/forge-jig/docs/WHERE-THINGS-ARE.md`
> and `WHAT-EXISTS-ALREADY.md` (2026-08-31), and the bot at
> `workshop/willow-bot`. The jig's first rule is the one this paper was first
> written without: ask the corpus, then the box, then remote.

The engine doc's list names it: *CI outcome and decision edges written back
into the project's Nestor, by a propose-only identity.* The shape doc argued it
(§12, §13) and left five things open. This paper closes what can be closed from
the chair that cannot seal, and says which hand closes the rest.

## The question it answers

Rule 3 of the shape doc asks three questions of every build, in order: *has
this been asked, was the answer current, did the result come back?* The entry
answers the first. Nothing answers the third. A PR merges, CI runs, the run
goes green or red, and the project store that the next build will ask first
knows none of it. **A red run that leaves no trace is an empty success.**

The deposit is the third question given a value.

## What is fixed before anything is chosen

These are not decisions of this paper; they are the walls it is built inside.

- **The store is local; CI is not.** `paths.project_nestor("forge-engine")`
  resolves under `~/.forge` on the operator's box. A GitHub workflow cannot
  reach it. So the deposit has two halves, a *claim* made where CI is
  observable and a *landing* where the store is, and the design is mostly the
  choice of where the seam between them sits.
- **Propose only.** Every row the deposit writes is `draft`; every edge it
  writes has `edge_sig=''`. `DecisionMemory.propose` and `propose_edge` are
  the only verbs it may call. Sealing a CI outcome, if anyone ever wants to,
  is a human's key.
- **An actor is a type, never a login.** Two renames already made every login
  string wrong (§13). The origin carries `actor=Bot` or `actor=User`, nothing
  else about who.
- **The model never touches it.** Which decisions a PR relates to is read by
  a rule from the PR's own text, never inferred.
- **Record the failures.** Pass, fail, and *could not run* are three rows,
  not one row and two silences. This is the engine's four-coverage-states
  rule applied to CI: an unreadable run is COULD NOT RUN, never clean.
- **Zero runtime dependencies.** The engine module takes a store and writes
  through it; the network, `gh`, and Nestor's import path are the caller's.

@constraint severity=critical
The deposit writes drafts and unsigned edges only. No path through it reaches
`seal`, `seal_edge`, or a keyring.

## The row

A CI outcome is not a decision. Putting it in the `decision` domain would make
`decision check` find it, and a build asking *"has a human decided this?"*
should never be answered by a workflow run. So the deposit gets its own
domain, keyed `ci`→`ci`, and the store's decision verbs stay blind to it.

| field | value |
| --- | --- |
| domain | `ci` → `ci` (`DecisionMemory(store, domain="ci")`) |
| question | `How did CI go for <owner>/<repo>@<sha>?` |
| commitment | `<state>: <workflow> <conclusion> (run <id>)` per run, `;`-joined, sorted by workflow name |
| reason | the PR: `PR #<n> "<title>" merged <iso-date>`; absent for a push with no PR |
| origin | `<owner>/<repo>@<sha> actor=<Bot|User> via=<tool> at=<iso-utc>` |

`<state>` is one of four, and the mapping from GitHub's conclusion is a table,
not a judgment:

| GitHub `conclusion` | state |
| --- | --- |
| `success` | `pass` |
| `failure`, `startup_failure` | `fail` |
| `cancelled`, `timed_out`, `skipped`, `action_required`, `neutral`, `stale`, empty, unknown | `could_not_run` |
| run still `in_progress` / `queued` | `pending` — the deposit refuses; come back when it is done |

The question is stable per sha. A re-run at the same sha proposes a **new**
row and a `supersedes` edge from the new row to the previous one; the newest
of the chain is the answer, the older ones are the history. That is the same
convention the project store already uses for its own revised drafts.

## The edges

Three relations were named. Two land now; one waits, and the reason is
recorded so it is not mistaken for forgotten.

- **CI row → decision.** When the PR body or any commit in it carries a
  `Decision: <id-prefix>` trailer (8 or more hex characters of a pair id in
  the project store), the deposit proposes `refines` from the CI row to that
  decision. The extractor is a regular expression over the text; an id prefix
  that matches no pair, or more than one, is reported and skipped, never
  guessed. This is the only way a PR relates to a decision, and it is in the
  maker's hand at PR time.
- **CI row → earlier CI row.** `supersedes`, on a re-run at the same sha.
- **PR ↔ issue, file ↔ file.** Not yet. An edge needs both endpoints to be
  pairs in the store (`propose_edge` refuses otherwise, decision 0144), and
  neither an issue nor a file is a pair today. When the corpus lane lands in
  the project store they become addressable; until then an edge to them would
  be an edge to nothing.

## Where each half runs

The shape doc left it open: *workflow, hook, or merge queue*, and *store
deposit or git deposit*. Three shapes fit the walls above, and the fleet
already runs one of them.

**C. The event arrives on the box.** `workshop/willow-bot` is a signed
webhook listener on the box. Its fleet bridge runs before any handler and,
for every completed check run, files one JSON item into
`$WILLOW_HOME/upstream_steward/webhook_inbox/<work_id>.json` with the
conclusion, the check name, the run URL and the PR number, deduplicated on
the path. That inbox is the deposit's inbound half. Nothing consumes it. The
deposit tool reads that directory and writes the row through `forge.deposit`.
No polling, no `gh`, no lease from any seat; the actor is the payload's
sender type.

Read at the code level, 2026-09-03, the bridge has four defects the consumer
must not inherit and one it must work around:

- **One check per PR.** The work id is `<repo>:check:<pr_number>`, and a
  path that exists is skipped. The first completed check on a PR is filed;
  every later one on the same PR is dropped silently. A PR with four
  workflows leaves one item. The consumer cannot repair this; the bridge's
  key must include the check id or the head sha.
- **No head sha.** The item carries no `head_sha`, and the deposit keys on
  the sha. The payload has it; the bridge does not copy it.
- **A check with no PR** is keyed on the check id, so it is filed, but the
  item cannot say which sha it belongs to. Same fix.
- **The router drops could-not-run.** Success and failure get a voice line;
  cancelled, skipped, stale and neutral return without a log line. The
  bridge files them (it filters on `completed`, not on conclusion), so the
  inbox is the honest record and the router is not.
- **Not running here.** No inbox directory exists under either willow home,
  the unit is not installed, and the bridge's default home is the decoy
  path one level above the fleet's. Until the bot runs on this box under
  the right home, the inbox is empty by construction.

**A. Pull, from the box.** `tools/pr_deposit.py --sha` asks GitHub through
`gh` for the runs at a sha and the PR that merged it. The backfill for
history the bot never saw, and the path for a box without the bot. Needs the
operator's `gh`; from a seat, it is egress the gate does not watch, and it
must not be a warrant recipe.

**B. Push, from CI.** A workflow job on `push: master` produces a Nestor
bundle as a run artifact; a local step imports it. The shape for a box with
neither the bot nor `gh`. Stays open, not wrong.

**C first, A for backfill, B on the shelf.** C is event-driven and keeps
§0.2 by construction: the bot reads and comments and cannot commit. The
bridge fix (key on check id and carry `head_sha`) is a willow-bot change,
small, and paper for it is a gap in the backlog (`1d737ffa2595`).

@constraint severity=high
The deposit tool gates on what it read, never on an exit code. A run that
cannot be read is a `could_not_run` row, not a skipped deposit.

## The age (Rule 3, second question)

Once rows exist, the store can say how old its newest deposit is. That is a
read, not a write, and it belongs in the entry's report, not in the deposit:
`Entry.tiers` gains `deposit_age` beside `nestor` so a build can see it asked
a store whose last CI knowledge is nine days old. Second PR; named here so the
row carries what the read will need (`at=` in the origin).

## What the engine ships

- `forge/deposit.py` — pure over a store.
  `outcome_state(conclusion) -> str`, the table above.
  `extract_decision_refs(text) -> list[str]`, the regex.
  `deposit_ci(store, *, repo, sha, runs, pr=None, actor_type, via) -> row`,
  proposes the row and the `supersedes` edge.
  `link_decisions(store, row, refs) -> list[edge]`, proposes `refines` edges,
  reports the unmatched.
- `tools/pr_deposit.py` — the caller. `--inbox <dir>` reads the bot's
  webhook inbox (shape C); `--sha` asks `gh` (shape A, backfill). `--project-id`,
  `--dry-run` prints the row and edges and writes nothing.
- `tests/test_deposit.py` — the mapping table, the regex, the supersedes
  chain, the refusal on a pending run, the unmatched-ref report, and that the
  module never names `seal`.

## Decisions taken

- The CI outcome lives in its own domain, `ci`; the decision verbs do not see
  it.
- Four states, mapped by table; `pending` refuses.
- A re-run supersedes; the question text is stable per sha.
- A PR names its decisions with a `Decision:` trailer; nothing else links
  them.
- Shape C (the bot's inbox on the box) first, A for backfill, B stays open.
- Issues and files are not edge endpoints until they are pairs.

## Open

- The bot's installation token as the runner, so the origin says
  `actor=Bot` because the credential is one, not because a string says so.
- Whether the post-merge hook is a git hook on the operator's checkout or a
  step in the same place the corpus `refresh.py` runs. Both are local.
- The age in `Entry.tiers` (the second PR).
- Whether `ci` rows should ever be sealed, and by whom. The paper's answer is
  *no one needs to*; a sealed CI outcome adds nothing a signed run URL does
  not.

@prompt
When building this: the module takes a store and never opens the network.
`propose` and `propose_edge` are the only Nestor verbs it calls. If a test
wants to assert a seal, the test is wrong.
