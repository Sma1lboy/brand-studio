# Marketing Harness Workflows

Run commands from the product repository root. The product repo owns
`workspace/`, `outputs/`, and `published/`; the installed skill owns the harness
implementation.

Use the `harness_entrypoint` reported by `scripts/check_harness.sh` as the
command prefix. In this harness repo it is usually `uv run harness`. In a
consumer repo it is usually `uv --project <skill-root> run harness`. Replace
`uv run harness` in the examples below with the reported prefix when needed.

## Setup

Consumer repo:

```bash
sh "$SKILL_ROOT/scripts/bootstrap_project.sh" .
cp "$SKILL_ROOT/.env.example" .env
```

Harness development repo:

```bash
uv sync
cp .env.example .env
```

Edit `.env` locally for the GPT Image skill/CLI:

```env
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
HARNESS_REPO_PUBLISH_DIR=published  # usually an asset git repo or submodule
```

`.env` is ignored by git. Never paste key values into committed files.

## Validate Existing Campaign

```bash
uv run harness validate workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/brand.lock.yaml
```

## Dry-Run Render

```bash
uv run harness render workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/brand.lock.yaml \
  --dry-run
```

Expected output:

```text
outputs/feature-x-launch/
├── *.svg
├── manifest.json
└── run.lock.json
```

## Live Render With GPT Image Skill CLI

Confirm with the user before running because this calls the configured image API
through the GPT Image skill/CLI and can incur cost. `brand.lock.yaml` must set
`provider.gateway` to `gpt-image-skill` or its alias `skill-cli`. The provider
calls the local `gpt-image` CLI or the installed Codex skill launcher, then
resizes the output to each deliverable's exact size.

```bash
command -v gpt-image || true
test -f ~/.codex/skills/gpt-image/scripts/generate.py && echo "gpt-image skill installed"

uv run harness render workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/brand.lock.yaml
```

Expected output:

```text
outputs/feature-x-launch/
├── *.png
├── manifest.json
└── run.lock.json
```

This is only the local render buffer. Do not publish it yet unless the user
explicitly pre-approved auto-publish after render. Inspect the assets and ask
for human acceptance before any `--publish` command.

## Publish To Repo

Only enter this step after the user accepts the rendered assets, or when the
user explicitly asked to auto-publish after render. API-cost approval is not
asset approval.

Dry-run:

```bash
uv run harness publish feature-x-launch --channel repo --repo-dir published
```

Write versioned artifacts:

```bash
uv run harness publish feature-x-launch --channel repo --repo-dir published --publish
```

Expected output:

```text
published/portfolios/<portfolio-id>/<portfolio-version>/
├── portfolio.meta.yaml
├── elements.yaml
└── accepted.yaml

published/products/<portfolio-id>/<brand-id>/<brand-lock-version>/
├── portfolio/
├── metadata/
├── brand/brand.lock.yaml
├── campaigns/feature-x-launch.campaign.yaml
├── references/
└── artifacts/feature-x-launch/
    ├── *.png
    ├── manifest.json
    └── run.lock.json
```

`published/` is normally a separate asset repository or git submodule inside the
product repo. Portfolio snapshots are stored there too. The harness does not run
`git add`, `commit`, or `push`; commit the asset repo/submodule after reviewing
the snapshot.

## Produce Style Proposal

Use this when a design skill, Claude, or Codex is responsible for style production.

Design skill routing is intentionally fuzzy:

- If the user writes a hint after an explicit skill mention such as `$marketing-harness`, honor it first, for example "use local frontend-design" or "prefer claude-design".
- If the user does not name one, use an already-installed local design skill that fits brand/frontend/visual design.
- If none is available, stop. Do not install, clone, or download a fallback unless the user explicitly asks.
- The built-in local harness producer is only a deterministic scaffold; do not treat it as a replacement for creative style production from scratch unless the user explicitly accepts that tradeoff.

```bash
uv run harness style propose \
  --base workspace/products/codefox/codefox/brand.lock.yaml \
  --brief workspace/products/codefox/codefox/brief.md \
  --source workspace/products/codefox/codefox/references/ \
  --out workspace/products/codefox/codefox/proposals/<brand-name>.lock.yaml \
  --version <next-version>
```

Then validate:

```bash
uv run harness validate workspace/products/codefox/codefox/campaigns/example.campaign.yaml \
  --brand workspace/products/codefox/codefox/proposals/<brand-name>.lock.yaml
```

Run regression before promotion:

```bash
uv run harness regression \
  --brand workspace/products/codefox/codefox/proposals/<brand-name>.lock.yaml \
  --dry-run
```

Promote only after user review:

```bash
uv run harness style promote \
  workspace/products/codefox/codefox/proposals/<brand-name>.lock.yaml \
  --to workspace/products/codefox/<brand-name>/brand.lock.yaml
```

## External Design Producer

Use `--producer command` when an external design skill or script will generate the complete brand lock proposal:

```bash
uv run harness style propose \
  --producer command \
  --producer-command "./scripts/design-skill-producer" \
  --base workspace/products/codefox/codefox/brand.lock.yaml \
  --brief workspace/products/codefox/codefox/brief.md \
  --source workspace/products/codefox/codefox/references/ \
  --out workspace/products/codefox/codefox/proposals/<brand-name>.lock.yaml \
  --version <next-version>
```

The command contract is documented in `references/design-producer-protocol.md`.

## Regression Review

Regression does not auto-score image quality.

```bash
uv run harness regression --brand workspace/products/codefox/codefox/brand.lock.yaml
```

Fill in the generated `scores.csv` manually. If quality drops, do not promote or publish the style change.
