#!/usr/bin/env bash
set -euo pipefail

APP="/home/kali/ProductionProjectUI/src/app.py"
PY="/usr/bin/python3"
LOG="/tmp/bytebite.log"

cd /home/kali/ProductionProjectUI
echo "==== $(date -Is) bytebite client start ====" >> "$LOG"

need # Keep display awake: disable X screen saver and DPMS power-down.
if command -v xset >/dev/null 2>&1; then
  xset s off >> "$LOG" 2>&1 || true
  xset -dpms >> "$LOG" 2>&1 || true
  xset s noblank >> "$LOG" 2>&1 || true
fi

exec "$PY" -u "$APP" >> "$LOG" 2>&1
