#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo 'Missing trading_stack/.env; run install_mac.sh first.' >&2; exit 2; }
docker info >/dev/null
dc() { docker compose --env-file .env --profile v10 "$@"; }

echo 'Building V10 paper runtime and dashboard...'
dc build crypto crypto_v10 dashboard
echo 'Checking existing V10 records without resetting them...'
dc run --rm -T --no-deps --entrypoint python crypto_v10 - <<'PY'
import json, sqlite3, sys, time
from pathlib import Path
sys.path.insert(0, '/freqtrade/user_data')
from paper_v10 import VERSION, SPEC
p = Path('/freqtrade/data/paper-v10/ledger.sqlite3')
if p.exists():
    with sqlite3.connect(f'file:{p}?mode=ro', uri=True) as db:
        row = db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    if row is None:
        raise SystemExit('Existing V10 ledger is incomplete. No records changed.')
    s = json.loads(row[0])
    if s['version'] != VERSION or s['spec'] != SPEC:
        raise SystemExit('Existing V10 specification differs. No records changed.')
    if s['deadline_ms'] <= time.time()*1000 or s.get('halt_reason'):
        raise SystemExit('Existing V10 campaign is complete or halted. Review status_v10_mac.sh; the ledger will not be erased.')
    print('Resuming existing V10 campaign with its original deadline and balance.')
else:
    print('New separate $100 V10 campaign; seven days from activation.')
PY

echo 'Verifying fresh public bid/ask and closed 15m candles for all six assets...'
echo 'Recent signal counts below are historical diagnostics, not paper trades or profit.'
dc run --rm -T --no-deps crypto_v10 --once --check-activity --state-dir /tmp/v10-preflight

echo 'Verifying the existing V1 is PAPER and pausing new V1 entries...'
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
    raise SystemExit('Expected the existing PAPER V1. V10 cutover was not performed.')
try:
    call('pause', 'POST')
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise
    call('stopbuy', 'POST')
c = call('show_config')
if str(c.get('state', '')).lower() != 'paused' and c.get('max_open_trades') != 0:
    raise SystemExit('V1 entry pause could not be verified. V10 was not started.')
print('V1 entries paused. Its existing positions keep their original exits.')
PY

echo 'Backing up existing ledgers and persisting the V1 entry veto...'
dc run --rm -T --no-deps --entrypoint python crypto_v10 - <<'PY'
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
root = Path('/freqtrade/data')
backup = root/'v10-upgrade-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup.mkdir(parents=True, exist_ok=True)
sources = [p for p in root.iterdir() if p.is_file() and p.suffix in ('.sqlite', '.sqlite3', '.db')]
sources += [root/'paper-final-v9'/'ledger.sqlite3', root/'paper-v10'/'ledger.sqlite3']
for p in sources:
    if p.exists():
        name = f'{p.parent.name}-{p.name}'
        with sqlite3.connect(f'file:{p}?mode=ro', uri=True) as src, sqlite3.connect(backup/name) as dst:
            src.backup(dst)
target = root/'paper-v10'
target.mkdir(exist_ok=True)
(target/'activated').write_text('V10 selected; separate seven-day paper ledger. V1 entries vetoed across restarts.\n')
print('Consistent SQLite backups saved. V9 records retained.')
PY

failed() {
  echo 'V10 verification failed; no operational success is being claimed.' >&2
  dc logs --tail=35 crypto_v10 dashboard || true
  echo 'V1 entries remain paused. Fix the reported error and rerun this launcher; ledgers will not reset.' >&2
}
trap failed ERR
dc up -d --no-deps --force-recreate crypto
dc up -d --no-deps crypto_v10 dashboard
echo 'Waiting for V10 runtime and selected dashboard verification...'
ok=0
for attempt in {1..60}; do
  if dc exec -T dashboard python - <<'PY'
import json, time, urllib.request
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8090'+path, timeout=15) as r:
        return json.load(r)
s = get('/api/paper-v10')
assert s['version'] == 'V10-PAPER-1'
assert s['status'] in ('RUNNING','DAILY_LOSS_LIMIT','DRAINING') and s['cycles'] >= 1
assert time.time()*1000-(s['last_success_ms'] or 0) < 120000
d = get('/api/snapshot')
assert d['paper_final']['version'] == 'V10-PAPER-1'
assert d['crypto']['config']['timeframe'] == '15m'
print('Fresh V10 market cycle and dashboard verified.')
PY
  then ok=1; break; fi
  sleep 3
done
[[ "$ok" == 1 ]]

if [[ -x /usr/bin/caffeinate ]]; then
  if [[ ! -f .caffeinate.pid ]] || ! kill -0 "$(cat .caffeinate.pid)" 2>/dev/null; then
    nohup /usr/bin/caffeinate -dimsu >/tmp/signal-vault-caffeinate.log 2>&1 &
    echo $! > .caffeinate.pid
    chmod 600 .caffeinate.pid
  fi
fi
echo 'VERIFIED: V10 synthetic paper runtime is active. Dashboard: http://127.0.0.1:8090'
echo 'New campaign: first scan sets the boundary; entries start at the next 15m close if a signal qualifies.'
echo 'Resume: original deadline, balance, positions and consumed signals are retained.'
echo 'No historical trades are added. No forced entries or profit guarantee.'
echo 'Keep Docker running and the Mac plugged in with its lid open.'
echo 'Status: bash trading_stack/status_v10_mac.sh'
if command -v open >/dev/null; then open http://127.0.0.1:8090; fi
