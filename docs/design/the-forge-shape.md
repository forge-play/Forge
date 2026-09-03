# The Forge — the shape, as talked out 2026-08-30

Captured from a working conversation, before it was lost. It lives here because
the architecture map is here; it may want to move into `forge-play/Forge` once
the shape settles. Nothing below is built unless it says so.

Written down for a specific reason: a survey the night before found the corpus
holds **8,340 claims about what the code does and none about why any of it
exists**, because the corpus extracts committed files and intent lives in
transcripts nothing reads. This is that failure being caught in the act.

---

## 1. What the Forge is

The place where 10,000 kinds of things get built — and the only part of the box
that was built to **find out** rather than to record. Everything else keeps
books: Nestor records what a human checked, FRANK records what happened, the
corpus records what the code says. The Forge states a confidence, builds the
thing, and learns whether it was right.

`forge/calibration_ledger.py` implements exactly that loop and **has never been
called once**. `~/.forge` does not exist because nothing has ever had a
prediction to record. The reason is not neglect: `stub_builder` emits
`hello_world_command` and nothing else, so there has never been a build real
enough to be wrong about.

An APK is the first target that isn't hello world. It compiles or it doesn't,
installs or it doesn't, runs on a device or it doesn't. **Ground truth arrives
on its own**, which is the input the calibration ledger has been waiting for.

## 2. The entry

The unit is a **project**, not a user — many projects live on one box.

A person opens the app or the CLI, and **Vishwakarma** asks:

> **What's the first bite?**

*Bite* is already the Forge's own unit of work (`bite 3 of the learning
layer`), so the onboarding question and the thing the checkpoint/FSRS machinery
schedules are the same object. No translation layer.

First run is onboarding: **scripted questions, model synthesis only at the
leaves.** What are your ideas, what do you want to accomplish. The questions do
not drift because they are not generated. Same discipline as the rest of the
box — the deterministic part stays deterministic.

## 3. From a sentence to a major

A real opening sentence contains almost no spec:

> *"I got sum kol sites for app to spin"*

That is not a reasoning problem. It contains **two keywords** — `site` and
`app` — and a regex finds both. They map to different majors: `site` → web;
`app` → web, mobile, or desktop.

Two candidates and no way to choose is **a detectable condition with a scripted
response: ask.** The next node is a disambiguating question, not a guess.

This is the three-state contract in a new place. Nestor answers `pending` when
nothing verified matched rather than improvising; Jeles returns `found: False`
with candidates. Ambiguity is information the flowchart consumes, never a
failure the model papers over.

**The first artifact to build is the keyword → major table.** A flat file
somebody can read and argue with.

### The scan has two callers, not one

Operator, 2026-08-30: *"this loops back to our keyword workflow in the forge."*

It does, and it makes the scan load-bearing twice over.

**Caller one** is the entry above: a sentence arrives, the scan pulls out apps,
languages and references to other repos, and a major falls out.

**Caller two is a document.** Measured tonight: `willows-grove` was extracted and
produced 790 claims — **706 code docstrings, 84 table terms, and 5 rows from
`docs/design/`.** `extract_standard.py` reads four shapes and narrative prose is
none of them, so an entire night of design writing sat inside an extracted
repository and remained unfindable. Extraction was never the missing step. **A
design section is not a shape anything can query.**

The scan is what makes it one. A document is an opening sentence that ran long:
same operation, same keyword vocabulary, same trip through jeles, different
input length. So the prose extractor the corpus needs is **not a markdown
parser** — it is this scan pointed at a file.

That is the same economy `marching-arts` P1 states about the authorization
resolver — *"the sync spine … is the same component wearing a different hat"* —
and the reason to say it here is that it changes what gets built. A scan written
for one caller acquires a sentence-shaped interface and has to be rewritten for
the second. Written for both, the Forge gets its entry and the corpus gets its
missing lane from one component.

Two properties follow, and both are cheap only if declared now:

- **The input is a span of text, not a prompt.** No turn structure, no user
  framing, no assumption of a single sentence.
- **The output carries an origin.** The Forge can discard it; the corpus cannot
  — a claim without a resolvable origin is not a claim. So the scan emits
  `(source, target, reason, path, anchor)` and the Forge ignores the last two.


### Look in the box before you look outside it

Operator, 2026-08-30, after I queried the GitHub API for a repository sitting on
the disk:

> *"You don't need to go remote for things that could be in the box. Just
> because it's not right in front of you doesn't mean it isn't there. Think of it
> like the cliché mom-knows-where-everything-is joke — it's only a joke because
> it's usually true."*

The failure was not laziness about search. It was treating **absent from the
working set** as **absent from the box.** The legacy fleet monolith is archived on GitHub, so
I reached for the API; it was also sitting clean at
`~/github-archive-greenfield-2026-08-10/`, 52,320 files, and had been the whole
time. Extracting it locally produced **3,583 claims** in one pass, including the
two things being looked for: `apps/ratatosk` — a *"shared phone + desktop
runtime"* with a capability gate that refuses raw remote shell — and
`scripts/gitsync/gitsync-loop.py`, the whole-tree timer the old box map assumed
and which no longer runs.

So the rule has three tiers and they are strictly ordered:

1. **Ask Nestor.** If the corpus answers, stop.
2. **Look in the box** — including archives, greenfield, `superseded/`,
   anything retired. Retired is not gone; it is a different shelf.
3. **Only then go remote**, and say why the first two did not answer.

The second tier is the one that was missing, and it is where the volume is: the
greenfield archive holds two dozen retired repositories — `willow-1.9`,
`willow-canonical`, `willow-compose`, `willow-nest`, `willow-tech-manual`,
`safe-design`, `jeles-remote` — none of them in the corpus.

**A silent corpus is not proof of absence, it is proof nobody extracted.** That
is the same distinction the refresh driver already draws between *refused* and
*retired*, applied one level up: at the moment Nestor returned zero for
"ratatosk", the correct reading was *the corpus was never given the legacy monolith* —
not *ratatosk does not exist*.

For the Forge this is a hook, not a habit. The entry scan (§3) already asks the
corpus; the tier-2 step is a second, cheap, local lookup before any network
call, and it fails the same way — loudly, naming which tier answered. A build
that reaches the network without recording that the box was checked has skipped
a step and left no trace of the skip, which is §11's rule again in a different
place.


## 4. The almanac gains a tech rung

Working name **`almanac-tech`** — not settled.

It holds two things, and holding them together is the point:

- **official documentation, pinned per version.** `c++ v0.0.0.1`,
  `windows dev v whatever`. The doc set for *that* version, held — not queried
  live. This is H-5 exactly: public reference data, held not fetched, the same
  for every household, names nobody. `as_of` must be a literal, or a pinned doc
  set quietly becomes a live feed wearing a version number.
- **the awesome lists, with their criteria.** `awesome-sovereign-software`
  moves here — 120 entries, 35 sections, a stated five-point test, and every
  entry documenting its exit plan.

**Why together:** it puts the accounting bar in one place. *Here is what the
docs say. Here is what the lists say.* A builder asking "what do I build this
with" gets both from the same shelf, and both carry their basis.

### Criteria are what make a list citable

A list with a stated test is a source you can quote and a reader can check. A
list without one is a pile of links wearing a badge. The Forge must never hand
those to a builder as if they were the same thing — that is the hollow
`verified_by` problem in a new costume.

So a **criteria registry** falls out, three columns and no more:

```
list · what it covers · does it state criteria (and what are they)
```

It stays a *registry*, not a curation project. "The best lists" needs taste and
maintenance and rots; "lists, and whether they state a bar" is checkable by
anyone and stale-proof, because a list either has a criteria section or it does
not. That is a fact, not an opinion.

The **major picks the list** — the same keyword table doing a second job.

## 5. How documents get in

**The Nest already solved this**, and it was built for something else.

> *"Dump your life and let the pigeon figure it out."* Walk a folder, extract
> text — OCR / PDF / docx / plaintext — classify fragments by meaning through a
> **regex → local-embedding → LLM cascade**, write a canonical SQLite DB.

Format-agnostic, no commit sha required. It answers the provenance question the
corpus extractors could not: `repo@sha:path#anchor` has no meaning for a PDF
pulled from an archive.

**One inversion.** The Nest's wall exists because its source is a person:

> *"relative/structural shape is process (shareable); absolute content is
> person (walled)"*

Correct for journals, backwards for a C++ spec. Public documentation has no
person in it — the content **is** the shareable part, and structure-only
promotion yields a taxonomy of a manual you still cannot quote. The Apple IIe
case needs the actual opcode table, not a count of opcode-shaped fragments.

So: same engine, and **which side of the wall you land on is a property of the
source, not of the reader.**

Jeles is the fetcher. It already reaches institutional sources with provenance
and rungs; what is missing is that it *gives to the almanac*.

## 6. Nestor at the centre — the connections, not the pairs

Nestor has never stood at the centre of anything, and the reason is visible:

```
decision_edges       0 rows
decision_evidence    0 rows
decision_warrants    0 rows
```

Plus `memory_lineage`, `memory_edges_to/from`, `superseded_by` — the whole
connection layer, built and never populated. All 599 seals are pairs. **Nothing
has ever been an edge.** 11,061 corpus claims, not one relation between two of
them.

### The test case that cannot be solved by search

Reproducing something built in 1982 on an Apple IIe. The docs and lineage
documentation still exist, in parts. To rebuild it you need: this instruction
in this manual → that opcode → this emulator's implementation → that flag which
changed in 1987. **Every hop is a lineage question.** A blob can hold the manual
and cannot hold *"this and that are the same thing thirty years apart."*

### So the division

- **the almanac holds the documents** — pinned, public, identical for everyone
- **the project's nestor holds the connections** — every dep, module, runtime
  and doc that Kart will actually run, and the edges between them, added one at
  a time as the build grows

Per-project is the right grain: not the fleet store with its 599 seals, but a
store whose whole content is *this build's world* — disposable, portable, ships
with the project. The same property that made `willow_personal` its own
database rather than a column.

### And the blob plan dies

- a blob makes the agent read the manual
- a corpus makes the agent **ask the manual and get a cited answer**
- edges let it ask **across** manuals, which is the only part a blob cannot do

The corpus lane is already correct for this by accident of design: all 11,061
claims are `draft`, none sealed, because it is *"one non-authoritative corpus
lane… exposed only as attributed, authority-free drafting context."* **You do
not seal the C++ spec. You cite it.** Seals and documents never touch.

### The dogfooding is what makes this reproducible

19 of 24 repositories are pinned to one extractor digest. One extractor,
nineteen codebases, same claims, same provenance. That generality was not
designed; it fell out of having to eat 24 repos that disagreed about
everything. The intake contract it produced:

- a source, anything walkable
- a declared extractor, content-hashed with `provenance.py`
- claims with resolvable origin
- a refresh plan **derived from what is stored**, never a maintained list
- honest refusals — dirty tree, missing checkout, unresolvable toolchain
- tombstones — retired reads *retired with a forwarding pointer*, not *refused*
- a miss log — what was asked that nothing answered

**The domains are arbitrary.** `symbol → docstring` is not privileged.
`opcode → mnemonic`, `error_code → cause`, `api_version → successor`,
`flag → semantics_in_1987` — same two columns, same machinery. The corpus never
knew it was about code; it only knew it was about pairs with provenance.

### The graph has to rank its own edges

As nodes connect, the answer to *what connects to what* stops being useful by
growing. A script that only knows "these two have been mapped before" returns a
near-infinite list the moment the graph is dense — every pair is mappable, so
every pair gets offered. The map has to know which connections have been the
**good** ones.

Nothing in the box ranks an edge today. `corpus_search` returns `score` and
`query_coverage`, but those rank a *claim against a query* — retrieval order,
computed fresh each call, forgotten after. An edge's worth is a property of the
edge, accumulated over many crossings, and there is no field holding it because
there are no edges.

The signal cannot be similarity. Two claims that look alike are the pairs a
search already finds; the valuable edge is the one between things that do *not*
look alike — the 1987 flag change and the emulator that implements it. So the
rank has to come from **use**:

- an edge a build actually crossed, on the way to something that ran, earns rank
- an edge nothing has ever traversed decays toward the bottom of the list
- an edge crossed and found useless is recorded as **tried and poor**, not
  dropped — a recorded negative is not an absence, and an edge that is merely
  deleted gets re-proposed forever

That is FSRS again, pointed at edges instead of pairs. The box already runs it
over `friction_score` for the Socratic loop (§7); the same scheduler grades a
connection by whether recalling it helped. Corroboration is the second signal
and jeles already counts it the right way — `conflict_scan` emits only when
`>= min_sources` **independent domains** agree, which is exactly the property
that separates a real cross-manual link from two copies of one manual.

Neither is a new mechanism. Both are mechanisms the box built for something
else and has never pointed at a graph, because the graph has zero rows.

## 7. The Socratic method, explained

Held back from promotion because it *"was tested and working and I never
understood how."* Here is how, and **there is no questioner anywhere** — which
is why it was hard to see.

1. A checkpoint makes the maker **decide** (D8), and D9's thesis is that the
   deciding has to be real, not a rubber-stamp.
2. The maker writes a **rationale**.
3. `friction_score(text, context)` scores how *other* it is on [0,1] — pushback
   markers, grounding markers, **novelty** (`len(a_words - u_words) /
   len(a_words)`, the unechoed fraction), asking.
4. Same scorer, pointed the other way. willow-mcp aims it at an **agent's**
   turns to catch mirroring. The Forge aims the identical vendored scorer at
   the **maker's own rationale**. *"Yes, sounds good"* scores near 0.
5. The score feeds the scheduler:

```
RUBBER_STAMP_FLOOR   = 0.34
_HARD_MAX_ENGAGEMENT = RUBBER_STAMP_FLOOR    (imported, not a second literal)
_EASY_MIN_ENGAGEMENT = 0.66

engagement < 0.34  →  Hard  →  FSRS resurfaces it SOONER
engagement > 0.66  →  Easy  →  pushed OUT
```

**Wave a decision through and it comes back sooner. Argue it and it goes away
longer.** The Socratic feel is emergent — the system returns to what you did not
think about. It is not detecting whether you were *right*; it detects whether
you *engaged*, and lets FSRS do the rest.

Three refusals it is careful about:

- **it never blocks** — *"a gate that blocked a seal on a low score would be
  exactly the frictionless-in-reverse coercion the friction primitive refuses
  to become"*
- **deterministic and model-free** — pure stdlib. *"A sandboxed build cannot
  game a scorer that never runs inside it."*
- **it runs outside the party it watches** — the store scores the maker.
  *"A mirror cannot audit itself."*

## 8. What flows back

**Not people's apps. The shape of how things connected.**

That is the Nest's wall, already decided, unchanged in a word — structure is
process and travels; content is person and stays. It is the fourth independent
arrival at that line, after the Nest's bridge, corpus-lens's Guard, and
homestead's I-31 (counts only, categories that fail a re-identification check
going **absent, not zero**).

Three properties follow:

- **It cannot leak, structurally.** Not a promise — there is nothing to look at.
  `this dep + that runtime + this doc version → worked` does not contain an app.
- **It is the part that compounds.** Ten thousand apps teach nothing. Ten
  thousand *builds* teach which combinations work, which docs were wrong, which
  dep breaks against which runtime, which 1982 manual maps onto which emulator
  flag.
- **A shape contribution needs no review.** A code PR needs a human to read it;
  an edge is either reproducible or it is not — and the machinery to say which
  exists, because a claim carries its origin and a warrant carries a recipe and
  an expected digest. Contribution stops being a social process and becomes a
  measurement. Nobody has to *decide* to contribute; the build already knows
  what it connected.

### And it is an exit plan

`awesome-sovereign-software`'s premise is *"if the vendor vanished tomorrow,
everything still works,"* and every entry documents how you walk away with your
data. A Forge user's exit plan is trivially satisfiable: **they keep everything
they made, and the only thing that ever left was topology they could regenerate
anyway.** The Forge would pass the test its own list publishes.

## 9. Which model runs it

Not one large model. The job was already shrunk seven times, by seven authors,
for seven separate reasons:

| piece | what it removes from the model |
|---|---|
| Nest cascade | regex → embedding → LLM; most fragments reach no model |
| Jeles' judges | may only demote, veto, phrase — never create, propose, cite |
| `friction_floor` | model-free entirely; the Socratic loop needs no model |
| onboarding | fixed questions; synthesis only at the leaves |
| the flowchart | the graph is decided, the language is not |
| nestor edges | a precomputed connection is a traversal, not an inference |
| the corpus | ask and get a cited passage instead of reading a blob |

Convergent arrival, same shape as decision `0227`: **make the model's job small
enough that being wrong is cheap and visible.**

What still wants a large model, honestly: turning a person's opening sentence
into a real project shape — though §3 shows even that is mostly keywords plus a
disambiguation tree — and **writing the code**. Two expensive calls, at the top
and at the point of writing; twenty cheap steps around them. A very different
bill from "an agent runs the Forge."

---

## 10. What the verbs return today — measured 2026-08-30

The Forge does not call `nestor_ask`; it calls the corpus verbs. Measured
against a copy of the live 11,061-claim corpus, served with `--corpus-dir`
(which is the only thing that registers these two tools at all):

```
nestor_corpus_search(query, limit=3)     3,749 bytes  — 1,249 per claim
  40.1%  key names, braces, indentation
  28.5%  content            <- the only part a model can act on
  10.6%  identity hashes    (id + row_sha256 = 128 hex chars per claim)
   6.6%  origin string
   3.9%  envelope           (query_sha, snapshot_sha, three counts)
   3.2%  source_norm        (source_text with punctuation stripped)
   3.0%  source_pair_id     (a third identity for the same row)
   2.9%  ranking            (score, rank, query_coverage, matched_terms)
   1.2%  non-authority markers x3

nestor_corpus_map()                      5,328 bytes for 24 repositories
```

Two things follow.

**The covenant is not what costs.** `authority: "none"`, `source_status` and
`comparison_labels` — the three fields carrying the non-authority posture — are
45 bytes, 1.2%. And the verb has no answer field at all: it returns a place to
look, by construction. Nothing here argues for weakening the posture.

**The cost is recomputability.** Three separate identities per row and two
digests in the envelope exist so a later auditor can prove the row was not
altered. That is right for a ledger and wrong for a model that is about to open
the file named in `origin` anyway. `source_norm` is derivable from a field two
lines above it. `indent=2` at `serve.py:937` is 548 bytes — 14% — on its own.

The same payload as pointers (`repo` / `at` / `says`) is **1,176 bytes, 31% of
served**, and loses nothing a build would use.

This is the mirror of the `nestor_ask` measurement: 880 bytes to encode
*trustworthy* seven ways for a 57-byte answer. One verb overspends on trust, the
other on proof, and both are audit shapes handed to an actor.

It matters for the Forge specifically because `corpus_map` is the **first** call
a session makes — a small model spends 5 KB before it has asked anything, then
~1.2 KB per result after. Two queries and ten results is 17 KB of provenance
carrying maybe 5 KB of pointers, on a model chosen (§9) for running locally.

The fix is one argument, not a redesign: a `fields` / `verbosity` parameter
defaulting to lean — `repo`, `at`, `says`, `authority` — with the digests
available on request, so the auditor's payload stays whole. Filed as a nestor
issue.

## 11. Nestor is the first tool

Operator, 2026-08-30, stated as a build requirement rather than a preference:

> *"This is what I want built into the Forge so it's not a fault. Nestor needs
> to be the first tool."*

### What it is reacting to

Tonight, asked where the earlier mobile-vault design went, I grepped four repo
trees, read three READMEs and a decision log, reported it missing, and was
wrong. One `nestor_corpus_search` returned it as the **first result on every
query I tried**: `apps/marching-arts/docs/BUILD_PLAN.md`, with
`sync-scope-equals-permission` already settled as a SOIL record — *"a device
receives only what its holder may see; the authorization resolver does double
duty as the sync filter — build it once."*

The corpus was not missing the answer. **The answer was never asked for.**

Worse than not finding it: my own grep listed that file and I read past it. So
this is not a retrieval problem to be solved with a better search. It is a
**sequencing** problem, and sequencing is the one thing a design can fix.

### Why an advisory is not enough

The box already tried the advisory shape. `nestor/hooks/before_build.py` exists,
cites `the-house-already-knew.md` by name, and was sealed into `prompt_submit`
(`4d070950`). It could not fire tonight for two independent reasons — the
`github` seat carries `"hooks": false`, and its command resolves nothing from a
directory that is not a git repo. It is also deliberately *"silent unless it's a
build,"* and tonight was a survey.

An advisory that fires on every turn trains a reader to skip the line (0221).
An advisory that fires rarely is not there when it matters. Either way it
depends on somebody choosing to read it, which is exactly the fault this
requirement removes.

### So: first, not available

The distinction is the whole decision.

- **Available** — Nestor is one of the tools the Forge can call, and a
  well-behaved agent calls it early.
- **First** — the Forge's entry path calls Nestor **before it calls anything
  else**, and what comes back is an input to the next step rather than a
  suggestion to the operator of it.

Under §3, a user's opening sentence is already scanned for keywords — apps,
languages, references to other repos. That scan is the natural hook: the same
pass that decides which major is in play asks the corpus what the box already
knows about it, and the answer enters the prompt as attributed, authority-free
context. No new mechanism; the two calls already exist and are simply ordered.

**The Forge should not be able to start a build that never asked.** Not
discouraged from it — unable. A build that begins with an unanswered corpus call
is the same shape as a seal with no verifier: a step that was skipped and left
no trace of having been skipped. **A recorded negative is not an absence** — a
corpus call that returns nothing is a fact worth carrying into the build, and it
is the miss log (§6) that catches it. Silence because nobody asked is not.

### What this costs, and what it requires

The cost is measured in §10: a `corpus_map` plus one search is 55% of a 4096
window served, 10% lean. Making Nestor the first tool makes #261 load-bearing —
a mandatory call has to be cheap, or the mandate gets removed the first time
somebody is in a hurry.

The requirement is freshness, and it is not a chore attached to this rule; it is
the rule's precondition. Measured 2026-08-30: the corpus is pinned two days back
for `willow-mcp` and `nestor`, so every PR from the last two sessions — the lane
crossing, the capability permissions, decision `0227`, the rejection-reason fix —
is outside it. `willows-grove` has **zero** claims while its archived
predecessor `willow-grove` still holds 693. And the decay is worst where it
hurts most: the repos sitting at zero commits behind are current because nobody
is touching them.

**A first tool that answers from a stale corpus is worse than no first tool**,
because it converts "nobody asked" into "the box says no" — an authority the
silence never had. So `nestor corpus refresh` (plan Round 0.1) is not
housekeeping. It is what makes this rule safe to enforce.


## 12. The PR is the extraction event

Operator, 2026-08-30:

> *"Everything that is under github should be in Nestor, and really, updated at
> every PR. That is also the shape of a hook that I see for the Forge — same
> hook shape that we have for Nestor. Has this been looked at in the last 30
> minutes, has Nestor been looked at, has it been refreshed. Or on a PR, record
> the PR, the stage of how the things connected, and how CI passed or how it
> didn't, into Nestor."*

Two rules and one hook shape. §11 says Nestor is asked first; this says what
guarantees there is something worth asking.

### Rule 1 — coverage: everything under `~/github`

Measured 2026-08-30, immediately after a successful refresh:

```
37 git checkouts under ~/github      24 repositories in the corpus
```

The 16 outside it are not a random tail:

```
almanac-data/  agriculture · civic · climate · economy · education · energy
               environment · health · justice · science · transportation
               almanac-template          (13 repositories, 0 claims)
willow-memory/ willows-grove             (0 claims — the live grove)
               .willow                   (see the exception below)
hornbook-knowledge/ dotgithub
```

**The entire almanac is invisible to Nestor.** §4 makes the almanac the Forge's
documentation rung — where the official docs and the awesome list live — and §11
makes Nestor the first thing the Forge asks. Today that first call cannot see the
almanac at all. The two rungs the Forge stands on do not know about each other.

`willows-grove` is the second gap and the sharper one: it is the forwarding
target of both tombstones, and it holds this document. **Nothing written here is
findable by the tool this document is about.**

### The one exception, written down because it must be

`willow-memory/.willow` is a git checkout and must **not** be extracted. It is a
live box — `vault.db`, `vault.key`, receipts, the gate ledger, per-app ACL
manifests — not a repository of source. Extracting it would put box state into
a corpus whose whole posture is that it holds attributed, non-authoritative
*public* context.

This is the same line `willow-data-vault`'s README already draws — *repo is
blueprint, box is the populated instance that stays home* — and the same reason
`sean-data-vault` was taken under an allowlist rather than wholesale.

It is recorded here rather than agreed in passing because `docs/corpus-order.md`
warns in its own first paragraph: *"an exception agreed in conversation and not
written down is one a later session will silently undo."* So: **15 to add, 1
excluded on the record.**

### Rule 2 — the PR is when it happens

Not a nightly cron. The PR, and the reasons are structural rather than
preferential:

- **A merged PR is the one moment the refusal cannot fire.** `refresh.py`
  refuses a dirty tree — *"rows would be pinned to X, which does not contain
  them"* — and three of tonight's four refusals were exactly that. A merge
  commit is by construction clean.
- **The pin format already fits.** `origin` is `<repo>@<sha>:<path>#<anchor>`.
  A merge commit is a sha. Nothing new has to be invented to say when a claim
  was true.
- **A cron pins to whatever the tree happened to be at 3am**, which is a commit
  nobody decided on. A PR is a decision with a boundary, an author, and a
  review.

### What a PR should deposit

Three things, and only the first exists today:

| what | shape | today |
| --- | --- | --- |
| the code as of the merge | `<repo>@<merge-sha>` claims | `refresh.py` does this |
| **how CI went** | `commit → ci_outcome`, pass **and** fail | nothing records it |
| **how things connected** | edges: PR ↔ issue, PR ↔ decision, file ↔ file | `decision_edges` is 0 rows |

**Record the failures.** Most systems keep only green. The box's own rule is
that **a recorded negative is not an absence**: "CI failed at this sha for this
reason" is a claim with provenance and is often the more useful one — it is the
difference between *nobody ran it* and *it was run and it broke here.* A red run
that leaves no trace is an empty success.

"How the things connected" is §6's edge layer arriving through the front door. A
PR is a natural edge event — it closes an issue, cites a decision, touches files
together — and those are precisely the relations `decision_edges`,
`memory_lineage` and `superseded_by` were built for and never given. It also
makes §6's **edge ranking** mandatory rather than clever: at PR cadence the graph
densifies fast, and an unranked graph returns a near-infinite list.

### Rule 3 — the hook asks how old the answer is

The operator's third question — *"has this been looked at in the last 30
minutes"* — is not a nice-to-have beside §11; it is what makes §11 safe.

A first tool that answers from a stale corpus converts *"nobody asked"* into
*"the box says no."* So the hook has to carry the corpus's own age with the
answer, and the store already holds it: `corpus_snapshots.consolidated_at`, plus
the per-repository `behind` count `refresh.py --dry-run` already computes.

The three questions, in order, and they are the same shape for the Forge and for
Nestor:

1. **Has this been asked?** — §11. A build that never called the corpus is a
   skipped step that left no trace of being skipped.
2. **Was the answer current?** — this rule. Report the age and the behind-count
   *with* the answer, never silently.
3. **Did the result come back?** — the PR deposit. What was built, whether CI
   passed, and what connected to what.

An advisory answers none of these, which is why `before_build.py` did not save
tonight (§11). These are questions with values, and a value can be checked.

### Honest limits

- **`refresh.py` cannot see `~/sean-data-vault`** — it searches under `~/github`
  only, so that repository refuses every run with *"no checkout named
  sean-data-vault."* A roster fix, not a missing repo.
- **`refresh.py` exits non-zero when anything refuses**, while printing a
  successful sync line. Correct behaviour, and a trap for a hook: **gate on
  stdout, never on `$?`**, or a normal run with one dirty tree reads as a broken
  corpus and the hook gets disabled.
- **Nothing here is built.** `refresh.py` exists and works. The CI deposit, the
  edge deposit, the age report, and the PR trigger do not.


## 13. The bot is the actor the hook was missing

Operator, 2026-08-30: *"and that ties in with the willow-bot and github app work
I've been doing."*

It does, at the exact point §12 stops. §12 says a PR should deposit what was
built, how CI went, and what connected to what. A deposit needs someone to make
it, and that identity now exists.

### The split is already real, and it is the covenant at the credential layer

From `BOT-INVENTORY.md`, installed 2026-08-29 across all seven orgs:

| App | id | may |
| --- | --- | --- |
| `willow-ci` | 4749508 | commit, tag, propagate |
| `willows-bot` | 4001890 | read and comment — **cannot commit** |

*"Covenant §0.2 — proposing and ratifying never rest in the same hand — enforced
by GitHub rather than by convention."* The permission trim went from 19 write
permissions to 5 and cleared the entire organization tier.

This is the same shape Nestor states about itself: **you may propose, you may
not confirm.** It is now true of a credential, not only of a server.

### The permission §12 needs is already granted

The reviewer core is `contents: read`, `pull_requests: write`, `issues: write`,
**`checks: read`**, `metadata: read`.

`checks: read` is exactly the missing middle row of §12's deposit table — *how CI
went, pass and fail.* The hardest-sounding part of that design is already
provisioned; nothing needs asking for.

### And the corpus is precisely the surface a propose-only identity may write

This is the part that fits better than it had to.

Every corpus claim is `draft`. Not one is sealed, deliberately —
`corpus.py` opens *"one non-authoritative corpus lane… exposed only as
attributed, authority-free drafting context."* **Draft is what "may propose, may
not confirm" produces.** So a bot that cannot commit is not thereby blocked from
depositing: what it writes is already marked unverified by the lane it writes
into, and sealing remains a human act with a name attached.

`willows-bot`'s inability to commit is therefore **alignment, not a limitation**.
It is allowed to write exactly the kind of row it is qualified to write.

### The fork this opens, and it is a real one

Where the deposit lands decides which App is involved:

- **Into the store** (`corpus_claims`, a SQLite write) — `willows-bot` can do it
  with the permissions it already has, and the covenant holds by construction.
- **Into git** (a committed corpus artifact) — that needs `willow-ci`, the App
  that commits and tags. The deposit and the propagation credential become the
  same hand, which is the separation §0.2 was drawn to keep.

The first is the one that preserves the property. Recorded as open rather than
decided, because it depends on whether the corpus is ever versioned in git.

### Identity in a deposit is a type, never a login

`BOT-INVENTORY.md` already carries this as a constraint, and §12's deposit is
exactly where it would be violated:

> *Never identify this bot by login string. `.env.example:4` still says
> `GITHUB_BOT_LOGIN=willow-bot[bot]`, which was wrong before the rename
> (`willow-bot-rudi193[bot]`) and is wrong after it (`willows-bot[bot]`). Match
> on `user.type == "Bot"` instead. That is a fact GitHub asserts about the
> credential; a login is a string that survives a rename by being wrong.*

Two renames have already happened. A corpus row recording *who* did something
must record the asserted type, not the name — the corpus already pins claims to
a sha for the same reason, so this is the existing discipline applied to the
actor rather than the code.

### The gap worth naming

`willow-bot` — the repository that holds `bot.py`, `github_app.py`, `router.py`,
the Loki and Oakenscroll personas, and `willow-bot.json`'s per-event voice lines
including **`ci_fail`** — is:

- **cloned to `~/github/workshop/willow-bot` on 2026-08-30**, which closes the
  first half of this gap. `workshop/` is staging; the operator is deciding
  between `willow-memory` and `forge-play` and leaning toward the forge. The
  GitHub repo has not been transferred
- **0 claims in the corpus**
- **already has an extractor**: `scripts/corpus/extract_willow_bot.py`, 3.6 KB,
  written and never run against anything — a third dead extractor beside
  `extract_willow_19.py` and `extract_willow_20.py`

**The thing that would run the hook was the one thing the hook could not see.**
Under §12's rule — everything under `~/github` belongs in the corpus — it was
not even a candidate, because it was not there. It is there now; extracting it
and settling its org are what remain.

Reading it turned up a fifth stale-org sighting and a sixth: the Nestor
dependency points at `rudi193-cmd/Nestor` in **both** `requirements.txt:11` and
`loki/requirements.txt:6`, resolving only through GitHub's transfer redirect, and
`scripts/audit_app_config.py:22-28` audits a **pre-migration fleet** — `Willow`,
the legacy fleet monolith, `willow-config`, `safe-app-willow-grove`, several cut or archived
on 2026-08-27. The fleet watcher's own roster cannot see the seven orgs that
exist. Full checklist in `BOT-INVENTORY.md`.

It also already knows how to say `ci_fail`. The voice line exists; the deposit
does not.


## Decisions taken

- The awesome list **moves** — into the almanac's tech rung, beside the docs,
  so the accounting bar sits in one place.
- Contribution is **shape, never content**.
- The project store is **per-project nestor**, not the fleet store.
- Documents are **cited, never sealed**.
- **Nestor is the first tool, not an available one** — the Forge cannot start a
  build that never asked. §11.
- **Everything under `~/github` belongs in the corpus**, refreshed **at every
  PR**, with `willow-memory/.willow` the one recorded exception. §12.
- **Failed CI is recorded, not only green.** A recorded negative is not an
  absence. §12.
- **The deposit is written by a propose-only identity.** `willows-bot` cannot
  commit, and the corpus lane is all `draft` — the two fit. §13.
- **An actor is recorded by `user.type`, never by login.** §13.
- **Ask Nestor, then the box, then remote** — in that order, and say which
  tier answered. Retired is a different shelf, not gone. §3.
- **The keyword scan has two callers** — the Forge's entry and the corpus's
  prose lane. Build it for both; the corpus half needs an origin. §3.

## Open

- The name. `almanac-tech` is not settled.
- 13 almanac repos and `willows-grove` are outside the corpus; adding them is
  an operator act, and rung order in `docs/corpus-order.md` is deliberate.
- What a CI-outcome claim looks like as a pair, and which lane it lands in.
- Whether the PR trigger is a workflow, a hook, or the merge queue.
- Store deposit (`willows-bot`) or git deposit (`willow-ci`) — the first keeps
  §0.2 intact; the second collapses it. §13.
- `willow-bot` is not under `~/github` and has 0 claims, while its extractor
  exists and has never run. Cloning it into an org is a prerequisite. §13.
- Whether this document belongs here or in `forge-play/Forge`.
- `plan.py` has no notion of majors; a second major forces it.
- The toolchain bind — nothing binds `forge-play` into Kart (68 binds, zero
  mention). See `governance/architecture/willow-v08-toolchain-path.drawio`.
- `~/.forge` symlink missing; `forge-play/.forge` exists and is empty.
- `promotion.json` carries `host_repointed: false` — the recorded reason the
  Forge was never fully promoted.
- Documentation and GitHub both need updating for the list's move.
- Edge rank has no store. FSRS grades pairs today; nothing grades a connection.
- Prose is not a shape. Design sections are unfindable until the scan exists;
  until then, decisions belong in decision records, not paragraphs.
- Whether the lean corpus payload is a default or an opt-in. §11 makes it
  load-bearing: a mandatory call must be cheap or the mandate gets removed.
- Where the first-tool call is enforced — the entry scan (§3), the hook, or
  both. An advisory alone has already been tried and did not fire.
