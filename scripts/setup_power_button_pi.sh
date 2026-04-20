#!/usr/bin/env bash
set -euo pipefail

echo "[ByteBite] Configuring Raspberry Pi shutdown button on GPIO26 (pin 37 -> GND)."

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ByteBite] ERROR: This script must run on Linux (your Pi), not on macOS/Windows."
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "[ByteBite] ERROR: sudo is required."
  exit 1
fi

CONFIG_FILE=""
for candidate in /boot/firmware/config.txt /boot/config.txt; do
  if [[ -f "$candidate" ]]; then
    CONFIG_FILE="$candidate"
    break
  fi
done

if [[ -z "$CONFIG_FILE" ]]; then
  echo "[ByteBite] ERROR: Could not find /boot/firmware/config.txt or /boot/config.txt."
  exit 1
fi

OVERLAY_LINE="dtoverlay=gpio-shutdown,gpio_pin=26,active_low=1,gpio_pull=up,debounce=200"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="${CONFIG_FILE}.bytebite-backup-${STAMP}"
TMP_FILE="$(mktemp)"

echo "[ByteBite] Using config file: ${CONFIG_FILE}"
echo "[ByteBite] Creating backup: ${BACKUP_FILE}"
sudo cp "${CONFIG_FILE}" "${BACKUP_FILE}"

echo "[ByteBite] Applying shutdown overlay..."
sudo awk -v overlay="${OVERLAY_LINE}" '
  /^[[:space:]]*#/ { print; next }
  /^[[:space:]]*dtoverlay=gpio-shutdown([[:space:]]*|,.*)$/ { next }
  { print }
  END {
    print ""
    print "# ByteBite shutdown button (GPIO26 -> GND)"
    print overlay
  }
' "${CONFIG_FILE}" > "${TMP_FILE}"

sudo cp "${TMP_FILE}" "${CONFIG_FILE}"
rm -f "${TMP_FILE}"

echo "[ByteBite] Verifying applied line..."
if sudo grep -Fqx "${OVERLAY_LINE}" "${CONFIG_FILE}"; then
  echo "[ByteBite] Success: shutdown button overlay is set."
else
  echo "[ByteBite] ERROR: overlay line not found after write."
  exit 1
fi

echo
echo "[ByteBite] Next step: reboot your Pi to activate this."
echo "  sudo reboot"
echo
echo "[ByteBite] Wiring reminder:"
echo "  - Button switch: GPIO26 (pin 37) <-> GND (pin 39 or 34)"
echo "  - Never wire 5V (pin 2) to GPIO26."
echo "  - If you also need wake-from-halt, wire a second momentary switch on GPIO3 pin 5 <-> GND pin 6."
