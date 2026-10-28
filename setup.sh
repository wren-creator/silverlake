#!/usr/bin/env bash
# One-time setup: a venv with Silverlake installed in editable mode.
set -euo pipefail
cd "$(dirname "$0")"
source ./lib.sh

# PYTHON=/path/to/python overrides. Otherwise the first of python3.14 .. python3.12, then python3, that is new enough.
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.14 python3.13 python3.12 python3; do
    if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 12))'; then PY="$c"; break; fi
  done
fi
[ -n "$PY" ] && command -v "$PY" >/dev/null || { bad "Python 3.12 or newer not found (set PYTHON=/path/to/python)"; exit 1; }
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 12))' \
  || { bad "$PY is older than 3.12 (set PYTHON=/path/to/python)"; exit 1; }

info "creating .venv"
"$PY" -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e '.[dev]'

# The ssh listener for the PASE shell needs asyncssh. Optional: ./setup.sh --ssh adds it, and without it the
# ssh port is simply not started.
case " $* " in *" --ssh "*) .venv/bin/pip install --quiet -e '.[ssh]' && ok "asyncssh installed (ssh listener available)" ;; esac

# The RPG runtime. Optional: Silverlake runs without it, and CALL on an RPG program says so.
if [ -d ../rpgle_library/python ]; then
  info "installing rpgle_library from ../rpgle_library (editable)"
  .venv/bin/pip install --quiet -e ../rpgle_library/python
elif .venv/bin/pip install --quiet 'rpgle_library @ git+https://github.com/wren-creator/rpgle_library#subdirectory=python' 2>/dev/null; then
  ok "installed rpgle_library from GitHub"
else
  info "rpgle_library not installed (no sibling folder, GitHub not reachable): RPG programs will not run"
fi
# The instance secret that flags and secure-state passwords come from. Kept at the repo root, never committed,
# and not wiped by reset.sh. Made once.
.venv/bin/python -m silverlake.flags init >/dev/null && ok "instance secret in place (.instance-secret)"
# The throwaway certificate behind the TLS ports (5250, the console, FTP, the sign-on server). Needs openssl;
# without it the TLS ports just do not start. ./setup.sh --force-tls makes a new one.
.venv/bin/python -m silverlake.net.certs $(case " $* " in *" --force-tls "*) echo --force ;; esac) \
  && ok "TLS certificate in place (.tls/)" || warn "no TLS certificate (openssl missing?), TLS ports will not start"
ok "ready. next: ./start.sh"
