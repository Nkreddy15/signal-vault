#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=== Forward lab container ==="
docker compose --env-file .env --profile forwardlab ps crypto_v8_forward_lab || true

echo
echo "=== Recent forward-lab events ==="
docker compose --env-file .env --profile forwardlab logs --tail=60 crypto_v8_forward_lab || true

echo
echo "=== Current candidate summary ==="
docker compose --env-file .env --profile forwardlab run --rm --no-deps \
  --entrypoint sh crypto_v8_forward_lab -lc '
    if [ -f /freqtrade/data/v8-forward-lab/summary.json ]; then
      cat /freqtrade/data/v8-forward-lab/summary.json
    else
      echo "No summary yet."
    fi
  ' || true

echo
echo "=== Most recent closed paper trades ==="
docker compose --env-file .env --profile forwardlab run --rm --no-deps \
  --entrypoint sh crypto_v8_forward_lab -lc '
    if [ -f /freqtrade/data/v8-forward-lab/trades.csv ]; then
      tail -n 25 /freqtrade/data/v8-forward-lab/trades.csv
    else
      echo "No trade ledger yet."
    fi
  ' || true

echo
echo "=== Last hourly diagnostics ==="
docker compose --env-file .env --profile forwardlab run --rm --no-deps \
  --entrypoint sh crypto_v8_forward_lab -lc '
    if [ -f /freqtrade/data/v8-forward-lab/hourly_diagnostics.csv ]; then
      tail -n 25 /freqtrade/data/v8-forward-lab/hourly_diagnostics.csv
    else
      echo "No hourly diagnostics yet."
    fi
  ' || true
