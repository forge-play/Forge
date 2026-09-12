# Contributing to the Forge

## Receipts, not claims

Run the suite before pushing, and quote the command and its result in the
pull request:

```sh
python -m pytest tests/ -q
```

That is the exact command `.github/workflows/tests.yml` runs on every pull
request, after `pip install -e ".[test]"`, on Python 3.11 and 3.13 (3.12 as
well on `master`). A second leg installs nothing but `pytest` and `pyyaml` and
runs the same command, so a change must not make the base install need
anything: the engine's soft dependencies (Nestor, fsrs) skip honestly when
absent, and a test that needs one is marked so.

Quote the counts the way the workflow prints them (`N passed, M skipped`),
before and after, when the change adds or removes tests.

## Commit and pull-request titles

Conventional commits, one type per commit. `docs:`, `test:`, `ci:` and
`chore:` are hidden from the changelog and cut no release; every other type
releases on its own the moment it merges — see `release-please-config.json`,
`$comment-what-cuts-a-release` and `$comment-hidden-rule` for why the line is
where it is. Pull-request titles are held to the same rule by
`.github/workflows/pr-title.yml`, because this repo merges with merge
commits, the merge commit carries the title, and release-please reads it.

## The fleet's conventions

`tests/test_fleet_conventions.py` holds this tree to the fleet's published
convention set (willow-reconciler's `reconciler conventions --json`, saved
verbatim as `tests/fleet_conventions.json` and pinned by hash). If it fails,
read the document's `sources` — each rule names the release it was learned
from — before changing either the tree or the test.
