@markdownai v1.0

# The session entry — moved

This paper moved to willows-grove, where the session flowchart lives:
**`willow-memory/willows-grove` `docs/design/forge-convergence.md`**
(branch `docs/forge-convergence`).

Operator, 2026-09-23: "lets land the paper in the grove."

The move also changed the paper. This version put the session's door at the
MCP verb (`session_enter` / `session_handoff_write`). The grove version puts
it at the hook, because the grove's sealed hook rows (`session_start →
orient`, `session_end → deposit`) always fire, and a verb only fires when a
model remembers to call it. The earlier text is in this file's history on
this branch.

## What stays the Forge's

Two pieces of that paper are Forge work, and it tracks them here:

- **`forge.tiers`**: one state vocabulary and a frozen `Tier(name, state,
  detail)`, which the grove's orient, willow-mcp's orientation and
  `forge.entry` all report in. `Entry.tiers` keeps its `dict[str, str]` and
  gains a structured twin.
- **`.forge/project`**: a checkout declaring its own project id, so the id
  survives a rename, an org transfer and a move. The grove paper's Open row 1
  is still in discussion.

The Forge's bite refusal without Nestor is unchanged. Session entry is a
different door with a different rule. The Forge never imports willow-mcp or
Grove.
