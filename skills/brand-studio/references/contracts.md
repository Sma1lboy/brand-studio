# Harness Contracts

## Theme

`theme.md` is the repo visual direction single source of truth. It must start
with YAML frontmatter containing the machine-readable style tokens and producer
config, followed by Markdown design direction for humans and agents.

Required top-level fields:

```yaml
repo:
  id: "codefox"
  name: "CodeFox"
version: "1.1.0"
producer:
  # Optional: id: "<local-producer-skill-or-capability>"
  # Optional: model: "<producer-model-name>"
  params: {}
global: {}
alias: {}
```

Token rules:

- Every token is a mapping with `$value` and `$type`.
- `global` contains raw visual decisions with no usage intent.
- `alias.style.*` contains semantic style composites.
- Alias references may only use `{global.path.to-token}`.
- Use kebab-case token and group names.
- Changing producer params or visual tokens requires a version bump and dry-run review.
- `producer.model` is optional. The marketing harness only passes it through when present.

`repo.version` is the theme lock version for this repo's visual asset tree.
Generating a campaign does not bump it. Change it only when locked visual
tokens or producer config change.

## Metadata, Elements, And Asset State

Product repos may keep optional sidecars next to the metadata-declared
`theme.md`. A common package-local shape is:

```text
assets/marketing/theme.md
assets/marketing/theme.meta.yaml
assets/marketing/elements.yaml
assets/marketing/campaigns/release/
assets/marketing/campaigns/promo/
assets/marketing/asset-state.yaml
assets/marketing/accepted.yaml
assets/marketing/portfolios/release/accepted.yaml
assets/marketing/portfolios/release/asset-state.yaml
assets/marketing/portfolios/release/patterns.md
assets/marketing/portfolios/promo/accepted.yaml
assets/marketing/portfolios/promo/asset-state.yaml
assets/marketing/portfolios/promo/patterns.md
assets/marketing/plans/
public/marketing/<directory>/asset-state.yaml
```

These files are loaded, validated, and snapshotted for traceability. They do not
implicitly change render prompts. A human or style producer must distill them
into a reviewed `theme.md` update before they affect generation.

The metadata file should declare the full state surface the agent must read
before planning:

```yaml
organization:
  id: "codefox-org"
  name: "CodeFox Org"
skillDistribution:
  upstream: "sma1lboy/brand-studio"
  fork: "codefox-org/brand-studio"
  scope: "org"
  ref: "main"
brandStandard:
  source: "org-fork"
  path: "public/brand/brand-standard.md"
  themeBase: "public/brand/theme.base.md"
  references: "public/brand/references"
  version: "1.0.0"
theme:
  path: "assets/marketing/theme.md"
  references: "assets/marketing/references"
campaigns:
  release: "assets/marketing/campaigns/release"
  promo: "assets/marketing/campaigns/promo"
skills:
  image: "gpt-image"
  design: "frontend-design"
state:
  plans: "assets/marketing/plans"
  assetIndex: "assets/marketing/asset-state.yaml"
  accepted: "assets/marketing/accepted.yaml"
  directoryStateFile: "asset-state.yaml"
portfolios:
  release:
    accepted: "assets/marketing/portfolios/release/accepted.yaml"
    assetState: "assets/marketing/portfolios/release/asset-state.yaml"
    patterns: "assets/marketing/portfolios/release/patterns.md"
  promo:
    accepted: "assets/marketing/portfolios/promo/accepted.yaml"
    assetState: "assets/marketing/portfolios/promo/asset-state.yaml"
    patterns: "assets/marketing/portfolios/promo/patterns.md"
sources:
  assetRoots:
    - "assets/marketing"
    - "public/marketing"
  relatedRepos:
    - id: "sibling-product"
      kind: "same-org-product"
      root: "../sibling-product"
      metadata: "assets/marketing.harness.yaml"
      state: "assets/marketing/accepted.yaml"
```

Use local related repo paths when available. Remote GitHub/GitLab state should
be fetched only when declared by metadata, and the resolved commit must be
recorded in the production plan or review notes.

When commands may run outside the product repo, pass `--project-root`; metadata
relative paths are resolved under that root:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata marketing.harness.yaml <command>
```

## Skill Forks And Shared Metadata

For personal or organization use, fork the upstream skill repo and clone or
install from that fork. The fork is the right place for shared defaults that
multiple people or repos should see: producer preferences, policy defaults,
templates, install notes, org-level metadata, and org brand standards.
Product-specific theme locks, campaigns, portfolio accepted state, and public
assets stay in product repos or asset repos.

An org fork can publish shared brand standards under:

```text
public/brand/brand-standard.md
public/brand/theme.base.md
public/brand/references/
```

`brand-standard.md` is the reviewable human contract. `theme.base.md` is the
machine-readable base style lock. `brief.md` is not required; keep source-input
rationale inside `brand-standard.md` when it matters. The org `public/brand/`
directory is already the curated brand distribution, so product-style
`accepted.yaml`, `asset-state.yaml`, and preview campaigns are not required
there. Product repos should declare these files through `brandStandard` and
derive their own product-local `theme.md` instead of editing the org standard
in place.

Agents should respect `skillDistribution.fork` or the repo's pinned submodule
when present. They should not silently switch back to the upstream repo because
that can drop team metadata and policy.

## Producer Capabilities

Third-party producer skills are local capabilities, not dependencies vendored by
this skill. The metadata can bind producer capabilities under `skills`, but
agents must not auto-download, auto-install, or silently switch producer
implementations. Brand Studio orchestrates planning, state, review, and dry-run
context; it does not own the actual image, slide, logo, or social-card producer
skill.

- `skills.image`: optional local or external image producer skill.
- `skills.design`: optional local visual design skill for theme proposals.
- `skills.slide`: optional local presentation/PPT producer.
- `skills.logo`: optional local logo or vector producer.
- `skills.social`: optional local social-card producer.
- Credentials stay in environment variables and are never copied to YAML,
  manifests, run locks, or state files.

For `gpt-image`, validate handoff constraints before producer calls:

- deliverable width and height should be 16px aligned.
- output format should be `png`, `jpg`/`jpeg`, or `webp`.
- aspect ratio should stay between 1:4 and 4:1.
- reference images should be `png`, `jpg`/`jpeg`, or `webp`, with at most 10
  references per resolved style.

## Campaign

Campaigns describe content only:

```yaml
name: "feature-x-launch"
brief: "What this campaign says"
style: "launch-hero"
content:
  headline: "Visible copy"
  subject: "Scene or subject"
deliverables:
  - id: "web-banner"
    size: [1920, 608]
```

Campaigns must not include style prompt fragments, palette, negative prompts, references, or producer params.

## Production Plan

Plans are source state written before rendering:

```yaml
schema_version: "1.0"
id: "feature-x-launch"
created_at: "2026-06-19T00:00:00Z"
objective: "Generate launch assets for feature X."
inputs:
  state_preflight: ".harness/marketing/state/feature-x-launch.json"
  theme: "assets/marketing/theme.md"
  campaign: "assets/marketing/campaigns/promo/feature-x-launch.campaign.yaml"
  asset_index: "assets/marketing/asset-state.yaml"
  accepted_corpus: "assets/marketing/portfolios/promo/accepted.yaml"
  references:
    - "assets/marketing/references/main_visual.png"
sources:
  repo:
    id: "codefox"
    version: "1.1.0"
  related_products: []
deliverables:
  - id: "web-banner"
    size: [1920, 608]
acceptance_criteria:
  - "Matches locked visual style."
  - "Visible text is legible."
  - "Can influence future launch assets if accepted."
status: "planned"
```

Plans may reference remote registry or related-product sources, but generated
runs should pin the resolved commit in the plan or review notes.

## Directory Asset State

`asset-state.yaml` is a small directory-local memory file. It can be used under
marketing source directories, approved public directories, or
related local repos:

```yaml
schema_version: "1.0"
owner:
  kind: "repo"
  id: "kobe"
revision: 2
purpose: "Accepted Xiaohongshu launch card patterns."
assets:
  - id: "xhs-launch-card-01"
    path: "public/marketing/xhs-launch/card-01.png"
    kind: "xhs-post"
    size: [1242, 1660]
    checksum_sha256: "..."
    tags: ["xhs", "launch", "accepted"]
patterns:
  - id: "manifest-card-grid"
    notes: "Use stacked artifacts plus a compact manifest label."
```

Directory state is descriptive input for future planning. It is not a place to
hide generated scratch outputs. Asset entries should point at files that already
exist in the directory and were accepted or explicitly curated.

Prefer `owner.kind: "repo"` for repo-level `asset-state.yaml` and
`accepted.yaml`. Use `owner.kind: "directory"` only for a directory-local state
file whose scope is intentionally narrower than the product repo.

## Portfolio State

Release and promo assets have separate style pools. The root `accepted.yaml`
may remain as a transitional aggregate index, but the domain-specific accepted
file is the default style corpus for future production.

Release generation reads:

```text
assets/marketing/theme.md
assets/marketing/campaigns/release/
assets/marketing/portfolios/release/accepted.yaml
assets/marketing/portfolios/release/asset-state.yaml
assets/marketing/portfolios/release/patterns.md
CHANGELOG.md or copy.yaml
```

Promo generation reads:

```text
assets/marketing/theme.md
assets/marketing/campaigns/promo/
assets/marketing/portfolios/promo/accepted.yaml
assets/marketing/portfolios/promo/asset-state.yaml
campaign brief and references
```

Accepted entries must include the domain fields:

```yaml
accepted:
  - id: "release-v0-7-45-poster-logfull"
    kind: "artifact"
    campaign: "release-v0-7-45"
    asset_id: "release-poster"
    domain: "release"
    source_kind: "changelog"
    asset_type: "release-poster"
    style_family: "log-full-editorial"
    path: "public/marketing/release-v0-7-45/release-poster.png"
```

Use `domain: promo`, `source_kind: campaign-brief`,
`asset_type: hero`, and `style_family: screen-first-field-scene` for normal
campaign-first promotional assets unless the repo has a more specific approved
taxonomy.

## Run Lock

`<metadata artifacts.scratch>/<campaign>/run.lock.json` stores reproducibility metadata:

- full theme lock snapshot
- repo metadata sidecar snapshots, when present
- full campaign snapshot
- resolved style
- prompt per asset
- seed and producer params
- sanitized producer metadata

It must never contain API keys, authorization headers, or inline-encoded image payloads.

## Dry-Run Manifest

`<metadata artifacts.scratch>/<campaign>/manifest.json` describes the dry-run
placeholder output and prompt context. It is not the approved manifest for real
producer files:

```json
{
  "schema_version": "1.0",
  "campaign": "feature-x-launch",
  "repo": {
    "id": "codefox",
    "name": "CodeFox",
    "version": "1.1.0"
  },
  "theme_version": "1.1.0",
  "producer": {
    "id": "external-producer",
    "model": null
  },
  "assets": [
    {
      "id": "web-banner",
      "file": "web-banner.svg",
      "path": "web-banner.svg",
      "url": null,
      "size": [1920, 608],
      "mime_type": "image/svg+xml",
      "checksum_sha256": "...",
      "seed": 12345
    }
  ]
}
```

## Approved Manifest

Approved manifests describe real accepted files and are generated only after
user acceptance:

```json
{
  "schema_version": "1.0",
  "kind": "approved_manifest",
  "campaign": "feature-x-launch",
  "assets": [
    {
      "id": "web-banner",
      "file": "web-banner.png",
      "path": "public/marketing/feature-x-launch/web-banner.png",
      "source_path": ".harness/marketing/out/feature-x-launch/web-banner.png",
      "run_lock": ".harness/marketing/out/feature-x-launch/run.lock.json",
      "size": [1920, 608],
      "mime_type": "image/png",
      "checksum_sha256": "..."
    }
  ]
}
```

## Accepted State

Accepted state is the durable memory used by future planning. It is updated
only after the user accepts exact candidate files:

```yaml
schema_version: "1.0"
owner:
  kind: "repo"
  id: "kobe"
revision: 3
accepted:
  - id: "feature-x-launch-web-banner-2026-06-19"
    kind: "artifact"
    campaign: "feature-x-launch"
    asset_id: "web-banner"
    domain: "promo"
    source_kind: "campaign-brief"
    asset_type: "hero"
    style_family: "screen-first-field-scene"
    path: "public/marketing/feature-x-launch/web-banner.png"
    manifest: "public/marketing/feature-x-launch/manifest.json"
    run_lock: ".harness/marketing/out/feature-x-launch/run.lock.json"
    checksum_sha256: "..."
    tags: ["launch", "web-banner"]
    notes: "Accepted by the user after review."
```

The recommended approved path shape is:

```text
<artifacts.approved>/<campaign>/<asset-file>
<artifacts.approved>/<campaign>/manifest.json
```

Use a deeper product/version/channel path only when the product repo already has
that asset repository layout or the metadata-declared approved path points at a
submodule or asset package requiring it.

Do not use scratch output as accepted state. Do not add assets to this corpus
without user acceptance.

## Legacy Migration

Legacy `brand.lock.yaml`, `brand.meta.yaml`, `elements.yaml`, and loose
`references/` files are source context, not automatically accepted assets.
Migrate by distilling stable visual decisions into `theme.md`, moving durable
references under metadata `theme.references`, recording reusable facts in
`asset-state.yaml`, and writing root plus matching portfolio `accepted.yaml`
only for files the user or repo history clearly marks as accepted deliverables.
