#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "=== V8 overnight container ==="
docker compose --env-file .env --profile overnight ps crypto_v8_overnight || true

echo
echo "=== Recent V8 overnight logs ==="
docker compose --env-file .env --profile overnight logs --tail=40 crypto_v8_overnight || true

echo
echo "=== Persisted V8 state ==="
docker compose --env-file .env --profile overnight run --rm --no-deps   --entrypoint sh crypto_v8_overnight -lc '
    if [ -f /freqtrade/data/v8-overnight/state.json ]; then
      cat /freqtrade/data/v8-overnight/state.json
    else
      echo "No V8 state yet."
    fi
  ' || true

echo
echo "=== Closed V8 paper trades ==="
docker compose --env-file .env --profile overnight run --rm --no-deps   --entrypoint sh crypto_v8_overnight -lc '
    if [ -f /freqtrade/data/v8-overnight/trades.csv ]; then
      tail -n 20 /freqtrade/data/v8-overnight/trades.csv
    else
      echo "No trade ledger yet."
    fi
  ' || true
