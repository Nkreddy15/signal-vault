#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-market-data"
RESULT_DIR="/freqtrade/data/v2-backtests"
DAYS="${V2_BACKTEST_DAYS:-90}"

echo "Signal Vault V2 research runner"
echo "PAPER/research only. This does not restart the running trading container."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Downloading/refreshing $DAYS days of public Kraken trade history and converting to 15m candles..."
docker compose -f "$COMPOSE" run --rm --no-deps   --entrypoint /bin/bash crypto -lc "
    mkdir -p '$DATA_DIR' '$RESULT_DIR'
    freqtrade download-data       --config /freqtrade/user_data/config.json       --datadir '$DATA_DIR'       --timeframes 15m       --days 180       --dl-trades       --convert
  "

echo
echo "Running SignalVaultPaperExecutionV2 backtest..."
docker compose -f "$COMPOSE" run --rm --no-deps   --entrypoint /bin/bash crypto -lc "
    mkdir -p '$RESULT_DIR'
    set -o pipefail
    freqtrade backtesting       --config /freqtrade/user_data/config.json       --datadir '$DATA_DIR'       --strategy-path /freqtrade/user_data/strategies       --strategy SignalVaultPaperExecutionV2       --timeframe 15m       --export trades       --backtest-directory '$RESULT_DIR'       2>&1 | tee '$RESULT_DIR/latest-summary.txt'
  "

echo
echo "V2 backtest complete."
echo "Results are persisted in Docker volume trading_stack_crypto_data under:"
echo "  $RESULT_DIR"
echo
echo "The running V1 PAPER bot was not restarted or switched."
