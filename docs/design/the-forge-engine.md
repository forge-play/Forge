@markdownai v1.0

# The Forge engine — as built

What stands, what each part promises, and what is next. The founding design
is in the sibling documents; this one describes the engine as it is.

## The one question

Everything in the engine asks the same thing of its record: **has a human
already answered this?** Nestor asks it of facts and answers with a signature.
The Forge asks it of a maker's decisions and answers with a confirm. The
workflow — never the model — proceeds without asking exactly when this maker
already answered this same decision-type and the record says so under their
name. Proceeding is a light confirm, never a silent commit; "it's different"
always escapes to a full Socratic ask. Permission is per decision-type, never
per session. Waved-through answers decay; argued ones hold.

## The parts

### The entry — `forge/entry.py`, `forge/majors.py`, `forge/keywords.toml`

`open_bite(sentence, project_id=, builder_id=, responder=)`.

1. **Nestor, first, or refuse.** The per-project store at
   `paths.project_nestor(project_id)` is asked before anything else. Absent
   Nestor is `EntryError`: a build that never asked cannot start. A sealed
   answer short-circuits the rest.
2. **The box.** A `BoxLookup` seam; the default returns nothing and says so.
   The real lookup — the corpus, the app catalog — plugs in from the willow
   side.
3. **Remote.** Not built. Recorded as `not_attempted`, never pretended.
4. **The scan.** `majors.scan` over `keywords.toml`: word-boundary,
   case-insensitive, deterministic. One major: the bite knows what it is.
   More than one: a `Decision` (the majors as options, the table's reasons as
   tradeoffs) through `run_checkpoint`. No keyword: an honest empty.

`Entry.tiers` records which tier answered and how. The scan emits
`(source, target, reason, path, anchor)` so the corpus's prose lane can use
the same component; the Forge discards the last two.

@constraint severity=critical
The entry refuses without Nestor. There is no soft degrade at the door.

### The checkpoint loop — `forge/checkpoint.py` and siblings

`run_checkpoint(decision, builder_id=, responder=, root=)` routes a
`Decision(decision_type, surface, options, recommended)` against the maker's
own memory (`checkpoint_memory`, one Nestor store per builder, domain
`builder:<id>:decision:<type>`) into one of three bands:

- **auto** — a sealed hit at or above Nestor's seal threshold: a light confirm,
  no re-seal.
- **recognize** — a real but sub-threshold match: a light confirm that seals
  on yes and falls through to Socratic on "it's different", teaching the
  memory to stop conflating the two.
- **socratic** — a fresh decision-type, an escape from either band, or memory
  unavailable: the options with their tradeoffs, the maker's pick and
  rationale, sealed (or, without memory, decided and reported unsealed).

Around it: the engagement gate scores the maker's rationale with the vendored
friction scorer (`RUBBER_STAMP_FLOOR = 0.34`; a signal, never a block); FSRS
or a fixed-interval fallback resurfaces seals (`checkpoint_schedule`,
`checkpoint_calibration`), and a held decision the maker barely re-argued
comes back sooner; the mid-session nudge (`checkpoint_nudge`) watches a run
for mirroring; every memory-backed commit writes a `human_loop` attestation
and a decision can be parked into the human-required queue and resumed
(`checkpoint_governance`).

@constraint severity=critical
The model never touches the router. Bands come from memory; extraction is by
rule; `recommended` is only the fallback for an explicit "you choose".

### Decision extraction and the build loop — `forge/plan_shape.py`, `decision_extract.py`, `build_loop.py`

A plan is `app_name` plus entries. The host's plan carries only `file_write`
entries and cannot express a choice; the engine adds one kind, **`fork`**:
`decision_type`, `surface`, `options[{label, tradeoff}]`, `recommended`,
`confidence`, `resolves{label: [file_write…]}`. A model-written plan carries
forks; nothing else it writes reaches the router.

`extract(plan, entry=)` notices decisions by rule: **R1** the entry's open
major ambiguity; **R2** every fork (a fork that cannot be asked is refused
*with its reason*, never dropped); **R3** two writes to one path. A plan with
none extracts to nothing and says so — `nothing_to_decide`, which is the
difference between "no decision here" and "could not look".

`resolve(plan, builder_id=, responder=, root=)` runs each decision through
the checkpoint in plan order, substitutes the chosen branch back, and refuses
to return a plan with a fork left in it.

**The calibration wire.** For each fork with a recommendation and a
confidence: `record_prediction("<type>: maker picks <recommended>",
confidence)` before the ask; `resolve_prediction(chosen == recommended)`
after. The maker's pick is the ground truth; no opinion enters. No
confidence, no record. A settled prediction is never reopened. The ledger is
a plain file store and learns with or without Nestor; only the seal needs
memory.

### The measuring panel — `forge/measure_panel.py`, the instruments

Instruments run across a build directory; **convergence** — two or more
instruments naming one artifact — is the alarm, and with a builder id the
convergent findings route into the human-required queue. Four coverage
states, kept distinct on purpose: findings; RAN BUT FOUND NOTHING MEASURABLE;
COULD NOT RUN (with the reason); NOT COVERED AT ALL (with the fleet tool that
would cover it). Tool caches and outputs are pruned by a named set
(`PRUNED_DIRS`); anything unlisted is still walked.

`instrument_callgraph` drives codebase-memory-mcp for dead code and refuses
what it cannot read — a format change is COULD NOT RUN, never clean.
`instrument_execution` parses inside kartikeya's sandbox or declares the gap.

### Calibration — `forge/calibration.py`, `calibration_ledger.py`

Predictions in `[0.5, 1.0]` stated in the believed direction; a scorecard of
brier, log score, hit rate and overconfidence over the resolved ones; one
`review` item routed to a human when the record is thick enough and the
model promises more than it delivers. Never blocks; surfaces.

### Model routing and egress — `forge/model_route.py`, `model_egress.py`

Declared-not-ambient: local by default; cloud only when the maker's signed
manifest permits it, and the egress module is the one impure adapter (lazy
network imports), so the package core stays pure.

### Promotion trust — `forge/trust.py`, `tools/promotion_trust.py`

§0.2 — proposing and ratifying never rest in the same hand — as a mechanism:
the author **enrolls** (a provisional, custody-chained seal through the
gate), a different hand **ratifies** (a custody checkpoint signed by the
verifier's key), and **witness** recomputes both the way the store's gate
does and prints the `trust` block. Optional (`forge[trust]`); fail-closed on
import without the seam.

### The home — `forge/paths.py`

`~/.forge` (or `FORGE_HOME`), resolved in one place. `checkpoints/` for the
per-builder memory, schedules and ledger; `projects/<id>/nestor/keep/` for
the per-project store.

## Invariants the tests hold

- The engine never imports `willow_mcp` (`tests/test_no_reach_back.py`).
  Willow depends on the Forge; the reverse is a cycle.
- Zero runtime dependencies; the base install runs the suite without Nestor
  (`tests.yml`, the no-extras leg).
- The three release files agree, and every disagreement would be silent
  (`tests/test_release_wiring.py`, fifteen rules). The version has exactly
  one source: the git tag.
- Only commits that change what `pip install forge-play` gives someone cut a
  release (`pr-title.yml`, both directions).
- `forge/friction_floor.py` is byte-identical to the willow-gate original
  below its header; willow-mcp's drift guard hashes this file to prove it.
- The demo never writes outside its own playground (`tests/test_demo.py`).

## What is next

- **Vendoring went home (2026-09-03).** willow-mcp pins `forge-play>=0.1.0,<1.0.0`
  and re-exports `human_loop`, `friction_floor` and the detection half of
  `model_egress` from `forge`; `denial()` stays with willow-mcp's consent store.
- **The host side.** The store's stub builder emits a `fork` from the entry's
  scan of a sentence, and its build spine calls `forge.build_loop.resolve`
  before the seam; the seam refuses an unresolved fork.
- **The box.** A real `BoxLookup` over the corpus and the app catalog.
- **Model-proposed candidates.** The fork is the seam; a local model that
  writes forks into a plan is the first thing that can use it.
- **The PR-time deposit.** Built (2026-09-03): `forge/deposit.py` writes
  `ci` rows and `refines` edges, propose-only, and reads willow-bot's webhook
  inbox; `tools/pr_deposit.py` is the caller. Paper: `the-pr-time-deposit.md`.
  `Entry.tiers["deposit"]` reports the store's last CI knowledge with its
  age (Rule 3's second question), `none` when there is none. The bridge fix
  in willow-bot (key on check id, carry `head_sha`) is on a branch there.
- **The store pull.** A project store comes home to the box as shape, gated
  the way the app store promotes. On paper: `the-store-pull.md`, four drafts.
- **The forge-workshop.** The template repo where the first question gets
  asked; the same package; the live store stays home and the repo carries
  the bundle. On paper: `the-forge-workshop.md`.
- **The record gate.** Seven mechanical gates over a workshop's bundle,
  beside the store's nine. On paper: `the-record-gate.md`; the store holds
  a pointer.
- **The store diff.** Built (2026-09-03): the entry's third tier reports how
  far the project store is from the main one — verified upstream, proposed
  here, conflicts, retired here but sealed there — or `not consulted`.
  `forge/store_diff.py`, `tools/store_diff.py`. Paper: `the-store-diff.md`.
- **The trust block on this repo's own promotion.** The tool exists; the
  ratifying half is a verifier's act.

@prompt
When changing the engine, keep the four coverage states distinct, keep the
model out of the router, and keep the entry's refusal hard. Put new decisions
on paper — a draft in the per-project Nestor with the recipe that checks it —
before code.
