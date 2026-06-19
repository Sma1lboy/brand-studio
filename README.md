# Marketing Harness Skill

[简体中文](README.zh-CN.md)

Marketing Harness is an installable agent skill for producing brand-locked
marketing images. Install the skill once, invoke it from a product repository,
and let the agent validate brand tokens, prepare campaigns, render through a
local image skill/CLI, and record only user-accepted assets into that product
repository's brand state.

This repo ships one installable skill payload plus maintainer tooling:

- `skills/marketing-harness/`: the installable skill payload.
- `scripts/package_skill.py`: packages only the skill payload.

The runtime used by agents is bundled under `skills/marketing-harness/scripts/`.
There is no top-level `src/` package in the skill shape.

## What The Skill Does

Marketing Harness keeps style and content separate:

```text
brand state -> production plan -> candidates -> user acceptance -> accepted state -> next production
```

The skill helps an agent:

- read a small YAML/JSON metadata file that declares product paths and policy.
- read organization, portfolio, repo, related-repo, and directory asset state
  before planning.
- build or update brand metadata and design-token style locks.
- validate `brand.lock.yaml` and campaign files.
- run dry-run renders without spending API credits.
- call a local image skill/CLI for live renders.
- require human asset review before state updates.
- copy accepted files into approved assets and update `accepted.yaml`.

Downstream apps consume accepted files and manifests. They do not run
generation, and scratch candidates are not brand memory.

## Install

For Claude Code:

```bash
npx skills add CodeFox-Repo/marketing-harness \
  --skill marketing-harness \
  --agent claude-code
```

For local Codex development, point Codex at the skill folder:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/marketing-harness" ~/.codex/skills/marketing-harness
```

Restart the agent after installation.

## Use

Open a product repo, then mention the skill in the task:

```text
$marketing-harness bootstrap this repo for a new product brand
$marketing-harness validate the CodeFox example campaign
$marketing-harness create a campaign for a Claude flag poster, dry-run first
$marketing-harness render this campaign with the current brand lock, then wait for review
$marketing-harness record the accepted launch banner into brand state
```

The installed skill contains a launcher:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" ...
```

The launcher keeps paths rooted in the current product repo and runs the bundled
scripts in the installed skill. It does not call `uvx` or discover a parent
runtime checkout.

## Product Repo Shape

The product repo owns the work and outputs. Paths should come from metadata,
not a hard-coded root layout. One common shape is:

```text
packages/branding/
  marketing/
    brand.lock.yaml
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
  .harness/out/
```

- `project.marketingRoot` is editable source input: brand metadata, style
  locks, campaign YAML, proposals, references, and accepted-work notes.
- `artifacts.scratch` is the local render buffer.
- `artifacts.approved` is the reviewed asset path, asset repo, or submodule
  target.
- `state.assetIndex` is the repo-level visual asset memory.
- `state.accepted` is the durable accepted corpus used by future planning.
- `state.directoryStateFile` is the per-directory memory filename, usually
  `asset-state.yaml`.
- `sources.relatedRepos` points at same-org or same-portfolio repos whose
  accepted state should inform this repo's production.

Raw scratch outputs are not valuable by default. Promote only human-approved
final assets into the approved path and accepted state.

Before producing banners, landscape visuals, slide/PPT backgrounds,
logo-theme variants, X/XHS cards, or social images, the agent should run the
read-only state preflight and use that output in the production plan:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
```

## Brand Lock Contract

`brand.lock.yaml` is the single source of truth for a product brand's visual
style. Its tokens follow the W3C Design Tokens Format Module convention:
`$value` plus `$type`.

Reference: https://www.designtokens.org/tr/drafts/format/

The lock has two token layers:

- `global`: raw decisions such as colors, typography, style fragments, negative
  prompts, and reference assets.
- `alias`: semantic style recipes that reference `global`, such as
  `alias.style.launch-hero`.

Campaign files can only choose a locked style alias and provide current content:
headline, subject, and deliverable sizes. They must not inline prompts,
palettes, negative prompts, reference images, model names, or provider params.
`provider.model` in `brand.lock.yaml` is optional; when omitted, the underlying
image CLI chooses its default.

## Human Review

Live render approval and asset approval are different.

The skill should dry-run first, ask before spending API credits, render live
only after approval, then show the generated files for review. Accepted state
should change only after the user or reviewer explicitly accepts exact files or
asset ids.

Use dry-run renders for review before changing an official brand lock or
recording live assets. The harness does not pretend to auto-grade image
quality, and it does not offer a user-facing command to manually add assets.

## Skill Contents

```text
skills/marketing-harness/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── harness.py
│   ├── cli.py
│   ├── harness_runtime/
│   ├── bootstrap_project.sh
│   └── check_harness.sh
├── references/
│   ├── contracts.md
│   └── workflows.md
├── assets/
```

`SKILL.md` is the agent-facing operating guide. This README is the human-facing
overview. Detailed schemas and lifecycle guidance live in `references/` so the
skill can load only what a task needs.

The development checkout may also contain `examples/`, but examples are not
included in the default packaged skill artifact.

## Runtime Requirements

For dry-run validation:

- Python 3.9+
- `uv` recommended

For live generation:

- local image skill/CLI, or an equivalent command via
  `HARNESS_SKILL_CLI_COMMAND`
- environment values for the chosen image provider, for example:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

Secrets are read from environment only. They should not be written into YAML,
manifests, run locks, logs, or accepted snapshots.

## Maintainer Notes

This repo root is for maintaining the skill:

```bash
uv sync
uv run ruff check .
uv run pytest
python3 skills/marketing-harness/scripts/harness.py validate \
  skills/marketing-harness/examples/codefox/packages/branding/marketing/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/packages/branding/marketing/brand.lock.yaml
```

Package only the skill payload:

```bash
python3 scripts/package_skill.py
```

The zip includes `skills/marketing-harness/` contents only. It does not bundle
root `tests/`, `examples/`, `outputs/`, or `published/`. Use
`--include-examples` only for maintainer/debug packages.

Packaging enforces the skill payload shape: top-level `scripts/`, `references/`,
`assets/`, and `agents/` are allowed; top-level `src/` or `tests/` inside the
skill payload are rejected.
