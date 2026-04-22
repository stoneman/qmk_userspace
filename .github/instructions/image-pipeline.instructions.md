---
description: "How to work on the keymap-diagram generation pipeline (tools/, images/, keymap_drawer config). Use when: editing tools/gen_layer_images.py, tools/keymap_drawer_config.yaml, regenerating images/layer_*.svg, debugging missing key labels, transparent-key rendering, or CSS colour categories."
applyTo: "tools/**,images/**,Makefile,.github/workflows/check-images.yml,.githooks/pre-push"
---

# Layer-image generation pipeline

The pipeline turns [layouts/ergodox/stoneman/keymap.c](../../layouts/ergodox/stoneman/keymap.c)
into one SVG **and** one PNG per layer in [images/](../../images/). Driven by
[tools/gen_layer_images.py](../../tools/gen_layer_images.py) and configured by
[tools/keymap_drawer_config.yaml](../../tools/keymap_drawer_config.yaml).

## Required tooling

- **`qmk`** CLI, with `qmk config user.qmk_home` (or `QMK_HOME` env var)
  pointing at a `qmk_firmware` checkout. `qmk c2json` is run from inside that
  checkout — *not* this repo. Without it the pipeline cannot start.
- **`keymap-drawer`** ≥ 0.23.0, installed via `pipx install keymap-drawer`
  (the `keymap` CLI on `$PATH`). The script borrows PyYAML from this venv
  via `ensure_yaml()` — system `python3` does not need PyYAML installed.
- **`swift`** (Xcode command-line tools) for the SVG→PNG step. macOS only;
  on other platforms PNG generation is silently skipped.
- **No `librsvg`/`rsvg-convert`** — we don't use it. PNG rasterisation goes
  through WebKit via [tools/svg2png.swift](../../tools/svg2png.swift)
  because it's the only readily-available macOS SVG renderer that draws
  Apple Color Emoji in colour. `rsvg-convert` and CoreSVG both fall back
  to monochrome outlines.

## Pipeline stages (in `gen_layer_images.py`)

1. `qmk c2json --no-cpp` → `keymap.json`
2. `keymap parse -q keymap.json -l <layer names>` → YAML
3. **`extract_combos()` + `inject_combos()`** — combos are parsed out of
   `keymap.c` (keymap-drawer doesn't see them) and merged into the YAML.
4. **`resolve_transparent_keys()`** — substitutes the layer-0 binding into
   any `▽` (KC_TRANSPARENT) slots in higher layers and tags them
   `type: trans` so CSS can fade them. Without this, transparents render as
   bare triangles and you can't tell what falls through.
5. `keymap draw -s <layer name>` → one SVG per layer.
6. **`rasterize_to_png()`** — runs `swift tools/svg2png.swift` on each SVG
   to produce a 2× retina PNG (consumed by the doxaid macOS app, which
   uses `NSImageView` and an asset catalog). Skipped on non-macOS.

`--check` re-runs stages 1–5 into a tempdir and diffs the SVGs against
[images/](../../images/). PNGs are *not* diffed — font rasterisation is
not byte-stable across machines / OS versions, and CI runs on Linux where
the Swift step is skipped.

## Gotchas (we hit all of these)

- **`raw_binding_map` entries that set only `type:` render as blank keys.**
  Always pair with a `t:` label, e.g.
  `KC_PGUP: {t: "PgUp", type: "nav"}`. keymap-drawer's default labels are
  *not* applied when you provide a dict value.
- **CSS class is `rect.key.<type>`**, not `rect.keypos.<type>` and not
  `.key-<type>`. Inspect the generated SVG to confirm.
- **`dark_mode: true`** is baked in. `auto` emits a `prefers-color-scheme`
  media query that browsers honour but SVG rasterisers (and most embedders)
  ignore — colours then mismatch between viewers.
- **Transparent-key resolution is an approximation.** It assumes layer 0 is
  always active underneath. True for this keymap. If layering ever changes
  (e.g. base-layer toggle), revisit `resolve_transparent_keys()`.
- **Emoji glyphs render as monochrome outlines** in `librsvg` and Apple's
  CoreSVG. That's why we shell out to WebKit (`tools/svg2png.swift`) for
  the PNG step — it's the only macOS-native renderer that does colour
  emoji. Browsers also render the SVGs in colour. Don't switch the PNG
  step to `rsvg-convert` or NSImage's CoreSVG path.
- **`KC_TRANSPARENT` ≠ `KC_NO`.** `KC_NO` keys legitimately have no label
  and no inheritance — they appear dark and empty. That is correct.
- **GUI git clients (Fork, GitHub Desktop, …) run hooks with a sanitised
  PATH** that excludes `~/.local/bin` (pipx) and `/opt/homebrew/bin`. The
  pre-push hook prepends both — keep that `PATH=…` line in
  [.githooks/pre-push](../../.githooks/pre-push) when editing.

## Verification

```sh
make images        # regenerate
make check-images  # diff against committed
```

Both run via [.githooks/pre-push](../../.githooks/pre-push) (after
`make install-hooks`) and
[.github/workflows/check-images.yml](../../.github/workflows/check-images.yml).
The CI workflow installs `qmk` + `keymap-drawer` only — keep it that way.

## Don't

- Switch the PNG step to `rsvg-convert` / CoreSVG — colour emoji will
  break (see Gotchas).
- Hand-edit files in [images/](../../images/) — `make check-images` will
  fail on push.
- Add `librsvg` to CI.
