#!/usr/bin/env bash
set -euo pipefail

: "${FREQTRADE__API_SERVER__USERNAME:?FreqUI username required}"
: "${FREQTRADE__API_SERVER__PASSWORD:?FreqUI password required}"
: "${FREQTRADE__API_SERVER__JWT_SECRET_KEY:?FreqUI JWT secret required}"
: "${FREQTRADE__API_SERVER__WS_TOKEN:?FreqUI websocket token required}"

PERSIST_DIR="${PERSIST_DIR:-/freqtrade/data}"
mkdir -p "$PERSIST_DIR" /freqtrade/user_data/strategies

# Fail closed: this image is an experimental PAPER/dry-run adapter only.
case "${FREQTRADE__DRY_RUN:-true}" in
  false|False|FALSE|0|no|No|NO)
    echo "Refusing to start: Signal Vault Freqtrade adapter is PAPER/dry-run only." >&2
    exit 2
    ;;
esac

if [[ -n "${FREQTRADE__EXCHANGE__KEY:-}" || -n "${FREQTRADE__EXCHANGE__SECRET:-}" ]]; then
  echo "Refusing to start: exchange credentials are not accepted by this PAPER-only adapter." >&2
  exit 2
fi

python - <<'PY'
import json
from pathlib import Path

cfg = json.loads(Path("/freqtrade/user_data/config.json").read_text())
if cfg.get("dry_run") is not True:
    raise SystemExit("Refusing to start: config.json must keep dry_run=true")
exchange = cfg.get("exchange") or {}
if exchange.get("key") or exchange.get("secret"):
    raise SystemExit("Refusing to start: PAPER-only config must not contain exchange credentials")
PY

DB_URL="${FREQTRADE_DB_URL:-sqlite:///$PERSIST_DIR/tradesv3.sqlite}"

echo "Starting Signal Vault experimental PAPER strategy: hourly EMA 12x26, six-pair universe."
echo "This is paper execution evidence collection, not a validated-profitability claim."

exec freqtrade trade \
  --config /freqtrade/user_data/config.json \
  --strategy SignalVaultPaperEMA12x26V1 \
  --db-url "$DB_URL"
