#!/usr/bin/env bash
# Is it up, and is it still loopback only. Re-audits the listener rather than
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

rc=0
while read -r addr; do
  case "$addr" in
    127.*|\[::1\]*) ok "listening on $addr" ;;
    *) bad "listening beyond loopback: $addr"; rc=1 ;;
  esac
done <<<"$listeners"
exit $rc
