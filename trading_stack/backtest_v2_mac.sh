#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-market-data"
RESULT_DIR="/freqtrade/data/v2-backtests"
DAYS="${V2_BACKTEST_DAYS:-90}"
PAIRS=(BTC/USD ETH/USD SOL/USD XRP/USD DOGE/USD ADA/USD)

echo "Signal Vault V2 research runner"
echo "PAPER/research only. This does not restart the running trading container."
echo "Target historical window: $DAYS days"
echo

docker compose -f "$COMPOSE" build crypto

for pair in "${PAIRS[@]}"; do
  echo
  echo "=== DOWNLOAD/RESUME $pair ==="
  docker compose -f "$COMPOSE" run --rm --no-deps \
    --entrypoint freqtrade crypto \
    download-data \
    --config /freqtrade/user_data/config.json \
    --datadir "$DATA_DIR" \
    --pairs "$pair" \
    --timeframes 15m \
    --days "$DAYS" \
    --dl-trades \
    --convert
done

echo
echo "=== DOWNLOADED TRADE COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --trades \
  --show-timerange

echo
echo "=== GENERATED 15m CANDLE COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --show-timerange

echo
echo "Running SignalVaultPaperExecutionV2 multi-pair backtest..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint /bin/bash crypto -lc "
    mkdir -p '"$RESULT_DIR"'
    set -o pipefail
    freqtrade backtesting \
      --config /freqtrade/user_data/config.json \
      --datadir '"$DATA_DIR"' \
      --strategy-path /freqtrade/user_data/strategies \
      --strategy SignalVaultPaperExecutionV2 \
      --timeframe 15m \
      --export trades \
      --backtest-directory '"$RESULT_DIR"' \
      2>&1 | tee '"$RESULT_DIR"'/latest-summary.txt
  "

echo
echo "V2 backtest complete."
echo "The running V1 PAPER bot was not restarted or switched."
