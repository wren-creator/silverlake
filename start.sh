#!/usr/bin/env bash
# Bring Silverlake up. Refuses to launch if the listener would bind beyond
# loopback.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

[ -x .venv/bin/python ] || { bad "no .venv, run ./setup.sh first"; exit 1; }

info "loopback-only guard"
assert_loopback_only || { bad "not starting"; exit 1; }
ok "listener binds to $HOST only"

if pid="$(running_pid)"; then
  warn "already running (pid $pid)"
  exit 0
fi

mkdir -p "$STATE_DIR"
info "starting on $HOST:$PORT"
nohup .venv/bin/python -m silverlake >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"
sleep 1

if running_pid >/dev/null; then
  ok "Silverlake is up"
  echo "  5250 sign-on   $HOST:$PORT   (tn5250 $HOST:$PORT)"
  echo "  logs:          $LOG_FILE"
  echo "  reset to seed: ./reset.sh"
else
  bad "exited right away, see $LOG_FILE"
  tail -n 5 "$LOG_FILE" >&2
  rm -f "$PID_FILE"
  exit 1
fi
