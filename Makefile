.SILENT:

MAKEFLAGS += --no-print-directory

QMK_USERSPACE := $(patsubst %/,%,$(dir $(shell realpath "$(lastword $(MAKEFILE_LIST))")))
ifeq ($(QMK_USERSPACE),)
    QMK_USERSPACE := $(shell pwd)
endif

QMK_FIRMWARE_ROOT = $(shell qmk config -ro user.qmk_home 2>/dev/null | cut -d= -f2 | sed -e 's@^None$$@@g')

.PHONY: images check-images install-hooks

# Regenerate images/layer_*.svg from layouts/ergodox/stoneman/keymap.c.
# Requires: qmk (in a qmk_firmware checkout), keymap-drawer.
# Set QMK_HOME if `qmk config user.qmk_home` is not configured.
images:
	python3 $(QMK_USERSPACE)/tools/gen_layer_images.py

# Exit non-zero if `make images` would change anything in images/.
# Used by the pre-push hook and CI.
check-images:
	python3 $(QMK_USERSPACE)/tools/gen_layer_images.py --check

# Point git at .githooks/ so the pre-push image-freshness check is active.
# One-time setup per clone. Bypass with `git push --no-verify` when needed.
install-hooks:
	git -C $(QMK_USERSPACE) config core.hooksPath .githooks
	@echo "Hooks installed. Bypass with: git push --no-verify"

%:
	$(if $(QMK_FIRMWARE_ROOT),,$(error Cannot determine qmk_firmware location. `qmk config -ro user.qmk_home` is not set))
	+$(MAKE) -C $(QMK_FIRMWARE_ROOT) $(MAKECMDGOALS) QMK_USERSPACE=$(QMK_USERSPACE)
