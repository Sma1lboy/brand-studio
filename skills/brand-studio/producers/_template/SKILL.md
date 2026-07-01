---
name: _template
description: Copy this directory to producers/<id>/ and fill in the contract.
capability: image
modality: image
lane: generator
---

# Producer template

This is a read-only producer template. The catalog skips any directory whose
name starts with `_`, so this entry never appears in the routing registry.

Document, for the reading agent:

- **Inputs it expects** — the structured brand weight (palette, typography,
  references, avoid, accepted samples) plus the deliverable spec. Resolve
  `producer-context.json` `weight_profile` through metadata `weightProfiles`;
  use `history`/`request`/`org`/`copy`/`producer` as soft priority hints while
  treating resolved `theme.md` style facts as hard constraints.
- **What it produces** — the optimal prompt / composition for its `modality`.
  For `lane: generator`, the configured `backend` renders the pixels; this
  producer yields prompt-craft, not the final asset. For `lane: reference`,
  borrow its UI convention only — not its technique — unless the user asks.
- **Constraints** — sizes, aspect ratios, formats it is good for.

Keep it instruction-grade. Do not embed a heavy toolchain here.
