#!/usr/bin/env bash
set -euo pipefail

: "${ALPACA_API_KEY:?Alpaca PAPER API key required}"
: "${ALPACA_API_SECRET:?Alpaca PAPER API secret required}"

if [[ "${ALPACA_IS_PAPER:-true}" != "true" ]]; then
  echo "Refusing to start: this one-week experiment is PAPER-only." >&2
  exit 2
fi

export ALPACA_IS_PAPER=true
export STOCK_LOGICAL_BUDGET_USD="${STOCK_LOGICAL_BUDGET_USD:-100}"

exec python /app/stock_bot.py
