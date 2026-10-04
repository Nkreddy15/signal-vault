#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
mkdir -p "$HOME/Downloads"
TEMP="$(mktemp "$HOME/Downloads/.v11-results.XXXXXX")"
trap 'rm -f "$TEMP"' EXIT
docker compose --env-file .env --profile v11 run --rm -T --no-deps --entrypoint python crypto_v11 - <<'PY' > "$TEMP"
import io,json,sqlite3,sys,zipfile
from pathlib import Path
root=Path('/freqtrade/data/paper-v11-500')
with sqlite3.connect(f"file:{root/'ledger.sqlite3'}?mode=ro",uri=True) as db:
    db.execute('BEGIN')
    row=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    if not row:raise SystemExit('V11 account has not started.')
    state=json.loads(row[0])
    if state.get('version')!='V11-PAPER-500-1':raise SystemExit('Unexpected paper account version.')
    events=[json.loads(v[0]) for v in db.execute('SELECT payload FROM events ORDER BY id')]
    db.commit()
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
    z.writestr('account.json',json.dumps(state,allow_nan=False))
    z.writestr('events.json',json.dumps(events,allow_nan=False))
    if (root/'candles.json').exists():z.writestr('observed-daily-candles.json',(root/'candles.json').read_bytes())
    z.writestr('README.txt','Canonical SQLite state and events share one read snapshot. Candles are a separate observed cache. Synthetic paper only; no credentials included.\n')
sys.stdout.buffer.write(buffer.getvalue())
PY
mv "$TEMP" "$HOME/Downloads/signal-vault-v11-500-results.zip"
echo 'Saved Downloads/signal-vault-v11-500-results.zip for review. No account changes made.'
open -R "$HOME/Downloads/signal-vault-v11-500-results.zip"
