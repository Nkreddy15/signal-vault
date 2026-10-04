#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

[[ -f .env ]] || {
  echo "Missing trading_stack/.env. Run the normal install first." >&2
  exit 2
}

echo "Stopping the older single-candidate overnight observer if it exists..."
docker compose --env-file .env --profile overnight stop crypto_v8_overnight >/dev/null 2>&1 || true

echo "Building the multi-candidate V8 forward lab..."
docker compose --env-file .env --profile forwardlab build crypto_v8_forward_lab

echo "Starting forward lab..."
docker compose --env-file .env --profile forwardlab up -d crypto_v8_forward_lab

PIDFILE="$ROOT/.caffeinate.pid"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" >/dev/null 2>&1; then
  echo "Mac keep-awake helper already running (PID $(cat "$PIDFILE"))."
else
  nohup /usr/bin/caffeinate -dimsu >/tmp/signal-vault-caffeinate.log 2>&1 &
  echo $! > "$PIDFILE"
  chmod 600 "$PIDFILE"
  echo "Started Mac keep-awake helper (PID $!)."
fi

sleep 4
echo
docker compose --env-file .env --profile forwardlab ps crypto_v8_forward_lab
echo
docker compose --env-file .env --profile forwardlab logs --tail=30 crypto_v8_forward_lab || true

echo
echo "V8 forward lab is running continuously until you stop it."
echo "It shadows four V8 candidates independently on fresh Kraken data."
echo "It never submits orders and does not read exchange credentials."
echo "Morning report: bash trading_stack/status_v8_forward_lab_mac.sh"
echo "Stop command:    bash trading_stack/stop_v8_forward_lab_mac.sh"
