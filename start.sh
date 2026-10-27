#!/usr/bin/env bash
# Bring Silverlake up. Refuses to launch if the listener would bind beyond
# loopback.
set -uo pipefail
cd "$(dirname "$0")"
source ./lib.sh

usage() {
  echo "usage: ./start.sh [-p PORT | --port PORT] [--services]"
  echo "  Listens on 127.0.0.1, default port 5250. SILVERLAKE_PORT does the same."
  echo "  --services also starts the network services (HTTP Admin 2001, FTP 2121, host servers 4449 and 8476), loopback only."
  echo "  SILVERLAKE_SERVICES=1 does the same, and ./scenario.sh keeps it across its restart."
}

SERVICES_MARK="$STATE_DIR/services.on"
SERVICES="${SILVERLAKE_SERVICES:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    -p|--port)
      [ $# -ge 2 ] || { bad "$1 needs a port number"; usage >&2; exit 2; }
      PORT="$2"; shift 2 ;;
    --port=*) PORT="${1#--port=}"; shift ;;
    --services) SERVICES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) bad "unknown option: $1"; usage >&2; exit 2 ;;
  esac
done
case "$PORT" in
  ''|*[!0-9]*) bad "port must be a number, not '$PORT'"; exit 2 ;;
esac
{ [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ]; } || { bad "port must be between 1 and 65535, not $PORT"; exit 2; }
export SILVERLAKE_PORT="$PORT"
mkdir -p "$STATE_DIR"
case "$SERVICES" in
  ''|0|off|no) SERVICES=""; rm -f "$SERVICES_MARK" ;;
  *) SERVICES=1; export SILVERLAKE_SERVICES=1; : >"$SERVICES_MARK" ;;
esac

[ -x .venv/bin/python ] || { bad "no .venv, run ./setup.sh first"; exit 1; }

info "loopback-only guard"
assert_loopback_only || { bad "not starting"; exit 1; }
ok "listener binds to $HOST only"

if pid="$(running_pid)"; then
  warn "already running (pid $pid)"
  exit 0
fi

mkdir -p "$STATE_DIR"
if .venv/bin/python -c "import socket; socket.create_connection(('$HOST', $PORT), 0.5).close()" 2>/dev/null; then
  bad "port $PORT is already in use. Pick another: ./start.sh --port $((PORT + 1))"
  exit 1
fi
if [ -n "$SERVICES" ]; then
  for spec in "HTTP Admin:${SILVERLAKE_HTTPADMIN_PORT:-2001}:SILVERLAKE_HTTPADMIN_PORT" "FTP:${SILVERLAKE_FTP_PORT:-2121}:SILVERLAKE_FTP_PORT" "Host server mapper:${SILVERLAKE_MAPPER_PORT:-4449}:SILVERLAKE_MAPPER_PORT" "Sign-on server:${SILVERLAKE_SIGNON_PORT:-8476}:SILVERLAKE_SIGNON_PORT"; do
    IFS=: read -r svc svc_port svc_var <<<"$spec"
    if .venv/bin/python -c "import socket; socket.create_connection(('$HOST', $svc_port), 0.5).close()" 2>/dev/null; then
      bad "port $svc_port ($svc) is already in use. Set $svc_var to another"
      exit 1
    fi
  done
fi
info "starting on $HOST:$PORT"
nohup .venv/bin/python -m silverlake >"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

# Wait for our own process to say it is listening. Watching for the PID alone misses a crash
# that lands after a short sleep, and probing the port alone can be fooled by something else
# already holding it.
listening=""
for _ in $(seq 1 50); do
  running_pid >/dev/null || break
  if grep -q "listening on" "$LOG_FILE" 2>/dev/null; then
    listening=yes
    break
  fi
  sleep 0.1
done

if [ -n "$listening" ]; then
  ok "Silverlake is up"
  echo "  5250 sign-on   $HOST:$PORT   (tn5250 $HOST:$PORT)"
  [ -n "$SERVICES" ] && echo "  HTTP Admin     $HOST:${SILVERLAKE_HTTPADMIN_PORT:-2001}   (http://$HOST:${SILVERLAKE_HTTPADMIN_PORT:-2001}/HTTPAdmin)"
  [ -n "$SERVICES" ] && echo "  FTP            $HOST:${SILVERLAKE_FTP_PORT:-2121}   (ftp $HOST ${SILVERLAKE_FTP_PORT:-2121})"
  [ -n "$SERVICES" ] && echo "  Host servers   $HOST:${SILVERLAKE_MAPPER_PORT:-4449} (mapper), $HOST:${SILVERLAKE_SIGNON_PORT:-8476} (sign-on)"
  echo "  logs:          $LOG_FILE"
  echo "  reset to seed: ./reset.sh"
else
  bad "did not start listening on $HOST:$PORT, see $LOG_FILE"
  tail -n 5 "$LOG_FILE" >&2
  if pid="$(running_pid)"; then kill "$pid" 2>/dev/null; fi
  rm -f "$PID_FILE"
  exit 1
fi
