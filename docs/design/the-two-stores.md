@markdownai v1.0

# The two stores — why a workshop's bundle cannot carry its decisions

> **Prior art, read before code:** `forge/paths.py`'s docstring, which says the
> split out loud; `the-forge-workshop.md`'s rule on what the repo carries;
> `the-store-pull.md`'s table of what flows back; and `forge/bundle.py`, which
> exports one of the two stores and not the other.

Found on 2026-09-07, while tracing where a maker's first decision goes. The
answer is: somewhere real, and not where the bundle looks.

## The finding

Exactly one module in the engine writes a pair into a project store:

```
grep -rnE '\.propose\(|propose_edge|DecisionMemory' forge/*.py
  → forge/deposit.py, and nothing else
```

`deposit.py` writes `ci` rows on a merged PR. The entry does not propose. The
checkpoint does not propose. The build loop does not propose.

A maker's decisions go to the **per-builder checkpoint memory** instead. After
the first bite on `source-trail`:

```
~/.forge/checkpoints/rudi193.db              the decision, sealed
~/.forge/checkpoints/rudi193.soil.json       its attestation
~/.forge/checkpoints/ledger.jsonl            4 entries, domain
                                             builder:rudi193:decision:major

~/.forge/projects/source-trail/…/nestor.db   1 entry, pairs 0   ← exported
```

`forge-export` cuts the second. So the bundle read:

```
cut source-trail at head 11ccea963dc3a481  pairs 0 sealed 0
counts: {pairs 0, sealed 0, evidence 0, warrants 0, rejections 0}
```

A decision had just been made, argued at the checkpoint, and sealed. The bundle
that is supposed to be the project's shape contains none of it.

## This is not a bug

`paths.py` names the split deliberately: the project store is *"distinct from
the per-BUILDER checkpoint memory under `<home>/checkpoints/` (a maker's own
sealed decisions)"*. The two exist for different reasons.

- **The project store** is one build's world — disposable, portable, ships with
  the project.
- **The builder store** is one maker's calibration across every project they
  have ever touched. It is what `has_sealed` reads to decide how hard to argue
  with them next time. It is keyed `builder:<id>:decision:<type>` and carries
  no project at all.

Both are right. The gap is that nothing joins them.

## What the papers assume, and what is true

`the-forge-workshop.md` says the repo carries *"questions, commitments, edges,
warrants with recipes and digests, rejections, the ledger chain."*
`the-store-pull.md`'s table says the pull moves *"drafts, unsigned edges,
warrants, rejections."*

Measured today, a workshop bundle can carry exactly one thing: `ci` rows from
`deposit.py`, once a PR has merged. Before the first merge it is empty, and it
is empty however many decisions the maker has taken. The two papers describe a
bundle whose contents no code path produces.

## Why the obvious fix is wrong

Export the builder store into the workshop repo, and a workshop's committed
bundle carries every decision that maker has made — on their finances, on their
employer's code, on the app they abandoned last year. The builder store spans
projects by design, because calibration that reset per project would not be
calibration.

@constraint severity=critical
A workshop bundle never carries a row from another project. The builder store
is per-maker and cross-project; it may not be exported into a project
repository whole, at any tier, under any gate.

## The shape of an answer

What a workshop wants is not the builder store. It is a **projection** of it —
the decisions this maker took *in this project* — and that projection cannot be
computed today, because a checkpoint row records the builder and the
decision-type and never the project.

That suggests the smallest honest change is not an export path but a field: the
project on the checkpoint row, so the projection is a filter rather than a
guess. Everything else follows from it, and nothing else is safe without it.

Three questions that a field alone does not settle:

- **Which direction writes.** Does the checkpoint also propose into the project
  store (two writes, one truth), or does the export project from the builder
  store at cut time (one write, a derived view)? The second keeps calibration
  authoritative in one place; the first survives a builder store the workshop
  cannot read.
- **What a shared workshop does.** Two makers, two builder stores, one repo. A
  projection per maker is a bundle that differs by who cuts it, which the
  ledger head is supposed to make impossible.
- **Whether an unsealed decision travels.** The pull's rule is drafts only and
  nothing sealed crosses the seam. A checkpoint seal is a *maker's* seal, not a
  verifier's, so the word means something different on each side of the join.

## Decisions taken

- The split is deliberate and stays: per-maker calibration, per-project world.
- The builder store is never exported whole into a project repository.
- What a workshop's bundle carries today is `ci` rows and nothing else, and the
  workshop and store-pull papers overstate it until this is closed.

## Open

| gap | state | waiting on |
|---|---|---|
| A checkpoint row records builder and decision-type, never project — so "the decisions taken in this workshop" cannot be computed. | **open, and upstream of the rest** | Adding the field is small; it is the join everything else needs. |
| Whether the checkpoint proposes into the project store, or the export projects from the builder store at cut time. | open | The two-writes / one-derived-view argument above. |
| Two makers, one workshop: a per-maker projection makes the bundle depend on who cuts it. | open | Conflicts with the ledger head being the pin. |
| A maker's seal and a verifier's seal are both "sealed" and mean different things across this join. | open | `the-store-pull.md`'s "nothing sealed crosses the seam" reads differently depending on which is meant. |

@prompt
Before adding an export path here, check what a checkpoint row actually holds —
`forge/checkpoint_memory.py`, the domain string. If it still has no project,
every export is a guess about which rows belong to this repository, and a guess
that is wrong once has published someone's unrelated work.
