#!/usr/bin/env bash
set -euo pipefail

# One-command Mac helper:
# 1) Run forensic suite on Pi
# 2) Copy latest run + master workbook from USB to Mac
# 3) Open both Excel files on Mac

PI_HOST="${PI_HOST:-192.168.0.36}"
PI_USER="${PI_USER:-kali}"
PI_PROJECT_DIR="${PI_PROJECT_DIR:-/home/kali/ProductionProjectUI}"
SUITE_CONFIG="${SUITE_CONFIG:-scripts/test_suite_config.example.json}"
DEST_ROOT="${DEST_ROOT:-$HOME/Desktop/bytebite_forensic_tests_from_pi}"
USB_ROOT="${USB_ROOT:-/media/kali/BYTEBITE_USB/bytebite_forensic_tests}"

if ! command -v expect >/dev/null 2>&1; then
  echo "ERROR: 'expect' is required on macOS. Install it first."
  exit 1
fi

if [[ -z "${PI_PASS:-}" ]]; then
  read -r -s -p "Pi password for ${PI_USER}@${PI_HOST}: " PI_PASS
  echo
fi

export PI_HOST PI_USER PI_PASS

expect_ssh() {
  local remote_cmd="$1"
  REMOTE_CMD="$remote_cmd" expect <<'EOF'
set timeout -1
log_user 1
spawn ssh -tt -o StrictHostKeyChecking=no "$env(PI_USER)@$env(PI_HOST)" "$env(REMOTE_CMD)"
expect {
  -re "(?i)yes/no" { send "yes\r"; exp_continue }
  -re "(?i)password.*:" { send "$env(PI_PASS)\r"; exp_continue }
  eof
}
EOF
}

expect_scp() {
  local src="$1"
  local dst="$2"
  SRC="$src" DST="$dst" expect <<'EOF'
set timeout -1
log_user 1
spawn scp -o StrictHostKeyChecking=no -r "$env(SRC)" "$env(DST)"
expect {
  -re "(?i)yes/no" { send "yes\r"; exp_continue }
  -re "(?i)password.*:" { send "$env(PI_PASS)\r"; exp_continue }
  eof
}
set status [lindex [wait] 3]
if {$status != 0} {
  exit $status
}
EOF
}

expect_fetch_file() {
  local remote_path="$1"
  local local_path="$2"
  mkdir -p "$(dirname "$local_path")"
  rm -f "$local_path"
  REMOTE_PATH="$remote_path" LOCAL_PATH="$local_path" expect <<'EOF'
set timeout -1
log_user 1
set cmd "ssh -o StrictHostKeyChecking=no \"$env(PI_USER)@$env(PI_HOST)\" 'cat \"$env(REMOTE_PATH)\"' > \"$env(LOCAL_PATH)\""
spawn sh -lc $cmd
expect {
  -re "(?i)yes/no" { send "yes\r"; exp_continue }
  -re "(?i)password.*:" { send "$env(PI_PASS)\r"; exp_continue }
  eof
}
set status [lindex [wait] 3]
if {$status != 0} {
  exit $status
}
EOF
}

mkdir -p "$DEST_ROOT"

echo "[ByteBite] Running suite on Pi..."
RUN_OUTPUT="$(expect_ssh "cd \"$PI_PROJECT_DIR\" && sudo mkdir -p /media/kali/BYTEBITE_USB && sudo mount -t exfat -o uid=1000,gid=1000,umask=0022 /dev/sda1 /media/kali/BYTEBITE_USB 2>/dev/null || true && source .venv/bin/activate && python -u scripts/run_test_suite.py --suite-config \"$SUITE_CONFIG\"")"
printf "%s\n" "$RUN_OUTPUT"

RUN_PATH="$(printf '%s\n' "$RUN_OUTPUT" | tr -d '\r' | sed -n 's/^\[ByteBite\] Run directory: //p' | tail -n1)"

if [[ -z "$RUN_PATH" ]]; then
  echo "[ByteBite] Could not parse run directory from output, querying Pi..."
  QUERY_OUT="$(expect_ssh "ls -1dt \"$USB_ROOT\"/*-CASE-* 2>/dev/null | head -n1")"
  RUN_PATH="$(printf '%s\n' "$QUERY_OUT" | tr -d '\r' | grep -E '^/.*-CASE-.*$' | tail -n1 || true)"
fi

if [[ -z "$RUN_PATH" ]]; then
  echo "ERROR: Could not determine latest run path on Pi."
  exit 1
fi

RUN_ID="$(basename "$RUN_PATH")"
REMOTE_RUN="${PI_USER}@${PI_HOST}:${RUN_PATH}"
REMOTE_MASTER="${PI_USER}@${PI_HOST}:${USB_ROOT}/forensic_test_master.xlsx"

echo "[ByteBite] Copying run folder: $RUN_ID"
expect_scp "$REMOTE_RUN" "$DEST_ROOT/"

echo "[ByteBite] Copying master workbook"
expect_fetch_file "${USB_ROOT}/forensic_test_master.xlsx" "$DEST_ROOT/forensic_test_master.xlsx"

LOCAL_RUN_REPORT="$DEST_ROOT/$RUN_ID/reports/forensic_test_report.xlsx"
LOCAL_MASTER="$DEST_ROOT/forensic_test_master.xlsx"

echo "[ByteBite] Local run folder: $DEST_ROOT/$RUN_ID"
echo "[ByteBite] Local run report: $LOCAL_RUN_REPORT"
echo "[ByteBite] Local master: $LOCAL_MASTER"

if [[ ! -f "$LOCAL_RUN_REPORT" ]]; then
  echo "ERROR: Local run report was not copied."
  exit 1
fi
if [[ ! -f "$LOCAL_MASTER" ]]; then
  echo "ERROR: Local master workbook was not copied."
  exit 1
fi

if command -v open >/dev/null 2>&1; then
  [[ -f "$LOCAL_RUN_REPORT" ]] && open "$LOCAL_RUN_REPORT" || true
  [[ -f "$LOCAL_MASTER" ]] && open "$LOCAL_MASTER" || true
fi
