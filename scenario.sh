#!/usr/bin/env bash
# Switch a lesson between its vulnerable and secure state, or the whole range.
#   ./scenario.sh list
#   ./scenario.sh show payrun-qtemp
#   ./scenario.sh set payrun-qtemp secure        (or vulnerable)
#   ./scenario.sh reset payrun-qtemp             (vulnerable again, exploit leftovers cleared)
#   ./scenario.sh mode secure                    (every lesson at once)
# A change needs the server stopped, so this stops it, changes the saved state and starts it again.
# Anyone signed on is signed off.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

[ -x .venv/bin/python ] || { bad "no .venv, run ./setup.sh first"; exit 1; }

case "${1:-}" in
  set|reset|mode)
    was_up=""
    if running_pid >/dev/null; then
      was_up=yes
      warn "stopping the server; open sessions end"
      ./stop.sh
    fi
    .venv/bin/python -m silverlake.scenarios "$@"
    rc=$?
    [ -n "$was_up" ] && ./start.sh
    exit $rc
    ;;
  *)
    exec .venv/bin/python -m silverlake.scenarios "$@"
    ;;
esac
