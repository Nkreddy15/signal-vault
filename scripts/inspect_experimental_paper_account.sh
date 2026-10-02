#!/usr/bin/env bash
# Read-only Alpaca PAPER account inventory for experimental sandbox blockers.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${SV_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || true)"
  fi
fi
[[ -n "$PYTHON" ]] || { echo "Python 3 is required." >&2; exit 1; }

for forbidden in ALPACA_API_KEY_ID ALPACA_API_SECRET_KEY APCA_API_KEY_ID APCA_API_SECRET_KEY ALPACA_LIVE_KEY_ID ALPACA_LIVE_SECRET_KEY; do
  if [[ -n "${!forbidden:-}" ]]; then
    echo "Refusing to run while generic/live Alpaca credential variable $forbidden is set." >&2
    exit 1
  fi
done

if [[ -z "${ALPACA_PAPER_KEY_ID:-}" ]]; then
  read -r -s -p "Alpaca PAPER key ID: " ALPACA_PAPER_KEY_ID
  echo
  export ALPACA_PAPER_KEY_ID
fi
if [[ -z "${ALPACA_PAPER_SECRET_KEY:-}" ]]; then
  read -r -s -p "Alpaca PAPER secret key: " ALPACA_PAPER_SECRET_KEY
  echo
  export ALPACA_PAPER_SECRET_KEY
fi

OUTDIR="$ROOT/.data/experimental-paper-local"
mkdir -p "$OUTDIR"
chmod 700 "$OUTDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUTDIR/paper-account-inventory-$STAMP.json"

PYTHONPATH="$ROOT/src" "$PYTHON" -m signal_vault.experimental_paper_inventory --output "$OUT"

unset ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY

echo "Inventory receipt: $OUT"
echo "GET-only: no order was submitted, cancelled, replaced, or closed."
