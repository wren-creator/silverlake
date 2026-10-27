#!/usr/bin/env bash
# One-time setup: a venv with Silverlake installed in editable mode.
set -euo pipefail
cd "$(dirname "$0")"
source ./lib.sh

command -v python3 >/dev/null || { bad "python3 not found"; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' \
  || { bad "Python 3.12 or newer required"; exit 1; }

info "creating .venv"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e '.[dev]'

# The RPG runtime. Optional: Silverlake runs without it, and CALL on an RPG program says so.
if [ -d ../rpgle_library/python ]; then
  info "installing rpgle_library from ../rpgle_library (editable)"
  .venv/bin/pip install --quiet -e ../rpgle_library/python
elif .venv/bin/pip install --quiet 'rpgle_library @ git+https://github.com/wren-creator/rpgle_library#subdirectory=python' 2>/dev/null; then
  ok "installed rpgle_library from GitHub"
else
  info "rpgle_library not installed (no sibling folder, GitHub not reachable): RPG programs will not run"
fi
ok "ready. next: ./start.sh"
