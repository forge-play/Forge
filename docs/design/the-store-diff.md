@markdownai v1.0

# The store diff — the build checks against the main store

The operator, 2026-09-03: *"something I have been fighting for a long long
time is that the build has to check against the main store to see what the
difference is."*

Tonight was the evidence. The project store built the engine. The operator
sealed all ninety-two of its questions in the main store. The entry, asked
again, asked the project store first and reported ninety-two drafts and no
seals, because nothing in the build had ever looked at the other store. A
build that proceeds on a draft the main store has sealed differently should
see that before it proceeds, not after.

## The difference

Four sets. All reads. No keyring is needed to compute them, because
comparing statuses is a read and only bringing seals home needs the key.

| set | means | what a build does with it |
|---|---|---|
| **verified upstream** | same question, draft here, sealed there, same answer | these seals should come home; the pull's return trip |
| **proposed here** | in the project store, absent from main | what the pull carries up |
| **conflicts** | same question, different answer, at least one side sealed, or two drafts that diverged | surfaced with both answers and who sealed which; never resolved by a build |
| **retired here, sealed there** | the project superseded a question (a `supersedes` edge from a newer row, or a revision) and main sealed the old one | named, so a seal on a retired question is not mistaken for a seal on the live one |

Tonight has all of the fourth kind: the pre-move store location was sealed
alongside its replacement.

## Where it runs

In the entry, as the third tier: asked (`nestor`), how current the answer
is (`deposit`), how far this store is from the main one (`main`). The tier
reports the four counts with the answer, or says `not consulted` when no
main store was given. It never blocks; the four coverage states rule
applies, and "could not read main" is its own state, never clean.

The main store is named by `FORGE_MAIN_NESTOR` (a `nestor.db` path or an
exported bundle) or passed to `open_bite(main=)`. From a workshop on
another box the main store is only ever reachable as its export at the
seam, so the diff reads a bundle as readily as a store.

`tools/store_diff.py` runs the same read from the command line and exits
non-zero on a conflict, so a pre-push hook can gate on it.

## What it is not

- Not a merge. Nothing is proposed, sealed, imported or edged.
- Not the pull. The pull carries `proposed here` up under an envelope; this
  says how many there are.
- Not the return trip. `verified upstream` is brought home by a verified
  import under the keyring, which is a separate act; this says whether it
  is worth doing.

## What the bundle cannot tell it

Two of the four sets read better from a live store than from a bundle, for
the same reasons the record gate found: the bundle carries neither
`reason` nor `superseded_by` nor edges (gaps 497e02f0606e, f8eb26f03f40).
From a bundle, `retired here` can only be detected on the project side,
and `conflicts` cannot show the rationale behind either answer. When the
bundle version carries them, the diff reads them; until then it says what
it could not read.

## Two refusals (loki's review, 2026-09-03)

- A main path that does not exist is refused before anything opens. Nestor's
  store creates on open, so without the guard a mistyped `FORGE_MAIN_NESTOR`
  became a fresh empty database and a diff that read "ahead by everything",
  an undisclosed write from a verb that promises none.
- A main path inside a workshop checkout is refused when the caller names
  the checkout (`forbid_under`, the tool's `--repo-root`), for the reason
  `bundle.cut` refuses a database there. The entry tier has no checkout to
  name and does not check this; the tool and the pre-push hook do.

## Decisions taken

- The diff is the entry's third tier and is write-free.
- Four sets; a conflict is surfaced, never resolved by the build.
- Main is a store or a bundle; the diff does not care which.
- "Not consulted" and "could not read" are reported, never silent.

## Open

- Whether the pre-push hook on a workshop should refuse on a conflict or
  only report. Report first.
- The return trip as a verb: `verified upstream` imported under the keyring
  by the seat that holds it, on the diff's say-so.

@prompt
When changing this: it reads two stores and writes to neither. If a test
wants the diff to fix a conflict, the test is wrong.
