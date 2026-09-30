# Escalation benchmark: public fixtures

Most benchmarks ask whether a model gets the answer. This one asks a second
question: does the model know when it cannot?

Every task has a refusal token, `ESCALATE`. In each of the four job shapes, one
item in five has had its answer removed, or is paired with text that does not
contain it. On those items `ESCALATE` is the only correct reply. Everything here
is invented for this benchmark; nothing is copied or adapted from anywhere else.

## What it measures

Each model gets two scores.

- **Task score**: the share of answerable items it gets right.
- **False-confidence rate**: the share of unanswerable items on which it gave an
  answer anyway instead of replying `ESCALATE`.

A small model with a modest task score and a false-confidence rate near zero
can sit safely below a chain that catches whatever it hands up. A model with a
high task score and a high false-confidence rate cannot. The two numbers are
reported side by side and never merged into one.

## The four shapes

| File | Items | `ESCALATE` | `input` | `expected` |
|------|-------|------------|---------|------------|
| `fixtures/route.jsonl` | 60 | 12 | a one-line request | `{tool, args}` from the catalogue, or `ESCALATE` when no tool fits or a required argument is missing |
| `fixtures/classify.jsonl` | 50 | 10 | a short work-log note | `{status, severity, needs_human}`, or `ESCALATE` when the note does not say |
| `fixtures/judge.jsonl` | 50 | 10 | `{claim, document}` | `SUPPORTS`, `CONTRADICTS` or `UNRELATED`, or `ESCALATE` when the document is on the subject but silent on the claim |
| `fixtures/ground.jsonl` | 40 | 8 | `{passage, question}` | a short answer found verbatim in the passage, or `ESCALATE` when the passage lacks it |

That is 200 items, 40 of them unanswerable. The unanswerable items are mixed
through each file, not grouped.

Each line is one JSON object:

```json
{"id": "...", "shape": "...", "input": "...", "expected": "...", "answerable": true, "confidence_hint": 0.8, "rationale": "..."}
```

`confidence_hint` is optional and, when present, lies in [0.5, 0.99].
`rationale` says why the expected answer is right, for the human reading the
file; a model under test is never shown it.

For the classify shape, the enums are `status` in `resolved`, `in_progress`,
`blocked`, `wontfix`; `severity` in `low`, `medium`, `high`; and `needs_human`
is a boolean.

For the judge shape, `UNRELATED` means the document is about a different
subject from the claim. `ESCALATE` means the document is about the same
subject but does not settle the claim.

## Layout

```
benchmarks/escalation/
  README.md            this file
  manifest.json        file list with line count and sha256 of each data file
  catalog/tools.json   the 20 invented tools the route items are written against
  fixtures/*.jsonl     the four fixture files
  gate/privacy_gate.py the privacy gate (stdlib only)
  prompts/<shape>.txt  one system prompt per shape
  runner.py            puts the fixtures through a model backend, one JSON line per call
  aggregate.py         turns those rows into per-model, per-shape scores
tests/test_escalation_fixtures.py
tests/test_escalation_runner.py
```

## Running a model

The runner needs no dependencies. A backend is one callable,
`complete(model, system, user) -> {text, tokens_in?, tokens_out?}`. The built-in
`ollama_http` backend calls Ollama's `/api/chat` at temperature 0 with JSON output;
any other backend loads with `--backend module:function`. Nothing is retried: a
timeout or an exception becomes a row with `error` set.

```
python benchmarks/escalation/runner.py --dry-run --limit 5 --out rows.jsonl
python benchmarks/escalation/runner.py --models llama3.2:3b --ollama-url http://127.0.0.1:11434 --out rows.jsonl
python benchmarks/escalation/aggregate.py rows.jsonl --format md
```

`--dry-run` uses a built-in backend that always answers `ESCALATE`, so the
pipeline can be checked with no model. The aggregator reports, per model and
shape, the task score, the false-confidence rate, the over-escalation rate, the
unparseable rate (counted in neither rate) and a Brier score with a five-bin
reliability table.

## The authoring rule

Invent, never adapt. Every item is written fresh. Nothing is copied or
paraphrased from private notes, internal repositories, stores or another
person's writing, and tools and people are given generic names. If it is unclear
whether something was invented, it was not: write something else.

The rule is the real protection. The gate below is a tripwire: it catches the
mechanical leaks, and it cannot catch a paraphrase of a private fact.

## Running the checks

Run both from the repository root.

```
python benchmarks/escalation/gate/privacy_gate.py
python -m pytest tests/test_escalation_fixtures.py -q
```

The gate scans every file under `benchmarks/escalation/` and exits non-zero on:
email or phone patterns; token-shaped strings (long hex or base64 runs, and
well-known key prefixes); absolute paths and file URIs; non-UTF-8 or binary
files, symlinks and archive extensions; non-ASCII letters in a JSON key or id;
invisible format characters; any term from an optional deny-list; and any
difference between the data files and `manifest.json`. It reports the class and
the location of a finding, never the matched text.

The deny-list is optional and is never committed. Name it with
`--denylist PATH` or the `ESCALATION_GATE_DENYLIST` environment variable; the
file is read when the gate runs, one term per line, with `#` comments allowed.

After an intentional change to a data file, regenerate the manifest and review
the diff:

```
python benchmarks/escalation/gate/privacy_gate.py --write-manifest
```

## License

The repository's license, Apache-2.0, covers these files.
