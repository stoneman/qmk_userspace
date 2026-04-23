# Repository guide for AI agents

This is a QMK userspace for an Ergodox EZ Glow (`ergodox_ez/glow`,
keymap `stoneman`).

## Layout

- [layouts/ergodox/stoneman/keymap.c](layouts/ergodox/stoneman/keymap.c) — the
  one and only keymap, 6 layers: Main, Func, Emoji, Num, Nav, Dota.
- [keyboards/ergodox/stoneman/](keyboards/ergodox/stoneman/) — board overrides
  (`config.h`, `keymap.c`, `rules.mk`).
- [tools/](tools/) — diagram generation pipeline. See
  [.github/instructions/image-pipeline.instructions.md](.github/instructions/image-pipeline.instructions.md)
  before touching anything in here.
- [images/](images/) — generated `layer_*.svg` (do not edit by hand) plus a
  couple of pre-existing static PNGs. Layer PNGs are written to the doxaid
  asset catalog, not here.
- [doxaid/](doxaid/) — git submodule (macOS menu-bar app that displays the
  layer images). `make install-doxaid` regenerates images and runs
  `doxaid/install.sh` to rebuild and install the app.
- [flash_stoneman.sh](flash_stoneman.sh) — flashes the firmware.

## Building / flashing

`flash_stoneman.sh` runs `make images` → `qmk compile` → `wally-cli` and
then prompts to reinstall doxaid. It locates the `qmk_firmware` checkout via
`$QMK_HOME` or `qmk config user.qmk_home` — set one of these on a fresh
machine. The image pipeline
([tools/gen_layer_images.py](tools/gen_layer_images.py)) uses the same lookup.
Sudo is primed up-front so the password prompt isn't buried in build output.

## Layer images

Regenerated automatically and verified in CI. Run `make images` to refresh,
`make check-images` to verify SVGs match the source. A pre-push hook
([.githooks/pre-push](.githooks/pre-push), installed via
`make install-hooks`) runs the check before pushing. PNG rasterisation is
macOS-only and writes into the doxaid submodule's asset catalog.
