#!/usr/bin/env bash
set -euo pipefail

# Phase 162 LOCAL research pipeline:
#   1) bounded Alpaca IEX historical DATA GET only
#   2) offline SHA/calendar validation
#   3) long-horizon six-stock ML tournament
#
# No order module is invoked. The env file is parsed by Python as data and is
# never sourced by this shell.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python}"
ENV_FILE="${SIGNAL_VAULT_PAPER_ENV_FILE:-$ROOT/trading_stack/.env}"
START_DATE="${SIGNAL_VAULT_STOCK_RESEARCH_START_DATE:-2025-10-01}"
END_DATE_EXCLUSIVE="${SIGNAL_VAULT_STOCK_RESEARCH_END_DATE_EXCLUSIVE:-2026-09-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_ROOT="${SIGNAL_VAULT_STOCK_RESEARCH_OUTPUT:-$ROOT/.data/phase162-equity-$STAMP}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "PAPER env file not found: $ENV_FILE" >&2
  exit 2
fi

mkdir -p "$ROOT/.data"
chmod 700 "$ROOT/.data"

"$PYTHON" - <<'PY'
import importlib
mods = ("numpy", "pandas", "sklearn", "exchange_calendars")
missing = []
for name in mods:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)
if missing:
    raise SystemExit(
        "Missing research dependencies: "
        + ", ".join(missing)
        + ". Install with: python -m pip install -e '.[research,equity-research]'"
    )
PY

PYTHONPATH=src "$PYTHON" -m signal_vault.local_long_equity_research   --env-file "$ENV_FILE"   --start-date "$START_DATE"   --end-date-exclusive "$END_DATE_EXCLUSIVE"   --output-root "$OUTPUT_ROOT"   --approval LOCAL_PHASE162_LONG_EQUITY_DATA_GET_ONLY

PYTHONPATH=src "$PYTHON" -m signal_vault.offline_long_equity_validation   --source-root "$OUTPUT_ROOT"   --output "$OUTPUT_ROOT/offline_long_equity_validation.json"

PYTHONPATH=src "$PYTHON" -m signal_vault.stock_ml_tournament   --source-root "$OUTPUT_ROOT"   --output "$OUTPUT_ROOT/phase162_stock_ml_tournament.json"

echo "Phase 162 stock research complete."
echo "Results: $OUTPUT_ROOT/phase162_stock_ml_tournament.json"
echo "No broker orders were submitted by this pipeline."
