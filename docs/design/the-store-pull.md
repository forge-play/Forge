@markdownai v1.0

# The store pull — a project store comes home as shape

Beside `the-pr-time-deposit.md`. The deposit is per PR, into a project's own
Nestor, propose-only. This is per store, from that Nestor into the box, and it
is a promotion. The operator named the pattern on 2026-09-03: *"it might
follow a similar pattern as promoted from safe-app-store"*, and then the
sentence that settles it: *"look at what the forge is itself."*

## What the Forge is

A machine whose output for any build is a per-project Nestor: one build's
world, disposable, portable, ships with the project
(`paths.project_nestor`). The engine was built inside its own instance of
that. Seventy-nine drafts, each with the recipe that checks it, edges between
them, a hash-chained ledger, and zero seals, because the seat that wrote them
cannot seal. That store is not a by-product of the sessions. It is the
Forge's product, applied to itself.

So the pull is not a new problem. It is the shape doc's §8, *what flows
back*, one level up from the deposit, and the store's promotion gate is the
shape it takes.

## The two tiers, written down

| | the deposit | the pull |
|---|---|---|
| cadence | per PR | per store, at a chosen ledger head |
| direction | GitHub → project store | project store → the box |
| who writes | a propose-only identity | the willow seat, through a gate |
| what lands | `ci` rows, unsigned edges | drafts, unsigned edges, warrants, rejections |
| who seals | nobody, at that tier | the operator, on the box, afterwards |

@constraint severity=critical
Nothing sealed crosses the seam. A bundle arriving with a seal is asserting a
verification the box did not perform; the importer demotes it to draft and the
gate reports it. Sealing is a human act on the box, after the pull.

## What flows

Topology, never content. Questions, commitments, the reason and origin on
each, edges with their kinds, warrants with recipes and expected digests,
evidence pointers, and the rejections a human made on the project side. The
user keeps their code. The Forge passes the exit test on its own list.

The carrier already exists: `nestor export` writes a bundle with the
domain's rows, its warrants and evidence, the source ledger, and a digest
over the whole. `nestor import` reads one, dry-run by default, and lands
drafts as drafts. The pull adds nothing to that wire format.

## The gates

The store's `promote_check` runs nine gates over a candidate, mechanical `[M]`
or attested `[A]`, and mints a record only on all-PASS. The pull runs the same
shape over a bundle. The mapping is closer than it had to be.

| store gate | pull gate | what it reads |
|---|---|---|
| `witnessed [M]` | `witnessed [M]` | who pulled and who will verify: two names, and the record writer refuses them equal on its own, independent of this list |
| `own_repo [A]` | `own_store [A]` | the bundle was exported from `paths.project_nestor(<project_id>)` and the exporting side attests it |
| `host_repointed [A]` | `head_pinned [A]` | the bundle names the ledger head it was cut at; a second pull can be checked against the first |
| `manifest [M]` | `bundle_verifies [M]` | `verify_bundle` passes: digest matches, fields are shaped |
| `tests_green [M]` | `warrants_hold [M]` | every construction warrant in the bundle is re-run here; BROKEN is reported per warrant, never filtered, and does not deny the pull (the world moved; the draft needs a human) |
| `vault_leak [M]` | `no_box_state [M]` | no row's origin or locator points under `.willow`, a vault, a key path, or a secrets directory (§12's one exception, applied to what a bundle may carry) |
| `import_pure_core [M]` | `drafts_only [M]` | zero rows claim `sealed`; a claimed seal is reported by id and the importer would demote it anyway |
| `inversion [M]` | `propose_only [M]` | every edge has `edge_sig=''`; every warrant was attached by a label, not a credential |
| `semantic_seam [M]` | `domain_keyed [M]` | the bundle's matcher label matches the domain it lands in; `ci` rows land in `ci`, `decision` rows in `decision`, and a mismatch is warned as the importer already warns |

The gate is not a file in this repo. See the jig below: the table is the
`bounds` of one envelope, and what `envelope_apply` and the importer already
refuse. The importer's
own ledger passage (`bundle_import`, with the digest and the verifier) sits
beside the FRANK citation as the second half of the audit line.

## What the pull is not

- **Not a merge of stores.** Conflicts, a source already sealed on the box
  with a different answer, are listed by the importer and never resolved by
  the pull. Two humans disagreeing through a file stays a human matter.
- **Not a revival.** A pair rejected on the box stays rejected; the importer
  needs its own separate flag to revive it, and the pull never passes that
  flag.
- **Not a door into the project store.** The willow seat needs the bundle at
  the seam, as it needs `promotion.json`, never a connection into
  `~/.forge/projects/*/nestor`. The project store keeps no MCP door and needs
  none for this.

## Where I would push back on the analogy, once

An app promotion happens once. A project store grows while the project is
alive. The nearest existing shape is the corpus refresh pinned to a merge sha:
the gates run every time, the record is per pull, the head is the pin. That
is why `head_pinned` is a gate and not a note.

## The jig

Everything above was drawn from the app store's promotion gate. The box holds
the same shape as verbs already, and they are the ones the pull should run
on, not a ninth copy of the pattern.

| the pull needs | the box already has |
|---|---|
| a seat asks to import one bundle into one domain | `envelope_propose(verb="nestor.import", grantee=<seat>, bounds={project_id, bundle_digest, ledger_head, drafts_only: true}, max_count=1)` |
| a human says yes, with a key | `envelope_ratify` — operator-only, keyring-checked, `issued_by` stamped root |
| the act is checked and recorded before it happens | `envelope_apply` — verifies the grant covers the verb and these `call_args`, then cites into FRANK. The citation is the pull record. |
| what crosses is structure, never content, with a look-first | `nest_promote(dry_run=True)` — the Nest's wall, which §8 names as the fourth arrival at the same line |
| records chain, and a later one retires an earlier one | `lineage_record` with `supersedes=[<previous pull atom>]`, `evidence=[bundle digest, FRANK citation id]`; rationale and evidence are required or the atom is refused |
| who verified, durably | `human_attestation_create` / `_list`; the `witnessed` gate reads an attestation, not two strings |
| the seat's own closeout carries the bundle | `handoff_write_v4` findings; `verify_handoff` on the orchestrator side |

So the nine gates do not become a new tool. They become the `bounds` of one
envelope and the checks `envelope_apply` already runs, plus what the importer
itself refuses. `tools/store_pull.py` shrinks to the exporter's side: cut the
bundle at a head, attest `own_store` in it, print the digest. The import side
is `envelope_apply` followed by `nestor import --apply`, and nothing else.

This also answers three of the four items I had left open. Which seat runs
the pull: whichever seat holds the ratified envelope, and the grant names it.
Where the record lives: the FRANK citation, with a lineage atom over it so
`lineage_why` can answer "why does the box hold this?". Whether the export
side attests by file or field: a field, because `bounds.bundle_digest` is
what the envelope covers and a file beside it is outside the digest.

@constraint severity=critical
The pull runs under an envelope or not at all. A bundle imported without an
`envelope_apply` citation is an import the box cannot explain.

## Decisions taken

- The pull is a promotion of a bundle, and the machinery is the envelope
  flow: propose, ratify, apply-and-cite, then import.
- Drafts only cross; seals are demoted and reported; sealing happens after.
- The ledger head is the pin; pull atoms chain by `supersedes`.
- Broken warrants are reported, not filtered, and do not deny a pull.
- The pull never revives a rejection and never resolves a conflict.
- No MCP door into a project store is needed for this.
- The gate table above is the envelope's `bounds`, not a new tool.

## Open

- The verb. `nestor.import` is not in the syscall table today; adding a verb
  is the operator's act, and its `bounds` signature should be written from
  the table above before the verb exists.
- The `ci` domain (the deposit paper) is the first domain other than
  `decision` to cross. `domain_keyed` is a bound written for it before it
  exists.

@prompt
When building this: the import side is envelope_apply then nestor import,
in that order, and nothing else. The export side is a tool in this repo.
The record writer refuses verifier == puller on its own. Never pass
override_rejections. If a test wants a seal to cross, the test is wrong.
