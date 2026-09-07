@markdownai v1.0

# The positional default — the engine's own confident wrong answer

> **Prior art, read before code:** `the-forge-shape.md` §3 (the keyword → major
> table, and *"More than one: a detectable condition with a scripted response —
> ASK"*), `forge/entry.py`'s `_PickResponder`, and `forge/checkpoint_memory.py`'s
> `has_sealed` — D8's lighter-touch trigger, which is what makes this compound.

The first sentence anyone typed at the Forge outside a test was the operator's,
2026-09-07, on `source-trail`:

    python -m forge.entry "is source-trail a tool or an app that lives in
      willow-grove" --project source-trail --builder rudi193

The engine offered three majors, took the first, sealed it at confidence 1.0,
and reported success. The chosen major was `web`, for a local citation store
with no server. Nobody decided that. Index zero did.

## What happened, exactly

The scan matched one keyword — `app` — which maps to three majors. That is §3's
*detectable condition*, and §3's scripted response is **ASK**. What the CLI does
instead:

```
[choose] 'is source-trail a tool or an app that lives in willow-grove'
         could be web, mobile, desktop — which major?
[choose] -> web
```

No prompt was shown and none was waited for. `_PickResponder` is documented as
"Non-interactive", `--choose` defaults to `decision.options[0].label`, and
`--why` defaults to the string `"picked at the command line"`. The engine never
checks whether it is on a terminal.

The word `tool` — the other half of the operator's question — is not a keyword
in the table at all. Eleven rows: `site, app, app, app, cli, api, bot, pics,
date, spreadsheet, game`. The `records tool` major exists and would have been
right, but it keys on `spreadsheet` with aliases `csv, table, ledger, tracker,
list`. So the table could hear only half the sentence, and answered from that
half with total confidence.

## What it became

The choice did not evaporate. From `~/.forge/checkpoints/ledger.jsonl`:

```
kind: entity_seal   domain: builder:rudi193:decision:major
  surface:   '…' could be web, mobile, desktop — which major?
  canonical: web: picked at the command line
  verifier:  rudi193
kind: entity_resolve
  canonical: web: picked at the command line   sealed: True   confidence: 1.0
```

and the attestation beside it, in `rudi193.soil.json`:

```json
{"attested_by": "rudi193", "by_human": false,
 "statement": "web: picked at the command line", "status": "attested"}
```

`by_human: false` is recorded honestly. It is also not consulted by anything.

## Why it compounds

`checkpoint_memory.has_sealed` is D8's trigger: has this builder sealed *any*
decision under this decision-type. A true answer downgrades the next decision
from the full Socratic checkpoint to a lighter-touch confirm. It resolves
through `is_verified_seal`.

Measured both ways, on the row above:

```
with the fleet keyring loaded:      {"has_sealed": false}
as the entry actually runs it:      {"has_sealed": true}
```

The second is the one that matters. The entry cannot run with the keyring
loaded — a builder id absent from the keyring is refused outright — so every
real invocation is the unset case, where Nestor's own warning applies:
*"seal signatures are NOT verified; any 'sealed' row is trusted."*

So on sentence one, a positional default became a trusted seal that argues less
with sentence two. The engine that refuses a confident wrong answer manufactured
one and then used it to lower its own guard.

@constraint severity=critical
An ambiguous major with no operator choice must refuse. A default chosen by
list position is not a decision, and nothing derived from one may be sealed,
attested, or counted by `has_sealed`.

## The asymmetry this exposes

The entry already knows how to refuse. Its first tier does it unprompted:

    REFUSED: Nestor is unavailable, and the Forge cannot start a build that
    never asked (the-forge-shape.md §11).

Nestor absent is a refusal. Three majors and no judgment is a shrug and a seal.
Both are the same condition — *the engine does not know* — and only one of them
is treated as such. The rule is not "ask a human every time"; it is that not
knowing must not be recorded as knowing.

## What was done about this instance

The seal was rejected, not deleted:

```
checkpoint_memory reject-pair rudi193 major 93f4430a-… --verifier rudi193
  --reason "Not a decision. 'web' was index zero …"
→ rejected;  has_sealed → false
```

`kind: reject_pair` is appended to the ledger with the reason intact. The chain
still shows the seal, and now shows the retraction. That is the correct shape:
the record of a wrong answer is evidence, and erasing it would cost more than
the wrong answer did.

## The options, and the argument for each

- **Refuse on ambiguity** (`--choose` absent, more than one major). Matches the
  Nestor tier. Costs a second invocation. Cannot produce a wrong seal.
- **Prompt when attached to a terminal**, refuse otherwise. Closest to §3's
  "ASK", and the `[choose]` output already reads as a prompt that never was.
  Adds an interactive path to a module that has none.
- **Record unsealed.** Keeps the run going and keeps the answer out of memory.
  Weaker: an unsealed row still resolves, and the maker is not told they made
  no decision.
- **Keep the default, drop the seal.** Smallest change; leaves an unexamined
  major driving a build.

The first is the one the engine's own name argues for. The third is what the
workshop paper already assumes when it says a decision is *"recorded unsealed if
they have none yet"* — which, measured, is not what happens either.

## Decisions taken

- A positional default is not a decision, and nothing derived from one is
  sealable.
- The rejection stays in the ledger; the wrong answer is evidence.
- `by_human` is recorded and must be consulted, not merely stored.

## Open

| gap | state | waiting on |
|---|---|---|
| Refuse, prompt, or record-unsealed on an ambiguous major. | open | The four options above. Refusal is the default reading of §11's precedent. |
| `--why` defaulting to `"picked at the command line"` puts argparse's help text into the record as a rationale. | **closed 2026-09-07** | Fixed: `--why` has no default, and `_PickResponder` seals an empty rationale rather than inventing one — which `_engagement_fields` scores 0.0 and flags as "the loudest rubber-stamp there is." Measured harm before the fix: the string scored **0.350** against a 0.34 floor and was **not** flagged, so it graded `Good` and pushed the review interval *out* — the engine's least-considered decision was also the one it re-asked least often. It cleared the floor on a homonym: `line` is in the friction scorer's grounding lexicon as in *file, line*. See `the-forge-engagement-defect.md` §1; pinned by `tests/test_entry.py::test_no_rationale_is_the_loudest_rubber_stamp`. |
| `has_sealed` trusts unverified seals whenever the keyring is absent — which is every real run of the entry. | open | Upstream of this paper: either the entry runs with a keyring, or `has_sealed` must weigh `by_human`. |
| No `tool` row in the keyword table, and the first real sentence used the word. | **deliberately open** | `the-forge-workshop.md`: the row to argue is measured after the first ten workshops, not guessed after the first. This is workshop one. Record the miss; do not add the row. |

@prompt
When changing the entry's choice path: the test that matters is a sentence with
two or more majors and no `--choose`, run non-interactively. Assert that nothing
reaches `checkpoint_memory` — not an unsealed row, not an attestation. A test
that asserts the *right* major was chosen is testing the table, not this.
