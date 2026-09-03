# Changelog

## [0.2.0](https://github.com/forge-play/Forge/compare/v0.1.0...v0.2.0) (2026-09-03)


### Added

* **bundle:** cut a project store's bundle into a checkout at a ledger head ([3d9f845](https://github.com/forge-play/Forge/commit/3d9f8452741e4d3cb39fa91905120ee0c21394bc))
* **entry:** report the store's last CI knowledge and its age with the answer ([ee9eaf6](https://github.com/forge-play/Forge/commit/ee9eaf6cc607e8aba223bf011263b07c647158f2))
* **deposit:** the PR-time deposit — CI outcomes into the project Nestor, propose-only ([eda2507](https://github.com/forge-play/Forge/commit/eda25079073d51d64a0d7053cb1acdf354a88055))


### Fixed

* **deposit:** propose-only as a type, not a grep ([f675a29](https://github.com/forge-play/Forge/commit/f675a29113b05789d653718227ccf19240001e54))

## 0.1.0 (2026-09-03)


### Added

* the Forge engine — the harness that refuses a confident wrong answer ([f611d90](https://github.com/forge-play/Forge/commit/f611d903ba75e47e77b321fc794dbb9d3af67758))

## Changelog

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
