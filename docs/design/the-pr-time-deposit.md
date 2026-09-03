@markdownai v1.0

# The PR-time deposit — paper before code

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
deposit or git deposit*. Two shapes fit the walls above.

**A. Pull, from the box.** A tool in this repo (`tools/pr_deposit.py`) runs
where the store is. Given a sha, it asks GitHub for the runs at that sha
(`gh run list --commit <sha>`), the PR that merged it, and the PR's text; it
maps the conclusions, writes the row and the edges through `forge.deposit`,
and prints what it wrote. It runs by hand after a merge, or from a
post-merge hook on the operator's checkout of master.

**B. Push, from CI.** A workflow job on `push: master` produces a Nestor
bundle (the `export` format) as a run artifact; a local step imports it with
`nestor import --apply`. The store still never leaves the box.

**A first.** Three reasons, and all of them are §0.2.

1. The credential that reads checks and the credential that commits never
   meet. Shape A needs `checks: read` and a PR read, which is exactly the
   `willows-bot` core (§13). Shape B needs a job that writes an artifact under
   the same token that could, in another job, tag a release.
2. Shape A puts no identity in CI and no bundle in transit. The propose-only
   property is enforced by the API surface the tool is allowed to call, and
   that surface is auditable in one file.
3. Shape A works today with nothing new provisioned. The operator's `gh` is
   logged in; the origin will say `actor=User` until the bot's installation
   token is what runs it, and the row will say so honestly.

Shape B is not wrong; it is the shape for a box that does not have `gh`. It
stays open, and nothing in A forecloses it: the row format is the bundle
format.

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
- `tools/pr_deposit.py` — the `gh`-driven caller. `--sha`, `--project-id`,
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
- Shape A (pull from the box) first; Shape B stays open.
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
