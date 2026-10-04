#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
RESUME_USER_STOP=0
TRADE_NOW=0
case "${1:-}" in
  '') ;;
  --resume-user-stop) RESUME_USER_STOP=1 ;;
  --trade-now) RESUME_USER_STOP=1; TRADE_NOW=1 ;;
  *) echo 'Usage: bash trading_stack/start_v11_500_mac.sh [--resume-user-stop|--trade-now]' >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Unexpected extra arguments.' >&2; exit 2; }
[[ -f .env ]] || { echo 'Missing trading_stack/.env from the existing installation.' >&2; exit 2; }
docker info >/dev/null
dc() { docker compose --env-file .env --profile '*' "$@"; }
echo 'Building the isolated $500 / 48-hour failed-rebound paper trial...'
dc build crypto crypto_v11 dashboard
echo 'Preflight public daily history and bid/ask; no account balance or deadline changed...'
dc run --rm -T --no-deps crypto_v11 --preflight
if [[ "$RESUME_USER_STOP" == 1 ]]; then dc stop crypto_v11; fi
dc run --rm -T --no-deps --entrypoint python crypto_v11 - "$RESUME_USER_STOP" <<'PY'
import fcntl, json, sqlite3, sys, time
from pathlib import Path
sys.path.insert(0, '/freqtrade/user_data')
from paper_v11 import VERSION,SPEC
p=Path('/freqtrade/data/paper-v11-500/ledger.sqlite3')
if p.exists():
    lock=(p.parent/'runtime.lock').open('a')
    if sys.argv[1]=='1':fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as db:
        row=db.execute('SELECT payload FROM state WHERE id=1').fetchone()
    if not row:raise SystemExit('Existing V11 ledger is incomplete; no reset performed.')
    s=json.loads(row[0])
    if s.get('version')!=VERSION or s.get('spec')!=SPEC:raise SystemExit('Existing V11 specification differs; no reset performed.')
    now=int(time.time()*1000)
    if s['deadline_ms']<=now:raise SystemExit('This V11 deadline has passed. Balance and history will not be reset.')
    if sys.argv[1]=='1':
        if s.get('halt_reason') not in (None,'USER_STOP'):
            raise SystemExit('Only a manual user stop can be resumed; risk/session halts are retained.')
        markers=[p.parent/'stop',p.parent/'drain']
        if s.get('halt_reason')=='USER_STOP' or any(marker.exists() for marker in markers) or s.get('drain'):
            if s.get('positions'):raise SystemExit('Manual stop/drain has unresolved positions. Resume refused; let them close first.')
            backup=p.parent/f'ledger-before-resume-{now}.sqlite3'
            with sqlite3.connect(f'file:{p}?mode=ro',uri=True) as source,sqlite3.connect(backup) as dest:source.backup(dest)
            event=dict(kind='USER_REQUESTED_RESUME',observed_ms=now,previous_halt=s.get('halt_reason'),deadline_ms=s['deadline_ms'])
            s.update(halt_reason=None,status='STOPPED',drain=False)
            with sqlite3.connect(p) as db:
                db.execute('UPDATE state SET payload=? WHERE id=1',(json.dumps(s,allow_nan=False),))
                db.execute('INSERT INTO events(payload) VALUES(?)',(json.dumps(event,allow_nan=False),))
            for marker in markers:marker.unlink(missing_ok=True)
            print('Manual stop released. Backup retained; original balance, signal boundary and deadline preserved.')
    if s.get('halt_reason'):raise SystemExit('This V11 trial is halted. Its balance and history will not be reset. Review status_v11_500_mac.sh.')
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
dc run --rm -T --no-deps --entrypoint python crypto_v11 - "$TRADE_NOW" <<'PY'
import json,shutil,sqlite3,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0, '/freqtrade/user_data')
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
if sys.argv[1]=='1':
    (target/'trade-now').write_text('User requested immediate entry checks; new timing experiment, fresh quotes only.\n')
print('Backups saved; older synthetic campaigns retained and flat. New account selected.')
PY
RESTORE_OLD=0
dc up -d --no-deps --force-recreate crypto
dc up -d --no-deps --force-recreate crypto_v11 dashboard
echo 'Waiting for a fresh runtime cycle and the $500 dashboard selection...'
ok=0
for attempt in {1..60}; do
  if dc exec -T dashboard python - "$TRADE_NOW" <<'PY'
import json,sys,time,urllib.request,urllib.error
def get(path):
    with urllib.request.urlopen('http://127.0.0.1:8090'+path,timeout=15) as r:return json.load(r)
try:
    s=get('/api/paper-v11')
    if s.get('version')!='V11-PAPER-500-1' or s.get('status')!='RUNNING' or s.get('cycles',0)<1:
        raise SystemExit('Waiting: V11 has not completed its first successful market cycle.')
    if time.time()*1000-(s.get('last_success_ms') or 0)>=120000:
        raise SystemExit('Waiting: V11 needs a fresh successful market cycle.')
    if len(sys.argv)>1 and sys.argv[1]=='1' and ((s.get('entry_policy') or {}).get('name')!='V11-IMMEDIATE-1' or s.get('entry_checks',0)<1):
        raise SystemExit('Waiting: immediate entry policy and first entry scan are not verified yet.')
    d=get('/api/snapshot')
    if d.get('paper_final',{}).get('version')!='V11-PAPER-500-1':
        raise SystemExit('Waiting: dashboard has not selected V11 yet.')
    crypto=d.get('crypto',{})
    if crypto.get('starting_balance')!=500 or crypto.get('config',{}).get('timeframe')!='1d':
        raise SystemExit('Waiting: dashboard account settings are not verified yet.')
except (urllib.error.URLError,TimeoutError,ConnectionError) as exc:
    raise SystemExit('Waiting: dashboard connection is not ready ('+str(exc)+').')
print('Fresh V11 cycle and $500 dashboard verified.')
if (s.get('entry_policy') or {}).get('name')=='V11-IMMEDIATE-1':
    print('Immediate entry checks verified. Checks:',s['entry_checks'],'| Total entries:',s['entries'])
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
echo 'VERIFIED: independent $500 simulated trial active. Original 48-hour deadline preserved on resume. No deposits or broker orders.'
echo 'Entry policy and current signal blockers: bash trading_stack/status_v11_500_mac.sh. No forced trades.'
echo 'Mac and Docker must remain running. Status: bash trading_stack/status_v11_500_mac.sh'
echo 'Dashboard: http://127.0.0.1:8090'
open http://127.0.0.1:8090
