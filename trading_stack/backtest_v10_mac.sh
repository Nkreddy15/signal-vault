#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile v10 "$@"; }
echo 'Frozen V10 backtest: Q1/Q2 historical research, not unseen validation.'
echo 'Running V10 and its ledger are unchanged. Research uses separate temporary campaigns.'
dc build crypto_v10
dc run --rm -T --no-deps --entrypoint python crypto_v10 /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q1 --archive /freqtrade/data/v4-2026q1-ohlcv/Kraken_OHLCVT_2026Q1.zip \
  --outdir /freqtrade/data/v10-2026q1-ohlcv
dc run --rm -T --no-deps --entrypoint python crypto_v10 /freqtrade/user_data/kraken_quarterly_ohlcv.py \
  --quarter 2026Q2 --archive /freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip \
  --outdir /freqtrade/data/v10-2026q2-ohlcv
dc run --rm -T --no-deps --entrypoint python crypto_v10 /freqtrade/user_data/backtest_v10.py \
  --data-dir /freqtrade/data/v10-2026q1-ohlcv --data-dir /freqtrade/data/v10-2026q2-ohlcv \
  --output-dir /freqtrade/data/v10-backtest-results
mkdir -p ../.data/v10-backtest-results
dc run --rm -T --no-deps --entrypoint python crypto_v10 - <<'PY' > ../.data/v10-backtest-results/v10-backtest-summary.json
from pathlib import Path
print(Path('/freqtrade/data/v10-backtest-results/v10-backtest-summary.json').read_text())
PY
echo 'Local summary: .data/v10-backtest-results/v10-backtest-summary.json'
