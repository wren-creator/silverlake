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
ok "ready. next: ./start.sh"
