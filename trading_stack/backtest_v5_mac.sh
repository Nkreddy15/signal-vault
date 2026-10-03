#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
Q1_DIR="/freqtrade/data/v5-2026q1-ohlcv"
Q2_DIR="/freqtrade/data/v5-2026q2-ohlcv"
HOLDOUT_DIR="/freqtrade/data/v5-2025q4-ohlcv"
RESULT_DIR="/freqtrade/data/v5-research-results"
Q1_ARCHIVE="/freqtrade/data/v4-2026q1-ohlcv/Kraken_OHLCVT_2026Q1.zip"
Q2_ARCHIVE="/freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip"

echo "Signal Vault V5 bidirectional research runner"
echo "Research only. This does not restart or switch the running V1 spot PAPER bot."
echo "2026 H1 = development; 2025 Q4 = predeclared holdout."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Preparing 2026 Q1 development data from cached archive..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q1 --archive "$Q1_ARCHIVE" --outdir "$Q1_DIR"

echo
echo "Preparing 2026 Q2 development data from cached archive..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q2 --archive "$Q2_ARCHIVE" --outdir "$Q2_DIR"

echo
echo "Preparing 2025 Q4 holdout from Kraken official quarterly archive..."
echo "First run may download one large archive; it will then remain cached."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2025Q4 --outdir "$HOLDOUT_DIR"

echo
echo "Running conservative long/short/no-trade research simulation..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/research_v5_bidirectional.py \
  --development-dir "$Q1_DIR" \
  --development-dir "$Q2_DIR" \
  --holdout-dir "$HOLDOUT_DIR" \
  --output-dir "$RESULT_DIR"

echo
echo "V5 research run complete."
echo "The running V1 PAPER bot was not restarted or switched."
