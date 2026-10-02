#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

[[ -f .env ]] || {
  echo "Run: bash trading_stack/install_mac.sh" >&2
  exit 2
}

docker compose --env-file .env up -d

PIDFILE="$ROOT/.caffeinate.pid"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
  echo "Mac keep-awake helper already running (PID $(cat "$PIDFILE"))."
else
  nohup /usr/bin/caffeinate -dimsu >/tmp/open-source-paper-week-caffeinate.log 2>&1 &
  echo $! > "$PIDFILE"
  chmod 600 "$PIDFILE"
  echo "Started Mac keep-awake helper (PID $!)."
fi

echo "PAPER week is running."
echo "Crypto FreqUI: http://127.0.0.1:8080"
echo "Do not enable LIVE credentials or change dry_run during the evaluation week."
