@markdownai v1.0

# The record gate — what a promotion can ask once there is a record

> Lives here, beside the engine, because the record it reads is the engine's
> product. `safe-app-store`'s `docs/design/the-record-gate.md` is a pointer
> to this file and nothing else; the store is where pieces are taken from
> and where the promotion record lives, not where the design is written.
> The gate it extends is `stores/promote_check.py` there, nine gates,
> mechanical `[M]` or attested `[A]`, all-PASS or nothing is written.

The operator, 2026-09-03: *"there's a lot of slop people are putting out into
the world right now and this possibly could be a solution to some of that."*

## What slop looks like from the record's side

Not bad code. A missing process. No decision was ever recorded, so nothing
was argued. Nothing was ever rejected, so no negative exists. CI was only
ever green at the end, because the history was squashed or never kept.
Nothing carries a recipe that recomputes. Nothing is an edge. And the author
and the verifier are the same hand, or the verifier is a string.

Every one of those is a property of the record, not of the code. Every one
of them is something a workshop produces as a side effect of building the
honest way, and something the store's gate cannot see today, because until
the workshop there was no record of the process to read.

## What the gate reads today

The nine gates read the artifact and its attestation: two names that differ,
a repo of its own, the host repointed, a manifest, tests green now, no vault
leak, a pure core, the seam. The record writer refuses `verified_by ==
author` on its own, independent of the gate list. That stays. What follows
is added beside it, never instead of it.

## What a workshop bundle lets the gate ask

Each of these is mechanical over the exported bundle. None is a judgment of
quality, and none is a model grading a model.

| gate | reads | passes when |
|---|---|---|
| `argued [M]` | sealed decisions' rationales through the engagement scorer | the share above the rubber-stamp floor is reported; denies only at zero. The scorer was measured at chance on stance (willow-gate#9), so it is a signal, never the verdict |
| `negatives_recorded [M]` | rejections with reasons; `ci` rows whose state is not `pass`; drafts with a `superseded_by` | at least one exists. A record that was only ever green has either never been run or has been cleaned |
| `warrants_hold [M]` | every construction warrant's recipe, re-run here | each recomputes to its digest; BROKEN is reported per warrant and denies (this is the tests-green of claims) |
| `human_verified [M]` | every seal's signature against the fleet keyring | all verify, and no seal's verifier equals the bundle's author. Unverifiable seals are demoted and counted, as the importer already does |
| `connected [M]` | `decision_edges`, `memory_lineage` | at least one edge or one lineage hop. Slop has no edges because nothing in it was ever related to anything |
| `deposited [M]` | `ci` rows against the repo's merge shas | the merge sha being promoted has a `ci` row, and it was not `pending` |
| `bundle_at_head [M]` | the bundle's ledger head against `forge/HEAD` and the ledger chain | they match and the chain verifies |

Seven gates, all over the bundle. The store's nine stay as they are. A
promotion that passes sixteen gates carries a record that says: argued,
run, checked, connected, and verified by a hand that is not the author's.

@constraint severity=critical
No gate here calls a model. Every verdict is a recomputation, a signature
check, or a count over the bundle. The engagement scorer is deterministic
and is reported as a share, never used alone to deny.

## The honest limit, stated first

This does not tell good from bad. It tells argued from waved through, run
from never run, checked from asserted, connected from isolated.

Someone can fabricate a record. What that costs: the seals need a key the
fabricator does not hold; the calibration ledger needs outcomes that only
come from running the thing; the warrants need digests that only recompute
if the recipe is real; the `ci` rows need runs that GitHub reports. Gaming
the record costs about what doing the work costs. **That is the property,
and it is the whole claim.** A gate whose bypass is cheaper than compliance
is theater; this one's bypass is compliance.

## The part that travels

A promoted app carries its record, and the record is shape, never content
(§8). So the record can sit public beside the app, and a reader who does
not trust the store can re-run the warrants and re-check the seals
themselves. That is what makes a promoted list citable rather than a badge.
The awesome list's own rule, in the shape doc: *criteria are what make a
list citable.* These are the criteria.

## Where each piece lives

- The bundle and its verbs: Nestor (`export`, `import`, `ledger verify`,
  `warrant`).
- The scorer and the floor: `forge/checkpoint_engagement.py`, the vendored
  `friction_floor`.
- The `ci` rows: `forge/deposit.py`.
- The gate functions: a module in the store beside `promote_check.py`,
  each returning `(name, ok, detail)` like the nine, reading a bundle path
  from the attestation. The store owns the gate list; the engine owns what
  the gates read. Nothing in the engine imports the store.

## Decisions taken

- The record gate extends the store's nine gates; it replaces none.
- Seven gates, all mechanical over the bundle; no model in the loop.
- The engagement score is reported as a share and denies only at zero.
- Broken warrants deny a promotion (unlike the pull, where they only
  report), because a promotion is a claim to strangers.
- The design lives in the Forge; the store holds a pointer.

## Open

- The rubber-stamp share below which `argued` should deny, if ever above
  zero. Measured on the first ten promoted workshops, not set now.
- Whether `deposited` should require every merge sha or only the promoted
  one.
- The attestation field that names the bundle path.

@prompt
When building this: gate functions go in the store, reading a bundle;
nothing new goes in the engine except what the gates read. If a gate wants
to call a model, it is not a gate.
