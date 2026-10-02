#!/usr/bin/env bash
# GET-only monitor for the strategy that opened an experimental BTC PAPER position.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:-}"
[[ -f "$SOURCE" ]] || {
  echo "Usage: bash scripts/monitor_experimental_paper_position.sh <executed-buy-receipt.json>" >&2
  exit 1
}

PYTHON="${SV_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then PYTHON="$ROOT/.venv/bin/python"; else PYTHON="$(command -v python3 || true)"; fi
fi
[[ -n "$PYTHON" ]] || { echo "Python 3 is required." >&2; exit 1; }

STRATEGY="$(
  "$PYTHON" - "$SOURCE" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as fh:
    x=json.load(fh)
allowed={
    "generic-ema12x26-v1-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
}
if x.get("kind")!="EXPERIMENTAL_SUPERVISED_BTC_PAPER_SANDBOX":
    raise SystemExit("Wrong BUY receipt kind.")
if x.get("paper_post_attempted") is not True:
    raise SystemExit("Executed PAPER BUY receipt required.")
if x.get("paper_order_submission")!="ATTEMPT_RECORDED":
    raise SystemExit("Executed PAPER BUY receipt required.")
if x.get("live_trading")!="UNAVAILABLE":
    raise SystemExit("Unsafe receipt contract.")
strategy=x.get("strategy")
if strategy not in allowed:
    raise SystemExit("Unsupported strategy in BUY receipt.")
print(strategy)
PY
)"

for forbidden in ALPACA_API_KEY_ID ALPACA_API_SECRET_KEY APCA_API_KEY_ID APCA_API_SECRET_KEY ALPACA_LIVE_KEY_ID ALPACA_LIVE_SECRET_KEY; do
  if [[ -n "${!forbidden:-}" ]]; then
    echo "Refusing to run while generic/live Alpaca credential variable $forbidden is set." >&2
    exit 1
  fi
done

if [[ -z "${ALPACA_PAPER_KEY_ID:-}" ]]; then
  read -r -s -p "Alpaca PAPER key ID: " ALPACA_PAPER_KEY_ID; echo
fi
if [[ -z "${ALPACA_PAPER_SECRET_KEY:-}" ]]; then
  read -r -s -p "Alpaca PAPER secret key: " ALPACA_PAPER_SECRET_KEY; echo
fi
export ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY

OUTDIR="$ROOT/.data/experimental-paper-local"
mkdir -p "$OUTDIR"; chmod 700 "$OUTDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUTDIR/paper-position-monitor-$STAMP.json"

PYTHONPATH="$ROOT/src" "$PYTHON" -m signal_vault.experimental_paper_position_monitor \
  --strategy "$STRATEGY" \
  --output "$OUT"

unset ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY
echo "Monitor receipt: $OUT"
echo "GET-only: no order was submitted, cancelled, replaced, or closed."
