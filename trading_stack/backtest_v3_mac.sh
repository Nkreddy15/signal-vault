#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
DATA_DIR="/freqtrade/data/v2-quarterly-ohlcv"
RESULT_DIR="/freqtrade/data/v3-backtests"

echo "Signal Vault V3 research runner"
echo "PAPER/research only. This does not restart or switch the running V1 bot."
echo "V3 uses 1h candles derived from the cached official Kraken Q2 2026 archive."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Preparing corrected 15m + 1h six-pair Kraken dataset..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --outdir "$DATA_DIR"

echo
echo "=== 1h DATA COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data \
  --config /freqtrade/user_data/config.json \
  --datadir "$DATA_DIR" \
  --show-timerange | grep -E "Pair|1h|Found"

run_bt () {
  local label="$1"
  local timerange="$2"
  echo
  echo "=== V3 BACKTEST: $label ($timerange) ==="
  docker compose -f "$COMPOSE" run --rm --no-deps \
    --entrypoint /bin/bash crypto -lc "
      mkdir -p '"$RESULT_DIR"/"$label"'
      set -o pipefail
      freqtrade backtesting \
        --config /freqtrade/user_data/config.json \
        --datadir '"$DATA_DIR"' \
        --strategy-path /freqtrade/user_data/strategies \
        --strategy SignalVaultPaperExecutionV3 \
        --timeframe 1h \
        --timerange '"$timerange"' \
        --export trades \
        --backtest-directory '"$RESULT_DIR"/"$label"' \
        2>&1 | tee '"$RESULT_DIR"/"$label"'/summary.txt
    "
}

run_bt full-q2 20260401-20260701
run_bt april 20260401-20260501
run_bt may 20260501-20260601
run_bt june 20260601-20260701

echo
echo "V3 research run complete."
echo "The running V1 PAPER bot was not restarted or switched."
