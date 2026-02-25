#!/usr/bin/env bash
set -e
APP="/home/kali/ProductionProjectUI/src/app.py"
PY="/usr/bin/python3"
export BYTEBITE_DATA_DIR="${BYTEBITE_DATA_DIR:-/home/kali/bytebite-data}"
mkdir -p "$BYTEBITE_DATA_DIR/logs"

# If X is up, use it; otherwise start it with the app
if [ -S /tmp/.X11-unix/X0 ]; then
  DISPLAY_TARGET=":0"
elif [ -S /tmp/.X11-unix/X1 ]; then
  DISPLAY_TARGET=":1"
else
  [ -f /tmp/.X0-lock ] && rm -f /tmp/.X0-lock
  # Start a fresh X server on vt7 quietly; logs go to /tmp/xorg-bytebite.log
  exec /usr/bin/startx "$PY" "$APP" -- :0 -nolisten tcp vt7 -quiet > /tmp/xorg-bytebite.log 2>&1
fi

export DISPLAY="$DISPLAY_TARGET"
export XAUTHORITY="/home/kali/.Xauthority"

# Avoid multiple instances
if pgrep -f "$APP" >/dev/null; then
  exit 0
fi

exec "$PY" "$APP" >> /tmp/bytebite.log 2>&1
