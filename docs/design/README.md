# The Forge — design

Two kinds of document live here.

**The founding design** — written before and during the engine's first build,
while it lived inside `safe-app-store` and its shape was worked out at
Willow's desk in the Grove. They are kept byte-identical to how they were
written, dates and all: they are the argument the engine was built from, and
a reader who wants to know *why* a thing is the way it is starts here. Their
cross-references point at the repositories they were written in.

| File | Written in | Date | What it is |
|---|---|---|---|
| `the-forge.md` | safe-app-store | 2026-08-11 | The founding design: D1–D13, the bite ladder for the learning layer, what landed first. |
| `the-forge-shape.md` | willows-grove | 2026-08-30 | A captured working conversation: what the Forge is, the keyword → major scan, per-project Nestor, Nestor-first, the PR deposit. Sixteen "Decisions taken". |
| `the-forge-reuse-map.md` | safe-app-store | 2026-08-11 | What the fleet already had and what the Forge wires rather than builds. |
| `the-forge-human-loop.md` | safe-app-store | 2026-08-11 | D-HL-1..6: the human-required queue and attestations, adopted under checkpoint. |
| `the-forge-fsrs.md` | safe-app-store | 2026-08-11 | D-FSRS-1..4: spaced resurfacing of seals; a soft dependency. |
| `the-forge-measure.md` | safe-app-store | 2026-08-11 | The measuring panel: convergence is the alarm; coverage reported honestly. |
| `the-forge-promotion.md` | safe-app-store | 2026-08-11 | The extraction and promotion plan; the `host_repointed` gate. |
| `the-forge-readiness.md` | safe-app-store | 2026-08-16 | D-R1..7: the panel measured against the production-readiness corpus; no mechanical Pass. |
| `the-forge-landscape.md` | safe-app-store | 2026-08-11 | Where the Forge sits among the fleet's components. |
| `the-forge-review-2026-07-31.md` | safe-app-store | 2026-07-31 | An external review of the v1 design. |

**The engine as built** — `the-forge-engine.md`: what stands today, the
invariants each part holds, and what is next. This one is maintained.

Decisions taken since the founding design are not in these files. They are
drafts in the engine's own per-project Nestor, each with the recipe that
checks it, waiting for a human seal. Documents are cited, never sealed.
