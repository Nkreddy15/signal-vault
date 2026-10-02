#!/usr/bin/env bash
# Owner-invoked local launcher for the experimental BTC PAPER sandbox.
# Defaults to dry-run. Never accepts live Alpaca credentials or a live host.
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

STRATEGY="${1:-all}"
MODE="${2:-dry-run}"
case "$STRATEGY" in
  all|generic-ema12x26-v1-predeclared|generic-momentum24bar50bps-v1-predeclared) ;;
  *) echo "Unsupported strategy: $STRATEGY" >&2; exit 1 ;;
esac
case "$MODE" in
  dry-run|execute) ;;
  *) echo "Mode must be dry-run or execute." >&2; exit 1 ;;
esac
if [[ "$MODE" == "execute" && "$STRATEGY" == "all" ]]; then
  echo "Execute mode requires exactly one fixed strategy." >&2
  exit 1
fi

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

OUT="$ROOT/.data/experimental-paper-local"
mkdir -p "$OUT"
chmod 700 "$OUT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

run_one() {
  local strategy="$1"
  local short="ema"
  [[ "$strategy" == "generic-momentum24bar50bps-v1-predeclared" ]] && short="momentum"
  local receipt="$OUT/paper-sandbox-$short-$STAMP.json"
  local args=(--strategy "$strategy" --receipt "$receipt")

  if [[ "$MODE" == "execute" ]]; then
    JOURNAL="$OUT/paper-sandbox-$short-$STAMP.sqlite3"
    args+=(--execute --acknowledgement "$ACK" --journal "$JOURNAL")
  fi

  echo
  echo "=== $strategy ==="
  PYTHONPATH="$ROOT/src" "$PYTHON" -m signal_vault.experimental_paper_sandbox "${args[@]}"
  echo "Receipt: $receipt"
}

if [[ "$MODE" == "execute" ]]; then
  echo "This can place exactly one USD 10 Alpaca PAPER BTC order only if the current signal is BUY."
  echo "It is experimental PAPER testing, not a validated strategy and not LIVE trading."
  read -r -p "Type I_ACKNOWLEDGE_ALPACA_CRYPTO_PAPER_ORDERS_ONLY to continue: " ACK
  [[ "$ACK" == "I_ACKNOWLEDGE_ALPACA_CRYPTO_PAPER_ORDERS_ONLY" ]] || {
    echo "Exact PAPER acknowledgement not provided. Canceled."
    exit 1
  }
  run_one "$STRATEGY"
  echo "Journal: $JOURNAL"
  echo "Do not run another execute until this journal is reconciled."
elif [[ "$STRATEGY" == "all" ]]; then
  run_one "generic-ema12x26-v1-predeclared"
  run_one "generic-momentum24bar50bps-v1-predeclared"
else
  run_one "$STRATEGY"
fi

unset ALPACA_PAPER_KEY_ID ALPACA_PAPER_SECRET_KEY
