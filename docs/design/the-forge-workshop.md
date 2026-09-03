@markdownai v1.0

# The forge-workshop — where the first question gets asked

> **Prior art, read before code:** `willow-data-vault`'s README rule, *repo is
> blueprint, box is the populated instance that stays home*; the shape doc's
> §8, *what flows back*; `forge-play/forge-jig/docs`; and `demo/the_first_bite.py`
> in this repo, which already walks the sequence below on a playground.

The operator, 2026-09-03: *"forge-workshop. It's the place the first question
really gets asked. What is the first bite? And the template repo, much like
willow-data-vault and, now that I'm thinking about it, it might just be the
same package."*

## What it is

A template repository a maker instantiates. Not a second engine. The first
thing that happens in a fresh workshop is the entry's question, `open_bite`
on a sentence a person typed, against a project store that did not exist a
minute before. Everything after that is the engine running on a real
project: the checkpoint loop, the build loop, the deposit, the pull.

It is the same package. The engine already ships the entry and its CLI, the
demo, the deposit and its tool. A workshop needs a layout and
`pip install forge-play`, and nothing of its own. The moment a workshop
grows code, the question is whether it is engine code (it goes to the Forge)
or template code (it stays, and stays thin). The vault's shape is the same:
the repo carries almost nothing, and that is the point.

## The rule this settles: where the project store lives

Two sentences in the record pull apart the moment a workshop is a repo.
`paths.project_nestor` puts the store under the box's forge home; the shape
doc says the store is *portable, ships with the project*. The vault's rule
and §8 give the same answer from two sides:

- **The live database stays home**, under `paths.project_nestor(<project_id>)`
  on the box, where it is today. It holds content: every draft's text, every
  rationale a maker typed, every rejection's reason.
- **The repo carries the exported bundle**, which is shape: questions,
  commitments, edges, warrants with recipes and digests, rejections, the
  ledger chain. `nestor export` writes it; the store pull reads it. A
  workshop checkout holds `forge/bundle.json` (name open) and never a
  database.

@constraint severity=critical
A workshop repository never contains a Nestor database. It contains the
exported bundle, cut at a ledger head, and the head is recorded beside it.

This is what makes a workshop the export side of the store pull without any
new machinery: the bundle in the repo is what the envelope's
`bounds.bundle_digest` names, and `own_store` is attested by the workshop
itself, because the workshop is the project.

## The first bite, as a sequence

1. **Instantiate.** The template becomes `<owner>/<name>`. The workshop's
   `project_id` is derived from the repo name under `forge/_ids.py`'s charset
   rule, so the store path and the repo name cannot drift apart.
2. **Ask.** `python -m forge.entry "<sentence>" --project <id> --builder <maker>`.
   Nestor first, or refuse; the store is created on this call. The box seam
   returns nothing until the catalog is wired. The scan finds a major or
   asks once.
3. **Decide.** The first `Decision` reaches the checkpoint router under the
   maker's name, is argued or waved through, and is sealed with the maker's
   key or recorded unsealed if they have none yet.
4. **Build.** The plan carries forks; the build loop resolves them; the
   calibration ledger records the engine's prediction and, later, the
   outcome.
5. **Deposit.** The first PR on the workshop repo runs CI, the bot files the
   check runs, the deposit writes them into the workshop's store with the
   PR's `Decision:` trailer as its edges.
6. **Export.** The bundle is cut at the ledger head and committed beside the
   code. That commit is the first thing the pull can read.

Steps 2 to 4 exist and are tested. Step 5 exists on two unpushed branches.
Step 6 is the export half of `tools/store_pull.py`, not yet written. Step 1
is the template itself.

## What the template holds

- `README.md` that opens with the question and nothing else.
- `pyproject.toml` depending on `forge-play` with the fleet's pin shape.
- `forge/bundle.json` (empty at instantiation) and `forge/HEAD` (the ledger
  head it was cut at).
- `.github/workflows/tests.yml`, ported from this repo's, so the deposit has
  runs to read.
- `pull_request_template.md` with a `Decision:` line, so the trailer is
  offered rather than remembered.
- No `.mcp.json` that grants the orchestrator seat. The jig's config is the
  model: Nestor first with the corpus verbs registered, willow second.

## The keyword row

The handoff's sixth item: `forge/keywords.toml` has eleven rows and a
sentence like *"what is the first bite?"* finds none of them. That is by
design; the first bite is not a major, it is the question that produces one.
No row is added for it. The row to argue is whichever major a workshop's
first sentences actually name, and that is measured after the first ten
workshops, not guessed before the first.

## Decisions taken

- forge-workshop is a template repo, and it is the same package.
- The live store stays home; the repo carries the bundle, which is shape.
- The workshop is the export side of the store pull; `own_store` is the
  workshop attesting itself.
- The first bite is the entry's question; no keyword row for it.

## Open

- The bundle's path and name in the template.
- Whether `project_id` is derived from the repo name or declared in the
  template's config; derivation keeps the two from drifting, declaration
  survives a rename.
- What the template's README says after the question. Less is right.

@prompt
When building the template: put nothing in it that the engine could ship
instead. If a file in the template has logic, it is in the wrong repo.
