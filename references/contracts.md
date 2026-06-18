# Harness Contracts

## Brand Lock

`brand.lock.yaml` is the style single source of truth. It must be versioned and validated before render.

Required top-level fields:

```yaml
portfolio:
  id: "codefox"
  name: "CodeFox"
  version: "1.0.0"
brand:
  id: "codefox"
  name: "CodeFox"
version: "1.1.0"
provider:
  gateway: "gpt-image-skill"
  model: "gpt-image-2"
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
- Changing provider/model/params or visual tokens requires a version bump and regression.

`portfolio` is optional for legacy locks but required for new product brands. Treat
`portfolio.version` and `brand.lock version` separately:

- `portfolio.version` changes when the parent brand metadata or element system changes.
- `brand.lock version` changes when this product's locked visual tokens or provider config changes.
- Generating a campaign does not bump either version.

## Metadata, Elements, And Accepted Corpus

New product workspaces use explicit sidecars:

```text
workspace/portfolios/<portfolio-id>/portfolio.meta.yaml
workspace/portfolios/<portfolio-id>/elements.yaml
workspace/portfolios/<portfolio-id>/accepted.yaml
workspace/products/<portfolio-id>/<brand-id>/brand.meta.yaml
workspace/products/<portfolio-id>/<brand-id>/elements.yaml
workspace/products/<portfolio-id>/<brand-id>/accepted.yaml
```

These files are loaded, validated, and snapshotted for traceability. They do not
implicitly change render prompts. A human or style producer must distill them
into a reviewed `brand.lock` proposal before they affect generation.

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
    size: [1920, 600]
```

Campaigns must not include style prompt fragments, palette, negative prompts, references, or provider params.

## Run Lock

`outputs/<campaign>/run.lock.json` stores reproducibility metadata:

- full brand lock snapshot
- portfolio/product metadata sidecar snapshots, when present
- full campaign snapshot
- resolved style
- prompt per asset
- seed and provider params
- sanitized provider metadata

It must never contain API keys, authorization headers, or raw image base64 payloads.

## Manifest

`outputs/<campaign>/manifest.json` is the consumer contract:

```json
{
  "schema_version": "1.0",
  "campaign": "feature-x-launch",
  "portfolio": {
    "id": "codefox",
    "name": "CodeFox",
    "version": "1.0.0"
  },
  "brand": {
    "id": "codefox",
    "name": "CodeFox",
    "version": "1.1.0"
  },
  "brand_lock_version": "1.1.0",
  "provider": {
    "gateway": "gpt-image-skill",
    "model": "gpt-image-2"
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

Published repo artifacts use the product repo's `published/` asset repository
or git submodule:

```text
published/portfolios/<portfolio-id>/<portfolio-version>/
published/products/<portfolio-id>/<brand-id>/<brand-lock-version>/artifacts/<campaign>/
```

Portfolio snapshots live in the same asset repository as product snapshots.
Manifest asset URLs update to `repo://...`.
