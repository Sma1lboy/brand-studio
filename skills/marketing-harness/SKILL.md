---
name: marketing-harness
description: >-
  Use this skill to operate the marketing-harness CLI from a product repo:
  bootstrap workspace folders, validate brand.lock/campaign YAML, propose or
  promote brand design tokens, run regression, render through the GPT Image
  skill/CLI provider, and publish versioned marketing artifacts.
---

# Marketing Harness

This folder is the reusable skill payload. Install it globally once, then run it
from the current product repository. The product repository owns `workspace/`,
`outputs/`, and `published/`; this skill provides workflow instructions,
bootstrap scripts, examples, and a launcher for the `harness` CLI.

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
- **Skill root:** this installed `skills/marketing-harness` folder. It contains
  `SKILL.md`, `scripts/`, `references/`, `assets/`, and `examples/`.
- **Harness project root:** an optional local checkout of this repository. It
  contains `pyproject.toml`, `src/harness/`, and tests.

Resolve the skill root from `$CLAUDE_SKILL_DIR` when available, otherwise from
the installed Codex skill path such as `~/.codex/skills/marketing-harness`.

The launcher is:

```bash
python3 "$SKILL_ROOT/scripts/harness.py"
```

It resolves the actual CLI in this order:

1. `HARNESS_PROJECT_DIR`: local checkout, run as `uv --project <dir> run harness`.
2. Ancestor repository of this skill folder, for development checkouts.
3. `harness` already installed on `PATH`.
4. Remote fallback: `uvx --from git+https://github.com/CodeFox-Repo/marketing-harness harness`.

Run the initial check from the project root:

```bash
sh "$SKILL_ROOT/scripts/check_harness.sh" .
```

In command examples below, `$HARNESS` means the launcher command above. It runs
while keeping relative paths rooted in the current product repo.

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
The harness CLI itself may use its `uvx` remote fallback when no local harness
checkout or installed CLI exists.

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
python3 skills/marketing-harness/scripts/harness.py validate \
  skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
python3 skills/marketing-harness/scripts/harness.py render \
  skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml \
  --dry-run
```

Check that no API key, authorization header, machine-specific path, or raw image
base64 payload is stored in tracked files.
