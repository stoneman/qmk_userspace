#!/bin/bash

set -ex

QMK_USERSPACE="/Users/jonathan/git/stoneman/qmk_userspace"
QMK_FIRMWARE="/Users/jonathan/git/qmk/qmk_firmware"

qmk config user.overlay_dir="${QMK_USERSPACE}"

sudo echo "building..." # trigger sudo password entry early

(cd "${QMK_FIRMWARE}"; qmk compile -kb ergodox_ez/glow -km stoneman)

chmod a+x /usr/local/bin/wally-cli

echo "flashing..."

sudo wally-cli "${QMK_FIRMWARE}/ergodox_ez_glow_stoneman.hex"

rm "${QMK_FIRMWARE}/ergodox_ez_glow_stoneman.hex" # so it's not confusing next time we pull from upstream and the filename changes
