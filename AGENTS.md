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
- [images/](images/) — generated `layer_*.svg` and `layer_*.png` (do not
  edit by hand) plus a couple of pre-existing static PNGs.
- [flash_stoneman.sh](flash_stoneman.sh) — flashes the firmware.

## Building / flashing

`flash_stoneman.sh` shells out to `qmk flash`. It locates the `qmk_firmware`
checkout via `$QMK_HOME` or `qmk config user.qmk_home` — set one of these on
a fresh machine. The image pipeline
([tools/gen_layer_images.py](tools/gen_layer_images.py)) uses the same lookup.

## Layer images

Regenerated automatically and verified in CI. Run `make images` to refresh,
`make check-images` to verify they match the source. A pre-push hook
([.githooks/pre-push](.githooks/pre-push), installed via
`make install-hooks`) runs the check before pushing.
