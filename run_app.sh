#!/usr/bin/env bash
set -e

APP="/home/kali/ProductionProjectUI/src/app.py"
PY="/usr/bin/python3"

# Use an existing X server; if none, exit quietly (service will be restarted later).
if [ -S /tmp/.X11-unix/X0 ]; then
  export DISPLAY=":0"
elif [ -S /tmp/.X11-unix/X1 ]; then
  export DISPLAY=":1"
else
  exit 0
fi

export XAUTHORITY="/home/kali/.Xauthority"

# Avoid multiple instances
if pgrep -f "$APP" >/dev/null; then
  exit 0
fi

exec "$PY" "$APP" >> /tmp/bytebite.log 2>&1
