# What the Forge could take from Willow

Written 2026-11-02 from three reads of the two checkouts (the Forge at
0.9.0, Willow at e376cf9) and from a willow stack assembled with Willow's
`ui/assemble.py` and run over a pile holding copies of both repositories.
The stack and its output stayed outside both trees; what it found is
carried below, with the file and line, so each line can be rerun.

The frame: the Forge is a decision engine that borrows its record from
Nestor. Willow is a record kernel with a discipline around it. The Forge
has the harder problem and the lighter discipline. What it could take is
mostly discipline, and a handful of small, stdlib-only pieces.

## Where the Forge stands today

From the Forge read, the plain facts a borrower needs:

- **No hash chain of its own.** Every seal goes through Nestor; the only
  chains are Nestor's `ledger.jsonl` and willow-gate's custody ledger.
  `soil_store.py` is a last-writer-wins JSON file with no chain, no lock,
  and it holds the calibration predictions and the human-loop queue.
- **No exit-code contract.** Refusal is 2 in `entry` and `build_loop`, 1
  almost everywhere else, 3 in `promotion_trust` for a missing seam, and
  `checkpoint_schedule due` uses 2 to mean "not due". Nothing uses 42. No
  test holds any of it.
- **No mutation testing, no write guard, no static no-network check, no
  strip test, no vectors, no coverage report over the constitution.**
  `calibration.py` cites a `tests/test_no_egress.py` that does not exist.
- **Stale claims in its own docs.** `the-forge-engine.md` says
  `friction_floor.py` is byte-identical to willow-gate's; the file's own
  header and the vendor manifest say it is not. CONTRIBUTING says 3.12 runs
  only on master; `tests.yml` runs it on every event.
- **No AGENTS.md or CLAUDE.md.** Willow's `instruction-files` add-on, run
  over the Forge, reports that no agent instruction file would load.
- **What it already has that Willow also has:** the "every scan has a
  planted test" meta-rule (`test_scans_fire.py`, 1,515 lines) is the same
  idea as Willow's `test_docs_fires.py`. The vendor manifest pins bodies by
  SHA-256 the way Willow's `STACK.json` does. The aggregate CI job that
  fails on a skipped leg is the same stance as Willow's "unreachable never
  counts as a pass".

## Deterministic shape to take, in order of value for cost

### 1. The three exit codes, and a contract test

Willow's 0 / 42 / 2: a person said it, not enough to say, refused. The
Forge's human loop already has the 42 state in prose ("silence
escalates", CONST-0-6) and no number for it. Settle one table across every
CLI in `forge/` and `tools/`, and hold it with a test shaped like Willow's
`test_contract.py`: run with no arguments exits 2 with the script's name on
stderr; the good argv exits 0 or 42; a stray argument exits 2. Cost: a day.
It also fixes `due` meaning two things.

### 2. CI verdicts as rows on a record, three states never collapsed

Willow's `ci.py` writes one `verdict` row per gate (state, files hash,
output hash, Python) to a kernel box, with `unreachable` distinct from
`failing`, and a before/after compared gate by gate. The Forge's aggregate
job already refuses a skipped leg, but nothing records what ran against
which tree. The piece to take is the shape, not the 720-line script:
a gate list, a row per gate, a hash of the tree, and a `show`. Without a
box of its own (see 4) the rows can go on the soil store for now.

### 3. Mutants over `forge/`

`mutants.py` (254 lines) is nearly generic: AST breaks on comparisons,
`and`/`or` and integer constants, the six lowest ids by hash so nobody
picks the easy ones, an `accepted.json` whose stale entries fail. It
copies the tree to a temp folder and runs pytest with `-x`. Point it at
`forge/<module>.py` with `tests/test_<module>.py` instead of
`adapters/<name>/`. The Forge has 9,500 lines of engine and no mutation
run; the engagement defect paper is a story about a scorer nobody had
broken on purpose.

### 4. A record of its own, pinned outside the box

The Forge should not reimplement Nestor. But two small things from the
kernel fit beside it:

- **`tip-pin`** (137 lines): the row count and tip hash kept outside the
  box, catching a truncation or a full re-hash that `verify` cannot see.
  Both Nestor's ledger and the custody ledger have this gap. Vendor it.
- **`merkle`** (208 lines): a root over rows and an inclusion proof for
  one, so a single deposit or decision can be proved without shipping the
  store. Vendor it.

And one rule from the kernel for `soil_store.py`: a torn tail is refused,
not repaired, and writes take a lock and fsync. The soil store holds the
calibration ledger; today a crash mid-write loses the file silently.

### 5. A static scan of the engine's own reach, with its plants

Willow's `test_kernel.py` walks the AST for imports outside the stdlib,
network modules, and `eval`/`exec`/`compile`/`__import__`, each with a
planted source that proves the check fires. The Forge's `deposit.py` test
does this by word list for one file. Lift it to every module in `forge/`,
declare the two that may import optional packages, and make the
`test_no_egress.py` that `calibration.py` already cites. The Forge's own
`test_scans_fire.py` will then demand a plant, which is the right pressure.

### 6. A promise per module, and a guard that holds it

Every Willow card says `writes:` and `network:`, and
`guard/sitecustomize.py` (312 lines) raises on the first write outside
the promise, through `sys.addaudithook`. The Forge's `paths.py` says it is
the only module allowed to resolve a home, and nothing holds that. A
header block per module (`writes: <home>/checkpoints/<builder>.*`,
`network: none`, `soft: nestor, fsrs`) plus the guard under the test run
would make the one-way arrows mechanical. This is the biggest lift on the
list; do it after 1 to 5.

### 7. DECISIONS.md with "Held by:", and LIMITS.md

Willow states each settled decision as one bold claim, its reason, and the
test that holds it, or "nothing" when nothing does. The Forge has twenty
design papers and an idea pile, and no single page a reader can use to ask
"is this still true, and what would tell me". The engine paper's stale
byte-identical claim is what happens without one. Cheap, and it makes the
next three items honest.

### 8. Strict xfail and a generated BUGS.md

`bugs.py` (157 lines): every `xfail` must be strict with a reason `bug
#N:`, and BUGS.md is rendered from the tests. The engagement defect and
`has_sealed` trusting unverified seals (ideas 18, 20) are open bugs with
no row anywhere a test can see. Vendor it.

### 9. A frozen case file shared with Willow's `forecasts`

Willow's `forecasts` add-on carries the Forge's Brier, log score and bins
by way of willow-bot, "unchanged". Willow holds its ports to one
`cases.json`; the two copies of the calibration math could be held to one
small case file the same way. That is cheaper than a byte pin and survives
reformatting.

### What not to take

The kernel's rank and search, the no-index rule, the deps floor rule (the
Forge has no runtime deps), the add-on folder layout, and `ci.py` as a
whole (it hard-codes Willow's tree). The constitution's coverage report is
worth copying only once the Forge cites clauses in more than one place;
today `trust.py` cites §0.2 and little else does.

## Add-ons to take

Grouped by what to do with them. Line counts are the add-on's non-test
code. "N" means it uses only the kernel's exit codes, so it vendors clean.

### Vendor as they are

| Add-on | Lines | Why for the Forge |
|---|---|---|
| tip-pin | 137 | pin for Nestor's ledger and the custody ledger (item 4 above) |
| merkle | 208 | prove one deposit or decision without the store |
| diverge | 148 (N) | first differing row, file or line between two stores; fits `store_diff` |
| hook-fail-closed | 89 (N) | wrap any instrument so a crash, timeout or unreadable output blocks, never passes |
| hook-fuzz | 112 (N) | empty, oversized and non-UTF-8 input at an instrument, as a test helper |
| agent-transcript | 169 (N) | Claude Code, Codex, Gemini, Cursor and Copilot sessions as numbered turns; the input `decision_extract` lacks for model-proposed forks (idea 8) |
| weights-pin | 94 (N) | hash the weights file and refuse one that differs from its card; fits `model_route` |
| slow-tests, test-shards | 258, 273 (N) | the Forge's test run is long enough to want both |
| ci/bugs.py | 157 | item 8 above |

### Vendor as measuring-panel instruments

Only census and hygiene run by default today, and the panel names
call-graph, execution and calibration as classes it cannot measure. These
are model-free and stdlib-only, so they fill "unseen" classes honestly:

- **risky-code** (180): known-dangerous patterns by class, "a lead, never
  proof". Over `forge/` today it finds one lead, in `instrument_execution.py`.
- **secrets-audit** (141) and **pii-audit** (173): the redaction class.
- **xref** (158): every link and quoted line still there and still saying
  it. Over the Forge today, five placeholder links in `changelog_dedup.py`.
- **pair-drift** (148): a summary that states what its full text does not;
  README against code, PR body against diff.
- **fixity** (142): the build directory re-hashed between runs, so drift
  without an edit is named.

One caution from running `contradictions` over a mixed pile: it finds the
demo fixture's dates against each other. It is a sibling tool over prose,
not an instrument over code.

### Adapt

- **mutants** (254): item 3 above.
- **test-impact** (648): the tests a change can reach from the import
  graph. About nineteen references to Willow's layout to rewrite.

### Take the idea

- **weakest-link**: an answer is worth its weakest input, marked
  measured, fitted or assumed, never an average. That is a confidence
  ceiling for the checkpoint's stated confidence, and it speaks to
  overconfidence directly.
- **decisions**: `no` with `--never` or `--reopen-when CONDITION`, and
  `chose --replaces ROW` for lineage. The Forge's `reject_match` and
  `reject_pair` have no reopen condition, and idea 72 (checkpoint fatigue)
  is the symptom.
- **stale** and the kernel's `standing()`: a sealed answer is served only
  while the thing it cites still hashes the same. The Forge's seals never
  re-check the artifact. The two-stores paper would read differently with
  this.
- **make-it-so**: the premises of an order pinned by hash and re-checked
  before acting. A deposit with its evidence attached.
- **predict**: the system's own forecast of an outcome put on the record
  before the question is asked. `band_probe` does this in memory; on the
  record it becomes evidence for idea 23 (does the engagement flag
  correlate with anything real).
- **hook-replay**: each instrument's input and output hashed, and `check`
  re-runs them to prove the same answer. A determinism proof for the
  measuring panel.
- **model-exam** and the planned **model-recall**: promote a model only
  after it passes the maker's own sealed checkpoints, and list the seals
  made from a model whose card is later marked flawed. These are the
  trust seam's missing content (ideas 15, 50).
- **pile-gold**: sealed answers as the search's test set. For the Forge:
  sealed decisions as `has_sealed`'s test set.
- **session-seal**: one seal over a whole session's rows is what
  `defer_seal` asks a host for. It is also the rubber-stamp shape the
  engagement score exists to catch. Score it; do not copy it.
- **ci-bets** (planned, unbuilt): a forecast on each PR going green. The
  deposit plus the calibration ledger already hold both halves.

### Call as sibling tools, no work needed

- **nestor** add-on: Willow already reads Nestor's checked pairs as cited
  passages, so a Forge checkpoint store is askable from Willow today.
- **oakenscroll** and **codebase-memory**: each reads a store the panel
  names as a class it cannot measure.
- **forecasts**: already downstream of the Forge's calibration module.
  Do not re-vendor; share a case file (item 9).
- **agents-md-check**, **instruction-files**: run over the Forge, they
  report there is nothing to load. The fix is an AGENTS.md, not a vendor.

## What the stack found running over the Forge today

- No AGENTS.md or CLAUDE.md, so none of the eight agents
  `instruction-files` knows would load anything.
- `xref`: five unresolved links, all placeholders in `changelog_dedup.py`.
  Not a bug; the pattern Willow uses for this is angle-bracket placeholders.
- `secrets-audit`: four hits on the word "password" in code and docs,
  values not shown. False leads on reading.
- `risky-code`: one lead, `instrument_execution.py:62`, a shell line that
  passes a path. Worth a read, not a finding.

And one bug in Willow, found assembling the stack: `ui/assemble.py add`
crashes with a `FileExistsError` traceback, exit 1, when a name it is given
was already copied in the same call as another name's hard dependency
(`secrets-audit` pulls `privacy`; naming `digest` after `decisions` does
the same). The `if name in m["addons"]` check at `ui/assemble.py:249`
reads the manifest, which is only written after every copy. Adding one
name per call works around it.

## A first three bites

1. The exit-code table and its contract test (item 1), with DECISIONS.md
   opened to hold it (item 7). One PR, no new dependency.
2. `tip-pin` and `bugs.py` vendored, the strict-xfail rule applied to the
   two open defects (items 4 and 8).
3. `mutants.py` adapted to `forge/`, run once on a clean tree, the
   survivors read and either killed or accepted with a reason (item 3).

Everything else on the list reads better after those three, because each
later piece wants a number to exit with, a page to be held on, and a
mutant run to prove its test bites.
