#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-market-data"
RESULT_DIR="/freqtrade/data/v2-smoke-results"

echo "Signal Vault V2 quick smoke test"
echo "Reuses the BTC Kraken trades already downloaded by the 90-day research run."
echo "If they are missing, it downloads only a short BTC trade window."
echo "This validates V2 wiring only; it is not a profitability test."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Preparing BTC/USD 15m candles from existing Kraken trade data..."
if ! docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  trades-to-ohlcv \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --pairs BTC/USD \
  --timeframes 15m; then
  echo "Existing BTC trade data was not usable; downloading a short BTC-only trade window..."
  docker compose -f "$COMPOSE" run --rm --no-deps \
    --entrypoint freqtrade crypto \
    download-data \
    -vv \
    --config /freqtrade/user_data/config.json \
    --datadir "$DATA_DIR" \
    --pairs BTC/USD \
    --timeframes 15m \
    --days 4 \
    --dl-trades \
    --convert
fi

echo
echo "Running V2 BTC-only smoke backtest..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  backtesting \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --strategy-path /freqtrade/user_data/strategies \
  --strategy SignalVaultPaperExecutionV2 \
  --pairs BTC/USD \
  --timeframe 15m \
  --export trades \
  --backtest-directory "$RESULT_DIR"

echo
echo "V2 smoke test complete."
echo "The running V1 PAPER bot was not restarted or switched."
