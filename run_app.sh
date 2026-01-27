#!/usr/bin/env bash
set -e
cd /home/kali/ProductionProjectUI
# Always rebuild the venv on device to avoid macOS binaries being copied in
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet ttkbootstrap ttkthemes Pillow

# Prefer an existing X server (lightdm, etc.). Fallback to :1 if :0 not available.
DISPLAY_TARGET=":0"
if [ ! -S /tmp/.X11-unix/X0 ] && [ -S /tmp/.X11-unix/X1 ]; then
  DISPLAY_TARGET=":1"
fi

APP_CMD="/home/kali/ProductionProjectUI/.venv/bin/python /home/kali/ProductionProjectUI/src/app.py"

# If no X server is running, start a temporary one just for the app.
if [ ! -S /tmp/.X11-unix/X0 ] && [ ! -S /tmp/.X11-unix/X1 ]; then
  exec /usr/bin/startx $APP_CMD -- :0 -nolisten tcp vt1 -keeptty
fi

exec env DISPLAY=$DISPLAY_TARGET XAUTHORITY=/home/kali/.Xauthority $APP_CMD
