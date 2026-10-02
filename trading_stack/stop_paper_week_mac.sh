#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

docker compose down

PIDFILE="$ROOT/.caffeinate.pid"
if [[ -f "$PIDFILE" ]]; then
  pid="$(cat "$PIDFILE")"
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" || true
  fi
  rm -f "$PIDFILE"
fi

echo "PAPER week stack stopped. Persistent Freqtrade data remains in the Docker volume."
