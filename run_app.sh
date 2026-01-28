#!/usr/bin/env bash
set -e
APP="/home/kali/ProductionProjectUI/src/app.py"
PY="/usr/bin/python3"

# Wait for an existing X server (up to ~20s)
for i in $(seq 1 40); do
  if [ -S /tmp/.X11-unix/X0 ]; then
    DISPLAY_TARGET=":0"; break
  elif [ -S /tmp/.X11-unix/X1 ]; then
    DISPLAY_TARGET=":1"; break
  fi
  sleep 0.5
done

# If no display, exit; systemd will retry later
if [ -z "${DISPLAY_TARGET:-}" ]; then
  exit 0
fi

export DISPLAY="$DISPLAY_TARGET"
export XAUTHORITY="/home/kali/.Xauthority"

# Avoid multiple instances
if pgrep -f "$APP" >/dev/null; then
  exit 0
fi

exec "$PY" "$APP" >> /tmp/bytebite.log 2>&1
