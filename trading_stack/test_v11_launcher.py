"""Reproduce Docker's python-stdin import context without Docker or network."""
import ast
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__=='__main__':unittest.main()
