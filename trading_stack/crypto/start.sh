#!/usr/bin/env bash
set -euo pipefail

: "${FREQTRADE__API_SERVER__USERNAME:?FreqUI username required}"
: "${FREQTRADE__API_SERVER__PASSWORD:?FreqUI password required}"
: "${FREQTRADE__API_SERVER__JWT_SECRET_KEY:?FreqUI JWT secret required}"
: "${FREQTRADE__API_SERVER__WS_TOKEN:?FreqUI websocket token required}"

PERSIST_DIR="${PERSIST_DIR:-/freqtrade/data}"
mkdir -p "$PERSIST_DIR/marketdata" /freqtrade/user_data/strategies

STRATEGY_URL="https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/Strategy001.py"
python - <<'PY'
import pathlib, urllib.request
url="https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/f3340ce11f5bdf62f598522e64d1f5638eaa13f5/user_data/strategies/Strategy001.py"
dst=pathlib.Path("/freqtrade/user_data/strategies/Strategy001.py")
if not dst.exists():
    urllib.request.urlretrieve(url,dst)
PY

if [[ ! -f $PERSIST_DIR/bootstrap-v1.done ]]; then
  echo "Downloading 30 days of Kraken spot data for the configured six-pair universe..."
  freqtrade download-data     --config /freqtrade/user_data/config.json     --datadir $PERSIST_DIR/marketdata     --days 30     --timeframes 5m

  echo "Running one bootstrap backtest before dry-run..."
  set +e
  freqtrade backtesting     --config /freqtrade/user_data/config.json     --datadir $PERSIST_DIR/marketdata     --strategy Strategy001     --export trades     --export-filename $PERSIST_DIR/bootstrap-backtest.json     > $PERSIST_DIR/bootstrap-backtest.log 2>&1
  code=$?
  set -e
  echo "$code" > $PERSIST_DIR/bootstrap-backtest-exit-code.txt
  touch $PERSIST_DIR/bootstrap-v1.done
fi

exec freqtrade trade   --config /freqtrade/user_data/config.json   --strategy Strategy001   --db-url sqlite:////freqtrade/data/tradesv3.sqlite
