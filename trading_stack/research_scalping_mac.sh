#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
CAPITAL="${1:-100}"
case "$CAPITAL" in
  100|500) ;;
  *) echo 'Usage: bash trading_stack/research_scalping_mac.sh [100|500]' >&2; exit 2 ;;
esac
if [[ $# -gt 0 ]]; then shift; fi
dc() { docker compose --env-file .env --profile edge "$@"; }
echo '15m scalping screen: three signal families, shared blend and churn control. Research only.'
dc build crypto_edge_lab
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab /freqtrade/user_data/scalping_edge_lab.py \
  --data-dir /freqtrade/data/edge-universe-v1 --starting-balance "$CAPITAL" \
  --output-dir "/freqtrade/data/scalping-edge-v1-$CAPITAL" "$@"
mkdir -p "$HOME/Downloads"
TEMP="$(mktemp "$HOME/Downloads/.scalping-summary.XXXXXX")"
trap 'rm -f "$TEMP"' EXIT
dc run --rm -T --no-deps --entrypoint python crypto_edge_lab - "$CAPITAL" <<'PY' > "$TEMP"
from pathlib import Path
import sys
print(Path(f'/freqtrade/data/scalping-edge-v1-{sys.argv[1]}/scalping-summary.json').read_text(),end='')
PY
mv "$TEMP" "$HOME/Downloads/scalping-summary-$CAPITAL.txt"
echo 'Results saved in the research data volume. Paper entries remain paused.'
open -R "$HOME/Downloads/scalping-summary-$CAPITAL.txt"
