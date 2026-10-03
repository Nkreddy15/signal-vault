#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-smoke-data"
RESULT_DIR="/freqtrade/data/v2-smoke-results"

echo "Signal Vault V2 quick smoke test"
echo "Uses Kraken direct OHLCV only for a short-window code/logic smoke test."
echo "This is NOT the 90-day research backtest and does not replace it."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Downloading the short Kraken OHLCV window for all six configured pairs..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint /bin/bash crypto -lc "
    mkdir -p '$DATA_DIR' '$RESULT_DIR'
    freqtrade download-data \
      -vv \
      --config /freqtrade/user_data/config.json \
      --datadir '$DATA_DIR' \
      --timeframes 15m \
      --days 7
  "

echo
echo "Running V2 short-window smoke backtest..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint /bin/bash crypto -lc "
    set -o pipefail
    freqtrade backtesting \
      --config /freqtrade/user_data/config.json \
      --datadir '$DATA_DIR' \
      --strategy-path /freqtrade/user_data/strategies \
      --strategy SignalVaultPaperExecutionV2 \
      --timeframe 15m \
      --export trades \
      --backtest-directory '$RESULT_DIR' \
      2>&1 | tee '$RESULT_DIR/latest-summary.txt'
  "

echo
echo "V2 smoke test complete."
echo "If this passes, use backtest_v2_mac.sh for the slower 90-day Kraken trade-history test."
