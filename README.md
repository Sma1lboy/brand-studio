# Marketing Harness

[简体中文](README.zh-CN.md)

Marketing Harness is a brand-locked image-generation pipeline. It keeps brand
style as a single source of truth, lets each project provide only the content for
the current campaign, calls the local GPT Image skill/CLI, and publishes
versioned marketing artifacts for downstream projects to consume.

The harness is designed to be installed once as a global agent skill and then
used from any product repository. The product repository owns its local
`workspace/` inputs, transient `outputs/`, and `published/` asset repository or
submodule.

The core boundary is strict:

```text
brand memory -> brand.lock.yaml -> campaign.yaml -> render -> human asset review -> publish
```

`workspace/portfolios/<portfolio-id>/` stores portfolio-level metadata and
element libraries. `workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml`
is the product brand lock: the stable style tokens plus provider/model/params.
`workspace/products/<portfolio-id>/<brand-id>/campaigns/*.campaign.yaml` is the
content layer. Campaigns may only reference a locked `alias.style`; they must not
inline visual style prompts, palettes, negative prompts, references, or provider
params.

Downstream app code does not run generation. It consumes published assets plus
`manifest.json` from the product repo's asset repository.

## Methodology

This repository follows a Design System / Design Token model. `brand.lock.yaml`
is the brand style single source of truth. Token objects follow the W3C Design
Tokens Format Module convention of `$value` plus `$type`, with two layers:

- `global`: raw visual decisions, such as colors, typography, style fragments,
  negative prompts, and reference assets.
- `alias`: semantic tokens that compose and reference `global`, such as
  `alias.style.launch-hero`.

Reference: https://www.designtokens.org/tr/drafts/format/

Governance is intentionally light: change tokens, bump `version`, run regression,
review manually, and publish only after approval.

Versions are namespaced. A `brand.lock.yaml` version is not global; it belongs to
a portfolio/product pair. A generation is identified by:

```text
portfolio.id + portfolio.version + brand.id + brand.lock version + campaign + run
```

Responsibilities are separate:

- `portfolio.version`: portfolio metadata and element-system version.
- `brand.lock version`: product brand style/provider/model/params version.
- `campaign`: one concrete marketing content brief, not a version.
- `run`: one render execution recorded in `run.lock.json`.
- `accepted.revision`: curated accepted-work corpus revision, used as proposal
  input only. It does not implicitly change render behavior.

## Quick Start

When developing this harness repo directly:

```bash
uv sync
cp .env.example .env
uv run harness validate examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
uv run harness render examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml \
  --dry-run
```

The standard entrypoint is `uv run harness`. If a machine temporarily lacks `uv`
but the repository already has `.venv/bin/harness`, the `.venv/bin/harness ...`
fallback can run the same commands. Long term, keep `uv` installed on `PATH`.

`--dry-run` does not call an image API. It writes SVG placeholders,
`run.lock.json`, and `manifest.json`.

When using the globally installed skill from another product repo, keep the
current directory in that product repo and run harness through the skill project:

```bash
SKILL_ROOT="$HOME/.codex/skills/marketing-harness"  # or $CLAUDE_SKILL_DIR
sh "$SKILL_ROOT/scripts/bootstrap_project.sh" .
uv --project "$SKILL_ROOT" run harness validate workspace/products/<portfolio-id>/<brand-id>/campaigns/<name>.campaign.yaml \
  --brand workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml
uv --project "$SKILL_ROOT" run harness render workspace/products/<portfolio-id>/<brand-id>/campaigns/<name>.campaign.yaml \
  --brand workspace/products/<portfolio-id>/<brand-id>/brand.lock.yaml \
  --dry-run
```

For live generation, put GPT Image skill/CLI credentials in `.env`:

```bash
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
uv run harness render examples/codefox/workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand examples/codefox/workspace/products/codefox/codefox/brand.lock.yaml
```

## Editing Tokens

Add raw decisions under `global`:

```yaml
global:
  color:
    success-green: { $value: "#20A67A", $type: "color" }
```

Compose semantic styles under `alias`:

```yaml
alias:
  style:
    social-success:
      $type: "composite"
      $value:
        prompt: "{global.style-fragment.base-aesthetic}, optimistic launch composition"
        palette: ["{global.color.success-green}", "{global.color.bg-neutral}"]
        negative: "{global.negative.global-exclude}"
        references: []
```

Campaigns only reference aliases:

```yaml
style: "social-success"
content:
  headline: "Now Available"
  subject: "a clean product announcement visual"
```

## Style Production

A design skill or human designer may produce style, but the output must be
frozen into a reviewed `brand.lock.yaml` proposal. Render never asks a design
skill dynamically.

Recommended flow:

```bash
uv run harness style propose \
  --base workspace/products/codefox/codefox/brand.lock.yaml \
  --brief workspace/products/codefox/codefox/brief.md \
  --source workspace/products/codefox/codefox/references/ \
  --out workspace/products/codefox/codefox/proposals/codefox.lock.yaml \
  --version 1.2.0

uv run harness validate workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/proposals/codefox.lock.yaml

uv run harness regression \
  --brand workspace/products/codefox/codefox/proposals/codefox.lock.yaml \
  --dry-run
```

After human review:

```bash
uv run harness style promote \
  workspace/products/codefox/codefox/proposals/codefox.lock.yaml \
  --to workspace/products/codefox/codefox/brand.lock.yaml
```

## Image Engine

The harness has one live image-generation entrypoint: the local GPT Image
skill/CLI. `provider.gateway` must be `gpt-image-skill` or its alias
`skill-cli`. The provider resolves `provider.params.command`, then
`HARNESS_SKILL_CLI_COMMAND`, then `gpt-image` on `PATH`, then
`~/.codex/skills/gpt-image/scripts/generate.py`.

Minimal config:

```yaml
provider:
  gateway: "gpt-image-skill"
  model: "gpt-image-2"
  params:
    seed_strategy: "fixed"
    seed: 12345
    quality: "high"
    output_format: "png"
    command: "gpt-image"
```

The harness resizes/crops provider output to each campaign deliverable's exact
size so `manifest.json` remains the delivery contract.

Changing model or generation params is a brand-lock change. Bump `version` and
run regression.

## Output Contract

Each render writes to `outputs/<campaign-name>/`:

- `<asset-id>.<ext>`: generated assets for each deliverable.
- `run.lock.json`: full reproducibility archive, including brand lock, campaign,
  resolved prompt, actual seed/params, timestamps, sidecars, and sanitized
  provider metadata.
- `manifest.json`: local render-buffer contract draft. Consumers use the
  published manifest under the product repo's asset repository:
  `published/products/<portfolio-id>/<brand-id>/<brand-version>/artifacts/<campaign>/manifest.json`.

Minimal consumer example:

```python
import json

manifest = json.load(open(
    "published/products/codefox/codefox/1.1.0/artifacts/feature-x-launch/manifest.json",
    encoding="utf-8",
))
hero = next(asset for asset in manifest["assets"] if asset["id"] == "web-banner")
print(hero["url"] or hero["path"])
```

`outputs/` is ignored and is not a consumer entrypoint. After live render, inspect
the images, text quality, dimensions, `manifest.json`, and `run.lock.json`. Only
after human acceptance should you run:

```bash
uv run harness publish <campaign> --channel repo --repo-dir published --publish
```

API-cost approval is not asset approval.

## Workspace And Published Asset Repo

Editable source inputs live in the product repository's `workspace/`:

```text
workspace/portfolios/<portfolio-id>/
├── portfolio.meta.yaml
├── elements.yaml
└── accepted.yaml

workspace/products/<portfolio-id>/<brand-id>/
├── brand.lock.yaml
├── brand.meta.yaml
├── elements.yaml
├── accepted.yaml
├── brief.md
├── campaigns/
├── references/
└── proposals/
```

The product repository's `published/` directory should usually be a separate
asset git repository or submodule. It stores immutable snapshots, including the
portfolio snapshot used for that render:

```text
published/portfolios/<portfolio-id>/<portfolio-version>/
├── portfolio.meta.yaml
├── elements.yaml
└── accepted.yaml

published/products/<portfolio-id>/<brand-id>/<brand-lock-version>/
├── portfolio/
├── metadata/
├── brand/brand.lock.yaml
├── campaigns/
├── references/
└── artifacts/<campaign-name>/
    ├── <asset-id>.<ext>
    ├── manifest.json
    └── run.lock.json
```

The repo channel writes into that asset repo/submodule. It does not run
`git add`, `commit`, or `push`; inspect snapshots, then commit the asset repo and
pin the submodule commit from the product repo if you use submodules.

## Publishing

All publish commands dry-run by default:

```bash
uv run harness publish feature-x-launch --channel cdn
uv run harness publish feature-x-launch --channel release
uv run harness publish feature-x-launch --channel repo --repo-dir published
```

Real publishing requires `--publish`:

```bash
uv run harness publish feature-x-launch --channel release --publish
uv run harness publish feature-x-launch --channel cdn --publish
uv run harness publish feature-x-launch --channel repo --repo-dir published --publish
```

The CDN channel uses S3-compatible object storage. Credentials are read only from
environment variables. The release channel writes
`releases/<campaign>-brand-<version>.zip`. The repo channel writes to
`HARNESS_REPO_PUBLISH_DIR` or `--repo-dir`, defaulting to `published`.

## Regression

Fixed regression prompts live in `tests/regression/prompts.yaml`. When
`brand.lock.yaml` provider/model/params or tokens change:

```bash
uv run harness regression
```

Without an API key, run placeholders first:

```bash
uv run harness regression --dry-run
```

Regression writes comparison images, `run.lock.json`, `manifest.json`, and
`scores.csv`. Humans fill `scores.csv`. If visual quality, brand consistency, or
key prompts regress, do not publish the style change. The harness does not fake
automatic image-quality scoring.

## CI And Release Workflows

The repository includes:

- `CI`: runs `ruff`, `pytest`, example campaign validation, and dry-run render.
  It does not call an image API.
- `Regression`: manual workflow. Dry-run by default; `live` calls the configured
  provider and reads required secrets.
- `Release`: manual workflow. Dry-run by default; `live_render` generates real
  images and `publish` performs the publishing action.

Relevant secrets and variables:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
HARNESS_SKILL_CLI_COMMAND
HARNESS_CDN_BUCKET
HARNESS_CDN_ENDPOINT
HARNESS_CDN_BASE_URL
HARNESS_CDN_ACCESS_KEY_ID
HARNESS_CDN_SECRET_ACCESS_KEY
HARNESS_CDN_PREFIX
HARNESS_CDN_REGION
HARNESS_REPO_PUBLISH_DIR
```

## Agent Skill

This repository is itself the reusable agent skill. It is not an
Anthropic-maintained official skill, but it follows the Claude Agent Skill
layout: the root `SKILL.md` is the entrypoint, with YAML frontmatter
(`name` and `description`) plus adjacent bundled resources.

The harness implementation lives in the same repo-root payload:
`src/`, `examples/`, `references/`, `assets/`, `scripts/`, tests, and
`pyproject.toml`. Real product `workspace/` and `published/` directories belong
to each consuming product repo, not to this central harness repo. There is no
nested `.claude/skills/...` wrapper to install or maintain.

For Claude Code, install the repo-root skill:

```bash
npx skills add CodeFox-Repo/marketing-harness \
  --agent claude-code
```

If a tool asks which skill to install, choose `marketing-harness`. Because the
repo root has `SKILL.md`, the installed skill carries the harness source and
workflow references as one self-contained payload.

For Codex local use, point the global skill entry at the repository root:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD" ~/.codex/skills/marketing-harness
```

That symlink is only a local installation mechanism. It is not a development
wrapper and it should not create a second skill copy inside this repository.

Restart the agent and invoke:

```text
$marketing-harness validate the example campaign
$marketing-harness create a new brand style, prefer local frontend-design
$marketing-harness dry-run render workspace/products/codefox/codefox/campaigns/example.campaign.yaml
```

When invoked from a product repo, the skill should run:

```bash
uv --project "$SKILL_ROOT" run harness ...
```

That keeps harness code global while resolving `workspace/`, `outputs/`, and
`published/` relative to the current product repo.

Design skills may own style production, but only up to a reviewed
`brand.lock.yaml` proposal. They should not directly render or publish.

To package the skill:

```bash
python3 scripts/package_skill.py
```

The zip contains the repo-root skill and the harness source, excluding root
local state and product assets such as `.env`, `.venv/`, `workspace/`,
`outputs/`, `published/`, `releases/`, and `tests/`. `examples/` is still
packaged for `--with-example`. Tests remain in this repository and run in CI;
they are not needed in the installed runtime skill bundle.

## CLI

```bash
harness validate <campaign.yaml>
harness render <campaign.yaml> [--dry-run]
harness publish <campaign-name> [--channel cdn|release|repo] [--repo-dir published] [--publish]
harness style propose --out <proposal.lock.yaml> [--brief <brief.md>] [--source <path>]
harness style promote <proposal.lock.yaml> --to <brand.lock.yaml>
harness regression
```

## Safety

- API keys and object-storage credentials are read from `.env` or environment
  variables only.
- Secrets are never written into config, manifests, or run locks.
- Campaign schema uses `extra=forbid`; campaigns cannot smuggle style fields.
- Project teams consume artifacts and manifests. They do not run generation.
