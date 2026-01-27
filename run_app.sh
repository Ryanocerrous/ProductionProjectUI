#!/usr/bin/env bash
set -e
cd /home/kali/ProductionProjectUI
# Always rebuild the venv on device to avoid macOS binaries being copied in
rm -rf .venv
python3 -m venv .venv || exit 0
.venv/bin/pip install --no-cache-dir --quiet --upgrade pip
.venv/bin/pip install --no-cache-dir --quiet ttkthemes Pillow ttkbootstrap

# Avoid multiple instances
if pgrep -f "/home/kali/ProductionProjectUI/src/app.py" >/dev/null; then
  exit 0
fi

# Prefer an existing X server (lightdm, etc.). Choose :0 or :1; if none, exit quietly.
DISPLAY_TARGET=""
if [ -S /tmp/.X11-unix/X0 ]; then
  DISPLAY_TARGET=":0"
elif [ -S /tmp/.X11-unix/X1 ]; then
  DISPLAY_TARGET=":1"
else
  exit 0
fi

APP_CMD="/home/kali/ProductionProjectUI/.venv/bin/python /home/kali/ProductionProjectUI/src/app.py"

exec env DISPLAY=$DISPLAY_TARGET XAUTHORITY=/home/kali/.Xauthority $APP_CMD >> /tmp/bytebite.log 2>&1
