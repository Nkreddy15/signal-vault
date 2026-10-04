#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
dc() { docker compose --env-file .env --profile v10 "$@"; }
echo 'Multi-strategy development: shared $100, compounding, normal and stress fills.'
echo 'Research only; running containers and paused entry markers stay untouched.'
dc build crypto_v10
# The V10 backtest already prepared these six-asset datasets. Reuse them when
# complete; otherwise rebuild from the existing cached Kraken archives.
for quarter in 2026Q1 2026Q2; do
  label="$(echo "$quarter" | tr '[:upper:]' '[:lower:]')"
  if ! dc run --rm -T --no-deps --entrypoint python crypto_v10 - "$label" <<'PY'
import sys
from pathlib import Path
p=Path('/freqtrade/data/v10-'+sys.argv[1]+'-ohlcv')
names=('BTC','ETH','SOL','XRP','DOGE','ADA')
raise SystemExit(0 if all((p/(n+'_USD-15m.feather')).is_file() for n in names) else 1)
PY
  then
    if [[ "$quarter" == 2026Q1 ]]; then
      archive=/freqtrade/data/v4-2026q1-ohlcv/Kraken_OHLCVT_2026Q1.zip
    else
      archive=/freqtrade/data/v2-quarterly-ohlcv/Kraken_OHLCVT_2026Q2.zip
    fi
    dc run --rm -T --no-deps --entrypoint python crypto_v10 /freqtrade/user_data/kraken_quarterly_ohlcv.py \
      --quarter "$quarter" --archive "$archive" --outdir "/freqtrade/data/v10-$label-ohlcv"
  fi
done
dc run --rm -T --no-deps --entrypoint python crypto_v10 /freqtrade/user_data/multi_strategy_lab.py \
  --data-dir /freqtrade/data/v10-2026q1-ohlcv --data-dir /freqtrade/data/v10-2026q2-ohlcv \
  --output-dir /freqtrade/data/multi-strategy-lab "$@"
mkdir -p ../.data/multi-strategy-lab
for name in multi-strategy-summary.json multi-strategy-results.md; do
  dc run --rm -T --no-deps --entrypoint python crypto_v10 - "$name" <<'PY' > "../.data/multi-strategy-lab/$name"
import sys
from pathlib import Path
print((Path('/freqtrade/data/multi-strategy-lab')/sys.argv[1]).read_text(),end='')
PY
done
echo 'Completed. Read .data/multi-strategy-lab/multi-strategy-results.md'
