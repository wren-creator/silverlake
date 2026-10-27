#!/usr/bin/env bash
# Score a Silverlake CTF submission.
#   ./check-flags.sh submission.txt     lines like  qsysopr-recon=FLAG{0123456789ab}
#   ./check-flags.sh --show             instructor only: every flag, state check and secure password
# Lessons whose win is a change (a profile made, authority granted) are read from the saved state, so
# nothing needs submitting for them. Works with the server running.
set -uo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "no .venv, run ./setup.sh first" >&2; exit 1; }
case "${1:-}" in
  --show) exec .venv/bin/python -m silverlake.flags show ;;
  -h|--help) sed -n '2,6p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) exec .venv/bin/python -m silverlake.flags check "${1:-submission.txt}" ;;
esac
