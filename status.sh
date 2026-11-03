#!/usr/bin/env bash
# Is it up, and is it still where it should be (loopback, or the one LAN address it was told to use). Re-audits the listener rather than
# trusting the config.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

if pid="$(running_pid)"; then
  ok "running (pid $pid)"
else
  warn "not running"
  exit 1
fi

listeners="$(lsof -nP -a -p "$pid" -iTCP -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $9}')"
if [ -z "$listeners" ]; then
  warn "no listening sockets yet"
  exit 0
fi

# A range started with --lan remembers its address in state/lan.host, so this audit knows what was asked for.
if [ -f "$STATE_DIR/lan.host" ]; then HOST="$(cat "$STATE_DIR/lan.host")"; LAN_OK=1; fi
rc=0
while read -r addr; do
  case "$addr" in
    127.*|\[::1\]*) ok "listening on $addr" ;;
    "$HOST":*) if [ -n "$LAN_OK" ] && is_private_ipv4 "$HOST"; then warn "listening on LAN address $addr (opted in)"; else bad "listening beyond loopback: $addr"; rc=1; fi ;;
    *) bad "listening beyond loopback: $addr"; rc=1 ;;
  esac
done <<<"$listeners"
exit $rc
