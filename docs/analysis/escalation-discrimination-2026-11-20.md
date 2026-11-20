# Does a model's stated confidence know when it is wrong?

**Measured 2026-11-20, over the escalation benchmark's rows on the
maintainer's machine** (`~/.forge/escalation-runs/`), with
`benchmarks/escalation/discrimination.py`, seed 0, 2,000 resamples. No new run:
every row was already there, from the runs `aggregate.md` beside them reports.

## Why ask

The published tables give a Brier score per model. Brier mixes calibration
(does 0.9 come true nine times in ten) with discrimination (is confidence
higher on the right answers than on the wrong ones). A model that states 0.95
on everything can be well calibrated at a 95% hit rate and still say nothing
about *which* answers are the wrong ones.

For the Forge that second property is the one that matters. A confidence that
cannot pick out the wrong answer cannot gate an escalation ("ask a person when
unsure"). It also cannot stand in for a fork's measured confidence. Willow's
forge add-on (willow-memory/Willow#374) makes a fork's confidence from the
person's sealed picks alone, never from a model's say-so. This is the
measurement behind that rule.

## What was found

AUROC: the chance that a right answer states more confidence than a wrong one.
0.5 is chance; under 0.5, the model is surer when wrong.

**Hosted models** (Kaggle runs). The intervals are wide because these models
are seldom wrong (4 to 25 wrong answers each):

| run | model | n | wrong | AUROC | 95% CI | conf right | conf wrong |
|---|---|---|---|---|---|---|---|
| day1 | claude-haiku-4-5 | 140 | 25 | 0.659 | [0.56, 0.75] | 0.949 | 0.941 |
| day1 | deepseek-r1-0528 | 141 | 7 | 0.517 | [0.41, 0.68] | 0.982 | 0.963 |
| day1 | gemini-3.7-flash | 197 | 4 | 0.597 | [0.27, 0.94] | 0.977 | 0.963 |
| day1 | gemini-3.8-flash | 194 | 5 | 0.405 | [0.23, 0.71] | 0.975 | 0.962 |
| day1 | gemma-4-26b-a4b | 183 | 6 | 0.590 | [0.40, 0.79] | 0.976 | 0.935 |
| day1 | gpt-5.4-nano | 197 | 25 | 0.453 | [0.35, 0.57] | 0.857 | 0.916 |
| day1 | gpt-oss-20b | 200 | 25 | 0.555 | [0.47, 0.65] | 0.921 | 0.973 |
| day1 | qwen3-235b-a22b | 197 | 17 | 0.610 | [0.50, 0.72] | 0.934 | 0.969 |
| day2 | claude-opus-5 | 400 | 12 | 0.500 | [0.31, 0.69] | 0.937 | 0.857 |
| day2 | claude-sonnet-5 | 400 | 8 | 0.623 | [0.46, 0.78] | 0.916 | 0.892 |
| day2 | gemini-3.1-pro-preview | 196 | 5 | 0.665 | [0.45, 0.88] | 0.986 | 0.964 |
| day2 | gpt-5.5 | 200 | 9 | 0.478 | [0.28, 0.69] | 0.975 | 0.962 |
| rep2+3b | claude-opus-5 | 305 | 10 | 0.605 | [0.40, 0.81] | 0.946 | 0.886 |
| rep2+3b | claude-sonnet-5 | 330 | 12 | 0.515 | [0.40, 0.63] | 0.914 | 0.927 |
| rep2+3b | gemini-3.1-pro-preview | 277 | 5 | 0.558 | [0.45, 0.76] | 0.986 | 0.982 |
| rep2+3b | gpt-5.5 | 320 | 8 | 0.484 | [0.28, 0.71] | 0.975 | 0.965 |

- Of 12 hosted models, only **claude-haiku-4-5** shows discrimination clear of
  chance; **qwen3-235b** sits on its edge. Every other interval contains 0.5.
- **Three state more confidence on their wrong answers than on their right
  ones:** gpt-5.4-nano (0.916 against 0.857), gpt-oss-20b (0.973 against
  0.921) and qwen3-235b (0.969 against 0.934).
- Read with care: with this few wrong answers, "not shown to discriminate" is
  what the rows support, not "shown not to". A larger unanswerable set would
  settle it.

**Local models** (the step2b run, 200 rows each, under ollama):

| model | wrong | AUROC | 95% CI | false-confident | their conf | gate: escalate below t |
|---|---|---|---|---|---|---|
| gemma4:e2b | 67 | 0.777 | [0.71, 0.85] | 38 | 0.872 | < 0.91 catches 61% at 3% |
| llama3.1:8b | 50 | 0.710 | [0.63, 0.79] | 31 | 0.873 | < 0.91 catches 65% at 4% |
| qwen3:4b | 90 | 0.708 | [0.64, 0.77] | 35 | 0.712 | < 0.91 catches 74% at 0% |
| gemma3:4b | 60 | 0.651 | [0.57, 0.73] | 32 | 0.871 | < 0.86 catches 44% at 0% |
| qwen3.5 | 36 | 0.597 | [0.51, 0.70] | 15 | 0.853 | < 0.91 catches 53% at 3% |
| llama3.2:3b | 81 | 0.581 | [0.51, 0.65] | 32 | 0.746 | < 0.81 catches 59% at 10% |
| llama3.2:1b | 160 | 0.525 | [0.43, 0.61] | 35 | 0.951 | < 0.91 catches 9% at 0% |
| phi4-mini | 59 | 0.503 | [0.42, 0.59] | 37 | 0.901 | < 0.86 catches 24% at 0% |

- **Five of eight local models' confidence does tell right from wrong**, and
  for three of them (gemma4:e2b, llama3.1:8b, qwen3:4b) a threshold catches
  61–74% of their false-confident answers while sending 0–4% of their right
  answers to a person.
- llama3.2:1b and phi4-mini state 0.90–0.95 on their false-confident answers
  and know nothing of when they are wrong (0.525, 0.503).

## What it means for the Forge

1. **A frontier model's stated confidence is not a fork's confidence.** On
   these rows it does not pick out the wrong answers. The Forge's rule (Willow
   #374, and `plan_shape`'s confidence as P(the maker picks the
   recommendation), measured by the ledger) stands on this: confidence comes
   from outcomes, not from the model.
2. **A confidence gate is per model, and has to be earned.** Where
   discrimination is real (here, some small local models), "escalate below t"
   is a cheap catch. Where it isn't, the same rule escalates almost nothing.
   A gate should be turned on for a model only once its own rows show an
   AUROC interval clear of 0.5.
3. **Brier alone ranks them the wrong way round.** On day 1, gpt-oss-20b's
   Brier is 0.144 and claude-haiku-4-5's is 0.165 (`kaggle-day1/aggregate.md`).
   By Brier, gpt-oss-20b is the better-calibrated model. Yet its confidence is
   higher on its wrong answers (0.973 against 0.921), while haiku's is the one
   hosted confidence here that does pick out its wrong answers (AUROC 0.66,
   [0.56, 0.75]).

## Not measured

- Whether discrimination holds on other prompts. These are four shapes
  (route, classify, judge, ground) from one benchmark.
- Hosted models at higher temperature, or with verbal rather than numeric
  confidence.
- The gate's threshold is chosen on the same rows it is scored on, so its
  catch rates are optimistic. A held-out split, or a threshold fixed before
  the run, would be the honest version.
