# Marketing Harness Lifecycle

This skill is state-driven. Do not ask users to add assets through commands.
Agents may use bundled scripts as private helpers, but the user-facing workflow
is always:

```text
plan -> produce candidates -> user accepts exact candidates -> record state -> next production
```

## State Sources

Start each task by reading the product repo's metadata and state files:

- organization and portfolio metadata declared by the metadata file.
- `brand.lock.yaml`: frozen product brand style.
- `campaigns/`: campaign inputs.
- `references/`: local reference assets.
- `asset-state.yaml`: directory-level memory under declared asset roots.
- `accepted.yaml`: user-accepted assets and patterns from prior cycles.
- `artifacts.scratch`: temporary candidate output.
- `artifacts.approved`: durable files copied only after acceptance.
- `sources.relatedRepos`: same-org or same-portfolio product repos that can
  provide accepted state and asset-state context.

When metadata declares portfolio or related-product sources, treat them as
read-only context. Prefer local checkouts or local caches. If remote GitHub or
GitLab access is needed, fetch only the declared files and pin resolved commits
in the plan. Do not copy other repos into the current product repo.

Run the bundled state preflight before writing a production plan:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --metadata path/to/marketing.harness.yaml state
```

Use the JSON as a read summary of the current org, portfolio, repo, directory,
accepted corpus, and related-repo state. This command is read-only and must not
be turned into a user-facing asset intake workflow.

## Planning

Write a production plan before rendering. A plan should capture:

- objective and audience
- current organization, portfolio, product, and directory state used
- accepted examples considered
- related products or registry sources consulted
- campaign file path
- brand lock path and version
- candidate deliverables
- cost/risk notes for live generation
- acceptance criteria

Store plans under metadata `state.plans`, for example:

```text
packages/branding/marketing/plans/<campaign>.plan.yaml
```

Plans are source state. They are not generated image artifacts.

## Production

Validate inputs and run a dry render first. Before live generation, ask the user
to approve API usage and cost. Live generation writes candidate files only under
`artifacts.scratch`.

Deliverables can include banners, landscape visuals, slide/PPT backgrounds,
logo-theme explorations, X/XHS promotional cards, website hero assets, social
post images, or other campaign-specific visual formats. They should all follow
the same state loop.

Candidates are not durable brand memory. They remain scratch until the user
accepts specific outputs.

Review candidates for:

- brand lock fit
- text quality and legibility
- dimensions and file format
- consistency with accepted examples
- whether the asset should influence future generations

## Acceptance

Ask the user to identify exactly which candidate files are accepted. Acceptance
must name concrete files or asset ids from the current render. Do not infer
acceptance from API-cost approval or from a successful render.

For each accepted candidate:

1. Copy the file into `artifacts.approved`.
2. Copy or reference its manifest entry.
3. Record an `accepted.yaml` entry with campaign, asset id, path, checksum,
   tags, notes, and source run lock path.
4. If the asset reveals a reusable pattern, update the relevant directory
   `asset-state.yaml`, `elements.yaml`, or a portfolio proposal separately.

Rejected or unreviewed candidates stay in scratch and should not feed future
planning.

## Accepted Corpus Shape

Use append-only entries unless the user explicitly asks to correct an existing
record:

```yaml
schema_version: "1.0"
owner:
  kind: "brand"
  portfolio_id: "codefox"
  id: "kobe"
revision: 3
accepted:
  - id: "launch-web-banner-2026-06-19"
    kind: "artifact"
    campaign: "launch"
    asset_id: "web-banner"
    path: "packages/branding/public/marketing/products/codefox/kobe/1.2.0/artifacts/launch/web-banner.png"
    manifest: "packages/branding/public/marketing/products/codefox/kobe/1.2.0/artifacts/launch/manifest.json"
    run_lock: "packages/branding/.harness/out/launch/run.lock.json"
    checksum_sha256: "..."
    tags: ["launch", "web-banner", "accepted"]
    notes: "Accepted by the user for the launch campaign."
```

Use tags and notes to help future agents understand why an asset matters.
Avoid long aesthetic essays in accepted state; keep deeper reasoning in the
plan or review notes.

## Next Cycle

Future plans must read `accepted.yaml` before proposing new assets. The corpus
is how the skill learns from prior accepted work. Related repo assets should be
read the same way: through their metadata, accepted state, manifests, and
selected reference files, not through ad hoc descriptions.

For same-org products, prefer local related repo paths declared in metadata.
If local paths are unavailable, use declared remote metadata only and record the
remote commit or version in the plan. Do not rely on a one-paragraph description
when the actual state files and accepted assets can be read.

Never treat rejected candidates or scratch output as brand memory.
