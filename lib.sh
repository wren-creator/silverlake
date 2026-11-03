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

LAN_OK="${SILVERLAKE_ALLOW_LAN:-}"
case "$LAN_OK" in ''|0|off|no) LAN_OK="" ;; *) LAN_OK=1 ;; esac

# True for one private IPv4 address: 10.x, 172.16-31.x, 192.168.x, or link-local 169.254.x.
is_private_ipv4() {
  case "$1" in
    10.*|192.168.*|169.254.*|172.1[6-9].*|172.2[0-9].*|172.3[01].*) return 0 ;;
    *) return 1 ;;
  esac
}

# Fail unless the configured host is loopback, or a private LAN address with SILVERLAKE_ALLOW_LAN set. Never 0.0.0.0
# or a public address. The Python side refuses too; this is the second lock on the same door.
assert_loopback_only() {
  case "$HOST" in
    127.*|::1) return 0 ;;
  esac
  if [ -n "$LAN_OK" ] && is_private_ipv4 "$HOST"; then return 0; fi
  if [ -z "$LAN_OK" ]; then
    bad "refusing to continue: SILVERLAKE_HOST=$HOST is not loopback (./start.sh --lan ADDRESS opts in to a private LAN address)"
  else
    bad "refusing to continue: SILVERLAKE_HOST=$HOST is not a private IPv4 address (10.x, 172.16-31.x, 192.168.x)"
  fi
  return 1
}

running_pid() {
  [ -f "$PID_FILE" ] || return 1
  local pid; pid="$(cat "$PID_FILE")"
  kill -0 "$pid" 2>/dev/null && printf '%s' "$pid"
}
