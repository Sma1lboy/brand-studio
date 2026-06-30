---
repo:
  id: "codefox"
  name: "CodeFox"
version: "1.1.0"

producer:
  params:
    seed_strategy: "fixed"
    seed: 12345
    quality: "medium"
    timeout_seconds: 120
    retry_attempts: 3
    output_format: "png"

global:
  color:
    theme-primary: { $value: "#1A1A2E", $type: "color" }
    theme-accent: { $value: "#E94560", $type: "color" }
    bg-neutral: { $value: "#F5F5F0", $type: "color" }
  typography:
    primary-face: { $value: "clean geometric sans serif, high legibility", $type: "fontFamily" }
  style-fragment:
    base-aesthetic:
      $value: "premium editorial product visual, crisp geometry, controlled contrast, refined lighting, balanced negative space"
      $type: "text"
    mood-clean:
      $value: "clean minimal composition, precise edges, quiet confidence, no clutter"
      $type: "text"
  negative:
    global-exclude:
      $value: "low quality, blurry, distorted text, malformed logo, watermark, crowded layout, mismatched colors"
      $type: "text"
  reference:
    main-visual: { $value: "packages/branding/marketing/references/main_visual.png", $type: "asset" }

alias:
  style:
    launch-hero:
      $type: "composite"
      $value:
        prompt: "{global.style-fragment.base-aesthetic}, {global.style-fragment.mood-clean}"
        palette: ["{global.color.theme-primary}", "{global.color.theme-accent}"]
        typography: "{global.typography.primary-face}"
        negative: "{global.negative.global-exclude}"
        references: ["{global.reference.main-visual}"]
    social-default:
      $type: "composite"
      $value:
        prompt: "{global.style-fragment.base-aesthetic}"
        palette: ["{global.color.theme-primary}", "{global.color.bg-neutral}"]
        typography: "{global.typography.primary-face}"
        negative: "{global.negative.global-exclude}"
        references: []
---

# CodeFox Visual Theme

CodeFox visuals should feel like a precise developer tool that can turn rough
launch ideas into organized, versioned marketing artifacts.

Use sharp product geometry, clean technical typography, compact metadata
labels, and controlled contrast. Prefer calm editorial layouts over decorative
illustration. Reuse accepted repo assets and directory `asset-state.yaml` files
before proposing new directions.

Avoid noisy launch art, unrelated mascot variants, ornamental type, and
unreviewed scratch output.
