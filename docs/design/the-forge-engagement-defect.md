# The engagement gate measures argument, not thought

> **Prior art, read before code:** `forge/checkpoint_engagement.py`'s own
> docstring (bite 3, the four honest properties), `forge/friction_floor.py`'s
> header (the vendoring lineage and the drift guard),
> `forge/checkpoint_schedule.py` §D-FSRS-2 (the `Hard`/`Easy` wire), and
> `docs/design/the-positional-default.md` (the incident that produced the first
> row of the corpus below).

The Forge's engagement gate scores a maker's rationale and
`checkpoint_schedule.grade` turns that score into a review interval: below
`RUBBER_STAMP_FLOOR = 0.34` grades `Hard` and resurfaces the decision sooner;
above `0.66` grades `Easy` and pushes it away. The score therefore moves dates
on real decisions.

Measured, 2026-09-07, with `python -m forge.engagement_probe`:

```
id                       label           score  grade         carried by
argparse-default         not_a_decision  0.350  Good          novelty     !
argparse-default-sealed  not_a_decision  0.350  Good          novelty     !
empty                    not_a_decision  0.000  Hard (sooner) —
echo                     not_a_decision  0.000  Hard (sooner) —
assent-bare              rubber_stamp    0.200  Hard (sooner) novelty
assent-polite            rubber_stamp    0.200  Hard (sooner) novelty
assent-deferential       rubber_stamp    0.200  Hard (sooner) novelty
real-plain               real            0.200  Hard (sooner) novelty      !
real-with-cues           real            0.600  Good          pushback
real-question            real            0.500  Good          pushback
real-short               real            0.350  Good          novelty
non-sequitur             not_a_decision  0.200  Hard (sooner) novelty

agrees with label: 9/12
```

Two rows are wrong, and they are wrong in opposite directions.

## 1. `"picked at the command line"` is not read as a rubber-stamp

That string is `forge/entry.py`'s `--why` default — argparse help text, typed by
nobody. It reached `~/.forge/checkpoints/ledger.jsonl` on 2026-09-07 as a sealed
rationale and was rejected by the operator the same morning
(`the-positional-default.md`). It scores **0.350**, clears the 0.34 floor, is
**not flagged**, and grades `Good`.

The decomposition says exactly why:

```
argparse-default: 0.350  (grounding=0.15, novelty=0.20)
  grounding tokens: ['line']
  unechoed fraction: 1.00
```

`friction_score` is `0.40·pushback + 0.30·grounding + 0.20·novelty +
0.10·question`. This phrase earns:

- **grounding 0.15**, because `line` is in `_GROUNDING` — a lexicon of tokens
  that evidence a claim against something outside the prompt: *test, ran,
  verified, error, output, file, line*. There, `line` means a code location.
  Here it is the second half of "command line." **A homonym collision is doing
  the work.**
- **novelty 0.20**, the maximum, because the phrase shares no content words with
  the decision it is answering. Novelty is the "unechoed fraction" — it rewards
  a rationale for not repeating the prompt, and a rationale about nothing repeats
  nothing.

Neither term has anything to do with whether a decision was made. Strike the
accidental `line` and the string scores 0.20 and is flagged correctly. The gate
is one word away from working on this input, and that word is a coincidence.

*(The control row settles a tempting over-reading: `non-sequitur` — "the kettle
is on and the cat needs feeding" — also has maximum novelty and still scores
0.200 and flags. Irrelevance alone does not clear the floor. The homonym is
decisive, not the novelty.)*

## 2. A real rationale is read as a rubber-stamp

`real-plain` scores **0.200 and flags**:

> the originals are already correct and a sidecar drifts the moment anyone
> re-exports, so we lose nothing by writing in place and gain one less thing to
> keep in sync

Thirty words. Names the tradeoff. States a consequence. It is flagged as a
rubber-stamp and grades `Hard`, so this decision comes back sooner *because the
maker argued it well without arguing with anyone.*

`real-with-cues` is the **same argument** rephrased with contrast markers —
"however", "I disagree", "whereas" — and scores **0.600**, three times as much.
`real-question` scores 0.500 for asking rather than concluding.

## 3. What the gate is actually keyed on

> **`friction_score` detects disagreement vocabulary. The Forge is using it to
> detect thought.**

That is not a defect in `friction_floor`. Read its own docstring: it watches
"whether the agent has stopped being **other** and started reflecting the user
back." For an *agent mirroring a user*, pushback vocabulary is a sound proxy for
otherness — an agent that never says "but" is the failure it was built to catch.
It is a smoke detector for sycophancy and it is good at that.

The Forge points the same scorer at a different subject. A **maker** deciding
their own fork is not being watched for whether they push back on the engine;
they are being watched for whether they *decided*. A maker who agrees with the
recommendation for excellent reasons is not a mirror. The proxy does not
transfer with the scorer.

`checkpoint_engagement`'s docstring claims the conservative direction as
intentional: *"A conservative scorer that reads a genuine one-line reason as
thin is the intended bias."* The measurement does not support the stated
mechanism. `real-short` — a genuine one-line reason — scores 0.350 and passes.
`real-plain` — thirty words — is flagged. **Length is not what is being
punished; the absence of an argument is.** The docstring's defence covers a
failure mode the scorer does not actually have, and misses the one it does.

## 4. What this costs, concretely

- The rubber-stamp flag on `CheckpointOutcome.rubber_stamp` is not measuring
  rubber-stamping.
- `checkpoint_schedule.grade`'s `Hard`/`Easy` wire moves review intervals on
  that signal, so makers who reason plainly are re-asked sooner, and makers who
  hedge are left alone longer.
- `docs/design/the-forge-pedagogy.md` §9 draws its line — *a loop that reads the
  maker may change when they are asked, never what is argued to them* — around
  precisely this loop. The line still holds. What it permits is now known to be
  noisy, which §9.4's argument anticipated: the backstop is
  `calibration_ledger`, which scores outcomes rather than prose.

## 5. What is NOT proposed here

**Do not edit `forge/friction_floor.py`.** Its header is explicit: the file is
byte-for-byte with willow-gate's original, willow-mcp hashes it as a drift
guard, and *"edit the scorer in willow-gate first, then re-sync, never here
alone."* A lexicon tuned for the Forge's subject would silently change
willow-mcp's sycophancy detection, which is a different product with a different
correct answer.

The options, none of them taken in this paper:

- **Retune the lexicon upstream.** Correct home, wrong blast radius — `line` is
  right for willow-gate.
- **Wrap rather than re-vendor.** `checkpoint_engagement` already wraps; it
  could drop or reweight terms for its own subject (e.g. score grounding and
  novelty, discard pushback) without touching the vendored file. Cheapest honest
  fix.
- **Stop feeding it to the scheduler.** Keep the annotation, cut the
  `Hard`/`Easy` wire, so a noisy signal stops moving dates. `grade()` already
  has the `engagement=None` path and calls it "the deliberate degraded path."
- **Replace the subject.** Score the *decision*, not the prose — whether the
  maker chose against the recommendation, whether they later revised. That is
  §5's "mastery is calibration, not correctness" and needs the join keys.

## Decisions taken

- The gate measures argument, not thought, and the docstring's "intended bias"
  claim is not what the scorer does. Recorded; the remedy is the operator's.
- `forge/friction_floor.py` is not edited from this repo.
- The corpus lives in `forge/engagement_probe.py` and the probe exits 1 while
  any `not_a_decision` row scores at or above the floor, so the condition is
  gateable rather than remembered.

## Open

| gap | state | waiting on |
|---|---|---|
| Which of §5's four options. | open | Operator. "Wrap rather than re-vendor" is the cheapest that keeps the drift guard intact. |
| `_EASY_MIN_ENGAGEMENT` is private to `checkpoint_schedule` and restated in the probe. | open | If it moves, the probe's `grade` column goes wrong silently. Either export it or have the probe import the private name deliberately. |
| Does the flag correlate with anything real? | blocked | Needs the calibration join keys — `band` and engagement are never persisted together. See the pedagogy paper §5. |
