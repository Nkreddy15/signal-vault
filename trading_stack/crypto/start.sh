#!/usr/bin/env bash
set -euo pipefail

: "${FREQTRADE__API_SERVER__USERNAME:?FreqUI username required}"
: "${FREQTRADE__API_SERVER__PASSWORD:?FreqUI password required}"
: "${FREQTRADE__API_SERVER__JWT_SECRET_KEY:?FreqUI JWT secret required}"
: "${FREQTRADE__API_SERVER__WS_TOKEN:?FreqUI websocket token required}"

PERSIST_DIR="${PERSIST_DIR:-/freqtrade/data}"
mkdir -p "$PERSIST_DIR" /freqtrade/user_data/strategies

case "${FREQTRADE__DRY_RUN:-true}" in
  false|False|FALSE|0|no|No|NO)
    echo "Refusing to start: Signal Vault execution harness is PAPER/dry-run only." >&2
    exit 2
    ;;
esac

if [[ -n "${FREQTRADE__EXCHANGE__KEY:-}" || -n "${FREQTRADE__EXCHANGE__SECRET:-}" ]]; then
  echo "Refusing to start: exchange credentials are not accepted by this PAPER-only harness." >&2
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

STRATEGY="${SIGNAL_VAULT_CRYPTO_STRATEGY:-SignalVaultPaperExecutionV1}"

case "$STRATEGY" in
  SignalVaultPaperExecutionV1)
    DEFAULT_DB="signal-vault-execution-paper-v1.sqlite"
    DESCRIPTION="V1 high-activity execution harness: 5m, six-pair universe"
    ;;
  SignalVaultPaperExecutionV2)
    DEFAULT_DB="signal-vault-execution-paper-v2.sqlite"
    DESCRIPTION="V2 cost-aware regime strategy: 15m, six-pair universe"
    ;;
  SignalVaultPaperEMA12x26V1)
    DEFAULT_DB="signal-vault-ema12x26-paper-v1.sqlite"
    DESCRIPTION="EMA 12x26 research adapter: 1h, six-pair universe"
    ;;
  *)
    echo "Refusing to start: unsupported PAPER strategy '$STRATEGY'." >&2
    exit 2
    ;;
esac

DB_URL="${FREQTRADE_DB_URL:-sqlite:///$PERSIST_DIR/$DEFAULT_DB}"

if [[ "$STRATEGY" == "SignalVaultPaperExecutionV2" && "$DB_URL" == *"paper-v1.sqlite"* ]]; then
  echo "Refusing to start V2 against the V1 trade database." >&2
  echo "Unset FREQTRADE_DB_URL or point it to a dedicated V2 PAPER database." >&2
  exit 2
fi

echo "Starting Signal Vault PAPER strategy: $DESCRIPTION."
echo "Purpose: collect PAPER evidence. No profitability claim and no live execution."

exec freqtrade trade \
  --config /freqtrade/user_data/config.json \
  --strategy "$STRATEGY" \
  --db-url "$DB_URL"
