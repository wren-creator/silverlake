#!/usr/bin/env bash
# Back to the golden seed state: stop, wipe runtime state, start again.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

lan=(); [ ! -f "$STATE_DIR/lan.host" ] || lan=(--lan "$(cat "$STATE_DIR/lan.host")")
./stop.sh
info "wiping $STATE_DIR"
rm -rf "$STATE_DIR"
./start.sh ${lan[@]+"${lan[@]}"}
