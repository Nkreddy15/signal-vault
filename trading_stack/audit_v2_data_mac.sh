#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-market-data"

echo "=== V2 TRADE-DATA COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --trades \
  --show-timerange

echo
echo "=== V2 15m CANDLE COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --show-timerange
