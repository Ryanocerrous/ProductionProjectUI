#!/usr/bin/env bash
set -euo pipefail

echo "[ByteBite] GPIO setup for Kali on Raspberry Pi"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "[ByteBite] ERROR: This script must run on Linux (your Pi), not on macOS/Windows."
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[ByteBite] ERROR: apt-get not found. This script is for Debian/Kali-based systems."
  exit 1
fi

echo "[ByteBite] Installing base packages..."
sudo apt-get update
sudo apt-get install -y python3-gpiozero python3-rpi.gpio python3-libgpiod gpiod

echo "[ByteBite] Configuring gpiochip permissions for user access..."
sudo groupadd -f gpio
sudo usermod -aG gpio "${USER}"
printf '%s\n' 'SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-bytebite-gpio.rules >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger
sudo chgrp gpio /dev/gpiochip* 2>/dev/null || true
sudo chmod 660 /dev/gpiochip* 2>/dev/null || true

echo "[ByteBite] Verifying GPIO backends..."
python3 - <<'PY'
ok = True

try:
    import RPi.GPIO as GPIO
    print("[check] RPi.GPIO: OK")
except Exception as exc:
    print(f"[check] RPi.GPIO: WARN ({exc})")

try:
    import gpiod
    print("[check] gpiod import: OK")
except Exception as exc:
    ok = False
    print(f"[check] gpiod import: FAIL ({exc})")

try:
    settings = gpiod.LineSettings(
        direction=gpiod.line.Direction.INPUT,
        bias=gpiod.line.Bias.PULL_UP,
    )
    req = gpiod.request_lines(
        "/dev/gpiochip0",
        consumer="bytebite-setup-check",
        config={(22,): settings},
    )
    _ = req.get_value(22)
    req.release()
    print("[check] gpiod line request: OK")
except Exception as exc:
    ok = False
    print(f"[check] gpiod line request: FAIL ({exc})")

if not ok:
    raise SystemExit(1)
PY

echo "[ByteBite] Setup complete."
echo "[ByteBite] If this is your first run after group changes, log out/in (or reboot) once."
echo "[ByteBite] Next:"
echo "  1) python3 scripts/gpio_diagnostics.py"
echo "  2) python3 src/ui/offensive_menu.py"
