# The join: one record, and the engine that builds the stack

Written 2026-11-03, after `the-forge-from-willow.md`. That paper is about
borrowing. This one is about the two becoming one thing: the Forge's
decisions on Willow's record under the person's key, the Forge's scan run
over Willow's catalogue of add-ons, and the Forge as the builder that turns
a sentence into a stack the person seals before it runs.

Three threads, one shape. Each has a seam already built on one side and a
gap on the other, so most of this is wiring, not invention.

## What each side has today, measured

The same sentence through both:

    "I want to keep track of what my tenants owe and when the boiler is
     due, and read my email about it"

- The Forge's scan (`forge/majors.py` over `forge/keywords.toml`) returns
  no hit. The table's eleven rows know site, app, cli, api: what to
  **build**. They do not know owe, due or email.
- Willow's card search (`ui/canvas.py` `search`) returns mail, renewals,
  coming-up, home-upkeep, apple-mail, calendar-out, with a reason for each:
  "you named it", "what *due* usually means here", "close to what you
  said". It also returns `email-ask`, which is not built. The cards know
  what to **read and track**.

And the other way:

    "a site for my running club with the race dates"

- The Forge's scan: `site → web`, one major, unambiguous.
- Willow's card search: attendance, strava, secrets-audit, gh-json,
  hook-stop, all "close to what you said". No real candidate; BM25 over
  500 cards finds something for any sentence.

So the two scans are complements, not rivals. The Forge's table is small,
hand-argued and knows kinds of thing. Willow's cards are many, generated
from the same discipline (a name, a line, a section, promises), and know
jobs. Neither alone is the matchmaker.

One more fact: `search` already has the three tiers the Forge's entry
wants. "You named it" is the Forge's unambiguous hit. "What *due* usually
means here" is an alias row, kept in `ui/search-words.txt` in the kernel's
own words-list format. "Close to what you said" is ranking, which the
Forge treats as a suggestion that can be wrong, and scores.

## Thread 1: the catalogue is the table

`majors.load_table` reads TOML rows of `keyword, aliases, major, reason,
caps`. A Willow card is the same row in another spelling:

| keyword table | a card |
|---|---|
| `keyword` | the add-on's name, and the topic tags `similar` works out |
| `aliases` | the `search-words.txt` lines that point at it |
| `major` | the add-on itself (or its `section`, when the job is the major) |
| `reason` | the card's `line` |
| `caps` | `writes`, `network`, `needs`, `uses` |

So the first piece is a loader, `forge/card_table.py`, that renders a
Willow checkout's cards (built and planned, `adapters/planned.json`
included) into `majors.Row`s. `scan` does not change. The entry's hits
then carry add-on names as targets, and `ambiguous_majors` means what it
already means: one sentence, several add-ons that do that job, no way to
choose. That is a `Decision` with the cards as options and their lines as
tradeoffs, through `run_checkpoint`, per builder. The second time this
maker says "owe", they are confirmed, not re-asked. Nothing new is built
on the Forge side for that: it is the entry's existing loop over a bigger
table.

Two things the scan cannot do, and should not try:

- **Ranking.** "Close to what you said" is BM25, Willow's `pile-rank`,
  which AGENTS.md calls pointing, not answering. It belongs on the Willow
  side and it stays there. The Forge consumes its output as the fork's
  `recommended`, never as a hit.
- **The folder.** A sentence names what the person wants; the folder says
  what they have. The canvas already counts what the kernel cannot read by
  kind, with the readers that could read it. Those are candidates the
  sentence never named, and they go into the same plan as forks.

## Thread 2: the stack is the plan

`plan_shape` has two entry kinds: `file_write`, and `fork` with `options`,
`tradeoff`, `recommended`, `confidence` and `resolves` mapping each option
to file writes. A stack is exactly that:

- The `file_write`s are the stack file (`## pool` headings and `- NAME --
  ARGS` steps, the format `stack.py` reads) and the list of names to hand
  `ui/assemble.py add`, with each name's `uses` closure.
- A `fork` is a job several add-ons do: `mail` or `apple-mail`;
  `local-model`, `openai-compatible` or `in-process`; a stdlib reader or a
  deps one that reads more but `needs` a package. The options are cards,
  the tradeoffs their lines and promises, `resolves` the lines each would
  add.
- `recommended` is the ranking's top card. `confidence` is **null until
  the ledger has data.** The Forge records no fabricated 0.5. Once makers
  have resolved enough forks, the matcher's confidence that its top pick
  is taken is its own measured hit rate by rank, and the calibration
  ledger then scores the matchmaker the way it scores any proposer. That
  is the loop the Forge exists to close, with ground truth that arrives on
  its own: the maker's pick.

`decision_extract` and `build_loop.resolve` then do what they do today.
What comes out is a plan with no fork left: a stack file and an add list.

## Thread 3: one record

Today there are three records in play and none of them is the person's:

- the Forge's per-builder Nestor store, sealed with no key by default
  (`NESTOR_SEAL_KEY` unset, so "any sealed row is trusted", idea 18);
- the stack's own kernel box, one `assemble` row per add-on put in;
- the person's willow box, with their bites.

The join puts the Forge's decisions on the person's box, sealed with the
person's key, and nowhere else first.

**The mechanism already exists on both sides.** The Forge has
`defer_seal=True`: a card answer held as a draft "for a host that seals at
the session's end". The kernel has `propose`: a row `{path, data, cites,
claim}` that passes the door only if it cites what the last bite served,
then waits for `seal`, an HMAC under the key, which only the person holds.
So:

1. The sentence is a **bite** against a pile that holds the cards. The
   kernel serves the cards it holds; the ranking points at the rest. Both
   are on the record as `served`.
2. Each resolved fork is a **proposal**: path
   `forge/<decision_type>.json`, data the chosen card and the maker's
   rationale, cites the served card passages, claim the tradeoff the maker
   took. The door holds it to what was served. Nothing is written yet.
3. The person **seals**, with their key, in the UI's existing step: "Look
   it over, and seal it. Nothing runs until you do."
4. Only then does `assemble add` copy the add-ons and `stack.py` run.

The Forge never writes a seal and never reads the key. It drafts. That is
AGENTS.md's first rule and CONST-0-2 in one sentence, and it is what the
Forge's own README means by "authorship is not authority".

**Reading back.** The kernel serves a sealed answer first when the same
words come again: the Forge's `auto` band. The Forge's `recognize` band
(a different sentence, the same decision type, confirm rather than ask) is
what the kernel does not do, and the per-builder store keeps earning its
place for that: as an index over the sealed rows, rebuilt from the record,
never the record itself. The `nestor` add-on already reads a Nestor store
into passages for a bite, so the index is askable from Willow today.

**The two-stores paper still holds.** The person's box is theirs, private,
never shipped; a workshop's bundle still carries only the project store's
`ci` rows. What changes is that the builder store stops being the only
place a maker's decision exists, and stops being sealed by nobody.

**The entry's first rule changes its spelling, not its meaning.** "Nestor
first, or refuse" becomes "the record first, or refuse": a build that
never asked the person's box cannot start. Without a box the entry refuses
the way it refuses without Nestor today.

## The builder, end to end

    sentence ──bite──▶ cards served, ranking pointed      (Willow: kernel, pile-rank)
             ──scan──▶ hits, forks, folder candidates     (Forge: majors over card_table)
             ──resolve──▶ each fork through the checkpoint (Forge: build_loop, per-builder memory)
             ──propose──▶ one proposal per decision, citing the cards  (kernel: the door)
             ──seal──▶ the person, their key                (kernel: nobody else)
             ──assemble──▶ add-ons copied, hashed, rowed    (Willow: ui/assemble.py)
             ──run──▶ the stack file, peaks first           (Willow: stack.py)
             ──score──▶ the matcher's predictions resolved  (Forge: calibration ledger)

Everything on the Willow side exists. On the Forge side, the scan, the
checkpoint, the plan, the build loop and the ledger exist; what is missing
is the table loader, a `BoxLookup` over the cards, and a plan writer that
knows the stack file's shape.

## Where the code goes, so the arrows stay one way

- **Forge:** `forge/card_table.py` (cards and planned entries to
  `majors.Row`s), `forge/card_box.py` (a `BoxLookup` that returns
  `Candidate(name, where=card path, why)` from a Willow checkout, closing
  idea 7), `forge/stack_plan.py` (candidates and forks to a `PlanDoc`
  whose file writes are a stack file and an add list). No import of the
  kernel: the Forge calls `kernel.py` and `assemble.py` as subprocesses
  and reads exit codes, the way every add-on does. The Forge stays at zero
  dependencies.
- **Willow:** a deps add-on `forge` (`needs: forge-play`), section
  Assistants, `writes: record, to`, `network: none`. `suggest --box DIR
  "sentence"` bites the cards, runs the Forge's extraction and prints the
  plan; `propose` hands each resolved fork to the kernel's door;
  `build --to STACK` runs only once the proposals are sealed, and refuses
  otherwise. Its tests run under the guard, so the promise that it writes
  the box only through the kernel is held mechanically. It goes on
  `adapters/planned.json` first; `similar near` finds nothing close to it
  today, in either sentence I tried.
- **Nobody:** `kernel.py` does not change. It never names an add-on, and
  the Forge is an add-on to it like any other.

## What this answers in the Forge's idea pile

- **7**, a real `BoxLookup` over the catalogue: the card box.
- **8**, model-proposed forks: a plan with forks now has a first caller
  that is not a test, and the proposer whose confidence is scored is the
  matchmaker before any model.
- **18**, `has_sealed` trusting unverified seals: the seal moves to the
  key the person already has, and the Forge reads it through `sealed()`,
  which verifies every proof.
- **23**, whether the engagement flag correlates with anything real: every
  stack decision lands on a record with the band and the rationale, so the
  question has data.
- **29**, where the checkpoint proposes: into the person's record, as a
  proposal, never into a bundle.
- **72**, checkpoint fatigue: the `auto` band is the kernel's own
  "sealed answer first", so a repeated sentence costs nothing.

And in Willow's: `assistant-scores`, `model-recall` and `second-opinion`
are all reports over proposals by proposer. The Forge's ledger is that
report with a Brier score on it.

## Caveats, stated now

- **Pointing is not answering.** The ranking's "close to what you said"
  finds a card for any sentence. It is only ever a `recommended`, and the
  record says so. The running-club sentence shows why.
- **The alias file is the weak link.** "owe" found nothing today; the
  cards for it (debts, lending, invoices) exist. `search-words.txt` is
  forty-seven lines, hand-kept. The Forge's rule applies: add a row when a
  real sentence missed, argue a row when it mapped wrong, and the ledger
  says which rows map wrong.
- **Confidence waits.** No number until the ledger has outcomes. Until
  then the fork carries `recommended` and `confidence: null`, and the
  ledger records nothing, by the Forge's existing rule.
- **The `recognize` band needs the index.** The kernel matches a sentence
  by its words, exactly. Recognising a decision type across different
  sentences is the Forge's job, and the per-builder store keeps it, as an
  index rebuilt from sealed rows. If the index and the record disagree,
  the record wins; that is a test to write first.
- **Two keys would be wrong.** The stack's own box and the person's box
  each have a key today. The join should not add a third. The stack's
  record is the stack's (which files, which hashes); the person's record
  is the decisions. The Forge writes neither directly.

## A first three bites

1. **`card_box.py` and `card_table.py`**, with the entry's `tiers["box"]`
   naming the candidates it found and the scan's hits carrying add-on
   names. Tested on the two sentences above: the first finds mail and
   coming-up by name and alias; the second finds `web` from the Forge's
   table and nothing from the cards, honestly. Closes idea 7.
2. **The `forge` add-on on Willow's planned list, then built as
   `suggest`** only: bite, scan, print the plan with its forks, propose
   nothing yet. Under the guard, in `COMMANDS`, with mutants run.
3. **`propose` and the seal**, with `has_sealed` reading the person's
   sealed rows through `sealed()` before it asks the index. The first
   stack built this way is the one this session assembled by hand:
   twenty-eight add-ons chosen from a sentence, each choice on a record,
   sealed by the person, not by me.
