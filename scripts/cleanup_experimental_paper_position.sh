#!/usr/bin/env bash
# Supervised cleanup of one reviewed small BTC Alpaca PAPER position.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${SV_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then PYTHON="$ROOT/.venv/bin/python"; else PYTHON="$(command -v python3 || true)"; fi
fi
[[ -n "$PYTHON" ]] || { echo "Python 3 is required." >&2; exit 1; }

INVENTORY="${1:-}"
MODE="${2:-dry-run}"
[[ -f "$INVENTORY" ]] || {
  echo "Usage: bash scripts/cleanup_experimental_paper_position.sh <inventory.json> [dry-run|execute]" >&2
  exit 1
}
case "$MODE" in dry-run|execute) ;; *) echo "Mode must be dry-run or execute." >&2; exit 1 ;; esac

for forbidden in ALPACA_API_KEY_ID ALPACA_API_SECRET_KEY APCA_API_KEY_ID APCA_API_SECRET_KEY ALPACA_LIVE_KEY_ID ALPACA_LIVE_SECRET_KEY; do
  if [[ -n "${!forbidden:-}" ]]; then
    echo "Refusing to run while generic/live Alpaca credential variable $forbidden is set." >&2
    exit 1
  fi
done

if [[ -z "${ALPACA_PAPER_KEY_ID:-}" ]]; then
  read -r -s -p "Alpaca PAPER key ID: " ALPACA_PAPER_KEY_ID; echo; export ALPACA_PAPER_KEY_ID
fi
if [[ -z "${ALPACA_PAPER_SECRET_KEY:-}" ]]; then
  read -r -s -p "Alpaca PAPER secret key: " ALPACA_PAPER_SECRET_KEY; echo
fi

export ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY

if ! PYTHONPATH="$ROOT/src" "$PYTHON" - <<'PY'
import os
from signal_vault.paper_credentials import PaperCredentials
try:
    PaperCredentials.from_environment(os.environ)
except Exception:
    raise SystemExit(2)
print("PAPER credential handoff: OK")
PY
then
  unset ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY
  echo "PAPER credentials were not available to the Python process. Re-run and enter both PAPER values." >&2
  exit 1
fi

OUTDIR="$ROOT/.data/experimental-paper-local"
mkdir -p "$OUTDIR"; chmod 700 "$OUTDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECEIPT="$OUTDIR/paper-cleanup-$STAMP.json"
ARGS=(--source-inventory "$INVENTORY" --receipt "$RECEIPT")

if [[ "$MODE" == "execute" ]]; then
  JOURNAL="$OUTDIR/paper-cleanup-$STAMP.sqlite3"
  echo "This can SELL only the exact reviewed BTC PAPER quantity, capped at USD 25 market value."
  echo "It cannot buy, use LIVE trading, or automatically retry."
  read -r -p "Type I_ACKNOWLEDGE_ALPACA_CRYPTO_PAPER_ORDERS_ONLY to continue: " ACK
  [[ "$ACK" == "I_ACKNOWLEDGE_ALPACA_CRYPTO_PAPER_ORDERS_ONLY" ]] || {
    echo "Exact PAPER acknowledgement not provided. Canceled."
    exit 1
  }
  ARGS+=(--execute --acknowledgement "$ACK" --journal "$JOURNAL")
fi

PYTHONPATH="$ROOT/src" "$PYTHON" -m signal_vault.experimental_paper_cleanup "${ARGS[@]}"
unset ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY

echo "Cleanup receipt: $RECEIPT"
if [[ "$MODE" == "execute" && -f "${JOURNAL:-}" ]]; then
  echo "Cleanup journal: $JOURNAL"
  echo "Do not place another PAPER order until this cleanup is reconciled."
fi
