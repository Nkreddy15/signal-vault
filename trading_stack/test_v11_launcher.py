"""Reproduce Docker's python-stdin import context without Docker or network."""
import ast
import contextlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error

ROOT=Path(__file__).parent


def blocks(script):
    return re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY(?:\n|$)",script,re.S)


class LauncherTests(unittest.TestCase):
    def resume_fixture(self,root,halt='USER_STOP',expired=False,held=False,enabled=True):
        sys.path.insert(0,str(ROOT/'crypto'))
        import paper_v11 as runtime
        now=int(time.time()*1000)
        ledger=runtime.Ledger(root/'ledger.sqlite3',now-(3*runtime.m.DAY if expired else 10000))
        ledger.state.update(balance=498.75,entries=3,boundary=now//runtime.m.DAY*runtime.m.DAY-runtime.m.DAY,
                            halt_reason=halt,status=halt or 'STOPPED')
        if held:ledger.state['positions']={'BTC/USD':{'stake_amount':15}}
        ledger.commit();ledger.db.close()
        (root/'stop').write_text('user stop')
        block=blocks((ROOT/'start_v11_500_mac.sh').read_text())[0]
        block=block.replace('/freqtrade/user_data',str(ROOT/'crypto')).replace('/freqtrade/data/paper-v11-500/ledger.sqlite3',str(root/'ledger.sqlite3'))
        scope={}
        try:
            with patch.object(sys,'argv',['-',str(int(enabled))]),contextlib.redirect_stdout(io.StringIO()):
                exec(block,scope)
        finally:
            if 'lock' in scope:scope['lock'].close()

    def test_manual_resume_preserves_balance_boundary_history_and_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.resume_fixture(root)
            with sqlite3.connect(root/'ledger.sqlite3') as db:
                s=json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
                event=json.loads(db.execute('SELECT payload FROM events').fetchone()[0])
            self.assertEqual(s['balance'],498.75);self.assertEqual(s['entries'],3)
            self.assertIsNone(s['halt_reason']);self.assertFalse((root/'stop').exists())
            self.assertEqual(event['deadline_ms'],s['deadline_ms'])
            self.assertEqual(event['kind'],'USER_REQUESTED_RESUME')
            backups=list(root.glob('ledger-before-resume-*.sqlite3'));self.assertEqual(len(backups),1)
            with sqlite3.connect(backups[0]) as db:
                before=json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
            for field in ('started_ms','deadline_ms','balance','boundary','entries','closed','fills','next_id'):
                self.assertEqual(s[field],before[field])
            self.assertEqual(before['halt_reason'],'USER_STOP')

    def test_resume_refuses_risk_halts_expired_trials_and_pending_positions(self):
        for args,message in [({'halt':'SESSION_LOSS_LIMIT'},'risk/session'),({'expired':True},'deadline has passed'),
                             ({'held':True},'unresolved positions'),({'enabled':False},'is halted')]:
            with self.subTest(args=args),tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                with self.assertRaises(SystemExit) as error:self.resume_fixture(root,**args)
                self.assertIn(message,str(error.exception))
                self.assertTrue((root/'stop').exists())
                with sqlite3.connect(root/'ledger.sqlite3') as db:
                    s=json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
                    count=db.execute('SELECT count(*) FROM events').fetchone()[0]
                self.assertEqual(s['balance'],498.75);self.assertEqual(count,0)

    def test_both_stdin_imports_work_from_outside_the_source_directory(self):
        script=(ROOT/'start_v11_500_mac.sh').read_text();tested=0
        for block in blocks(script):
            tree=ast.parse(block)
            imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='paper_v11']
            if not imports:continue
            # Execute the actual launch prefix, mapping only the image's source
            # directory onto this workspace. No ledger/backup/API code runs.
            code='\n'.join(block.splitlines()[:imports[0].end_lineno])
            code=code.replace('/freqtrade/user_data',str(ROOT/'crypto'))
            # Local third-party test packages stand in for installed image
            # dependencies; the project itself stays absent from PYTHONPATH.
            code='import site\nsite.addsitedir('+repr(str(ROOT.parent.parent/'test-deps'))+')\n'+code
            env=os.environ.copy();env.pop('PYTHONPATH',None)
            with tempfile.TemporaryDirectory() as cwd:
                result=subprocess.run([sys.executable,'-'],input=code,text=True,cwd=cwd,env=env,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr);tested+=1
        self.assertEqual(tested,2)

    def test_all_inline_python_blocks_parse_and_missing_dashboard_is_explained(self):
        for name in ['start_v11_500_mac.sh','status_v11_500_mac.sh','stop_v11_500_mac.sh','export_v11_500_mac.sh']:
            for block in blocks((ROOT/name).read_text()):ast.parse(block)
        block=blocks((ROOT/'status_v11_500_mac.sh').read_text())[0]
        # Exercise the user's exact 404 response, rather than a generic error.
        prefix="from unittest.mock import patch\nimport urllib.error\n"
        indented='\n'.join('    '+line for line in block.splitlines())
        code=prefix+"with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('http://127.0.0.1:8090/api/paper-v11',404,'NOT FOUND',{},None)):\n"+indented
        result=subprocess.run([sys.executable,'-'],input=code,text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('dashboard still runs an older image',result.stderr)
        self.assertNotIn('Traceback',result.stderr)

    def test_readiness_waits_without_tracebacks_and_requires_every_gate(self):
        block=blocks((ROOT/'start_v11_500_mac.sh').read_text())[-1]
        state={'version':'V11-PAPER-500-1','status':'RUNNING','cycles':1,'last_success_ms':time.time()*1000}
        dashboard={'paper_final':{'version':'V11-PAPER-500-1'},'crypto':{'starting_balance':500,'config':{'timeframe':'1d'}}}
        cases=[
            ({**state,'cycles':0},dashboard,'first successful market cycle'),
            ({**state,'status':'STARTING'},dashboard,'first successful market cycle'),
            ({**state,'last_success_ms':0},dashboard,'fresh successful market cycle'),
            (state,{**dashboard,'paper_final':{}},'has not selected V11'),
            (state,{**dashboard,'crypto':{'starting_balance':100}},'account settings'),
        ]
        for s,d,message in cases:
            with self.subTest(message=message):
                output=io.StringIO()
                responses=[io.StringIO(json.dumps(s)),io.StringIO(json.dumps(d))]
                with patch('urllib.request.urlopen',side_effect=responses),contextlib.redirect_stdout(output):
                    with self.assertRaises(SystemExit) as error:exec(block,{})
                self.assertIn(message,str(error.exception))
                self.assertEqual(output.getvalue(),'')
        with patch('urllib.request.urlopen',side_effect=urllib.error.URLError('starting')):
            with self.assertRaises(SystemExit) as error:exec(block,{})
        self.assertIn('dashboard connection is not ready',str(error.exception))
        output=io.StringIO()
        with patch('urllib.request.urlopen',side_effect=[io.StringIO(json.dumps(state)),io.StringIO(json.dumps(dashboard))]),contextlib.redirect_stdout(output):
            exec(block,{})
        self.assertIn('Fresh V11 cycle and $500 dashboard verified.',output.getvalue())

    def test_trade_now_verification_requires_enabled_policy_and_actual_entry_scan(self):
        block=blocks((ROOT/'start_v11_500_mac.sh').read_text())[-1]
        state={'version':'V11-PAPER-500-1','status':'RUNNING','cycles':1,'last_success_ms':time.time()*1000,'entries':0}
        dashboard={'paper_final':{'version':'V11-PAPER-500-1'},'crypto':{'starting_balance':500,'config':{'timeframe':'1d'}}}
        for fields in ({},{'entry_policy':{'name':'V11-IMMEDIATE-1'},'entry_checks':0}):
            with patch.object(sys,'argv',['-','1']),patch('urllib.request.urlopen',return_value=io.StringIO(json.dumps({**state,**fields}))):
                with self.assertRaises(SystemExit) as error:exec(block,{})
            self.assertIn('first entry scan',str(error.exception))
        state.update(entry_policy={'name':'V11-IMMEDIATE-1'},entry_checks=1)
        output=io.StringIO()
        with patch.object(sys,'argv',['-','1']),patch('urllib.request.urlopen',side_effect=[io.StringIO(json.dumps(state)),io.StringIO(json.dumps(dashboard))]),contextlib.redirect_stdout(output):
            exec(block,{})
        self.assertIn('Immediate entry checks verified.',output.getvalue())


if __name__=='__main__':unittest.main()
