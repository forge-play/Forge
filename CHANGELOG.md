# Changelog

Maintained by release-please from conventional commits; the first tagged
release will be `v0.1.0`. Entries below the first release heading are written
by the tool. This section is the hand-written history of what the engine
holds on the day the repository began.

## Unreleased

The engine, complete through the first loop:

- **The entry** — `forge/entry.py`: Nestor first (the per-project store), then
  the box, then remote, each tier reporting what it answered; refuses without
  Nestor. `forge/keywords.toml` + `forge/majors.py`: the keyword → major table
  and the deterministic scan over it. More than one major is a `Decision`.
- **The checkpoint loop** — three bands (auto / recognize / socratic) over the
  maker's sealed decisions (`forge/checkpoint.py`, `checkpoint_memory.py`),
  the engagement gate that scores rubber-stamping (`checkpoint_engagement.py`),
  spaced resurfacing with FSRS or a fixed-interval fallback
  (`checkpoint_schedule.py`, `checkpoint_calibration.py`), the mid-session
  nudge (`checkpoint_nudge.py`), and the governance record: a human-loop queue
  and non-forgeable attestations (`checkpoint_governance.py`, `human_loop.py`).
- **Decision extraction and the build loop** — `forge/plan_shape.py` (the
  `fork` entry), `decision_extract.py` (forks, open majors, conflicting
  writes), `build_loop.py` (each decision through the checkpoint, the answer
  substituted back, and the calibration wire: predict before, resolve after).
- **The measuring panel** — `forge/measure_panel.py` with census and hygiene
  instruments, convergence as the alarm, honest coverage states, tool caches
  pruned by name; `instrument_callgraph.py` (dead code via
  codebase-memory-mcp, unreadable output reported as COULD NOT RUN) and
  `instrument_execution.py` (parse-in-a-sandbox via kartikeya).
- **Calibration** — `forge/calibration.py` and `calibration_ledger.py`: brier,
  log score, hit rate, overconfidence, and one routed review item when the
  model promises more than it delivers.
- **Model routing and egress** — `forge/model_route.py`, `model_egress.py`:
  local by default, cloud only when the maker's signed manifest asks.
- **Promotion trust** — `forge/trust.py` and `tools/promotion_trust.py`:
  enroll, ratify, witness — §0.2 (proposing and ratifying never rest in the
  same hand) as a mechanism, not a string.
- **The demo** — `demo/the_first_bite.py`: one person's day through the
  engine, with a friction log as the real output.
- **Packaging and release** — `forge-play` on hatchling + hatch-vcs, the
  fleet's release chain (release-please, Trusted Publishing, the PR-title
  guard in both directions), the release-wiring rules as tests, and the
  invariant that the engine never imports willow-mcp.

Origins: the engine was designed and first built inside `safe-app-store`
(2026-07 → 2026-08), extracted to a standalone repository on 2026-08-11, and
carried to this greenfield home with its history left behind on 2026-09-03.
The founding design is in `docs/design/`.
