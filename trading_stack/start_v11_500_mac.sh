#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
[[ -f .env ]] || { echo 'Missing trading_stack/.env from the existing installation.' >&2; exit 2; }
docker info >/dev/null
dc() { docker compose --env-file .env --profile '*' "$@"; }
echo 'Building the isolated $500 / 48-hour failed-rebound paper trial...'
dc build crypto crypto_v11 dashboard
echo 'Preflight public daily history and bid/ask; no paper account created yet...'
dc run --rm -T --no-deps crypto_v11 --preflight
dc run --rm -T --no-deps --entrypoint python crypto_v11 - <<'PY'
import json, sqlite3, time
from pathlib import Path
from paper_v11 import VERSION,SPEC
p=Path('/freqtrade/data/paper-v11-500/ledger.sqlite3')
if p.exists():
    with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    if not row:raise SystemExit('Existing V11 ledger is incomplete; no reset performed.')
    s=json.loads(row[0])
    if s.get('version')!=VERSION or s.get('spec')!=SPEC:raise SystemExit('Existing V11 specification differs; no reset performed.')
    if s['deadline_ms']<=time.time()*1000 or s.get('halt_reason'):raise SystemExit('This V11 trial has ended. Its $500 balance and history will not be reset. Review status_v11_500_mac.sh.')
    print('Resume original V11 balance, positions and deadline.')
else:print('New independent $500 simulated account, 48 hours from first runtime start.')
PY
echo 'Verifying the old Freqtrade account is paper and pausing new entries...'
CRYPTO_RUNNING=0
while IFS= read -r service; do
  if [[ "$service" == crypto ]]; then CRYPTO_RUNNING=1; fi
done < <(dc ps --status running --services)
if [[ "$CRYPTO_RUNNING" == 1 ]]; then
dc exec -T crypto python - <<'PY'
import base64,json,os,urllib.request,urllib.error
auth=base64.b64encode((os.environ['FREQTRADE__API_SERVER__USERNAME']+':'+os.environ['FREQTRADE__API_SERVER__PASSWORD']).encode()).decode()
def call(path,method='GET'):
    req=urllib.request.Request('http://127.0.0.1:8080/api/v1/'+path,method=method,headers={'Authorization':'Basic '+auth})
    with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
c=call('show_config')
if c.get('dry_run') is not True or c.get('strategy')!='SignalVaultPaperExecutionV1':raise SystemExit('Expected existing PAPER V1; cutover not performed.')
try:call('pause','POST')
except urllib.error.HTTPError as exc:
    if exc.code!=404:raise
    call('stopbuy','POST')
c=call('show_config')
if str(c.get('state','')).lower()!='paused' and c.get('max_open_trades')!=0:raise SystemExit('Old entry pause could not be verified.')
print('Old V1 entry pause verified. Existing positions retain their exits.')
PY
else
  dc run --rm -T --no-deps --entrypoint python crypto - <<'PY'
import json,os
from pathlib import Path
c=json.loads(Path('/freqtrade/user_data/config.json').read_text())
if c.get('dry_run') is not True or c.get('exchange',{}).get('key') or c.get('exchange',{}).get('secret'):raise SystemExit('Expected a credential-free paper configuration.')
if os.environ.get('SIGNAL_VAULT_CRYPTO_STRATEGY','SignalVaultPaperExecutionV1')!='SignalVaultPaperExecutionV1':raise SystemExit('Expected V1 for the persistent entry veto.')
print('Old engine is offline. It will start only after the persistent entry veto is installed.')
PY
fi
OLD_RUNNING=()
while IFS= read -r service; do
  case "$service" in crypto_final|crypto_v10|crypto_v8_forward_lab|crypto_v8_overnight) OLD_RUNNING+=("$service");; esac
done < <(dc ps --status running --services)
RESTORE_OLD=1
failed() {
  echo 'Trial startup did not verify. Existing ledgers have not been erased.' >&2
  if [[ "$RESTORE_OLD" == 1 && ${#OLD_RUNNING[@]} -gt 0 ]]; then dc up -d --no-deps "${OLD_RUNNING[@]}" || true; fi
  dc logs --tail=30 crypto_v11 dashboard || true
}
trap failed ERR
dc stop crypto_final crypto_v10 crypto_v8_forward_lab crypto_v8_overnight
echo 'Backing up old ledgers and checking that older synthetic campaigns are flat...'
dc run --rm -T --no-deps --entrypoint python crypto_v11 - <<'PY'
import json,shutil,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from paper_v11 import has_held_positions
root=Path('/freqtrade/data')
backup=root/'v11-upgrade-backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
backup.mkdir(parents=True)
for p in root.iterdir():
    if p.is_file() and p.suffix in ('.db','.sqlite','.sqlite3'):
        with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as src,sqlite3.connect(backup/p.name) as dst:src.backup(dst)
held=[]
for folder in ('paper-final-v9','paper-v10','v8-forward-lab','v8-overnight'):
    source=root/folder
    if source.exists():shutil.copytree(source,backup/folder)
    p=source/'ledger.sqlite3'
    if p.exists():
        with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:row=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
        if not row:raise SystemExit(f'{folder}: incomplete old ledger; cutover stopped.')
        if has_held_positions(json.loads(row[0])):held.append(folder)
    p=source/'state.json'
    if p.exists():
        s=json.loads(p.read_text())
        if has_held_positions(s):held.append(folder)
if held:raise SystemExit('Old synthetic positions remain in '+', '.join(held)+'. Cutover stopped; old services will resume. Let them exit before retrying. Backups retained.')
target=root/'paper-v11-500';target.mkdir(exist_ok=True)
(target/'activated').write_text('Selected isolated $500 / 48h synthetic failed-rebound trial. V1 entries vetoed.\n')
print('Backups saved; older synthetic campaigns retained and flat. New account selected.')
PY
RESTORE_OLD=0
dc up -d --no-deps --force-recreate crypto
dc up -d --no-deps crypto_v11 dashboard
echo 'Waiting for a fresh runtime cycle and the $500 dashboard selection...'
ok=0
for attempt in {1..60}; do
  if dc exec -T dashboard python - <<'PY'
import json,time,urllib.request
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8090'+path,timeout=15) as r:return json.load(r)
s=get('/api/paper-v11')
assert s['version']=='V11-PAPER-500-1' and s['status']=='RUNNING' and s['cycles']>=1
assert time.time()*1000-(s['last_success_ms'] or 0)<120000
d=get('/api/snapshot')
assert d['paper_final']['version']=='V11-PAPER-500-1'
assert d['crypto']['starting_balance']==500 and d['crypto']['config']['timeframe']=='1d'
print('Fresh V11 cycle and $500 dashboard verified.')
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
echo 'VERIFIED: independent $500 simulated trial active for 48 hours. No deposits or broker orders.'
echo 'Daily signals at 00:00 UTC; initial historical signals are skipped. No forced trades.'
echo 'Mac and Docker must remain running. Status: bash trading_stack/status_v11_500_mac.sh'
echo 'Dashboard: http://127.0.0.1:8090'
open http://127.0.0.1:8090
