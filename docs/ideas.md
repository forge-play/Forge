# The Forge — idea pile

This repo's numbered idea pile, in the shape willow-reconciler reads: top-level
`N. ` items, optional legend tags, stable numbers. It is read by

```sh
reconciler run --repo ./ --doc docs/ideas.md --validate
```

and every `Idea-Id` trailer in this repo's history is resolved against it by
`.github/workflows/trailers.yml` (`reconciler verify`) on every pull request.

Legend: ✅ shipped · 🟡 partial · (untagged) proposed

**Numbers are permanent join keys.** `reconciler/ids.py` derives
`<corpus>-ideas-<num>` from the number written on the line, so a number is an
identity, not an ordinal. Never renumber; never write a markdown-auto-numbered
list (`1.` repeated) — retire a number instead and leave the gap.

Converted on 2026-09-12 (E3-piles, fleet plan Wave 3) from the "Open" /
"What is next" sections of `docs/design/*.md`. Every open item those sections
carry is here; nothing was invented. An item is tagged ✅ only where this
repo's git history shows the landing (the commit is named); an item the papers
mark settled by a fact, or answered in prose, is carried untagged with the
fact beside it. Items that record work landed in another repo are not items
and were not carried. A legend tag counts only when it LEADS the item text.

---

## A. The fleet plan's evidence loop, landing here

1. A numbered idea pile at `docs/ideas.md` in the reconciler's form (E3-piles): this file, converted from the design papers' open sections, validated by `reconciler run --validate`.
2. Adopt `Idea-Id` commit trailers (fleet CONVENTION, decision-2026-09-11): `.github/workflows/trailers.yml` runs `reconciler verify` on every PR, CONTRIBUTING.md names `reconciler id --grep` so no id is ever typed by hand, and `tests/test_release_wiring.py` holds the workflow to existing wherever this pile does (E3-trailers).
87. The fleet CI floor (decision 5; C4-tests-yml, C4-codeql): a Linux job whose Python matrix is derived from `pyproject.toml`'s `Programming Language :: Python :: 3.X` classifiers, a Windows job on the floor and ceiling Pythons, a lint job with ruff pinned to an exact version running `ruff check` and `ruff format --check`, CodeQL over python and actions, and an aggregate `test` job that needs every leg, runs `if: always()`, and fails when any needed result is not `success` — skipped and cancelled included — with `tests/test_release_wiring.py` holding each of those to the file and planting each check.
88. `forge/engagement_probe.py`'s `__all__` names `Row`, which the module never defines, so `from forge.engagement_probe import *` raises `AttributeError`; found by the CI floor's first ruff run (F822) on 2026-09-12. Remove the dead name.
89. The Windows leg's first run (#29, 2026-09-12) found that nestor-meaning's `cascade.ledger_append` opens the ledger in text mode (`open(ledger, "a+", encoding="utf-8")`), so Windows writes `\r\n` while the append-time tail checkpoint (`start = size - len(line) - 1`) assumes one byte of newline and lands one byte into its own line; the next append's `_check_tail` then reads a line missing its `{`, the hash differs, and the seal is refused as "a tampered tail" — 76 of the 78 Windows failures, every test that seals twice. Present in 0.19.1 through 0.20.1, the whole range `pyproject.toml` allows, so there is no version to move to and the fix is Nestor's (`newline="\n"` on that open, or a binary append; `verify()` already reads through `splitlines()`, so ledgers written with `\r\n` before the fix still verify). When Nestor ships it, raise the floor of the `nestor-meaning` pin to that release; until then the Windows leg is red and the aggregate gate holds `test` red on purpose — the floor found a real cross-platform bug, which is what it is for.

## B. The owner's decision of 2026-09-12 04:55Z: the Forge is the fleet's vendoring source

"The forge is to be vendored; safe-app-store isn't to be vendored — it's to be archived and turned into a parts bin." Recorded here as items, not done in the bite that recorded them.

3. `subject_consent` gets its home HERE (a Wave 6 bite): today willow-mcp, corpus-lens and UTETY each vendor it from safe-app-store's `libs/subject-consent`; the store is to be archived and turned into a parts bin, so the canonical copy moves to the Forge and the three consumers re-sync from here.
4. When item 3 lands, rewrite `forge/_ids.py`'s NOTICE line ("vendored from safe-app-store principal.py") and `promotion.json`'s `"host": "safe-app-store"` to say what is then true: the Forge is the source and the store is the archive it came out of.

## C. The engine (`the-forge-engine.md`, "What is next")

5. ✅ **shipped**: vendoring went home (a9ee4c2, 2026-09-03) — willow-mcp pins `forge-play>=0.1.0,<1.0.0` and re-exports `human_loop`, `friction_floor` and the detection half of `model_egress` from `forge`; `denial()` stays with willow-mcp's consent store.
6. The host side: the store's stub builder emits a `fork` from the entry's scan of a sentence, and its build spine calls `forge.build_loop.resolve` before the seam; the seam refuses an unresolved fork.
7. The box: a real `BoxLookup` over the corpus and the app catalog.
8. Model-proposed candidates: the fork is the seam; a local model that writes forks into a plan is the first thing that can use it.
9. ✅ **shipped**: the PR-time deposit (eda2507, 2026-09-03) — `forge/deposit.py` writes `ci` rows and `refines` edges, propose-only, and reads willow-bot's webhook inbox; `tools/pr_deposit.py` is the caller; propose-only is a type, not a grep (f675a29). Paper: `the-pr-time-deposit.md`.
10. The willow-bot bridge fix the deposit reads through (key on check id, carry `head_sha`) is on a branch in willow-bot, not merged.
11. The store pull: a project store comes home to the box as shape, gated the way the app store promotes. On paper (`the-store-pull.md`, four drafts); not built.
12. The forge-workshop: the template repo where the first question gets asked; the same package; the live store stays home and the repo carries the bundle. On paper (`the-forge-workshop.md`).
13. The record gate: seven mechanical gates over a workshop's bundle, beside the store's nine. On paper (`the-record-gate.md`); the store holds a pointer.
14. ✅ **shipped**: the store diff (26e6a62 and f2b0233, 2026-09-03) — the entry's third tier reports how far the project store is from the main one: verified upstream, proposed here, conflicts, retired here but sealed there, or `not consulted`. `forge/store_diff.py`, `tools/store_diff.py`.
15. The trust block on this repo's own promotion: `tools/promotion_trust.py` produces one; the ratifying half is a verifier's act, and `promotion.json` still carries no `trust` block.

## D. The positional default (`the-positional-default.md`)

16. ✅ **shipped**: refuse on an ambiguous major (be6a00f, 2026-09-07) — both CLI responders raise rather than take `options[0]` when more than one option is on offer and none was named; nothing reaches memory, pinned by `test_the_refusal_writes_nothing_to_memory`.
17. ✅ **shipped**: `--why` has no default (c42b73e, 2026-09-07) — argparse's help text no longer enters the record as a rationale; an empty rationale scores 0.0 and is flagged as the loudest rubber-stamp there is.
18. 🟡 **partial**: `has_sealed` trusts unverified seals whenever the keyring is absent, which is every real run of the entry — the say-so shipped (47ba5c0: `seal_signatures_verified()` and the qualification on the `nestor` and `scan` tiers); the trust change itself waits on D11 identity, since neither running with a keyring nor weighing `by_human` is reachable today.
19. No `tool` row in the keyword table, and the first real sentence used the word — deliberately open: the row to argue is measured after the first ten workshops, not guessed after the first.

## E. The engagement defect (`the-forge-engagement-defect.md`)

20. 🟡 **partial**: which of §5's four remedies — two are dead on measurement (not linearly separable, with collisions), "stop feeding it to the scheduler" shipped (01d398d, 2026-09-07), and "replace the subject: score the decision, not the prose" is the real answer and waits on data (§5.3).
21. Whether `engagement` should be scored at all once §5.3 lands: keep it while the paper is load-bearing; deleting it while it is the only record of the defect would be wrong.
22. `_EASY_MIN_ENGAGEMENT` is private to `checkpoint_schedule` and restated in the probe; if it moves, the probe's `grade` column goes wrong silently — export it or import the private name deliberately.
23. Does the flag correlate with anything real? The blocker named in the paper (band and engagement never persisted together) was cleared by 75928cb, which carries both onto the calibration row; the correlation itself has not been measured.

## F. The pedagogy paper (`the-forge-pedagogy.md`, §8)

24. Does the operator want UTETY vendored (as `friction_floor` was) or depended on? Vendoring a whole loop is heavier than vendoring a scorer.
25. Is "mastery = calibration" the right substitution, or does it smuggle in a different wrong thing? The claim most worth attacking.
26. UTETY carries a consent gate (`require_consent`, `ConsentError`) because its learners are children; the Forge's makers are not. Which of its guarantees are pedagogy and which are child-safety, and does dropping the latter break the former?
27. ✅ **shipped**: §5's claim that the band selector keys on store fill rather than the maker's calibration, measured rather than believed (75928cb, 2026-09-07) — `forge/band_probe.py` runs two makers a hundred calibration points apart through identical trajectories: no calibration sensitivity above the floor, a null result the instrument asserts its own contrast for.

## G. The two stores (`the-two-stores.md`)

28. ✅ **shipped**: a checkpoint row records which project a decision was taken in (408001b, 2026-09-07) — `project=<id>` in the row's `origin`, a field, not a domain key, so `has_sealed` keeps spanning projects; the projection is now a filter.
29. Whether the checkpoint proposes into the project store, or the export projects from the builder store at cut time — the two-writes / one-derived-view argument.
30. Two makers, one workshop: a per-maker projection makes the bundle depend on who cuts it, which conflicts with the ledger head being the pin.
31. A maker's seal and a verifier's seal are both "sealed" and mean different things across this join; `the-store-pull.md`'s "nothing sealed crosses the seam" reads differently depending on which is meant.

## H. The workshop (`the-forge-workshop.md`)

32. ✅ **shipped**: the bundle's path and name in the template (3d9f845, 2026-09-03) — `.forge/bundle.json` and `.forge/HEAD`, per `forge.bundle.BUNDLE_DIR`.
33. ✅ **shipped**: a fresh workshop's uncut bundle is not a failure (f8490e1, 0.4.0) — `bundle.check` has three states.
34. ✅ **shipped**: a workshop cuts and checks its bundle from a pip install (f8490e1, 0.4.0) — `forge-export` is a declared console script; `tools/` was never in the wheel.
35. An instantiated workshop inherits no branch protection, and the answer is known: apply the fleet's repo-level ruleset `require-test-for-merge` (required check `test`, strict, 0 approvals, non-fast-forward, default branch, admin bypass) as a step in standing up a workshop — 36 of 39 repos carry it, so there are 36 precedents.
36. Org community-health files (`forge-play/.github`'s CONTRIBUTING, SECURITY, templates) do not reach a working tree, so an agent reading the clone sees none of them; mitigated by the template carrying `CLAUDE.md`, not closed.
37. Whether `project_id` is derived from the repo name or declared in the template's config: derivation keeps the two from drifting, declaration survives a rename; the template derives today.
38. What the template's README says after the question. Less is right.

## I. The deposit, the record gate, the store diff, the store pull

39. Deposit: the bot's installation token as the runner, so the origin says `actor=Bot` because the credential is one, not because a string says so.
40. Deposit: whether the post-merge hook is a git hook on the operator's checkout or a step in the same place the corpus `refresh.py` runs. Both are local.
41. ✅ **shipped**: the age in `Entry.tiers` (ee9eaf6, 2026-09-03) — the entry reports the store's last CI knowledge with its age, `none` when there is none.
42. Deposit: whether `ci` rows should ever be sealed, and by whom. The paper's answer is no one needs to; a sealed CI outcome adds nothing a signed run URL does not.
43. Record gate: the rubber-stamp share below which `argued` should deny, if ever above zero — measured on the first ten promoted workshops, not set now.
44. Record gate: whether `deposited` should require every merge sha or only the promoted one.
45. Record gate: the attestation field that names the bundle path.
46. Store diff: whether the pre-push hook on a workshop should refuse on a conflict or only report. Report first.
47. Store diff: the return trip as a verb — `verified upstream` imported under the keyring by the seat that holds it, on the diff's say-so.
48. Store pull: the verb — `nestor.import` is not in the syscall table today; adding a verb is the operator's act, and its `bounds` signature should be written from the paper's table before the verb exists.
49. Store pull: the `ci` domain is the first domain other than `decision` to cross; `domain_keyed` is a bound written for it before it exists.

## J. Readiness (`the-forge-readiness.md`)

50. The `witnessed → Pass` tension: `witnessed` is the sole candidate for a legitimate mechanical Pass (a verifier's name backed by a seal signed with their own key) and `assess_gates()` still reports it Blocked on purpose; whether a verified cryptographic seal clears the D-R4 bar or is one step short of it (an identity check, not a review) is a design call held open.
51. The corpus's `PRC-02-*` immediate no-go conditions are still unwired for the panel's four instruments: twenty controls that stop a release outright, none borne on by an instrument.
52. Nothing consumes `note()` in a stored artifact yet; wiring it into a promotion record, or into the panel's routed queue items, is a separate call about where the sentence belongs.

## K. The shape paper (`the-forge-shape.md`, "Open")

53. The name: `almanac-tech` is not settled.
54. 13 almanac repos and `willows-grove` are outside the corpus; adding them is an operator act, and rung order in `docs/corpus-order.md` is deliberate.
55. ✅ **shipped**: what a CI-outcome claim looks like as a pair, and which lane it lands in (eda2507, 2026-09-03) — a `ci` row proposed into the project Nestor with a `refines` edge, by the deposit.
56. Whether the PR trigger is a workflow, a hook, or the merge queue.
57. ✅ **shipped**: store deposit (`willow-bot`) rather than git deposit (`willow-ci`) — the deposit module reads willow-bot's webhook inbox (eda2507), which keeps §0.2 intact.
58. `willow-bot` is not under `~/github` and has 0 claims, while its extractor exists and has never run; cloning it into an org is a prerequisite (§13).
59. ✅ **shipped**: whether the shape document belongs in the store or in `forge-play/Forge` — it is here, `docs/design/the-forge-shape.md`, since the repo's first commit (f611d90).
60. `plan.py` has no notion of majors; a second major forces it.
61. The toolchain bind: nothing binds `forge-play` into Kart (68 binds, zero mention; `governance/architecture/willow-v08-toolchain-path.drawio`).
62. `~/.forge` symlink missing; `forge-play/.forge` exists and is empty.
63. ✅ **shipped**: `promotion.json` no longer carries `host_repointed: false`, the recorded reason the Forge was never fully promoted — it has read `true` since the repo's first commit (f611d90), with the note that the host consumes the package.
64. Documentation and GitHub both need updating for the list's move.
65. Edge rank has no store: FSRS grades pairs today; nothing grades a connection.
66. Prose is not a shape: design sections are unfindable until the scan exists; until then, decisions belong in decision records, not paragraphs.
67. Whether the lean corpus payload is a default or an opt-in; §11 makes it load-bearing, and a mandatory call must be cheap or the mandate gets removed.
68. Where the first-tool call is enforced — the entry scan (§3), the hook, or both; an advisory alone has already been tried and did not fire.

## L. The store-side design (`the-forge.md` "Open / next" and the 2026-07-31 review)

These are open items in this repo's own papers about the safe-app-store design (D1–D12) the Forge grew out of. Item 3 records the owner's decision that the store is to be archived; each of these is carried as written, and which of them still has a home after that is a later call, not this file's.

69. `promote_check.py` executes candidate code host-side, unsandboxed: it runs each promotion candidate's real test suite, and the files AST-scanned for safety and the files executed are disjoint sets. Repo-wide, not Forge-specific; D3 depends on it being fixed (test execution inside Kart or an equivalent sandbox).
70. Where exactly "a decision" starts (D8): the line between "ask first" and "just write it" is asserted, not drawn; needs a working pass over real build sessions.
71. ✅ **shipped**: adopt Oakenscroll's Office's `calibration.py` for D9's calibration weight — vendored as `forge/calibration.py` in the repo's first commit (f611d90); what resolves a checkpoint claim as true/false, and what "confidence" means for a design decision, are still the open half and live in items 20–23.
72. Checkpoint fatigue has no escape hatch: whether "I don't know, you choose" is a legitimate answer that still seals as a taught decision, or something that should block progress.
73. GitHub OAuth app registration specifics (D11): scopes, callback and session-token lifetime, and whether an existing GitHub App is reused.
74. D11's first-login standing: mint-and-bind immediately, or only after an operator confirms it the way willow-mcp's `identity_binding.py` already does (unconfirmed on first sign-in, confirmation operator-only)? Also worth reusing regardless: its filename-safety charset and its atomic write.
75. The KB (docs from major software companies) lives locally, not in a repo; whatever plugs it in should go through D5's connector contract, likely via a small local adapter that speaks the same read/propose contract.
76. Exact plan format for the seam (D3): what a declarative plan for an MCP tool call or a file write serializes as; `seam_install.py`'s placement-plan shape is the starting reference, not yet adapted.
77. Scope cut proposed in review, not decided: a minimal single-tenant slice first (no D11 auth, no D4 signing, no Casbin; the seam with a real plan schema plus Kart plus LiteLLM), with D9/D10/D12 as a separable follow-on cut from v1.
78. Spend/abuse metering is undesigned: D7 gates permission to use cloud fallback, never cost.
79. Prompt injection is not in the threat model: KB documents and MCP tool results reach the model that authors the seam's plan and are untrusted planner input; D3's AST floor does not address tool-result or KB poisoning.
80. `apps/<builder_id>/<name>/` vs CLAUDE.md rule 10 (`app_id = directory name`, `make run app=<name>`): the catalog, `promote_check` paths and the dev-fallback `app_id` are unresolved.
81. `kartikeya` is not a declared dependency; `seam_install` shells to `bwrap` when available and proceeds silently without it, the opposite of what D2/D3 assume. v1 either declares Kart and fails closed, or the scope cut says bwrap-only prototype.
82. What each 2026-07-31 fix still needs before it is more than design: D11 has no authenticator re-linking flow; D4's signing-ledger storage and where the externally pinned tip lives are unspecified; D3's dangerous-pattern list for the pre-crossing scan is unenumerated.
83. D5 allowlists: Nestor's is documented; willow-mcp, GitHub and LiteLLM are not, and nothing yet stops a server from being registered without one — "register server without allowlist → refuse" should be explicit in D5.
84. One "which audit trail answers which question" table across the D3 seam, the D4 signing-event ledger, the D12 Nestor ledger, and consent/FRANK elsewhere.
85. Per-builder Nestor storage: document one `nestor.db` per `builder_id` versus a shared DB with domains, which is weaker if the seam mis-scopes once.
86. terpsi-music was brought in as a worked example, not a dependency; its three-zone privacy design may be worth a closer read once D6's tenant-isolation shape firms up.
