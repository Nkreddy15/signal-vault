#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/trading_stack/docker-compose.yml"
Q1_DIR="/freqtrade/data/v6-2026q1-ohlcv"
Q2_DIR="/freqtrade/data/v6-2026q2-ohlcv"
HOLDOUT_DIR="/freqtrade/data/v6-2025q3-crossvenue"
RESULT_DIR="/freqtrade/data/v6-research-results"
Q1_ARCHIVE="/freqtrade/data/v4-2026q1-ohlcv/Kraken_OHLCVT_2026Q1.zip"
Q2_ARCHIVE="/freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip"

echo "Signal Vault V6 gated strategy-family tournament"
echo "Research only. The running V1 PAPER bot is not restarted or switched."
echo "The 2025 Q3 holdout will remain unseen unless a development candidate passes."
echo

docker compose -f "$COMPOSE" build crypto

echo
echo "Preparing 2026 Q1 development data from cached Kraken archive..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q1 --archive "$Q1_ARCHIVE" --outdir "$Q1_DIR"

echo
echo "Preparing 2026 Q2 development data from cached Kraken archive..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q2 --archive "$Q2_ARCHIVE" --outdir "$Q2_DIR"

echo
echo "Running the 24-candidate development tournament..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/research_v6_tournament.py select \
  --development-dir "$Q1_DIR" \
  --development-dir "$Q2_DIR" \
  --output-dir "$RESULT_DIR"

echo
echo "Checking the frozen development gate..."
if docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto -c \
  "import json,sys; p=json.load(open(\"$RESULT_DIR/v6-selected.json\")); sys.exit(0 if p.get(\"selected\") else 2)"; then
  echo "A development candidate passed. The Q3 holdout may now be consumed once."
else
  echo "No candidate passed the V6 development gate."
  echo "Stopping here. The 2025 Q3 holdout remains unseen."
  exit 0
fi

echo
echo "Preparing the predeclared 2025 Q3 Binance cross-venue holdout..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/binance_quarter_holdout.py \
  --quarter 2025Q3 --outdir "$HOLDOUT_DIR"

echo
echo "Evaluating exactly the selected development winner on the holdout..."
docker compose -f "$COMPOSE" run --rm --no-deps --entrypoint python crypto \
  /freqtrade/user_data/research_v6_tournament.py holdout \
  --holdout-dir "$HOLDOUT_DIR" \
  --selected-json "$RESULT_DIR/v6-selected.json" \
  --output-dir "$RESULT_DIR"

echo
echo "V6 research run complete."
echo "The running V1 PAPER bot was not restarted or switched."
