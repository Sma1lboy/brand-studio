# Marketing Harness Skill

[简体中文](README.zh-CN.md)

Marketing Harness is an installable agent skill for producing theme-locked
marketing assets from a product repository. It validates repo visual tokens,
prepares campaigns, exports producer-ready dry-run context, and records only
user-accepted assets into repo-owned visual asset state.

This repo ships one installable skill payload plus maintainer tooling:

- `skills/marketing-harness/`: the installable skill payload.
- `scripts/package_skill.py`: packages only the skill payload.

The runtime used by agents is bundled under `skills/marketing-harness/scripts/`.
There is no top-level `src/` package in the skill shape.

## Recommended Sharing Model

For real personal or team use, fork this repository and clone or install from
your own fork. Treat `CodeFox-Repo/marketing-harness` as the generic upstream;
treat `your-user/marketing-harness` or `your-org/marketing-harness` as the
shared source of truth for your metadata, policy, producer preferences,
templates, and install notes.

Product repos should pin that fork through a submodule, tag, or local install.
Keep product-specific `theme.md`, campaigns, accepted state, and public assets
inside the product repo or its asset repo. Keep cross-person or cross-repo
defaults in the fork so teammates can pull the same skill behavior.

## What The Skill Does

Marketing Harness keeps style, campaign content, production, and accepted state
separate:

```text
repo visual state -> production plan -> candidates -> user acceptance -> accepted state -> next production
```

The skill helps an agent:

- read a YAML/JSON metadata file that declares repo paths and policy.
- read organization, repo, related-repo, and directory asset state before planning.
- validate `theme.md` frontmatter and campaign files.
- run dry-run renders without spending API credits.
- hand dry-run context to user-selected producer skills for live assets.
- require human asset review before state updates.
- copy accepted files into approved assets and update `accepted.yaml`.

Downstream apps consume accepted files and manifests. They do not run
generation, and scratch candidates are not visual memory.

## Use

Open a product repo, then mention the skill in the task:

```text
$marketing-harness bootstrap this repo for a new product visual system
$marketing-harness validate the CodeFox example campaign
$marketing-harness create a campaign for a launch poster, dry-run first
$marketing-harness render this campaign with the current theme, then wait for review
$marketing-harness record the accepted launch banner into visual asset state
```

The installed skill contains a launcher:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" ...
```

The launcher keeps paths rooted in the current product repo and runs the bundled
scripts in the installed skill. It does not call `uvx` or discover a parent
runtime checkout.

## Repo Shape

The product repo owns its asset hierarchy. Paths should come from metadata, not
a hard-coded root layout. One common shape is:

```text
assets/marketing/
  theme.md
  campaigns/
  references/
  proposals/
  plans/
  asset-state.yaml
  accepted.yaml
public/marketing/
  <channel-or-format>/
    asset-state.yaml
  <approved assets and manifests>
.harness/marketing/out/
```

- `project.marketingRoot` is editable source input: theme notes, campaign YAML,
  proposals, references, and accepted-work notes.
- `artifacts.scratch` is the local render buffer.
- `artifacts.approved` is the reviewed asset path, asset repo, or submodule target.
- `state.assetIndex` is the repo-level visual asset memory.
- `state.accepted` is the durable accepted corpus used by future planning.
- `state.directoryStateFile` is the per-directory memory filename, usually
  `asset-state.yaml`.
- `sources.relatedRepos` points at same-org repos whose accepted state should
  inform this repo's production.

Before producing banners, landscape visuals, slide/PPT backgrounds, logo-theme
variants, X/XHS cards, or social images, run the read-only state preflight and
use that output in the production plan:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
```

## Theme Contract

`theme.md` is the single source of truth for a repo's visual direction. YAML
frontmatter stores machine-readable style tokens and producer hints; the
Markdown body explains the design direction for humans and agents.

Campaign files can only choose a locked style alias and provide current content:
headline, subject, and deliverable sizes. They must not inline prompts,
palettes, negative prompts, reference images, model names, or producer params.

## Producer Capabilities

Third-party producer skills are managed as metadata-resolved local capabilities,
not dependencies bundled by Marketing Harness. Org rules metadata can define
allowlisted `skillRegistry` entries with declarative install hints; product
metadata maps local keys under `skills`; campaigns request keys under
`requires.skills`. In production, mount the org rules repo as a product repo
submodule such as `vendor/marketing-rules` and point `sources.skillRegistries`
at `vendor/marketing-rules/skills.yaml`. The agent must not auto-install,
silently switch producers, or fetch remote rules during generation. Use the
read-only resolver before live generation:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml skills
```

## Human Review

Live generation approval and asset approval are different. The skill should
dry-run first, ask before spending API credits, pass the exported context to the
selected producer only after approval, then show generated files for review.
Accepted state should change only after the user or reviewer explicitly accepts
exact files or asset ids.

## Verification

```bash
uv run ruff check .
uv run pytest
cd skills/marketing-harness/examples/codefox
python3 ../../scripts/harness.py --metadata marketing.harness.yaml validate
```

Only the installable skill payload is packaged by default; examples, tests,
root maintainer files, and scratch outputs are excluded.
