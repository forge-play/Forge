# The Forge

**The engine that refuses a confident wrong answer.** *Per ignem, probatur — proven through fire.*

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)
[![Runtime deps](https://img.shields.io/badge/runtime%20deps-none-lightgrey)](pyproject.toml)

The Forge is the **model side** of a SAFE-native app-building system: not a
model that emits answers, but the harness that refuses to let a confident wrong
one stand. It is the engine every builder in the fleet pins, and it needs **no
live model** to run — it works on decisions, plans and build directories the
way a linter works on source.

It asks one question of everything that passes through it: **has a human
already answered this?** When the answer is on file, the maker is confirmed,
not re-asked. When it is not, the maker is asked once, properly, and the answer
is sealed in their own memory. Waved-through answers come back sooner; argued
ones go away longer. And every time the engine states a confidence, it finds
out afterwards whether that confidence was earned.

## What it refuses, and where

| | Layer | What it refuses |
|---|-------|-----------------|
| 🚪 | **The entry** (`forge/entry.py`) | a build that never asked. Nestor is the *first* tool, not an available one: the entry asks the project's memory before anything else and refuses outright without it. Then the box, then remote — and it says which tier answered. |
| ⚖ | **The checkpoint loop** (`forge/checkpoint.py`) | a confident wrong **decision** — a three-band interaction (auto / recognize / socratic) over a memory of the maker's sealed decisions, with an engagement gate that scores rubber-stamping and a governance layer that records the maker's non-forgeable sign-off. *Authorship is not authority.* |
| 🔍 | **The measuring panel** (`forge/measure_panel.py`) | a confident wrong **artifact** — measuring instruments run across a build; **convergence** (two or more instruments naming one artifact) is the alarm, and the panel reports its own coverage honestly, so a class nothing measured is named *unseen*, never *sound*. |
| 📊 | **The calibration wire** (`forge/build_loop.py`) | a confidence nobody checked — a prediction is recorded before the maker answers and resolved after, against what they actually chose. Ground truth that arrives on its own. |

## From a sentence to a seal

The loop, end to end, with no model in it:

```bash
pip install forge-play nestor-meaning      # or, in a checkout: pip install -e '.[test]'

# 1. the entry — Nestor first, then the keyword → major table, then the first
#    decision through the router. Run it twice: asked once, confirmed the second time.
python -m forge.entry "I got sum kol sites for app to spin" --project rally --builder rosalind --choose web

# 2. a plan with a fork in it — extraction, the checkpoint, the calibration wire
python -m forge.decision_extract demo/fixtures/fork_plan.json
python -m forge.build_loop demo/fixtures/fork_plan.json --builder rosalind --choose "where-the-dates-live=exif in place"

# 3. the whole day, as a person would have it — the friction log is the real output
python demo/the_first_bite.py
```

- `forge/keywords.toml` — the keyword → major table. A flat file to read and argue with.
- `forge/majors.py` — the scan over it: a span of text in, hits out. Deterministic, model-free, two callers (the Forge's entry and the corpus's prose lane) through one interface.
- `forge/plan_shape.py` — the decision-bearing plan: `file_write` entries plus one `fork` kind that carries a decision (options, tradeoffs, a recommendation, a confidence). A model-written plan carries forks; nothing else it writes reaches the router.
- `forge/decision_extract.py` — noticing *that* a decision is being made, by rule: a fork the proposer declared, a major the sentence left open, two writes to one path.
- `forge/build_loop.py` — each decision through the checkpoint, the answer substituted back, no fork left; and the prediction recorded before, resolved after.
- `forge/calibration_ledger.py` — the scorecard: brier, hit rate, overconfidence — and one `review` item routed to a human when the model promises more than it delivers.

## The home

All Forge state hangs off a single root: **`~/.forge`** (override `FORGE_HOME`),
resolved in one place, `forge/paths.py`. Under it: the per-builder checkpoint
memory and calibration ledger (`checkpoints/`), and the per-project Nestor
store (`projects/<project>/nestor/`) — a store whose whole content is one
build's world, disposable, portable, and the first thing the entry asks.

## Dependencies

Zero at runtime, on purpose — the same promise `kartikeya` and `jeles` make,
and the reason `willow-mcp` can take this package cheaply. Every heavy piece
is soft, and the engine degrades around its absence honestly:

| Absent | The engine still runs, but… |
|--------|------------------------------|
| **Nestor** (`nestor-meaning`, the decision seal) | **the entry refuses** — a build that never asked cannot start. Everywhere else: full-Socratic every time, decisions made but not sealed, no recognition, no reseal. |
| **fsrs** (spaced resurfacing) | fixed-interval fallback |
| **kartikeya** (the sandbox) | the `execution` instrument declares an honest coverage gap instead of parsing unsandboxed |
| **codebase-memory-mcp** (the call graph) | `call-graph` is named uncovered; a payload it cannot read is COULD NOT RUN, never clean |
| **willow-gate** (`forge[trust]`) | the promotion-trust seam is off; `verified_by` stays a string the host checks |

The Forge never imports `willow-mcp`. Willow depends on the Forge; the reverse
would be a cycle, and `tests/test_no_reach_back.py` keeps it that way. Three
modules (`human_loop`, `friction_floor`, `model_egress`) are vendored
byte-for-byte from willow-mcp until they move home the other way;
`tools/vendor_sync_check.py` keeps them honest meanwhile.

## Development

```bash
pip install -e '.[test]'
pytest
```

The suite is green with the soft dependencies present; individual tests skip
or fall back when theirs is absent. With the fleet's per-verifier Nestor
keyring in your environment the seal tests are correctly refused (a synthetic
verifier has no key) — run with `NESTOR_KEYRING` unset.

Releases are cut by release-please from conventional commits and published to
PyPI as `forge-play` through Trusted Publishing; the version is the git tag,
never a literal. `tests/test_release_wiring.py` holds the fifteen rules that
keep the three release files agreeing. Only commits that change what
`pip install forge-play` gives someone cut a release.

## Design

`docs/design/` holds the founding design — the decisions the engine was built
from, and the record of what is built and what is next. Decisions made since
live as drafts in the engine's own per-project Nestor, waiting for a human
seal. Documents are cited, never sealed.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
