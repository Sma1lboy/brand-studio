---
name: marketing-harness
description: >-
  Use this repository as a self-contained marketing image-generation harness
  skill for Claude Code or other agents. Trigger when the user wants to create
  brand-locked marketing assets, define or promote brand.lock design tokens,
  validate campaign YAML, run regression, render via the local GPT Image
  skill/CLI entrypoint, publish versioned artifacts, or bootstrap a local
  harness workspace.
---

# Marketing Harness

This repository is the reusable skill payload. Install it globally once, then
run it against the current product repository. The current repository owns
`workspace/`, `outputs/`, and `published/`; the installed skill provides the
Python harness, schemas, the single GPT Image skill adapter, bundled examples,
and workflows.

Preserve the boundary:

```text
brand memory -> brand.lock.yaml -> campaign.yaml -> render -> human asset review -> publish
```

Never put visual style prompt text in campaign files. Campaigns describe content
and deliverables only.

## Resolve Roots

Keep these roots separate:

- **Project root:** the user's current product repo. Relative paths such as
  `workspace/...`, `outputs/...`, and `published/...` resolve here.
- **Skill root:** this installed marketing-harness skill. It contains
  `pyproject.toml`, `src/harness/`, `scripts/`, `references/`, and examples.

If the current working directory itself contains `pyproject.toml` and
`src/harness/`, it is both the skill root and a development project root.
Otherwise use `$CLAUDE_SKILL_DIR` when available, or the installed Codex skill
path such as `~/.codex/skills/marketing-harness`.

Run the initial check from the project root:

```bash
sh "$SKILL_ROOT/scripts/check_harness.sh" .
```

Use `harness_entrypoint` from the check output as the command prefix. In a
consumer repo it is normally:

```bash
uv --project "$SKILL_ROOT" run harness
```

In command examples below, `$HARNESS` means "replace with the
`harness_entrypoint` string from the check output".

This runs harness code from the global skill while reading and writing relative
paths in the current product repo. Do not copy this skill into each product
repo unless the user is intentionally developing the harness itself.

For a fresh product repo, initialize only the local project folders:

```bash
sh "$SKILL_ROOT/scripts/bootstrap_project.sh" .
```

Use `--with-example` only when the user wants the bundled CodeFox example copied
into the product repo.

## Common Defaults

- Brand lock: `workspace/products/codefox/codefox/brand.lock.yaml`
- Example campaign: `workspace/products/codefox/codefox/campaigns/example.campaign.yaml`
- Dry-run first for new flows
- Local review publish channel: `repo`, writing to the project repo's
  `published/` asset repo or submodule
- Do not commit automatically

For exact command sequences, read `references/workflows.md`. For schema
contracts, read `references/contracts.md`.

## Style Production

When a design skill, Claude, Codex, or a human produces style, freeze the result
as a `brand.lock.yaml` proposal before render.

Selection order for design producers:

1. If the user names a local design skill, prefer it.
2. Otherwise prefer an already-installed local brand/frontend/visual design skill.
3. If none exists, stop and ask the user to install/specify one or provide a
   reviewed brief and references.

Do not download, clone, or install a remote design skill as an implicit fallback.

Proposal flow:

```bash
$HARNESS style propose \
  --base workspace/products/codefox/codefox/brand.lock.yaml \
  --brief workspace/products/codefox/codefox/brief.md \
  --source workspace/products/codefox/codefox/references/ \
  --out workspace/products/codefox/codefox/proposals/<name>.lock.yaml

$HARNESS validate workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/proposals/<name>.lock.yaml

$HARNESS regression \
  --brand workspace/products/codefox/codefox/proposals/<name>.lock.yaml \
  --dry-run
```

Only after review:

```bash
$HARNESS style promote \
  workspace/products/codefox/codefox/proposals/<name>.lock.yaml \
  --to workspace/products/codefox/codefox/brand.lock.yaml
```

For external producer contracts, read `references/design-producer-protocol.md`.

## Rendering And Publishing

Before live render, confirm API usage and possible cost. The harness has one
live image entrypoint: the local GPT Image skill/CLI. Its credentials belong in
`.env`; never print, commit, or copy them into configuration files. Ensure the
local `gpt-image` skill/CLI is installed or `HARNESS_SKILL_CLI_COMMAND` points
to an equivalent command.

Live generation:

```bash
$HARNESS validate <campaign.yaml> --brand <brand.lock.yaml>
$HARNESS render <campaign.yaml> --brand <brand.lock.yaml>
```

After live render, inspect generated files, dimensions, text quality,
`manifest.json`, and `run.lock.json`. Show output paths and ask for explicit
human asset acceptance before any command with `--publish`, unless the user
explicitly pre-approved auto-publish.

After acceptance:

```bash
$HARNESS publish <campaign-name> --channel repo --repo-dir published --publish
```

`published/` should usually be a separate asset git repository or submodule
inside the product repo. The repo publish channel stores portfolio snapshots,
product brand snapshots, campaign inputs, references, generated assets,
`manifest.json`, and `run.lock.json` there. It never runs `git add`, `commit`,
or `push`.

Safe smoke test:

```bash
$HARNESS render <campaign.yaml> --brand <brand.lock.yaml> --dry-run
$HARNESS publish <campaign-name> --channel repo --repo-dir published
```

## Verification

After code or workflow changes:

```bash
uv run ruff check .
uv run pytest
uv run harness validate examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
uv run harness render examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml \
  --dry-run
```

Check that no API key, authorization header, machine-specific path, or raw image
base64 payload is stored in tracked files.
