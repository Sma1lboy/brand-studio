---
name: brand-studio
description: >-
  Use this skill to operate thin brand-studio scripts from a product repo:
  read YAML/JSON metadata, plan theme-locked campaigns, validate theme.md and
  campaign YAML, export producer-ready dry-run context, and record only
  user-accepted assets into repo-owned visual state.
---

# Brand Studio

This folder is the reusable skill payload. It should stay thin: `SKILL.md`,
small scripts, references, and templates. The runtime lives under `scripts/`;
do not add a top-level `src/` package or tests inside an installed skill
payload. A valid skill payload may have `scripts/`, `references/`, `assets/`,
and `agents/`.

Preserve the boundary:

```text
org standard -> repo visual state -> production plan -> generated candidates -> user acceptance -> settled repo assets -> next production
```

Never put visual style prompt text in campaign files. Campaigns describe content
and deliverables only.

Do not model asset collection as a user-facing command surface. Assets enter
the durable corpus only when a user accepts generated candidates or explicitly
marks existing work as accepted during review. Treat low-level scripts as
internal agent helpers, not as instructions for users to add assets manually.

Use stage names to classify user intent before acting:

- `init-org`: create the organization brand standard.
- `update-org`: revise organization standards, base theme, or references.
- `retire-org`: deprecate organization standards or references; do not default
  to physical deletion.
- `init-repo`: create a product repo's Brand Studio metadata and local theme.
- `gen-repo`: generate scratch candidates for a product repo.
- `settle-repo`: move accepted candidates into durable product assets.
- `update-repo`: revise product theme or replace an asset through a new
  candidate and review cycle.
- `delete-repo`: delete scratch candidates only.
- `retire-repo`: mark durable product assets inactive or superseded; purge
  physical files only with explicit approval and reference checks.

Agents may read images, infer intent, choose the stage, write proposals, and
select producer prompts. Deterministic helpers must handle path resolution,
validation, producer handoff context, checksum reporting, accepted-state
updates, approved-manifest writes, and any destructive operation.

Stage routing rules:

| User intent | Stage | Allowed durable writes |
| --- | --- | --- |
| "initialize our brand/org standard" | `init-org` | `public/brand/` only |
| "update the org standard/reference" | `update-org` | focused `public/brand/` edits |
| "remove/deprecate this org rule/reference" | `retire-org` | deprecation notes first |
| "init this product/repo" | `init-repo` | metadata, theme, empty state |
| "make/generate a release card/banner" | `gen-repo` | none; scratch output only |
| "this one is good/use it" | `settle-repo` | approved asset and state updates |
| "revise theme/update this asset" | `update-repo` | proposal or new settled revision |
| "delete this draft/candidate" | `delete-repo` | scratch deletion only |
| "remove this published asset" | `retire-repo` | state retirement; purge needs approval |

If a request can map to multiple stages, stop after the safest earlier stage.
For example, "update this release card" means `update-repo asset` followed by a
new `gen-repo` candidate; it does not mean editing an approved PNG in place.
Only move from `gen-repo` to `settle-repo` after user acceptance.

## Skill Distribution

For personal or organization use, prefer a fork of the upstream skill repo.
Treat the upstream repo as the generic runtime/template source, and treat the
personal or org fork as the shared source for team metadata, policies, producer
preferences, templates, install notes, and org brand standards.

When working inside a product repo, use the product repo's pinned fork or local
skill install. Do not silently switch to upstream. Product-specific `theme.md`,
campaigns, accepted state, and public assets remain in the product repo or its
asset repo; cross-person defaults belong in the fork.

## Org Brand Standard Init

For `init-org`, initialize the organization fork itself and store shared brand
standards under `public/brand/` in that fork. This is the distribution surface
product repos inherit from; it is not a product accepted corpus.

Recommended org fork shape:

```text
public/brand/
  brand-standard.md
  theme.base.md
  references/
```

`brand-standard.md` is the human-readable standard: positioning, visual
language, palette, typography direction, composition rules, logo usage, voice,
do/don't, product adaptation rules, and source-input rationale. `theme.base.md`
is the machine-readable base style lock. Do not require a separate `brief.md`;
if rationale is useful, keep it in `brand-standard.md` under a source inputs or
rationale section. Treat files under `public/brand/` as the curated org brand
distribution; do not add an org accepted-state loop unless the org fork later
needs a separate review ledger.

For org init, read user-supplied logo, website, deck, product UI, and marketing
references first. If no files are supplied, scan `public/brand/references/` and
then `public/brand/` once for images. Do not scan the whole fork, and do not
create product-style campaign, accepted, or asset-state files for the org fork.

Use the canonical runtime helper only to create or check the deterministic org
brand files:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" org init --write
```

The helper creates missing `brand-standard.md`, `theme.base.md`, and
`references/` paths, respecting `brandStandard.*` metadata when present. It does
not read images, infer brand direction, overwrite existing files, or create repo
asset state.

Product metadata can point back to the org standard:

```yaml
brandStandard:
  source: org-fork
  path: public/brand/brand-standard.md
  themeBase: public/brand/theme.base.md
  references: public/brand/references
  version: 1.0.0
```

During product init, read the org brand standard first, then combine it with the
product's uploaded images, declared asset roots, and repo context to write the
product-local `theme.md`.

For `update-org`, revise `brand-standard.md`, `theme.base.md`, or files under
`references/` only after reading the current standard and the user's new source
inputs. Prefer a focused patch and record rationale in `brand-standard.md`.
Never rewrite the whole org standard when a small rule, palette, reference, or
avoid-list update is enough.

For `retire-org`, mark standards or references as deprecated in
`brand-standard.md` before removing files. Physical deletion from
`public/brand/` requires explicit user instruction and a check for downstream
repo references when those repos are available locally.

## Image-First Init, Metadata Underneath

For `init-repo`, prefer image-first initialization when the user supplies brand
images, screenshots, or existing marketing assets. Use the agent's native
image-reading capability to infer the first brand direction, then write the
Brand Studio files directly. Do not ask the user to fill out YAML or a brand
brief before producing the first usable draft.

Accept prompts like:

```text
$brand-studio init this repo from the attached brand images
$brand-studio init this repo from existing repo assets
```

For image-first init:

1. Locate the skill root from the installed skill or repo submodule.
2. Find or create `marketing.harness.yaml` using metadata paths. If the file is
   missing, infer `project.id` from the repo directory name, use `root: .`, use
   `assets/marketing` for `project.marketingRoot`, use
   `assets/marketing/campaigns/release` and
   `assets/marketing/campaigns/promo` for campaign domains, use
   `.harness/marketing/out` for scratch output, and use `public/marketing` for
   approved assets. Omit `organization` unless the user supplied it or the repo
   already makes it clear.
3. Run `repo init` in dry-run mode first. Only create directories after the paths
   match the current repo shape.
4. Read the supplied images directly. Extract a compact brand direction:
   palette, typography direction, visual language, materials, lighting, mood,
   composition rules, avoid list, and initial style aliases such as
   `launch-hero` and `social-default`. If no images are attached, scan the
   declared asset roots once for image files and use those as initialization
   context. Do not add a separate init-assets path schema or per-image role
   schema.
5. Write `brief.md` as the human-readable rationale and `theme.md` as the
   machine-readable style lock with valid design-token frontmatter.
6. Write `campaigns/init-preview.campaign.yaml` as a representative preview.
7. Create root `asset-state.yaml`/`accepted.yaml` plus
   `portfolios/release/` and `portfolios/promo/` state if they do not exist.
8. Run validation and a dry render with the existing launcher.
9. Show the generated file paths and dry-run outputs. The user can edit
   `brief.md` or `theme.md`, or ask for a revision.

Do not add image understanding to `harness.py`. Codex, Claude, or the active
agent reads images; the harness remains deterministic and only handles paths,
validation, repo init, and dry-run rendering.

If `theme.md` already exists, do not silently replace it. Revise it in place
only when the user clearly asks to reinitialize; otherwise write a proposal
under the metadata-declared marketing root and ask before promotion.

This skill is still metadata-first internally: do not rely on hard-coded product
paths. Find or create a small metadata file in the product repo, then pass it to
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
  upstream: sma1lboy/brand-studio
  fork: my-org/brand-studio
  scope: org
  ref: main

brandStandard:
  source: org-fork
  path: public/brand/brand-standard.md
  themeBase: public/brand/theme.base.md
  references: public/brand/references
  version: 1.0.0

theme:
  path: assets/marketing/theme.md
  references: assets/marketing/references

campaigns:
  release: assets/marketing/campaigns/release
  promo: assets/marketing/campaigns/promo

skills:
  # Bind each capability to a locally installed producer skill (by name).
  # Leave a value empty until you have selected and installed that producer.
  image: ""
  design: ""
  slide: ""
  logo: ""
  social: ""

campaign:
  name: launch
  path: assets/marketing/campaigns/promo/launch.campaign.yaml

artifacts:
  scratch: .harness/marketing/out
  approved: public/marketing

state:
  plans: assets/marketing/plans
  assetIndex: assets/marketing/asset-state.yaml
  accepted: assets/marketing/accepted.yaml
  directoryStateFile: asset-state.yaml

portfolios:
  release:
    accepted: assets/marketing/portfolios/release/accepted.yaml
    assetState: assets/marketing/portfolios/release/asset-state.yaml
    patterns: assets/marketing/portfolios/release/patterns.md
  promo:
    accepted: assets/marketing/portfolios/promo/accepted.yaml
    assetState: assets/marketing/portfolios/promo/asset-state.yaml
    patterns: assets/marketing/portfolios/promo/patterns.md

sources:
  assetRoots:
    - assets/marketing
    - public/marketing
  relatedRepos: []

policy:
  requireHumanApprovalBeforeRender: true
  requireHumanApprovalBeforeStateUpdate: true
  allowRootWorkspaceBootstrap: false
```

`assets/brand-studio-template.yaml` contains a copyable starter. If the
repo already has its own marketing/branding layout, match it instead of moving
files to a generic root-level directory.

## Resolve Roots

Keep these roots separate:

- **Project root:** the user's current product repo.
- **Marketing root:** the product-owned source location from metadata, such as
  `assets/marketing`.
- **Campaign domains:** release-note/changelog campaigns live under
  `campaigns.release`; normal campaign-first promotion lives under
  `campaigns.promo`.
- **Org brand standard:** shared brand rules and base theme declared by
  `brandStandard`, usually from the org fork's `public/brand/`.
- **Repo asset tree:** the repo-owned hierarchy under declared asset roots.
  Treat the repo and its asset directories as the asset namespace.
- **Scratch output:** the product-owned temporary render location from metadata,
  such as `.harness/marketing/out`.
- **Approved assets:** the product-owned location for user-accepted generated
  files.
- **Accepted state:** the transitional aggregate accepted index, usually
  `assets/marketing/accepted.yaml`.
- **Portfolio state:** domain-specific accepted assets and patterns under
  `portfolios/release/` and `portfolios/promo/`.
- **Directory state:** `state.directoryStateFile`, usually `asset-state.yaml`,
  found under declared asset roots and read before production.
- **Related repo state:** local sibling repo metadata/state declared under
  `sources.relatedRepos`.
- **Skill root:** this installed `skills/brand-studio` folder.

Do not create root-level `workspace/`, `outputs/`, `published/`, or `releases/`
by default. Use metadata paths.

The launcher is:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" --metadata marketing.harness.yaml
```

Pass `--project-root` whenever the command may run from a skill checkout,
submodule, monorepo tool directory, or any cwd that is not the product repo root.
All metadata-relative paths are resolved under the resolved project root. The
launcher runs the bundled scripts in this skill. There is no `uvx` remote
runtime fallback and no ancestor checkout discovery.

YAML metadata requires PyYAML. Use `uv run python ...` from this skill checkout
or install dependencies with `uv sync`; do not rely on the old simplified YAML
fallback for metadata lists.

Prefer the canonical command surface:

| Stage | Command |
| --- | --- |
| `init-org` | `org init [--write]` |
| `init-repo` | `repo init [--write]` |
| repo path preflight | `repo paths` |
| repo config check | `repo check` |
| repo state preflight | `repo state` |
| validation | `repo validate` |
| dry render | `repo render --dry-run` |
| release copy review | `repo release copy --write --releases 4` |
| `gen-repo` release | `repo gen release --releases 4 --changelog <file>` |
| producer handoff | `repo handoff --campaign <name> --asset-id <id>` |
| `settle-repo` | `repo settle --campaign <name> --asset-id <id> --file <path>` |
| report | `repo report --file <path>` |
| `delete-repo` candidate | `repo delete candidate --file <path>` |

The old top-level helper commands are not a public command surface. Use
`org ...` or `repo ...`; helper functions under the hood are implementation
details. Use `scripts/check_harness.sh` and `scripts/bootstrap_project.sh` only
as internal setup wrappers. `repo init` is create-only, dry-run by default, and
must show the user the planned directories before any write.

## Common Defaults

- Always dry-run before asking any external producer to generate live assets.
- Do not commit automatically.
- Do not call image APIs until the user has approved the cost/action.
- Do not update accepted state until the user has accepted specific generated
  candidates.
- Do not physically delete durable repo assets by default. Scratch candidates
  can be deleted after path validation; approved assets should be retired unless
  the user explicitly asks to purge them.
- Brand Studio itself does not drive git. If the product repo's own AGENTS.md or
  user instructions explicitly require commits, follow those higher-priority
  repo rules and stage only Brand Studio metadata, state, manifests, and
  accepted assets related to the requested work.

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

### Portfolio Domains

Keep release and promo visual memory separate. Both domains share only the
brand base in `theme.md`: palette, typography direction, voice, avoid rules,
and brand tokens. Specific composition patterns do not cross domains by
default.

Use this repo state layout unless metadata overrides it:

```text
assets/marketing/
  theme.md
  campaigns/
    release/
    promo/
  accepted.yaml
  asset-state.yaml
  portfolios/
    release/
      accepted.yaml
      asset-state.yaml
      patterns.md
    promo/
      accepted.yaml
      asset-state.yaml
      patterns.md
```

For release images, read `theme.md`, `portfolios/release/accepted.yaml`,
`portfolios/release/asset-state.yaml`, `portfolios/release/patterns.md`, and
the changelog or release copy. Do not read promo accepted assets by default.
For promo images, read `theme.md`, `portfolios/promo/accepted.yaml`,
`portfolios/promo/asset-state.yaml`, campaign brief, and references. Do not
read release accepted assets by default.

Accepted entries must carry `domain`, `source_kind`, `asset_type`, and
`style_family`. Use `domain: release`, `source_kind: changelog`, and
`style_family: log-full-editorial` for changelog/release-note posters. Use
`domain: promo`, `source_kind: campaign-brief`, and
`style_family: screen-first-field-scene` for normal campaign-first promotion.
The root `accepted.yaml` may remain as a compatibility aggregate, but future
planning should use the matching portfolio accepted file as the style pool.

Classify product repo production requests into `gen-repo`, `settle-repo`,
`update-repo`, `delete-repo`, or `retire-repo` before running helpers.

Before live generation, confirm API usage, possible cost, and the exact
external producer skill. If the user directly asks for live generation, treat
that as action approval, but still state the selected producer and that the call
may bill before invoking it. If the request is ambiguous, stop and ask for
confirmation. The harness treats third-party production skills as local producer
capabilities, not vendored dependencies. It does not wrap GPT, OpenAI, or any
image API. Bind producer skills in metadata under `skills`, then use only
locally installed or explicitly configured producers. Do not auto-download,
auto-install, or silently switch production producers. Credentials belong to
the selected producer's environment; never print, commit, or copy them into
configuration files. `producer.model` is an optional hint; the selected
producer decides whether it supports it.

Validate producer constraints before handoff. For `gpt-image`, deliverable
dimensions must be positive, use supported image formats, keep reasonable aspect
ratios, and align width/height to 16px. Adjust campaign sizes during planning
or dry-run rather than after spending producer calls.

For `gen-repo`, use this loop:

1. Run the read-only state preflight and read current org, repo, directory,
   matching portfolio accepted corpus, reference, and related-repo state
   declared by metadata.
2. Write or update a production plan under `state.plans`.
3. Validate the plan inputs and run a dry render.
4. Ask the user to approve live generation cost and the external producer.
5. Pass the dry-run context to the selected producer and place candidates in
   `artifacts.scratch`.
6. Show candidate paths, producer output metadata, run lock, and review notes.

Stop here unless the user accepts a candidate. Scratch candidates are not
durable assets.

For `settle-repo`, continue only after user acceptance:

1. In a single-candidate context, language such as "this is good", "no
   changes", or "use this one" can count as accepting that candidate.
2. In a multi-candidate context, ask for exact asset ids or file paths.
3. Use the internal accept helper to copy accepted files into
   `artifacts.approved`, write an approved manifest from real files, update the
   root aggregate `state.accepted`, and update the matching portfolio accepted
   file.
4. Use the updated portfolio accepted state as input for the next production
   cycle.

The dry-run `manifest.json` describes SVG placeholders and prompt context. It is
not the approved manifest for real producer PNG/JPEG/WebP files. The approved
manifest is generated only after user acceptance, from the real file's mime
type, dimensions, and checksum.

The approved asset directory should come from metadata. It may be a public
package directory, a separate asset git repository, or a submodule. The skill
never edits `.gitattributes` and never runs `git add`, `commit`, or `push`.

Internal preflight helper:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata path/to/marketing.harness.yaml repo state
```

Use this output to ground the production plan. Do not treat it as an asset
intake or promotion command.

Internal producer handoff helper, after dry-run and before any paid/live
producer call:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata marketing.harness.yaml repo handoff \
  --campaign launch \
  --asset-id web-banner
```

Use this to read `producer-context.json`, validate the selected asset's prompt,
size, format, producer skill, and target scratch path, and print
`not_generated_yet=true`. This helper never calls the producer.

Internal acceptance helper, after the user has accepted a concrete candidate:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata marketing.harness.yaml repo settle \
  --campaign launch \
  --asset-id web-banner \
  --domain promo \
  --source-kind campaign-brief \
  --asset-type hero \
  --style-family screen-first-field-scene \
  --file .harness/marketing/out/launch/web-banner.png \
  --checksum-sha256 <sha256> \
  --notes "Accepted by user review." \
  --tags launch,web-banner \
  --plan assets/marketing/plans/launch.plan.yaml \
  --update-asset-state
```

Use this only after acceptance. In a single-candidate context, user language such
as "this is good", "no changes", or "use this one" can count as accepting that
candidate. In a multi-candidate context, ask for exact asset ids or file paths.
The helper copies from scratch to approved assets, writes an approved manifest,
validates mime, dimensions, and checksum, updates root `accepted.yaml` and the
matching portfolio `accepted.yaml`, optionally updates the matching portfolio
`asset-state.yaml` and plan status, and never runs git commands.
It prints the report fields needed for the final response, including
`accepted=true`, `corpus=approved`, `domain`, `source_kind`, `asset_type`,
`style_family`, `mime_type`, `size`, and `checksum_sha256`.

Internal report helper, for a real candidate before or after acceptance:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata marketing.harness.yaml repo report \
  --file .harness/marketing/out/launch/web-banner.png
```

Use this before final reporting when no accept command just ran. If
`corpus=scratch` and `accepted=false`, say the file has not entered the durable
accepted corpus.

## Repo Update and Delete

For `update-repo theme`, write a proposal under the metadata-declared marketing
root, validate it, dry-render a representative campaign, and ask before
promoting it to the official `theme.path`. Do not silently overwrite an
existing theme.

For `update-repo asset`, never overwrite an approved asset in place. Generate a
new scratch candidate, ask the user to review it, then use `settle-repo`. The
settled state should make replacement intent explicit through notes, tags, or
plan status so future production can tell the new asset supersedes the old one.

For `delete-repo candidate`, physical deletion is allowed only for files under
metadata `artifacts.scratch` after resolving the path under `--project-root`.
Do not remove approved assets, state files, org standards, or source references
through this path.

For durable repo assets under `artifacts.approved`, prefer `retire-repo asset`:
mark the asset inactive or superseded in repo-owned state and keep the file
unless the user explicitly asks for a purge. Before a purge, search the product
repo for references to the approved file path. If references exist, report them
and ask again before deleting. Brand Studio has no dedicated purge helper yet;
until one exists, do not perform durable deletion as an improvised state edit
unless the user has explicitly approved the exact file and state changes.

Final reporting must name the stage that actually completed:

- After `gen-repo`, report scratch candidate paths and say they are not settled.
- After `settle-repo`, report approved paths, dimensions, checksum, and state.
- After `update-repo`, report whether the update is still a proposal/candidate
  or has been settled.
- After `delete-repo`, report only scratch files removed.
- After `retire-repo`, report state changes and whether any physical files
  remain.

## Legacy Migration

Older repos may have `brand.lock.yaml`, `brand.meta.yaml`, `elements.yaml`, or
loose `references/` without a current `theme.md` and portfolio accepted state.
Migrate without treating every existing file as accepted:

1. Read old lock/meta/reference files as source context.
2. Distill stable visual decisions into `theme.md` frontmatter and notes.
3. Move reusable reference files under metadata `theme.references`.
4. Write curated facts or patterns into `asset-state.yaml`.
5. Write root `accepted.yaml` plus the matching portfolio `accepted.yaml` only
   for files the user explicitly accepts or that the repo already documents as
   approved deliverables.
6. Run validate and dry-run before replacing the official theme.

Release-version helpers:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata path/to/marketing.harness.yaml \
  repo release copy --write --releases 4
```

Use `repo release copy` when the task is to review or revise release wording
before image generation. It reads release entries from standard `CHANGELOG.md`
locations and writes a structured `copy.yaml` under the scratch directory. It
reads one latest release by default; use `--releases 4` for recent-release
notes. Treat that file as the text-asset handoff into campaign and image
production.
`copy.yaml` exposes `releases[]` as the canonical editable text asset, with
`changes[]` as direct changelog text. Single-product release entries do not
repeat `package`; only multi-package release copy needs release-level package
labels. It does not write a separate `key_points` block.

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata path/to/marketing.harness.yaml \
  repo gen release --releases 4
```

Use `repo gen release` when the task is to produce release-version marketing
after a version step. Release producer prompts must make the release notes page the
main subject: header, metadata chips, version heading, and changelog rows. Do
not frame changelog content as a small side panel on a generic product hero. If
`copy.yaml` already exists, it uses that revised text asset; otherwise it writes
the same `copy.yaml` first. It then writes a normal campaign file under the
metadata-declared campaigns directory, runs the existing dry-run render flow, and
exports `producer-context.json` for the metadata-selected image producer skill.
The producer context must point at the release portfolio and must not include
promo accepted assets by default.
Use `repo release campaign --write` only when you need to inspect or edit the
generated campaign before producer handoff.

### Release Image Production Checklist

`repo gen release` is a dry-run and producer handoff. It writes `copy.yaml`, a
campaign file, SVG placeholders, a dry-run `manifest.json`, and
`producer-context.json`, but it does not create a real image. Treat the output
as ready for producer handoff only after checking `source_count`,
`changelog_count`, and the actual `copy.yaml` `releases[]` count. In a
single-product flow, `--releases 4` should yield exactly four release sections.
If counts are abnormal or versions repeat, rerun with an explicit product
changelog, for example `--changelog packages/kobe/CHANGELOG.md`, and do not pass
the polluted `producer-context.json` to the image producer.

Real release images must be PNG, JPEG, or WebP files emitted by the configured
producer. SVG placeholders are not final images. For producer handoff, run
`repo handoff` for the target asset, generate one primary
candidate such as `release-card` unless the user asked for the full set, state
the helper's selected producer skill and possible billing before calling it, and
write the result to the helper's target path under `artifacts.scratch`. Use the
metadata-selected image skill, such as `gpt-image`.

Settle accepted release assets into the release portfolio, not the promo
portfolio. Release is a version-fact asset pipeline:
`CHANGELOG.md -> copy.yaml -> release campaign -> producer context -> real image
-> release portfolio settle`. It is not a normal campaign-first promotion.

Final responses after release image work must report the real image path,
dimensions, checksum, corpus, and whether it has been accepted. Use the latest
`repo settle` or `repo report` helper output as the source of truth. If the
PNG/JPEG/WebP is still in scratch, say that it has not entered the durable
accepted corpus.

## Verification

After code or workflow changes:

```bash
uv run ruff check .
uv run pytest
cd skills/brand-studio/examples/codefox
uv run python ../../scripts/harness.py --project-root "$PWD" --metadata marketing.harness.yaml repo validate
uv run python ../../scripts/harness.py --project-root "$PWD" --metadata marketing.harness.yaml repo render --dry-run
```

Check that no API key, authorization header, machine-specific path, or
inline-encoded image payload is stored in tracked files.
