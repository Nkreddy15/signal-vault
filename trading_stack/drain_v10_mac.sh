#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
docker compose --env-file .env --profile v10 exec -T crypto_v10 python - <<'PY'
from pathlib import Path
Path('/freqtrade/data/paper-v10/drain').write_text('User requested entry pause. Continue managing held paper positions.\n')
print('V10 new entries will pause on the next cycle; held positions retain their exits.')
PY
