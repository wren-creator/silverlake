#!/usr/bin/env bash
# Shared helpers for the Silverlake lifecycle scripts. Sourced, not run.

if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_BLU=$'\033[34m'; C_RST=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_BLU=""; C_RST=""
fi

info() { printf '%s[*]%s %s\n' "$C_BLU" "$C_RST" "$*"; }
ok()   { printf '%s[+]%s %s\n' "$C_GRN" "$C_RST" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_YEL" "$C_RST" "$*"; }
bad()  { printf '%s[x]%s %s\n' "$C_RED" "$C_RST" "$*" >&2; }

STATE_DIR="${SILVERLAKE_STATE_DIR:-state}"
PID_FILE="$STATE_DIR/silverlake.pid"
LOG_FILE="$STATE_DIR/silverlake.log"
HOST="${SILVERLAKE_HOST:-127.0.0.1}"
PORT="${SILVERLAKE_PORT:-5250}"

# Fail unless the configured host is a loopback address. The Python side
# refuses too; this is the second lock on the same door.
assert_loopback_only() {
  case "$HOST" in
    127.*|::1) return 0 ;;
    *) bad "refusing to continue: SILVERLAKE_HOST=$HOST is not loopback"; return 1 ;;
  esac
}

running_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid; pid="$(cat "$PID_FILE")"
  kill -0 "$pid" 2>/dev/null && printf '%s' "$pid"
}
