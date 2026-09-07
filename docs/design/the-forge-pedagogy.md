# The Forge's pedagogy — the band is not the method

*Draft. Nothing in this paper is sealed: `nestor_match("pedagogy")` is **pending**
against 808 candidate pairs, closest 0.278 against a 0.92 bar. No human has
verified a word of it. It is a proposal for the operator to argue with, and it
should be read as `band="socratic", sealed=False` — the engine's own honest
marking for a fresh decision with nothing behind it.*

## 1. The mistake in the current shape

`forge/checkpoint.py` names three bands — `auto | recognize | socratic`. Two of
those names describe **how much the store already knows** about this maker and
this decision. The third describes **a teaching method**. They are not the same
kind of thing, and putting them on one axis is why the third one does not do
what it is named after.

Read `_full_socratic` and it **presents** — options, tradeoffs, a recommendation
— then **captures** a choice and a rationale. `checkpoint_engagement` scores that
rationale for friction *afterwards*. Nothing asks a second question. Nothing
says "you chose A; the tradeoff you did not answer is B." The engine detects the
rubber-stamp and does nothing about it — by design, and the design is right that
a gate which blocked a seal on a low score would be coercion. But the result is
that the Forge measures engagement it never attempts to cause.

The fix is not a better socratic band. It is two axes:

| axis | question | current home |
|---|---|---|
| **band** | how much do we already know? | `auto / recognize / socratic` — keep, rename the third `fresh` |
| **mode** | how should we interact, given that? | new — and mostly already written elsewhere |

## 2. The jig next door

Before proposing a mode set, the sequencing rule (corpus, then box, then remote)
says look in the box. The box holds **`hornbook-knowledge/UTETY`** — the fleet's
`classroom-learning` seat, `role: "classroom-learning"`, indexed at 666 nodes.
It is a working learning engine, and it already implements, in the operator's
own idiom, every mode this paper was going to invent:

- `content/model.py` — `Item`, docstring: *"A single auto-checkable
  retrieval-practice opportunity."* Deterministic `check()`, explicitly *"no
  model call."*
- `Item.scaffold` — *"worked-example / faded prompt for novices"*, revealed by
  `LessonSession._present` only when `mastery < NOVICE_THRESHOLD`. Faded
  scaffolding, already built.
- `Item.difficulty` — *"for ~85%-success selection"*; `_select_item` picks the
  item whose estimated success is closest to `TARGET_SUCCESS`. Desirable
  difficulty, already built.
- `next_step` — *"Interleave: prefer the least-practised unmastered skill… In a
  discrimination domain (ramp vs lever), interleaving beats blocking (Rohrer
  2020)."* Interleaving with a citation, already built.
- `Item.feedback_for` — error-specific, task-focused messages, under a numbered
  house rule: *"NEVER self-directed praise (Rule 2)."*
- `core/mastery.py` — BKT: `predict_correct`, `update`, `mastered`.
- The **experience gate** — `requires_experience`, *"the physical experiment
  comes first (hands before vocabulary)"*, acknowledged into a disclosure log.

**So the Forge should not grow a pedagogy layer. It should reuse UTETY's**, the
way `forge/friction_floor.py` is vendored byte-for-byte from willow-mcp rather
than re-derived (rule 11). Anything else re-implements a measure that already
has a home and an owner, and the two would drift.

## 3. The thing that does not transfer

Here is the load-bearing difference, and it breaks a direct port:

> **UTETY grades. The Forge cannot.**

`Item.check(response)` returns `True` iff the response is correct — there *is* a
right answer, known in advance, on device. A Forge checkpoint decision is a
**fork**: options, tradeoffs, a recommendation, a confidence. There is no right
answer at answer-time. That is the entire point of asking a human.

Every mode above that depends on correctness therefore cannot be lifted as-is:

- **BKT is unusable in its UTETY form.** `record_outcome(correct=…)` needs a
  boolean the Forge does not have. Feeding it "the maker agreed with the
  recommendation" would define mastery as *compliance with the model* — the
  exact failure the whole engine exists to refuse. That is not a port bug; it is
  a value inversion, and it must be written down so nobody ships it by accident.
- **~85% success selection** has no success to target.
- **Error-specific feedback** has no error to key on.

But the Forge has something UTETY does not: **ground truth that arrives late**.
`forge/build_loop.py` records a prediction before the maker answers and resolves
it after; `forge/calibration_ledger.py` scores brier, hit rate and
overconfidence. So:

> **Mastery in the Forge is calibration, not correctness.** A maker is
> "mastered" on a decision-type when their *own* judgments on it stop being
> revised, not when they agree with the engine.

That single substitution — swap BKT's `correct` for a calibration outcome — is
what makes the UTETY loop importable at all, and it is the one piece of new
design this paper actually claims.

## 4. The mapping, once that substitution is made

| UTETY | Forge | status |
|---|---|---|
| learner | builder / maker | exists |
| skill | decision-type (`DECISION_TYPE_MAJOR`, fork kinds) | exists, unnamed as a skill |
| `Item` | one checkpoint presentation of a `Decision` | exists |
| `Item.check` → `correct` | **calibration outcome, resolved later** | **the gap** |
| `mastery.p_known` | per-maker, per-decision-type calibration | data exists in the ledger, unused for this |
| `is_mastered` | the `auto` band's threshold | **wrong today** — see §5 |
| `scaffold` + `NOVICE_THRESHOLD` | show/fade the recommendation and tradeoffs | new, cheap |
| interleaving by least-practised | which decision to surface first | new |
| experience gate ("hands first") | do not ask about an artifact class the panel has never measured | new, speculative |
| disclosure log + `citation` | the seal + the Nestor ledger | exists, better than UTETY's |
| Rule 2 (no self-directed praise) | adopt verbatim for checkpoint feedback | free |

## 5. The finding this turned up — measured 2026-09-07

The `auto` band currently keys on **the engine's confidence and whether memory
holds a match**. On the mapping above it should key on **the maker's
demonstrated calibration for that decision-type**. Those come apart exactly
where it matters: a maker who is reliably miscalibrated on a decision-type gets
*more* auto-applied answers as the store fills up, because the store's
confidence grows while their judgment does not. The engine's own thesis —
*a confidence nobody checked* — applies to the band selector itself.

**Structurally, this is not in doubt.** `run_checkpoint` branches on
`checkpoint_memory.check(surface)` and nothing else; no calibration value is in
scope at the branch. `result["sealed"] is True` → auto, full stop.

**Measured** (`python -m forge.band_probe --rounds 6`). Two simulated makers
answer the same decisions in the same order, differing only in whether they pick
what was recommended — the two extremes the ledger can express at a stated 0.9:

```
maker         n  auto  recog  socr   auto%    hit  overconf
aligned      18    15      0     3   83.3%   1.00     -0.10
contrary     18    15      0     3   83.3%   0.00     +0.90

calibration gap between them : 100pp
auto-band rate gap           :   0.0pp
reportability floor          :  10pp  (sealed benchmark-eval-harness-spread-pp)
```

Identical trajectories. A hundred points of calibration difference buys exactly
zero difference in how often the engine stops asking. And the number that
matters:

> **The `contrary` maker is wrong on every single decision and still has 83.3%
> of them auto-applied** — `by_band: auto → n=15, hit_rate=0.00`.

The per-round trace shows the other half of the claim: round 1 is entirely
socratic (nothing sealed yet), every later round entirely auto. **Store fill
drives the band, and fill only ever grows.** Being reliably wrong does not slow
it down.

This is a null result, so the instrument's own contrast is asserted rather than
assumed (`tests/test_band_probe.py::test_the_two_makers_are_maximally_apart_in
_calibration`), and the gap is reported against the operator-sealed 10–20pp
harness-spread floor. The honest claim is *no calibration sensitivity above the
floor*, not *provably none* — though here the structural argument already
settles it, and the measurement is the consequence rather than the evidence.

Note what made this runnable at all: `band`, `pair_id`, `match_confidence` and
`matched_band` now survive on `CheckpointOutcome`, and `resolve_prediction`
stamps them onto the calibration row. Before 2026-09-07 the two objects met in
one stack frame in `build_loop.resolve` and were appended to separate lists, so
the question had no answer at any sample size.

## 6. Outside evidence, and what it costs this paper

The operator's research brief of the same date
(`sean-data-vault/made-by-willow/2026-09-07-rosenberg-unanimous/`) surveys
Rosenberg and Unanimous AI — many humans converging on one decision, the mirror
image of the Forge's one maker. Three of its findings land on this paper, two
supporting and one damaging.

**It grounds §5.** Lorenz et al., *PNAS* 2011: mild social influence narrows the
diversity of estimates and **inflates confidence without improving accuracy**.
That is §5 stated in the literature, peer-reviewed, from outside this fleet — a
store whose confidence grows while the maker's judgment does not is a known
failure, not a hunch. §5 stays unverified as a claim about *our* ledger, but it
is no longer speculative as a mechanism.

**It names the precedent for disputation, and its flaw.** DeepMind's Habermas
Machine (Tessler et al., *Science*, Oct 2024, n=5,734): a mediator drafts, the
group critiques, it iterates. That is the disputation mode at scale, with the
rigor the Unanimous work lacks. But the brief's read of it is the warning: there,
*humans mostly react to the AI's drafts*. The Forge's `socratic` band has exactly
that shape today — the maker reacts to a recommendation the engine wrote first.
Any disputation mode that keeps the recommendation in front of the maker
inherits the anchoring rather than curing it. This is what makes the pretesting
mode (commit before seeing the recommendation) load-bearing rather than
optional.

**It indicts §6 as originally drafted.** Rosenberg's Manipulation Problem
(arXiv 2306.11748) argues the dangerous pattern is a system that *reads a
human's state in real time and adapts its behaviour to steer them* — and
proposes that closing that loop be forbidden outright. The first draft of this
section proposed triggering a challenge **when the maker's engagement score came
in low**. That is precisely a closed loop: score the human covertly, change the
interaction to move them. `checkpoint_engagement`'s own docstring already refuses
the blocking version as coercion; the adaptive version is the same thing wearing
a friendlier face, and I did not see it until the brief named the pattern.

The brief's methodological note applies too: the CSI studies never ablated the
surrogate agents against plain small-group chat, so the specific contribution of
the mechanism is unmeasured. A mode added here without an ablation would be the
same unfalsifiable claim. Note also that `calibration_ledger.py` already scores
**Brier** — one of the yardsticks the brief faults Unanimous for never using. The
Forge is better instrumented than the commercial art; it should not waste that.

## 7. The smallest bite, corrected

**Disputation, on a declared rule — never on a score of the maker.**

In the `socratic` band, after the maker chooses, present the tradeoff of the
option they did *not* pick and take one more answer. The counter-argument is
already written in the plan (`plan_shape.py` carries tradeoffs per option); it is
a lookup, not a generation, so it stays model-free. It never blocks a seal — it
adds one turn.

Three constraints, all from §6:

1. **The trigger is declared in advance and legible** — a property of the
   decision-type and band, written where the maker can read it. Not their
   engagement score, not any real-time read of them. If it fires, they can know
   *why* before they answer.
2. **`checkpoint_engagement` stays exactly where it is** — an annotation for a
   human and the scheduler. It never selects an interaction. The gate the engine
   already declined to make blocking, it must also decline to make adaptive.
3. **It ships with an ablation** — same decisions, same makers, disputation on
   and off, scored against the calibration ledger. If revision rates and Brier
   do not move, the mode is decoration and comes out.

This still fixes the gap in §1 — the engine attempts engagement instead of only
measuring it — without buying it by watching the maker.

## 8. Open, before any code

1. Does the operator want UTETY **vendored** (as `friction_floor` was) or
   **depended on**? Vendoring a whole loop is heavier than vendoring a scorer.
2. Is "mastery = calibration" the right substitution, or does it smuggle in a
   different wrong thing? This is the claim most worth attacking.
3. UTETY carries a consent gate (`require_consent`, `ConsentError`) because its
   learners are children. The Forge's makers are not. Which of its guarantees
   are pedagogy and which are child-safety, and does dropping the latter break
   the former?
4. §5 says the band selector is wrong. That is a claim about shipped behaviour
   and should be measured against the calibration ledger before it is believed.
5. ~~Where else does the engine already close a loop on the maker?~~ Answered
   in §9 — and the answer is sharper than the question assumed.

## 9. The line: re-ask, never re-argue

### 9.1 What actually ships

The open question in §8 assumed FSRS reads something coarse — "waved through"
versus "argued." It does not. Read `checkpoint_schedule.grade`:

```python
if engagement < _HARD_MAX_ENGAGEMENT:   # == checkpoint_engagement.RUBBER_STAMP_FLOOR
    return _RATING_HARD                 # resurface sooner
if engagement > _EASY_MIN_ENGAGEMENT:   # 0.66
    return _RATING_EASY                 # push it out
```

`checkpoint_calibration.resurface` scores the held rationale with
`checkpoint_engagement.engagement_score` and passes it straight through. So the
engine **already** reads a covert score of the maker's own words and adapts its
behaviour toward them — the same `RUBBER_STAMP_FLOOR`, imported rather than
copied so the two cannot drift. This is not a future risk introduced by adding
modes. It is shipped, wired, and tested (`test_checkpoint_calibration.py` §6).

So the line cannot be drawn as "we don't do that." It has to be drawn somewhere
that puts the existing scheduler on the permitted side and the §6 draft of
disputation on the forbidden side — or else it has to condemn the scheduler.
Four candidate distinctions, three of which fail:

- **"Covert versus declared."** Fails. The engagement score is not shown to the
  maker; they cannot see why a decision returned in three days rather than
  thirty. The scheduler is exactly as covert as the rejected draft was.
- **"Voluntary versus involuntary signal."** Holds, and matters — the score
  reads a rationale the maker chose to write and which is already in the seal,
  not an involuntary emission. But it is not sufficient on its own: the rejected
  §6 draft read the same voluntary artifact.
- **"Benign versus hostile intent."** Fails as an engineering line. Intent is
  not a property the code can carry, and every manipulative system has been
  built by someone who meant well.
- **"Whose objective function."** Holds. The scheduler optimizes the maker's own
  retention of their own decision; there is no third party whose interest the
  loop serves. But stated alone it is a promise, not a mechanism.

### 9.2 The line

> **A loop that reads the maker may change WHEN they are asked, and WHETHER
> something is asked. It may never change WHAT IS ARGUED to them — the options,
> the tradeoffs, the recommendation, or the force with which any of them is
> put.**

Re-asking is content-neutral and symmetric: it reopens a decision without
leaning on the outcome. A maker who is asked sooner is not being pushed toward
holding or toward regressing — they are being asked again, with the same
material. Re-arguing is not symmetric. Selecting *which counter-argument to
deploy* against a maker based on a live read of that maker is persuasion tuned
to a person, which is Rosenberg's closed loop with a different sensor.

That is why the scheduler survives and the first draft of §7 did not. FSRS moves
a date. The rejected design moved the argument.

### 9.3 Three rules that follow

1. **Timing and selection, never content.** A signal derived from the maker may
   feed the schedule, the queue order, and whether a checkpoint fires at all. It
   may not select, order, weight, or phrase a tradeoff, a recommendation, or a
   counter-argument. `plan_shape` content is a lookup keyed on the decision,
   never on the person.
2. **Authored artifacts only — never a behavioural trace.** The score reads what
   the maker deliberately wrote and sealed. It must never read latency,
   time-to-answer, hesitation, edit or revision counts, cursor behaviour, or
   session timing. These are sitting right there — `resurface` has the clock in
   hand — and they are the involuntary channel Rosenberg's argument is actually
   about. Grading a maker on how long they paused is the bright line, and it is
   crossed by an afternoon's convenience refactor unless it is written down.
   **Never grade on latency.**
3. **One objective, and it is the maker's own.** The only thing a maker-derived
   loop may optimize is that maker's calibration on their own decisions. No
   throughput target, no agreement-with-the-engine term, no fleet-level
   objective. `calibration_ledger` is the only scoreboard such a loop is allowed
   to serve.

Rule 2 also retires the §9.1 "covert versus declared" failure in the right
direction: the fix is not to keep the score secret but to make the *rule* legible
— a maker may ask why a decision is due today and be told which grade the
scheduler recorded. Legibility of the rule, not of a hidden signal.

### 9.4 The tension legibility creates, and why it settles

Telling makers the rule creates a gaming surface: `friction_floor` is a lexicon
scorer, so a maker who wants to be left alone can pad a rationale with grounded-
sounding language and buy a longer interval. This is real and should not be
waved off.

It settles for two reasons. First, gaming the scheduler harms only the maker's
own review cadence — there is no other party to defraud, per rule 3, which is
what makes this loop different in kind from the ones §6 warns about. Second, the
backstop is not gameable by the same trick: `calibration_ledger` scores Brier and
overconfidence against **what the maker actually chose later**, not against how
their rationale reads. A maker who writes their way out of reviews and is
genuinely miscalibrated will show it in the ledger, which is the signal §5 says
the band selector should have been keyed on all along.

That is the whole argument for keeping the scorer soft: a signal that only ever
moves a date, watched by a scoreboard that only ever counts outcomes.

### 9.5 What this forbids that we might otherwise have built

Written down so nobody has to rediscover it:

- Choosing the counter-argument by what this maker historically finds
  persuasive. **Forbidden** — content, tuned to a person (rule 1).
- Showing a stronger recommendation to makers who usually rubber-stamp.
  **Forbidden** — force of the argument, adapted to a read of them (rule 1).
- Re-ordering options so the one the maker under-picks appears first.
  **Forbidden** — presentation is content.
- Firing disputation on a decision-type at a declared band, for everyone.
  **Permitted** — a rule about decisions, not about a person.
- Surfacing a maker's overdue decisions before their fresh ones.
  **Permitted** — order of asking, content untouched (rule 1).
- Skipping a checkpoint entirely for a maker with strong calibration on that
  decision-type. **Permitted** — "whether something is asked", and it is the
  correct reading of the `auto` band that §5 asks for.
- Grading engagement on how quickly the maker answered. **Forbidden**, rule 2,
  and it is the cheapest of these to build by accident.

### 9.6 The signal this line permits is noisy — measured

§9 permits a maker-derived signal to move a date. That permission assumed the
signal means something. Measured on 2026-09-07
(`python -m forge.engagement_probe`, and see
`docs/design/the-forge-engagement-defect.md`), it largely does not:

- `"picked at the command line"` — argparse's `--why` default, typed by nobody —
  scores **0.350**, clears the 0.34 floor, is not flagged, and grades `Good`.
  It clears it because `line` collides with the `_GROUNDING` lexicon's *file,
  line*, plus maximum novelty for sharing no words with the question.
- A thirty-word rationale naming the tradeoff scores **0.200** and *is* flagged.
  The same argument with "however / I disagree / whereas" scores **0.600**.

`friction_score` detects disagreement vocabulary. It was vendored to catch an
agent mirroring a user, where that is the right proxy; the Forge points it at a
maker deciding their own fork, where it is not. So the loop §9 permits currently
moves review dates on rhetorical style.

This does **not** loosen the line — it tightens the case for it. A signal this
noisy is exactly why it must never be allowed to select *what is argued* to a
maker (§9.2), and why §9.4's backstop matters: `calibration_ledger` scores what
the maker actually chose later, not how their rationale reads. Rule 3's "the
only scoreboard such a loop may serve" is load-bearing, not decorative.

It also reorders the work. No mode in this paper should ship on top of this
signal until §5 of the defect paper is answered.
