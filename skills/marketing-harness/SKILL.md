---
name: marketing-harness
description: >-
  Use this skill to operate thin marketing-harness scripts from a product repo:
  read YAML/JSON metadata, plan brand-locked campaigns, validate brand.lock and
  campaign YAML, render candidates through a local image skill/CLI provider,
  and record only user-accepted assets into repo-owned brand state.
---

# Marketing Harness

This folder is the reusable skill payload. It should stay thin: `SKILL.md`,
small scripts, references, and templates. The runtime lives under `scripts/`;
do not add a top-level `src/` package or tests inside an installed skill
payload. A valid skill payload may have `scripts/`, `references/`, `assets/`,
and `agents/`.

Preserve the boundary:

```text
brand state -> production plan -> generated candidates -> user acceptance -> accepted state -> next production
```

Never put visual style prompt text in campaign files. Campaigns describe content
and deliverables only.

Do not model asset collection as a user-facing command surface. Assets enter
the durable corpus only when a user accepts generated candidates or explicitly
marks existing work as accepted during review. Treat low-level scripts as
internal agent helpers, not as instructions for users to add assets manually.

## Metadata First

This skill is for AI agents. Do not rely on hard-coded product paths. Start by
finding or creating a small metadata file in the product repo, then pass it to
the adapter scripts.

Template:

```yaml
project:
  id: my-product
  root: .
  marketingRoot: packages/branding/marketing

organization:
  id: my-org
  name: My Org

portfolio:
  id: my-portfolio
  name: My Portfolio
  version: 1.0.0

brand:
  lock: packages/branding/marketing/brand.lock.yaml
  campaigns: packages/branding/marketing/campaigns
  references: packages/branding/marketing/references

campaign:
  name: launch
  path: packages/branding/marketing/campaigns/launch.campaign.yaml

artifacts:
  scratch: packages/branding/.harness/out
  approved: packages/branding/public/marketing

state:
  plans: packages/branding/marketing/plans
  assetIndex: packages/branding/marketing/asset-state.yaml
  accepted: packages/branding/marketing/accepted.yaml
  directoryStateFile: asset-state.yaml

sources:
  assetRoots:
    - packages/branding/marketing
    - packages/branding/public/marketing
  relatedRepos: []

policy:
  requireHumanApprovalBeforeRender: true
  requireHumanApprovalBeforeStateUpdate: true
  allowRootWorkspaceBootstrap: false
```

`assets/marketing-harness-template.yaml` contains a copyable starter. If the
repo already has its own marketing/branding layout, match it instead of moving
files to a generic root-level directory.

## Resolve Roots

Keep these roots separate:

- **Project root:** the user's current product repo.
- **Marketing root:** the product-owned source location from metadata, such as
  `packages/branding/marketing`.
- **Organization and portfolio state:** shared parent-brand context declared in
  metadata, plus any local state files under declared asset roots.
- **Scratch output:** the product-owned temporary render location from metadata,
  such as `packages/branding/.harness/out`.
- **Approved assets:** the product-owned location for user-accepted generated
  files.
- **Accepted state:** the product-owned accepted corpus, usually
  `packages/branding/marketing/accepted.yaml`.
- **Directory state:** `state.directoryStateFile`, usually `asset-state.yaml`,
  found under declared asset roots and read before production.
- **Related repo state:** local sibling repo metadata/state declared under
  `sources.relatedRepos`.
- **Skill root:** this installed `skills/marketing-harness` folder.

Do not create root-level `workspace/`, `outputs/`, `published/`, or `releases/`
by default. Use metadata paths.

The launcher is:

```bash
python3 "$SKILL_ROOT/scripts/harness.py"
```

It runs the bundled scripts in this skill. There is no `uvx` remote runtime
fallback and no ancestor checkout discovery.

Use `scripts/check_harness.sh` and `scripts/bootstrap_project.sh` only as
internal setup helpers. Bootstrap is create-only, dry-run by default, and must
show the user the planned directories before any write.

## Common Defaults

- Always dry-run before live render.
- Do not commit automatically.
- Do not call image APIs until the user has approved the cost/action.
- Do not update accepted state until the user has accepted specific generated
  candidates.

For the lifecycle, read `references/workflows.md`. For schema contracts, read
`references/contracts.md`.

## Style Production

When a design skill, Claude, Codex, or a human produces style, freeze the result
as a reviewed `brand.lock.yaml` proposal before render. Style production is not
a harness command; use the most relevant local design skill or a human-provided
brief and references, then write or update a proposal file under the
metadata-declared marketing root.

Selection order for design producers:

1. If the user names a local design skill, prefer it.
2. Otherwise prefer an already-installed local brand/frontend/visual design skill.
3. If none exists, stop and ask the user to install/specify one or provide a
   reviewed brief and references.

Do not download, clone, or install a remote design skill as an implicit fallback.
Proposal review flow:

1. Write the proposal under the metadata-declared marketing root.
2. Validate it with the bundled helper.
3. Dry-render against a representative campaign.
4. Ask the user to review the proposal and candidates.
5. Only after review, update the official `brand.lock.yaml` path.

## Production Lifecycle

Before live render, confirm API usage and possible cost. The harness has one
live image entrypoint: a local image skill/CLI. Its credentials belong in the
environment; never print, commit, or copy them into configuration files. Ensure
the local `gpt-image` CLI is installed or `HARNESS_SKILL_CLI_COMMAND` points to
an equivalent command. `provider.model` is optional; when omitted, this skill
does not pass `--model` and lets the image provider choose its default.

Use this loop:

1. Run the read-only state preflight and read current org, portfolio, product,
   directory, accepted corpus, reference, and related-repo state declared by
   metadata.
2. Write or update a production plan under `state.plans`.
3. Validate the plan inputs and run a dry render.
4. Ask the user to approve live generation cost.
5. Generate candidates into `artifacts.scratch`.
6. Show candidate paths, manifest, run lock, and review notes.
7. Ask the user which exact candidates are accepted.
8. Copy accepted files into `artifacts.approved` and update `state.accepted`.
9. Use the updated accepted state as input for the next production cycle.

The approved asset directory should come from metadata. It may be a public
package directory, a separate asset git repository, or a submodule. The skill
never edits `.gitattributes` and never runs `git add`, `commit`, or `push`.

Internal preflight helper:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
```

Use this output to ground the production plan. Do not treat it as an asset
intake or promotion command.

## Verification

After code or workflow changes:

```bash
uv run ruff check .
uv run pytest
python3 skills/marketing-harness/scripts/harness.py validate \
  skills/marketing-harness/examples/codefox/packages/branding/marketing/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/packages/branding/marketing/brand.lock.yaml
python3 skills/marketing-harness/scripts/harness.py render \
  skills/marketing-harness/examples/codefox/packages/branding/marketing/campaigns/example.campaign.yaml \
  --brand skills/marketing-harness/examples/codefox/packages/branding/marketing/brand.lock.yaml \
  --dry-run
```

Check that no API key, authorization header, machine-specific path, or raw image
base64 payload is stored in tracked files.
