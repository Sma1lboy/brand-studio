# Marketing Harness Skill

[简体中文](README.zh-CN.md)

Marketing Harness is an installable agent skill for producing brand-locked
marketing images. Install the skill once, invoke it from a product repository,
and let the agent validate brand tokens, prepare campaigns, render through the
GPT Image skill/CLI, and publish reviewed assets into that product repository's
asset area.

This repo ships two things:

- `skills/marketing-harness/`: the installable skill payload.
- `src/`: the harness CLI runtime used by the skill launcher.

Most users should think of this as a skill first. The Python project exists so
the skill has a reproducible runtime instead of asking every product repo to
copy generation code.

## What The Skill Does

Marketing Harness keeps style and content separate:

```text
brand memory -> brand.lock.yaml -> campaign.yaml -> render -> human review -> publish
```

The skill helps an agent:

- bootstrap the expected `workspace/` folders in a product repo.
- build or update brand metadata and design-token style locks.
- validate `brand.lock.yaml` and campaign files.
- run dry-run renders without spending API credits.
- call the local GPT Image skill/CLI for live renders.
- require human asset review before publish.
- publish immutable snapshots to `published/` or another asset repo path.

Downstream apps consume `manifest.json` and published image files. They do not
run generation.

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
$marketing-harness publish the accepted campaign to the repo channel
```

The installed skill contains a launcher:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" ...
```

The launcher keeps paths rooted in the current product repo and resolves the
runtime in this order:

1. `HARNESS_PROJECT_DIR`, if you point it at a local checkout.
2. An ancestor checkout of this repo, useful while developing the skill.
3. A `harness` executable already on `PATH`.
4. Remote fallback with `uvx --from git+https://github.com/CodeFox-Repo/marketing-harness harness`.

That means the skill package can stay small while still working in fresh repos.

## Product Repo Shape

The product repo owns the work and outputs:

```text
workspace/
  portfolios/<portfolio-id>/
  products/<portfolio-id>/<brand-id>/
outputs/
published/
```

- `workspace/` is editable source input: brand metadata, style locks,
  campaign YAML, proposals, references, and accepted-work notes.
- `outputs/` is the local render buffer.
- `published/` is the reviewed asset repo path or submodule target.

`outputs/` and `published/` are normally ignored by the product repo unless
`published/` is intentionally managed as a separate asset repository or
submodule.

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

## Human Review

Live render approval and asset approval are different.

The skill should dry-run first, ask before spending API credits, render live
only after approval, then show the generated files for review. `publish
--publish` should run only after the user or reviewer explicitly accepts the
assets, unless they pre-approved automatic publishing.

Regression is also human-scored. The harness can generate comparison images and
`scores.csv`; it does not pretend to auto-grade image quality.

## Skill Contents

```text
skills/marketing-harness/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
│   ├── harness.py
│   ├── bootstrap_project.sh
│   └── check_harness.sh
├── references/
│   ├── contracts.md
│   ├── workflows.md
│   └── design-producer-protocol.md
├── assets/
└── examples/
```

`SKILL.md` is the agent-facing operating guide. This README is the human-facing
overview. Detailed schemas and command flows live in `references/` so the skill
can load only what a task needs.

## Runtime Requirements

For dry-run validation:

- Python 3.11+
- `uv` recommended

For live generation:

- local GPT Image skill/CLI, or an equivalent command via
  `HARNESS_SKILL_CLI_COMMAND`
- `.env` or environment values for image API credentials, usually:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

Secrets are read from environment only. They should not be written into YAML,
manifests, run locks, logs, or published snapshots.

## Maintainer Notes

This repo root is for maintaining the skill and CLI runtime:

```bash
uv sync
uv run ruff check .
uv run pytest
uv run harness validate skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
```

Package only the skill payload:

```bash
python3 scripts/package_skill.py
```

The zip includes `skills/marketing-harness/` contents only. It does not bundle
root `src/`, `tests/`, `outputs/`, or `published/`; runtime comes from a local
checkout, installed CLI, or the launcher's remote `uvx` fallback.
