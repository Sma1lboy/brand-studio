# Bundled producers (read-only)

Each `producers/<id>/SKILL.md` is a **read-only, instruction-grade** producer.
It is **not** registered with the agent's Skill tool, so it never pollutes the
user's global skill list. The agent (main or a producer subagent) **reads** the
relevant producer's `SKILL.md` as procedure/context — it does not invoke it as a
callable skill. `scripts/catalog.py` enumerates this directory and parses each
frontmatter into a `capability -> producers` routing registry.

Only bundle producers that are **instruction-grade** (prompt-craft, layout
conventions, copy direction). Do **not** vendor heavy-toolchain producers (e.g.
remotion's npm render pipeline) here — those stay at user/project scope or are
installed on demand into an unregistered private dir. See `../../../CLAUDE.md`.

## Frontmatter contract

```yaml
---
name: gpt-image-prompt          # producer id (defaults to the directory name)
description: One-line summary used during producer selection.
capability: image               # image | video | copy | slide | logo | social
modality: image                 # asset modality produced (defaults to capability)
lane: generator                 # generator | reference (borrow convention only)
---
```

Directories whose name starts with `_` (such as `_template/`) are ignored by the
catalog. Use `_template/SKILL.md` as the starting point for a new producer.
