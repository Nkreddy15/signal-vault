#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
docker compose --env-file .env --profile v11 exec -T crypto_v11 python - <<'PY'
from pathlib import Path
Path('/freqtrade/data/paper-v11-500/stop').write_text('User requested closure at next fresh public quotes.\n')
print('Entry veto set. Positions close on the next fresh quote cycle; unavailable quotes remain pending. The ledger is preserved.')
PY
