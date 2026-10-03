#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
Q2_DIR="/freqtrade/data/v4-2026q2-ohlcv"
Q1_DIR="/freqtrade/data/v4-2026q1-ohlcv"
RESULT_DIR="/freqtrade/data/v4-backtests"
Q2_ARCHIVE="/freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip"

echo "Signal Vault V4 research runner"
echo "PAPER/research only. The running V1 bot is not restarted or switched."
echo "Q2 = development evidence; Q1 = predeclared unseen holdout."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Preparing Q2 from the already cached Kraken archive..."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q2 \
  --archive "$Q2_ARCHIVE" \
  --outdir "$Q2_DIR"

echo
echo "Preparing Q1 holdout from Kraken official quarterly archive..."
echo "The first Q1 run may download a large ZIP once; progress is shown and then cached."
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q1 \
  --outdir "$Q1_DIR"

run_bt () {
  local label="$1"
  local datadir="$2"
  local timerange="$3"
  echo
  echo "=== V4 BACKTEST: $label ($timerange) ==="
  docker compose -f "$COMPOSE" run --rm --no-deps \
    --entrypoint /bin/bash crypto -lc "
      mkdir -p '"$RESULT_DIR"/"$label"'
      set -o pipefail
      freqtrade backtesting \
        --config /freqtrade/user_data/config.json \
        --datadir '"$datadir"' \
        --strategy-path /freqtrade/user_data/strategies \
        --strategy SignalVaultPaperExecutionV4 \
        --timeframe 1h \
        --timerange '"$timerange"' \
        --export trades \
        --backtest-directory '"$RESULT_DIR"/"$label"' \
        2>&1 | tee '"$RESULT_DIR"/"$label"'/summary.txt
    "
}

echo
echo "=== Q1 HOLDOUT DATA COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data --config /freqtrade/user_data/config.json \
  --datadir "$Q1_DIR" --show-timerange | grep -E "Pair|1h|Found"

echo
echo "=== Q2 DEVELOPMENT DATA COVERAGE ==="
docker compose -f "$COMPOSE" run --rm --no-deps \
  --entrypoint freqtrade crypto \
  list-data --config /freqtrade/user_data/config.json \
  --datadir "$Q2_DIR" --show-timerange | grep -E "Pair|1h|Found"

run_bt q1-holdout "$Q1_DIR" 20260101-20260401
run_bt q2-development "$Q2_DIR" 20260401-20260701

run_bt january "$Q1_DIR" 20260101-20260201
run_bt february "$Q1_DIR" 20260201-20260301
run_bt march "$Q1_DIR" 20260301-20260401
run_bt april "$Q2_DIR" 20260401-20260501
run_bt may "$Q2_DIR" 20260501-20260601
run_bt june "$Q2_DIR" 20260601-20260701

echo
echo "V4 research run complete."
echo "The running V1 PAPER bot was not restarted or switched."
