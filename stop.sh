#!/usr/bin/env bash
# Stop Silverlake.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

if pid="$(running_pid)"; then
  kill "$pid" && ok "stopped (pid $pid)"
else
  info "not running"
fi
rm -f "$PID_FILE"
