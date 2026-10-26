#!/usr/bin/env bash
# Back to the golden seed state: stop, wipe runtime state, start again.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

./stop.sh
info "wiping $STATE_DIR"
rm -rf "$STATE_DIR"
./start.sh
