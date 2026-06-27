# Brand Studio Skill

[简体中文](README.zh-CN.md)

Brand Studio is an installable agent skill for producing theme-locked
marketing assets from a product repository. It validates repo visual tokens,
prepares campaigns, exports producer-ready dry-run context, and records only
user-accepted assets into repo-owned visual asset state.

This repo ships one installable skill payload plus maintainer tooling:

- `skills/brand-studio/`: the installable skill payload.

The runtime used by agents is bundled under `skills/brand-studio/scripts/`.
There is no top-level `src/` package in the skill shape.

## Recommended Sharing Model

For real personal or team use, fork this repository and clone or install from
your own fork. Treat `sma1lboy/brand-studio` as the generic upstream;
treat `your-user/brand-studio` or `your-org/brand-studio` as the
shared source of truth for your metadata, policy, producer preferences,
templates, and install notes.

Product repos should pin that fork through a submodule, tag, or local install.
Keep product-specific `theme.md`, campaigns, accepted state, and public assets
inside the product repo or its asset repo. Keep cross-person or cross-repo
defaults in the fork so teammates can pull the same skill behavior.

## What The Skill Does

Brand Studio keeps style, campaign content, production, and accepted state
separate:

```text
repo visual state -> production plan -> candidates -> user acceptance -> accepted state -> next production
```

The skill helps an agent:

- read a YAML/JSON metadata file that declares repo paths and policy.
- read organization, repo, related-repo, and directory asset state before planning.
- validate `theme.md` frontmatter and campaign files.
- run dry-run renders without spending API credits.
- hand dry-run context to user-selected producer skills for live assets.
- require human asset review before state updates.
- copy accepted files into approved assets and update `accepted.yaml`.

Downstream apps consume accepted files and manifests. They do not run
generation, and scratch candidates are not visual memory.

## Use

Open a product repo, then mention the skill in the task. For a new visual
system, the preferred start is to provide brand images or let the agent scan the
repo's declared asset roots and create the first Brand Studio files:

```text
$brand-studio init this repo from the attached brand images
$brand-studio init this repo from existing repo assets
$brand-studio bootstrap this repo for a new product visual system
$brand-studio validate the CodeFox example campaign
$brand-studio create a campaign for a launch poster, dry-run first
$brand-studio render this campaign with the current theme, then wait for review
$brand-studio record the accepted launch banner into visual asset state
```

During image-first init, the agent uses its own image-reading capability to
derive the initial palette, typography direction, visual language, avoid list,
and style aliases. If no images are attached, it scans the declared asset roots
once for image files instead of requiring a separate init-assets path or role
schema. It writes `marketing.harness.yaml`, `assets/marketing/brief.md`,
`assets/marketing/theme.md`, a preview campaign, and initial state files, then
runs the existing launcher for validation and dry-run rendering. The harness
itself does not analyze images or call vision APIs.

The installed skill contains a launcher:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata marketing.harness.yaml ...
```

The launcher keeps paths rooted in the current product repo and runs the bundled
scripts in the installed skill. It does not call `uvx` or discover a parent
runtime checkout. YAML metadata requires PyYAML; use `uv run python ...` from
this checkout or run `uv sync` before invoking the launcher directly.

## Repo Shape

The product repo owns its asset hierarchy. Paths should come from metadata, not
a hard-coded root layout. One common shape is:

```text
assets/marketing/
  theme.md
  campaigns/
  references/
  proposals/
  plans/
  asset-state.yaml
  accepted.yaml
public/marketing/
  <channel-or-format>/
    asset-state.yaml
  <approved assets and manifests>
.harness/marketing/out/
```

- `project.marketingRoot` is editable source input: theme notes, campaign YAML,
  proposals, references, and accepted-work notes.
- `artifacts.scratch` is the local render buffer.
- `artifacts.approved` is the reviewed asset path, asset repo, or submodule target.
- `state.assetIndex` is the repo-level visual asset memory.
- `state.accepted` is the durable accepted corpus used by future planning.
- `state.directoryStateFile` is the per-directory memory filename, usually
  `asset-state.yaml`.
- `sources.relatedRepos` points at same-org repos whose accepted state should
  inform this repo's production.

Before producing banners, landscape visuals, slide/PPT backgrounds, logo-theme
variants, X/XHS cards, or social images, run the read-only state preflight and
use that output in the production plan:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata path/to/marketing.harness.yaml state
```

After the user accepts exact live candidates, agents may use the internal
`accept` helper to copy files from scratch into `artifacts.approved`, generate
an approved manifest from the real file, and update accepted state. The helper
does not run git commands and is not an asset collection workflow for
unreviewed files.

Release-version marketing starts with a copy asset. The launcher reads release
entries from standard `CHANGELOG.md` locations, summarizes them into
`copy.yaml`, then turns that copy asset into a normal campaign and producer
context. It reads only the latest release by default; pass `--releases 4` to
build a recent-release notes page from the latest four versions. Release
producer prompts make the release notes page the main subject: header, metadata
chips, version headings, and changelog rows. They should not treat the changelog
as a small side panel on a generic product hero. The launcher checks the repo
root and package directories. The editable `copy.yaml` exposes `releases[]` as
the canonical text asset; it does not write a separate `key_points` block.

Generate only the text asset when you want to review or revise the wording:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata path/to/marketing.harness.yaml \
  release-copy --write --releases 4
```

Run the full release prep flow when the copy, campaign, dry-run context, and
external-producer handoff should be created together. If `copy.yaml` already
exists, the renderer uses that revised copy asset instead of regenerating it
from the changelog. The resulting `producer-context.json` is the handoff to the
metadata-selected image producer skill:

```bash
python3 "$SKILL_ROOT/scripts/harness.py" --project-root "$PWD" \
  --metadata path/to/marketing.harness.yaml \
  release-render --releases 4
```

## Theme Contract

`theme.md` is the single source of truth for a repo's visual direction. YAML
frontmatter stores machine-readable style tokens and producer hints; the
Markdown body explains the design direction for humans and agents.

Campaign files can only choose a locked style alias and provide current content:
headline, subject, and deliverable sizes. They must not inline prompts,
palettes, negative prompts, reference images, model names, or producer params.

## Producer Capabilities

Third-party producer skills are managed as local capabilities declared in
metadata, not dependencies bundled by Brand Studio. The `skills` map binds each
capability key (`image`, `design`, `slide`, `logo`, `social`) directly to a
locally installed producer skill name. The agent must not auto-install or
silently switch producers.

## Human Review

Live generation approval and asset approval are different. The skill should
dry-run first, ask before spending API credits, pass the exported context to the
selected producer only after approval, then show generated files for review.
Accepted state should change only after the user or reviewer explicitly accepts
exact files or asset ids.

## Verification

```bash
uv run ruff check .
uv run pytest
cd skills/brand-studio/examples/codefox
uv run python ../../scripts/harness.py --project-root "$PWD" --metadata marketing.harness.yaml validate
```

Use the checked-in skill payload directly through a fork, submodule, or local
skill install.
