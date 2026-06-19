---
name: marketing-harness
description: >-
  Use this skill to operate thin marketing-harness scripts from a product repo:
  read YAML/JSON metadata, plan theme-locked campaigns, validate theme.md and
  campaign YAML, export producer-ready dry-run context, and record only
  user-accepted assets into repo-owned visual state.
---

# Marketing Harness

This folder is the reusable skill payload. It should stay thin: `SKILL.md`,
small scripts, references, and templates. The runtime lives under `scripts/`;
do not add a top-level `src/` package or tests inside an installed skill
payload. A valid skill payload may have `scripts/`, `references/`, `assets/`,
and `agents/`.

Preserve the boundary:

```text
repo visual state -> production plan -> generated candidates -> user acceptance -> accepted state -> next production
```

Never put visual style prompt text in campaign files. Campaigns describe content
and deliverables only.

Do not model asset collection as a user-facing command surface. Assets enter
the durable corpus only when a user accepts generated candidates or explicitly
marks existing work as accepted during review. Treat low-level scripts as
internal agent helpers, not as instructions for users to add assets manually.

## Skill Distribution

For personal or organization use, prefer a fork of the upstream skill repo.
Treat the upstream repo as the generic runtime/template source, and treat the
personal or org fork as the shared source for team metadata, policies, producer
preferences, templates, and install notes.

When working inside a product repo, use the product repo's pinned fork or local
skill install. Do not silently switch to upstream. Product-specific `theme.md`,
campaigns, accepted state, and public assets remain in the product repo or its
asset repo; cross-person defaults belong in the fork.

## Metadata First

This skill is for AI agents. Do not rely on hard-coded product paths. Start by
finding or creating a small metadata file in the product repo, then pass it to
the adapter scripts.

Template:

```yaml
project:
  id: my-product
  root: .
  marketingRoot: assets/marketing

organization:
  id: my-org
  name: My Org

skillDistribution:
  upstream: CodeFox-Repo/marketing-harness
  fork: my-org/marketing-harness
  scope: org
  ref: main

theme:
  path: assets/marketing/theme.md
  campaigns: assets/marketing/campaigns
  references: assets/marketing/references

skills:
  image: image.default
  slide: slide.default

campaign:
  name: launch
  path: assets/marketing/campaigns/launch.campaign.yaml

artifacts:
  scratch: .harness/marketing/out
  approved: public/marketing

state:
  plans: assets/marketing/plans
  assetIndex: assets/marketing/asset-state.yaml
  accepted: assets/marketing/accepted.yaml
  directoryStateFile: asset-state.yaml

sources:
  # Recommended: commit org rules as a product repo submodule.
  skillRegistries:
    - vendor/marketing-rules/skills.yaml
  assetRoots:
    - assets/marketing
    - public/marketing
  relatedRepos: []

policy:
  requireHumanApprovalBeforeRender: true
  requireHumanApprovalBeforeStateUpdate: true
  allowRootWorkspaceBootstrap: false
```

`assets/marketing-harness-template.yaml` contains a copyable starter. If the
repo already has its own marketing/branding layout, match it instead of moving
files to a generic root-level directory.

`assets/skill-registry-template.yaml` is the org rules starter. Keep
`skillRegistry` in an org rules repo mounted into product repos as a submodule,
for example `vendor/marketing-rules/skills.yaml`. Product metadata should bind
local capability keys under `skills`, not redefine org registry ids.

## Resolve Roots

Keep these roots separate:

- **Project root:** the user's current product repo.
- **Marketing root:** the product-owned source location from metadata, such as
  `assets/marketing`.
- **Organization direction:** high-level visual direction from `theme.path`.
- **Repo asset tree:** the repo-owned hierarchy under declared asset roots.
  Treat the repo and its asset directories as the asset namespace.
- **Scratch output:** the product-owned temporary render location from metadata,
  such as `.harness/marketing/out`.
- **Approved assets:** the product-owned location for user-accepted generated
  files.
- **Accepted state:** the product-owned accepted corpus, usually
  `assets/marketing/accepted.yaml`.
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

- Always dry-run before asking any external producer to generate live assets.
- Do not commit automatically.
- Do not call image APIs until the user has approved the cost/action.
- Do not update accepted state until the user has accepted specific generated
  candidates.

For the lifecycle, read `references/workflows.md`. For schema contracts, read
`references/contracts.md`.

## Style Production

When a design skill, Claude, Codex, or a human produces style, freeze the
machine-readable tokens as YAML frontmatter in `theme.md` before render. Style production is not
a harness command; use the most relevant local design skill or a human-provided
brief and references, then write or update a proposal file under the
metadata-declared marketing root.

Selection order for design producers:

1. If the user names a local design skill, prefer it.
2. Otherwise prefer an already-installed local frontend/visual design skill.
3. If none exists, stop and ask the user to install/specify one or provide a
   reviewed brief and references.

Do not download, clone, or install a remote design skill as an implicit fallback.
Proposal review flow:

1. Write the proposal under the metadata-declared marketing root.
2. Validate it with the bundled helper.
3. Dry-render against a representative campaign.
4. Ask the user to review the proposal and candidates.
5. Only after review, update the official `theme.md` path.

## Production Lifecycle

Before live generation, confirm API usage, possible cost, and the exact
external producer skill. The harness treats third-party production skills as
local producer capabilities, not vendored dependencies. It does not wrap GPT,
OpenAI, or any image API. Declare capability bindings in metadata, resolve them
through `skillRegistry`, then use only locally installed or explicitly
configured producers. Do not auto-download, auto-install, or silently switch
production producers. Credentials belong to the selected producer's environment;
never print, commit, or copy them into configuration files. `producer.model` is
an optional hint; the selected producer decides whether it supports it.

Use this loop:

1. Run the read-only state preflight and read current org, repo,
   directory, accepted corpus, reference, and related-repo state declared by
   metadata.
2. Write or update a production plan under `state.plans`.
3. Resolve campaign-required capabilities with `harness.py skills`; if a skill
   is missing, show the declared install command and wait for explicit user
   approval before installing.
4. Validate the plan inputs and run a dry render.
5. Ask the user to approve live generation cost and the resolved producer.
6. Pass the dry-run context to the selected producer and place candidates in
   `artifacts.scratch`.
7. Show candidate paths, manifest, run lock, and review notes.
8. Ask the user which exact candidates are accepted.
9. Copy accepted files into `artifacts.approved` and update `state.accepted`.
10. Use the updated accepted state as input for the next production cycle.

The approved asset directory should come from metadata. It may be a public
package directory, a separate asset git repository, or a submodule. The skill
never edits `.gitattributes` and never runs `git add`, `commit`, or `push`.

Internal preflight helper:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml skills
```

Use this output to ground the production plan. Do not treat it as an asset
intake or promotion command.

## Verification

After code or workflow changes:

```bash
uv run ruff check .
uv run pytest
cd skills/marketing-harness/examples/codefox
python3 ../../scripts/harness.py --metadata marketing.harness.yaml validate
python3 ../../scripts/harness.py --metadata marketing.harness.yaml render --dry-run
```

Check that no API key, authorization header, machine-specific path, or raw image
base64 payload is stored in tracked files.
