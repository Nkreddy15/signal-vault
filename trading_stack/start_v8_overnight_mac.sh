#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

[[ -f .env ]] || {
  echo "Missing trading_stack/.env. Run the normal install first." >&2
  exit 2
}

echo "Building and starting isolated V8 overnight PAPER observer..."
docker compose --env-file .env --profile overnight build crypto_v8_overnight
docker compose --env-file .env --profile overnight rm -sf crypto_v8_overnight >/dev/null 2>&1 || true
docker compose --env-file .env --profile overnight up -d crypto_v8_overnight

PIDFILE="$ROOT/.caffeinate.pid"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
  echo "Mac keep-awake helper already running (PID $(cat "$PIDFILE"))."
else
  nohup /usr/bin/caffeinate -dimsu >/tmp/signal-vault-caffeinate.log 2>&1 &
  echo $! > "$PIDFILE"
  chmod 600 "$PIDFILE"
  echo "Started Mac keep-awake helper (PID $!)."
fi

sleep 3
echo
docker compose --env-file .env --profile overnight ps crypto_v8_overnight
echo
docker compose --env-file .env --profile overnight logs --tail=20 crypto_v8_overnight || true

echo
echo "V8 overnight PAPER observer is running for up to 8 hours."
echo "It uses public Kraken data only and cannot submit orders."
echo "The existing V1 PAPER bot is untouched."
echo "Status command: bash trading_stack/status_v8_overnight_mac.sh"
