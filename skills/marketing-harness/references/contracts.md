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
assets/marketing/asset-state.yaml
assets/marketing/accepted.yaml
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
  upstream: "CodeFox-Repo/marketing-harness"
  fork: "codefox-org/marketing-harness"
  scope: "org"
  ref: "main"
theme:
  path: "assets/marketing/theme.md"
  campaigns: "assets/marketing/campaigns"
  references: "assets/marketing/references"
skills:
  image: "image.default"
  slide: "slide.default"
state:
  plans: "assets/marketing/plans"
  assetIndex: "assets/marketing/asset-state.yaml"
  accepted: "assets/marketing/accepted.yaml"
  directoryStateFile: "asset-state.yaml"
sources:
  skillRegistries:
    - "vendor/marketing-rules/skills.yaml"
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

`sources.skillRegistries` has no implicit default path. For production, mount
the org rules repo into the product repo as a submodule and point metadata at
that local file, for example `vendor/marketing-rules/skills.yaml`. The runtime
must not clone or fetch remote rules during generation.

The org rules registry file should own the shared producer allowlist:

```yaml
skillRegistry:
  image.default:
    kind: "codex-skill"
    skill: "gpt-image"
    source:
      type: "github"
      repo: "codefox-org/agent-skills"
      ref: "v0.3.2"
    install:
      tool: "npx-skills"
      package: "skills"
      command: "add"
      args:
        - "codefox-org/agent-skills"
        - "--skill"
        - "gpt-image"
        - "--agent"
        - "codex"
    policy:
      allowAutoInstall: false
      requiresApproval: true
```

Use local related repo paths when available. Remote GitHub/GitLab state should
be fetched only when declared by metadata, and the resolved commit must be
recorded in the production plan or review notes.

## Skill Forks And Shared Metadata

For personal or organization use, fork the upstream skill repo and clone or
install from that fork. The fork is the right place for shared defaults that
multiple people or repos should see: producer preferences, policy defaults,
templates, install notes, and org-level metadata. Product-specific theme locks,
campaigns, accepted state, and public assets stay in product repos or asset
repos.

Agents should respect `skillDistribution.fork` or the repo's pinned submodule
when present. They should not silently switch back to the upstream repo because
that can drop team metadata and policy.

## Producer Capabilities

Third-party producer skills are local capabilities resolved from metadata, not
dependencies vendored by this skill. Product metadata maps local capability keys
to org registry ids under `skills`; org rules metadata or product metadata
defines allowlisted entries under `skillRegistry`. Campaigns declare what they
need under `requires.skills`, and agents resolve only those keys before live
generation.

- `sources.skillRegistries`: optional org rules metadata files that provide
  shared `skillRegistry` entries.
- `skills.<capability>`: product-local capability key mapped to a registry id,
  such as `image: image.default`.
- `skillRegistry.<id>.kind`: currently `codex-skill` or `command`.
- `skillRegistry.<id>.install.tool`: currently only `npx-skills`.
- Registry ids must be unique across all sources. Product metadata must not
  override an org registry id with a different entry.
- `policy.allowAutoInstall: false`: default policy; ask the user before any
  install.
- Credentials stay in environment variables and are never copied to YAML,
  manifests, run locks, or state files.

The `install` block is declarative. It exists so preflight can detect missing
skills and show the same team-approved command, for example:

```bash
npx skills add codefox-org/agent-skills --skill gpt-image --agent codex
```

Agents must not execute arbitrary install commands from metadata. Unsupported
install tools must fail closed.

## Campaign

Campaigns describe content only:

```yaml
name: "feature-x-launch"
brief: "What this campaign says"
style: "launch-hero"
requires:
  skills:
    - "image"
content:
  headline: "Visible copy"
  subject: "Scene or subject"
deliverables:
  - id: "web-banner"
    size: [1920, 600]
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
  campaign: "assets/marketing/campaigns/feature-x-launch.campaign.yaml"
  asset_index: "assets/marketing/asset-state.yaml"
  accepted_corpus: "assets/marketing/accepted.yaml"
  references:
    - "assets/marketing/references/main_visual.png"
sources:
  repo:
    id: "codefox"
    version: "1.1.0"
  related_products: []
deliverables:
  - id: "web-banner"
    size: [1920, 600]
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
  kind: "directory"
  id: "xhs-launch-cards"
revision: 2
purpose: "Accepted Xiaohongshu launch card patterns."
assets:
  - id: "xhs-launch-card-01"
    path: "card-01.png"
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

## Run Lock

`<metadata artifacts.scratch>/<campaign>/run.lock.json` stores reproducibility metadata:

- full theme lock snapshot
- repo metadata sidecar snapshots, when present
- full campaign snapshot
- resolved style
- prompt per asset
- seed and producer params
- sanitized producer metadata

It must never contain API keys, authorization headers, or raw image base64 payloads.

## Manifest

`<metadata artifacts.scratch>/<campaign>/manifest.json` is the consumer contract:

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
      "file": "web-banner.png",
      "path": "web-banner.png",
      "url": null,
      "size": [1920, 600],
      "mime_type": "image/png",
      "checksum_sha256": "...",
      "seed": 12345
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
    path: "public/marketing/repos/kobe/1.1.0/artifacts/feature-x-launch/web-banner.png"
    manifest: "public/marketing/repos/kobe/1.1.0/artifacts/feature-x-launch/manifest.json"
    run_lock: ".harness/marketing/out/feature-x-launch/run.lock.json"
    checksum_sha256: "..."
    tags: ["launch", "web-banner"]
    notes: "Accepted by the user after review."
```

The metadata-declared approved asset directory may be a package directory,
asset repository, or git submodule:

```text
<approved>/repos/<repo-id>/<theme-version>/artifacts/<campaign>/
```

Do not use scratch output as accepted state. Do not add assets to this corpus
without user acceptance.
