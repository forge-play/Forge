@markdownai v1.0

# The workshop surface step and project home

> **Prior art, read before code:** `the-forge-workshop.md`, `the-forge-engine.md`,
> `the-forge-shape.md` §3 and §11, `forge/paths.py`, `forge/entry.py`,
> `forge/majors.py`, `forge/keywords.toml`; Jeles `jeles/corpus.py`
> (`ask_corpus`, `search_nuggets`); Almanac `catalog.json` +
> `almanac.config.yml`; awesome-sovereign-software `data/apps.yaml`.

The operator, 2026-09-12: the workshop is the place people create anything;
the git shape stays; the 99% already exists in open tools, living catalogs,
and verified answers; after the first bite a dedicated project home appears
and a deterministic step points at the right surface.

## What this settles

Two additions to the workshop flow, both after a successful first bite:

1. **Project home** — a concrete, maker-visible folder at
   `~/Forge/workshop/<project_id>/`.
2. **Surface step** — a deterministic choice among three existing surfaces
   (Jeles, Almanac, Awesome), followed by a soft pull of relevant candidates.

The workshop template remains a layout. All logic lives in the engine.

## The sequence

```
1. open_bite(sentence, project_id, builder_id, ...)   # existing — Nestor first or refuse
2. if entry succeeded:
     ensure_project_home(project_id)                 # NEW
3. after_bite(entry)                                 # NEW — surface choice + soft pull
4. host presents home path + surface choice + pulled items
5. normal Forge loop continues
```

A refused entry creates neither a home nor a surface choice.

## Hard constraints

@constraint severity=critical
Logic stays in the engine. The template carries documentation only.

@constraint severity=critical
Routing is deterministic. The table is the reasoning; no model in the router.

@constraint severity=high
No reach-back cycles. Soft optional imports only; the three surfaces are
never hard runtime dependencies.

@constraint severity=critical
The live Nestor store stays under `~/.forge`. It is never copied into the
project home or the git checkout.

@constraint severity=high
Honest absence. A missing surface is reported as absent or could-not-run,
never as empty success.

@constraint severity=critical
Nestor remains first. Both new steps run only after a successful entry.

@constraint severity=high
Project home creation is idempotent and happens only after success.

@constraint severity=critical
Authorship is not authority. Pulled items are candidates. Only a human seal
verifies.

## Project home

### Path

Resolved in `forge/paths.py`, the single path resolver:

- Default root: `Path.home() / "Forge" / "workshop"`
- Full path: `workshop_root() / <project_id>`
- Override: `FORGE_WORKSHOP_ROOT` — same spirit as `FORGE_HOME`: tests and
  deliberate moves, not casual convenience.

`project_id` is validated with the existing `_ids` charset rule.

### Behaviour

```python
def ensure_project_home(project_id: str) -> Path:
    """Idempotent. Creates the directory if missing.
    On first creation only, writes starter README.md.
    Refuses on empty/invalid id.
    Never modifies an existing directory's contents.
    """
```

### Starter README (written only on first creation)

```markdown
# <project_id>

This is the working folder for the project.

- Engine state (Nestor store, checkpoints, calibration) lives under `~/.forge`.
- The git repository is wherever you cloned or instantiated the workshop.
- This folder is yours for notes, experiments, pulled candidates, and local work.

Items pulled from Jeles, Almanac, or Awesome Sovereign Software are candidates only.
Only a human seal turns anything into a verified fact inside the project.
```

### What the engine never does here

- Never writes the Nestor database.
- Never writes `.forge/`.
- Never overwrites existing files.
- Never treats this folder as the project store or the git tree.

### Reporting

The path is returned by `ensure_project_home`. Whether it also appears in
`Entry.tiers["home"]` is left open; a host may report it without a tier.

## The three surfaces, as they exist

| Surface | What it is | Machine-readable shape today | Clean pull returns |
|---------|------------|------------------------------|--------------------|
| **Jeles** | Verified corpus of human-checked Q&A with citations and a verification ladder | Pure `jeles.corpus` (ask / search), optional MCP | Nuggets + gaps + verification kind + sources |
| **Almanac** | Self-monitoring catalogs of public data (catalog, not warehouse) | `catalog.json` (entries with id, title, description, topics, source, access, status, observed reachability) + `almanac.config.yml` | Matching catalog entries with reachability |
| **Awesome** | Finished applications that pass the sovereignty test; every entry has an exit plan | `data/apps.yaml` (categories → apps with name, url, license, badges, description, exit) | Matching tools with exit plan |

## Surface routing

### Table: `forge/surfaces.toml`

Same spirit as `keywords.toml`: flat, arguable, every row carries a reason.

```toml
# surfaces.toml — after the first bite, which surface to open first.
# Argue with the rows. Add a row when a real bite went to the wrong place.

[[route]]
id = "software-majors"
majors = ["web", "mobile", "desktop", "cli", "service", "agent", "game"]
surface = "awesome"
query_from = "major"
reason = "software-shaped majors are best served by existing sovereign tools"
priority = 80

[[route]]
id = "client-file-tools"
majors = ["records tool", "metadata tool", "image tool"]
surface = "awesome"
query_from = "major"
reason = "client-only file tools already exist and pass the sovereignty test"
priority = 75

[[route]]
id = "public-data-language"
keywords = ["dataset", "data source", "public data", "catalog", "statistics", "time series", "almanac"]
surface = "almanac"
query_from = "sentence"
reason = "language that points at public data belongs in a living catalog first"
priority = 70

[[route]]
id = "verified-answer-language"
keywords = ["what is", "has been verified", "is it true", "source for", "citation", "has anyone checked"]
surface = "jeles"
query_from = "sentence"
reason = "questions that seek an already-checked answer belong to the verified corpus"
priority = 70

[[route]]
id = "no-signal"
surface = "none"
reason = "no strong surface signal; do not invent a direction"
priority = 0
```

### Router behaviour

```python
def choose(entry: Entry, table: list[Route] | None = None) -> SurfaceChoice:
    # Collect matching routes from majors + keywords.
    # Sort by priority descending, then table order.
    # Highest unique priority wins.
    # If several share the top priority → first in table order (documented).
    # If nothing matches → surface="none".
```

**Conflict rule (settled for v1):** first among the highest-priority matches.
A later version may promote a small checkpoint Decision if real ambiguity
proves costly; the table remains the place to argue.

### SurfaceChoice

```python
@dataclass(frozen=True)
class SurfaceChoice:
    surface: Literal["jeles", "almanac", "awesome", "none"]
    reason: str
    query: str
    signals: tuple[str, ...]
    confidence: float  # derived from priority / match strength
```

## Pull adapters

All three are soft. Import failure or missing data → empty list + honest tier
message. Never raise into the entry path.

### Common return type

```python
@dataclass(frozen=True)
class PulledItem:
    kind: str  # "nugget" | "catalog_entry" | "tool"
    title: str
    summary: str
    url_or_path: str
    provenance: str
    verification: str | None  # Jeles ladder; None for others
    extra: dict  # surface-specific, never required by the engine core
```

### Jeles adapter (first to implement)

- Preferred: pure `jeles.corpus.ask_corpus` / `search_nuggets`.
- Returns human/machine nuggets as primary; institutional/asserted as candidates.
- Soft if `jeles` is not installed.

### Almanac adapter

- Configuration: list of paths or URLs to `catalog.json` files (under
  `~/.forge` or env).
- Simple text match against title, description, topics.
- Returns entries including observed reachability when present.
- Soft if none configured or readable.

### Awesome adapter

- Reads `data/apps.yaml` (or a path configured under `~/.forge`).
- Match against name, category, description.
- Always includes the exit plan when present.
- Soft if the file is absent.

## Integration

### Preferred API shape

Keep `open_bite` pure. Add:

```python
def after_bite(entry: Entry, ...) -> Entry:
    choice = surface_route.choose(entry)
    entry.surface_choice = choice
    entry.tiers["surface"] = ...
    if choice.surface != "none":
        entry.pulled = surface_pull.pull(choice)
    return entry
```

Host / workshop calls:

```python
e = open_bite(...)
if success:
    home = ensure_project_home(e.project_id)
    e = after_bite(e)
```

### Relationship to BoxLookup

`BoxLookup` remains the existing seam for "what does the box already have?"
(ideas item 7). Surface routing sits **after** it. Do not break or overload
the seam in v1. Later convergence is allowed once the three surfaces are
stable.

### Relationship to the rest of the fleet

The three locations stay distinct by design:

- git repo — shape + bundle
- `~/.forge/projects/<id>/…` — engine state
- `~/Forge/workshop/<id>/` — maker workspace

Future store-pull, record-gate, and promotion flows treat the workshop home
as maker workspace only. Any later decision to materialise pulled candidates
on disk targets the project home, as drafts, never sealed by the machine,
never into the live Nestor store.

## Failure modes

| Situation | Behaviour |
|-----------|-----------|
| Entry refused | No home, no surface step |
| Home already exists | No-op |
| No surface signal | `surface=none`, tier says so |
| Surface chosen, adapter missing | `pulled=[]`, tier names the missing piece |
| Adapter present, no matches | `pulled=[]`, tier says "looked, found nothing" |
| Adapter raises | Caught; reported as could-not-query; never clean success |
| Multiple top-priority routes | First in table order (v1 rule) |

## Testing recipe

1. `ensure_project_home` is idempotent and creates the starter README only once.
2. A refused `open_bite` creates no directory.
3. An invalid or empty `project_id` is refused.
4. The router is pure and deterministic for a fixed table + entry.
5. Missing optional surfaces produce empty pulls and honest tiers.
6. No Nestor database or `.forge/` appears under the project home.
7. The workshop template still contains no domain logic.
8. Existing invariants hold: no reach-back to willow-mcp, Nestor-first, zero
   hard runtime deps on the three surfaces.

## Phased delivery

- **Phase 0 — Paper.** This document, plus a draft in the engine's per-project
  Nestor carrying the testing recipe.
- **Phase 1a — Project home.** `paths` extensions, `ensure_project_home`,
  starter README, post-success call only.
- **Phase 1b — Router only.** `surfaces.toml`, `surface_route.py`,
  `SurfaceChoice` recorded on Entry / in tiers. No pulls.
- **Phase 2 — Jeles adapter.** Soft pure-corpus path, attach `pulled`.
- **Phase 3 — Almanac + Awesome adapters.** Config for catalog roots and the
  apps.yaml path.
- **Phase 4 — Template documentation.** README + CLAUDE.md describe the full
  sequence and the project-home path.
- **Phase 5 — Optional calibration of surface choice** (later).
- **Phase 6 — Possible materialisation of candidates into the project home /
  convergence with BoxLookup** (only after the above is stable).

## Decisions taken

- Default workshop root is `~/Forge/workshop`.
- Starter README is written on first creation only.
- Surface choice is deterministic and table-driven.
- Conflict among equal top-priority routes resolves to first in table order (v1).
- Project home, git repo, and `~/.forge` remain three distinct locations.
- Pulled items are candidates only.
- Both new steps run only after a successful first bite.

## Open

Carried as numbered items in `docs/ideas.md` (§M), not here — the pile is
where open items live and are joined to landings.

@prompt
When implementing: keep the three locations distinct, keep the router
model-free, keep adapters soft, and put nothing in the workshop template that
the engine can own.
