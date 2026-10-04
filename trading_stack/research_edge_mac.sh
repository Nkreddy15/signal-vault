#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile edge "$@"; }
echo 'Cost attribution + broader liquidity universe + past-only forecasting research.'
echo 'No account profit ceiling. Paused paper ledgers and containers remain intact.'
dc build crypto_edge_lab
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab /freqtrade/user_data/audit_strategy_results.py \
  --results-dir /freqtrade/data/multi-strategy-lab --output-dir /freqtrade/data/edge-research-v1
mkdir -p ../.data/edge-research-v1
# Export prior attribution immediately, even if a later dataset/model step fails.
for name in prior-strategy-audit.json prior-strategy-audit.md; do
  dc run --rm -T --no-deps --entrypoint python crypto_edge_lab - "$name" <<'PY' > "../.data/edge-research-v1/$name"
import sys
from pathlib import Path
print((Path('/freqtrade/data/edge-research-v1')/sys.argv[1]).read_text(),end='')
PY
done
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab /freqtrade/user_data/prepare_liquid_universe.py \
  --q1-archive /freqtrade/data/v4-2026q1-ohlcv/Kraken_OHLCVT_2026Q1.zip \
  --q2-archive /freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip \
  --output-dir /freqtrade/data/edge-universe-v1 --count "${EDGE_UNIVERSE_COUNT:-24}"
dc run --rm -T --no-deps crypto_edge_lab \
  --data-dir /freqtrade/data/edge-universe-v1 --output-dir /freqtrade/data/edge-research-v1 "$@"
for name in forecast-summary.json forecast-results.md forecast-diagnostics.json forecast-diagnostics.md; do
  dc run --rm -T --no-deps --entrypoint python crypto_edge_lab - "$name" <<'PY' > "../.data/edge-research-v1/$name"
import sys
from pathlib import Path
print((Path('/freqtrade/data/edge-research-v1')/sys.argv[1]).read_text(),end='')
PY
done
python3 - <<'PY'
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
root=Path('../.data/edge-research-v1')
with ZipFile('../.data/edge-research-review.zip','w',ZIP_DEFLATED) as z:
    for name in ('prior-strategy-audit.json','prior-strategy-audit.md','forecast-summary.json','forecast-results.md','forecast-diagnostics.json','forecast-diagnostics.md'):
        z.write(root/name,arcname=name)
print('Review bundle: .data/edge-research-review.zip')
PY
echo 'Readable results: .data/edge-research-v1/forecast-results.md'
