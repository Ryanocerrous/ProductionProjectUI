#!/usr/bin/env bash
set -euo pipefail
APP="/home/kali/ProductionProjectUI/src/app.py"
CLIENT="/home/kali/ProductionProjectUI/run_app_client.sh"
export BYTEBITE_DATA_DIR="${BYTEBITE_DATA_DIR:-/home/kali/bytebite-data}"
mkdir -p "$BYTEBITE_DATA_DIR/logs"

display_is_live() {
  local disp="$1"
  local num="${disp#:}"
  [ -S "/tmp/.X11-unix/X${num}" ] || return 1
  pgrep -f "(/usr/lib/xorg/Xorg|/usr/bin/X) ${disp}( |$)" >/dev/null 2>&1 || return 1
  return 0
}

cleanup_stale_display() {
  local disp="$1"
  local num="${disp#:}"
  if display_is_live "$disp"; then
    return 0
  fi
  [ -f "/tmp/.X${num}-lock" ] && rm -f "/tmp/.X${num}-lock"
  [ -S "/tmp/.X11-unix/X${num}" ] && rm -f "/tmp/.X11-unix/X${num}"
}

# If X is up, use it; otherwise start it with the app.
# A stale /tmp/.X11-unix/X0 socket can exist after a crash, so verify Xorg too.
if display_is_live ":0"; then
  DISPLAY_TARGET=":0"
elif display_is_live ":1"; then
  DISPLAY_TARGET=":1"
else
  cleanup_stale_display ":0"
  cleanup_stale_display ":1"
  # Start a fresh X server on vt7 quietly; logs go to /tmp/xorg-bytebite.log
  exec /usr/bin/startx "$CLIENT" -- :0 -nolisten tcp vt7 -quiet > /tmp/xorg-bytebite.log 2>&1
fi

export DISPLAY="$DISPLAY_TARGET"
export XAUTHORITY="/home/kali/.Xauthority"

# Avoid multiple instances
if pgrep -f "$APP" >/dev/null; then
  exit 0
fi

exec "$CLIENT"
