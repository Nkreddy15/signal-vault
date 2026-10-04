#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo 'Missing trading_stack/.env; run install_mac.sh first.' >&2; exit 2; }
docker info >/dev/null
dc() { docker compose --env-file .env --profile final "$@"; }
echo 'Building V9 overnight PAPER runtime and dashboard...'
dc build crypto_final crypto dashboard
echo 'Checking public data before changing the running V1...'
dc run --rm -T --no-deps crypto_final --once --state-dir /tmp/paper-preflight

# Abort rather than overwrite or silently restart an expired session.
dc run --rm -T --no-deps --entrypoint python crypto_final - <<'PY'
import json, sqlite3, time
from pathlib import Path
p = Path('/freqtrade/data/paper-final-v9/ledger.sqlite3')
if p.exists():
    with sqlite3.connect(f'file:{p}?mode=ro', uri=True) as db:
        s = json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
    if s['deadline_ms'] <= time.time()*1000 or s.get('halt_reason'):
        raise SystemExit('Existing V9 session is complete or halted. Records are preserved; use status_final_mac.sh to review it.')
print('Session preflight passed.')
PY

echo 'Verifying V1 is PAPER and pausing new entries...'
dc exec -T crypto python - <<'PY'
import base64, json, os, urllib.request, urllib.error
base = 'http://127.0.0.1:8080/api/v1/'
auth = base64.b64encode((os.environ['FREQTRADE__API_SERVER__USERNAME']+':'+os.environ['FREQTRADE__API_SERVER__PASSWORD']).encode()).decode()
def call(path, method='GET'):
    req = urllib.request.Request(base+path, method=method, headers={'Authorization':'Basic '+auth})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)
c = call('show_config')
if c.get('dry_run') is not True or c.get('strategy') != 'SignalVaultPaperExecutionV1':
    raise SystemExit('Expected the existing PAPER SignalVaultPaperExecutionV1. No cutover performed.')
try:
    call('pause', 'POST')
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise
    call('stopbuy', 'POST')
c = call('show_config')
if str(c.get('state', '')).lower() != 'paused' and c.get('max_open_trades') != 0:
    raise SystemExit('V1 pause could not be verified. Final runner not started.')
print('V1 entries paused; existing paper trades continue their original exits.')
PY

echo 'Saving V1 databases and activating the persistent handoff...'
dc run --rm -T --no-deps --entrypoint python crypto_final - <<'PY'
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
root = Path('/freqtrade/data')
backup = root / 'v1-backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup.mkdir(parents=True, exist_ok=True)
for p in root.iterdir():
    if p.is_file() and p.suffix in ('.sqlite', '.sqlite3', '.db'):
        with sqlite3.connect(f'file:{p}?mode=ro', uri=True) as src, sqlite3.connect(backup/p.name) as dst:
            src.backup(dst)
target = root / 'paper-final-v9'
target.mkdir(exist_ok=True)
(target/'activated').write_text('V9 active; V1 entry veto persists across restarts.\n')
print('Database backup complete. V1 trade history preserved.')
PY

failed() {
  echo 'Upgrade verification failed. Showing logs; no success is being claimed.' >&2
  dc logs --tail=30 crypto_final dashboard || true
  echo 'V1 new entries remain paused; its open trades are still managed. Rerun this command after resolving the error.' >&2
}
trap failed ERR
# Recreate V1 with its same strategy/database and the persistent entry veto.
dc up -d --no-deps --force-recreate crypto
dc up -d --no-deps crypto_final dashboard
echo 'Waiting for a successful market-data cycle and dashboard...'
ok=0
for attempt in {1..60}; do
  if dc exec -T dashboard python - <<'PY'
import json, time, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8090/api/paper-final', timeout=5) as r:
    s = json.load(r)
assert s['version']=='V9-OVERNIGHT-1'
assert s['status']=='RUNNING' and s['cycles'] >= 1
assert time.time()*1000-s['last_success_ms'] < 120000
PY
  then ok=1; break; fi
  sleep 3
done
[[ "$ok" == 1 ]]
docker compose --env-file .env --profile overnight --profile forwardlab stop crypto_v8_overnight crypto_v8_forward_lab
if [[ -x /usr/bin/caffeinate ]]; then
  if [[ ! -f .caffeinate.pid ]] || ! kill -0 "$(cat .caffeinate.pid)" 2>/dev/null; then
    nohup /usr/bin/caffeinate -dimsu >/tmp/signal-vault-caffeinate.log 2>&1 &
    echo $! > .caffeinate.pid
    chmod 600 .caffeinate.pid
  fi
fi
echo 'VERIFIED: V9 PAPER runner has completed a fresh market scan. Dashboard: http://127.0.0.1:8090'
echo 'Synthetic shorts only. Frozen V8 hypothesis is unvalidated; zero trades or a loss are possible.'
echo 'Keep Docker running and the Mac plugged in with the lid open. Status: bash trading_stack/status_final_mac.sh'
if command -v open >/dev/null; then open http://127.0.0.1:8090; fi
