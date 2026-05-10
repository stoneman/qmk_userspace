#!/bin/bash

set -e

# Trigger sudo password entry up-front so the prompt doesn't get buried
# in build output later. (wally-cli needs root to talk to the keyboard.)
sudo -v

set -x

QMK_USERSPACE="$(cd "$(dirname "$0")" && pwd)"

# Resolve qmk_firmware location: $QMK_HOME (the var the qmk CLI itself
# honours) or `qmk config user.qmk_home`.
QMK_FIRMWARE="${QMK_HOME:-}"
if [ -z "${QMK_FIRMWARE}" ]; then
    QMK_FIRMWARE="$(qmk config -ro user.qmk_home 2>/dev/null | sed 's/^user\.qmk_home=//')"
fi
if [ -z "${QMK_FIRMWARE}" ] || [ "${QMK_FIRMWARE}" = "None" ] || [ ! -d "${QMK_FIRMWARE}/lib/python/qmk" ]; then
    echo "error: cannot find qmk_firmware. Set QMK_HOME env var or run" >&2
    echo "       \`qmk config user.qmk_home=/path/to/qmk_firmware\`." >&2
    exit 1
fi

qmk config user.overlay_dir="${QMK_USERSPACE}"

(cd "${QMK_USERSPACE}" && make images)

(cd "${QMK_FIRMWARE}"; qmk compile -kb ergodox_ez/glow -km stoneman)

chmod a+x /usr/local/bin/wally-cli

echo "flashing..."

sudo wally-cli "${QMK_FIRMWARE}/ergodox_ez_glow_stoneman.hex"

rm "${QMK_FIRMWARE}/ergodox_ez_glow_stoneman.hex" # so it's not confusing next time we pull from upstream and the filename changes

set +x

DOXAID_INSTALL="${QMK_USERSPACE}/doxaid/install.sh"
if [ -x "${DOXAID_INSTALL}" ]; then
    printf '\nUpdate doxaid? [y/N] '
    read -r reply </dev/tty
    case "${reply}" in
        [yY]|[yY][eE][sS])
            "${DOXAID_INSTALL}"
            ;;
        *)
            echo "Skipping doxaid update."
            ;;
    esac
fi
