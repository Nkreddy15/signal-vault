#!/usr/bin/env bash
# Execute the one strategy selected by a fresh GET-only readiness receipt.
# The receipt is NOT order authority. The child sandbox re-fetches fresh BTC data,
# re-checks PAPER account readiness/duplicate state/risk, and still requires the
# exact owner PAPER acknowledgement before any POST attempt.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
READINESS="${1:-}"
[[ -f "$READINESS" ]] || {
  echo "Usage: bash scripts/execute_ready_experimental_paper.sh <paper-readiness.json>" >&2
  exit 1
}

PYTHON="${SV_PYTHON:-}"
if [[ -z "$PYTHON" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="$(command -v python3 || true)"
  fi
fi
[[ -n "$PYTHON" ]] || { echo "Python 3 is required." >&2; exit 1; }

STRATEGY="$(
  "$PYTHON" - "$READINESS" <<'PY'
import json,sys
from datetime import datetime,timezone,timedelta

path=sys.argv[1]
with open(path,encoding="utf-8") as fh:
    x=json.load(fh)

allowed={
    "generic-ema12x26-v1-predeclared",
    "generic-momentum24bar50bps-v1-predeclared",
}
if x.get("kind")!="EXPERIMENTAL_BTC_PAPER_GET_ONLY_READINESS_REPORT":
    raise SystemExit("Wrong readiness receipt kind.")
if x.get("status")!="READY_FOR_EXPLICIT_EXPERIMENTAL_PAPER_REVIEW":
    raise SystemExit("Readiness receipt is not in READY state.")
if x.get("paper_account_ready") is not True:
    raise SystemExit("PAPER account was not ready in the receipt.")
if x.get("experimental_only") is not True or x.get("strategy_validated") is not False:
    raise SystemExit("Experimental receipt contract mismatch.")
if x.get("independent_prospective_gate_passed") is not False:
    raise SystemExit("Unexpected prospective-gate claim.")
if x.get("actions_are_order_authority") is not False:
    raise SystemExit("Readiness receipt must explicitly deny order authority.")
if x.get("paper_order_submission")!="DISABLED" or x.get("live_trading")!="UNAVAILABLE":
    raise SystemExit("Readiness receipt execution safety contract mismatch.")

selected=x.get("selected_strategy_for_operator_review")
buys=x.get("buy_signal_strategies")
if selected not in allowed or buys!=[selected]:
    raise SystemExit("Exactly one supported BUY strategy must be selected.")

stamp=datetime.fromisoformat(str(x.get("checked_at_utc","")).replace("Z","+00:00"))
if stamp.tzinfo is None:
    raise SystemExit("Readiness timestamp missing timezone.")
age=datetime.now(timezone.utc)-stamp.astimezone(timezone.utc)
if age < timedelta(minutes=-1) or age > timedelta(minutes=30):
    raise SystemExit("Readiness receipt is stale; run a new dry-run first.")

print(selected)
PY
)"

echo "Readiness selected: $STRATEGY"
echo "The readiness receipt is NOT trading authorization."
echo "The sandbox will now re-fetch fresh BTC data and repeat every PAPER safety gate."
exec bash "$ROOT/scripts/run_experimental_paper_sandbox.sh" "$STRATEGY" execute
