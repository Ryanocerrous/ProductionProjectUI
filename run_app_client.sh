#!/usr/bin/env bash
set -euo pipefail

APP="/home/kali/ProductionProjectUI/src/app.py"
PY="/usr/bin/python3"
LOG="/tmp/bytebite.log"

cd /home/kali/ProductionProjectUI
echo "==== $(date -Is) bytebite client start ====" >> "$LOG"
exec "$PY" -u "$APP" >> "$LOG" 2>&1
