# Changelog

## [0.7.3](https://github.com/forge-play/Forge/compare/v0.7.2...v0.7.3) (2026-09-12)


### Fixed

* **engagement:** `__all__` no longer names a `Row` the module never defines ([fdfce54](https://github.com/forge-play/Forge/commit/fdfce540820f01fdcec2dc2a88dc0454a74e4c08))


### Build

* bump nestor-meaning floor to 0.20.2 to unblock Windows CI ([6150334](https://github.com/forge-play/Forge/commit/6150334a4717ec6bc52be618d0f668676d738e37))

## [0.7.2](https://github.com/forge-play/Forge/compare/v0.7.1...v0.7.2) (2026-09-11)


### Fixed

* **store:** read history explicitly now that nestor 0.19.1 lists live rows only ([9741cbf](https://github.com/forge-play/Forge/commit/9741cbf7f08d3364a99ec5f9a6387dc8ac995ff4))

## [0.7.1](https://github.com/forge-play/Forge/compare/v0.7.0...v0.7.1) (2026-09-07)


### Fixed

* **calibration:** the engagement score no longer moves a review date ([01d398d](https://github.com/forge-play/Forge/commit/01d398d20fc3bd6fbd15ac933540482f976ad1e1))

## [0.7.0](https://github.com/forge-play/Forge/compare/v0.6.0...v0.7.0) (2026-09-07)


### Added

* **entry:** say when a sealed row's signature could not be checked ([47ba5c0](https://github.com/forge-play/Forge/commit/47ba5c0daa5b3caa8b672e86ca4b440cd2ac7114))


### Fixed

* **entry:** an ambiguous major with no choice refuses instead of taking index zero ([be6a00f](https://github.com/forge-play/Forge/commit/be6a00ffa6ef6f588c4c6486c9678534fce88d01))

## [0.6.0](https://github.com/forge-play/Forge/compare/v0.5.0...v0.6.0) (2026-09-07)


### Added

* **checkpoint:** carry the keys that join a band to its calibration outcome ([75928cb](https://github.com/forge-play/Forge/commit/75928cbdcaa834151c3cdc1c85b1cf692c7e414d))
* **engagement:** a probe for what the engagement gate actually rewards ([554744c](https://github.com/forge-play/Forge/commit/554744c2bde0871934b4c0a5bd3da96fec1f7a38))


### Fixed

* **entry:** --why no longer fabricates a rationale nobody typed ([c42b73e](https://github.com/forge-play/Forge/commit/c42b73e0073942954555c02d243f8a725b06130c))

## [0.5.0](https://github.com/forge-play/Forge/compare/v0.4.0...v0.5.0) (2026-09-07)


### Added

* **checkpoint:** record which project a decision was taken in ([408001b](https://github.com/forge-play/Forge/commit/408001b905ba918c4ab027bc6f0a21b8bd3183fc))

## [0.4.0](https://github.com/forge-play/Forge/compare/v0.3.0...v0.4.0) (2026-09-07)


### Added

* **bundle:** a workshop can cut and check its bundle from a pip install ([f8490e1](https://github.com/forge-play/Forge/commit/f8490e13779dc1f6e2f023e9c04e068021bc149f))

## [0.3.0](https://github.com/forge-play/Forge/compare/v0.2.0...v0.3.0) (2026-09-03)


### Added

* **store-diff:** the build checks its store against the main one ([26e6a62](https://github.com/forge-play/Forge/commit/26e6a629cd6287e5e6f9b2aeca9f69312fdecfe1))


### Fixed

* **store-diff:** refuse a missing main path and a main path inside the checkout ([f2b0233](https://github.com/forge-play/Forge/commit/f2b023331e3a3de3eda9d3475b7a20690bb5cc6b))

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
