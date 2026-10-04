#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-quarterly-ohlcv"
RESULT_DIR="/freqtrade/data/v2-backtests"

echo "Signal Vault V2 research runner"
echo "PAPER/research only. This does not restart the running V1 trading container."
echo "Historical source: Kraken official 2026 Q2 OHLCVT archive (15m candles)."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Preparing six-pair Kraken Q2 2026 15m dataset..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --outdir "$DATA_DIR"

echo
echo "=== 15m DATA COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --show-timerange

echo
echo "Running SignalVaultPaperExecutionV2 multi-pair backtest for 2026 Q2..."
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
      --timerange 20260401-20260701 \
      --export trades \
      --backtest-directory '"$RESULT_DIR"' \
      2>&1 | tee '"$RESULT_DIR"'/latest-summary.txt
  "

echo
echo "V2 backtest complete."
echo "The running V1 PAPER bot was not restarted or switched."
