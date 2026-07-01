---
repo:
  id: "kobe"
  name: "kobe"
version: "1.0.5"

producer:
  model: "gpt-image-2"
  params:
    seed_strategy: "per_asset"
    seed: 20260618
    quality: "high"
    timeout_seconds: 180
    retry_attempts: 2
    output_format: "png"

global:
  color:
    ink: { $value: "#191713", $type: "color" }
    paper: { $value: "#F7F1E8", $type: "color" }
    lunar-dust: { $value: "#D8C8B0", $type: "color" }
    warm-stone: { $value: "#D8C8B0", $type: "color" }
    clay: { $value: "#D87857", $type: "color" }
    shell: { $value: "#EBBBAC", $type: "color" }
    graphite: { $value: "#3A342D", $type: "color" }
    copper: { $value: "#A85E34", $type: "color" }
    terminal: { $value: "#11161C", $type: "color" }
    signal-blue: { $value: "#2F6F9F", $type: "color" }
  typography:
    display-face:
      $value: "large crisp lowercase warm grotesk title typography, restrained tracking, highly legible launch copy"
      $type: "fontFamily"
    terminal-face:
      $value: "monospaced terminal UI typography, compact pane labels, readable task names, no fake paragraph walls"
      $type: "fontFamily"
  style-fragment:
    clean-product-promo:
      $value: "restrained product launch poster for a terminal developer tool, no narrative scene, no characters, no props. Use a simple editorial composition: matte dark graphite background, one large real terminal product surface, warm clay accents, generous negative space, and a clear poster-like headline/subtitle lockup"
      $type: "text"
    lunar-field-computing:
      $value: "cinematic lunar field-computing launch image, moon surface as the environment around the product, rugged terminal workstation, suited adult mission operator using the terminal, Earth glow in the black sky, believable lunar hardware, antenna mast, lander struts, cable harnesses, dust, hard vacuum shadows"
      $type: "text"
    tui-product-focus:
      $value: "use the provided kobe TUI screenshot as the canonical product reference. Preserve the actual layout language: full-height left task rail, large central engine pane, right column split into file tree above and shell pane below, thin tmux borders, dark graphite panels, clay-orange focus lines and labels, muted gray monospace text"
      $type: "text"
    warm-technical-palette:
      $value: "warm paper and stone background tones, clay and shell highlights, graphite and ink terminal panels, one restrained blue signal accent, quiet premium technology mood, not neon cyberpunk"
      $type: "text"
    launch-hierarchy:
      $value: "wide product hero card. Place the exact lowercase word \"kobe\" very large and poster-like, fully inside a top-left safe area with visible margin, no cropped letters. Put secondary copy \"parallel agents, one terminal\" directly below at smaller size. The real terminal screenshot is the dominant product surface."
      $type: "text"
    product-craft:
      $value: "ordinary clean promotional image, product-first framing, screenshot shown in a precise terminal window or floating screen plane with subtle shadow, sharp foreground, crisp UI structure, restrained texture, no people, no moon, no hardware, no cinematic environment"
      $type: "text"
  negative:
    clean-exclude:
      $value: "cropped headline, cropped kobe wordmark, letters cut off at the frame edge, astronaut, moon, lunar surface, planet, lander, rocket, helmet, human character, robot mascot, official Anthropic logo, standalone Claude logo outside the terminal UI, fake sponsor logos, basketball imagery, glossy SaaS cards, browser chrome, generic hologram dashboard, unreadable terminal gibberish, excessive neon, purple-blue gradient, malformed main headline, watermark"
      $type: "text"
    global-exclude:
      $value: "cropped headline, cropped kobe wordmark, letters cut off at the frame edge, huge foreground astronaut helmet, person touching frame edges, official Anthropic logo, standalone Claude logo outside the terminal UI, basketball imagery, celebrity likeness, robot mascot, glossy SaaS cards, browser chrome, unreadable terminal gibberish, excessive neon, malformed main headline, watermark"
      $type: "text"
  reference:
    # References live in the kobe PRODUCT repo, not this org skill repo. They are
    # declared as product-repo paths (the runtime uses them as prompt strings, not
    # files), so no product asset is embedded here.
    clean-tui: { $value: "kobe:workspace/products/kobe/kobe/references/kobe-tui-clean.png", $type: "asset" }
    actual-tui: { $value: "kobe:workspace/products/kobe/kobe/references/kobe-tui-actual.png", $type: "asset" }

alias:
  style:
    clean-product-hero:
      $type: "composite"
      $value:
        prompt: "{global.style-fragment.clean-product-promo}, {global.style-fragment.tui-product-focus}, {global.style-fragment.warm-technical-palette}, {global.style-fragment.launch-hierarchy}, {global.style-fragment.product-craft}"
        palette:
          - "{global.color.ink}"
          - "{global.color.paper}"
          - "{global.color.warm-stone}"
          - "{global.color.clay}"
          - "{global.color.shell}"
          - "{global.color.graphite}"
          - "{global.color.terminal}"
          - "{global.color.signal-blue}"
        typography: "{global.typography.display-face}; {global.typography.terminal-face}"
        negative: "{global.negative.clean-exclude}"
        references: ["{global.reference.clean-tui}"]
    lunar-launch-hero:
      $type: "composite"
      $value:
        prompt: "{global.style-fragment.lunar-field-computing}, {global.style-fragment.tui-product-focus}, {global.style-fragment.warm-technical-palette}, {global.style-fragment.launch-hierarchy}"
        palette:
          - "{global.color.ink}"
          - "{global.color.paper}"
          - "{global.color.lunar-dust}"
          - "{global.color.clay}"
          - "{global.color.shell}"
          - "{global.color.graphite}"
          - "{global.color.copper}"
          - "{global.color.signal-blue}"
        typography: "{global.typography.display-face}; {global.typography.terminal-face}"
        negative: "{global.negative.global-exclude}"
        references: ["{global.reference.actual-tui}"]
---

# kobe Visual Theme

kobe is a local-first terminal UI for running many parallel AI coding sessions
as git worktrees, tmux sessions, and branches. Its visuals must make the
terminal product unmistakable: real TUI panes (task rail, engine pane, file
tree, shell), tmux borders, compact status chips, warm clay accents.

Two style families share this brand base but never cross composition:
`clean-product-hero` (product-first, no scene) and `lunar-launch-hero`
(cinematic lunar field-computing). Palette is warm off-white, clay, shell,
graphite, ink, copper with one restrained blue signal accent — calm premium
technology, never neon cyberpunk.

Avoid official Claude/Anthropic marks, basketball imagery, robot mascots,
glossy SaaS cards, and illegible terminal gibberish.
