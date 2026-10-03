"""Reproduce Docker's python-stdin import context without Docker or network."""
import ast
import contextlib
import io
import json
import os
import re
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


if __name__=='__main__':unittest.main()
