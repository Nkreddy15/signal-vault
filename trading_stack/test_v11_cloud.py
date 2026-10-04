"""Cloud lifecycle/authentication checks; no market calls or profit fixtures."""
import base64
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

sys.path.insert(0, str(Path(__file__).parent))
import cloud_v11 as cloud


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.mount = Path(self.temp.name)
        self.directory = self.mount / 'paper-v11-500'
        self.env = dict(V11_DASHBOARD_PASSWORD='x' * 40, RAILWAY_VOLUME_MOUNT_PATH=str(self.mount),
                        PAPER_V11_STATE_DIR=str(self.directory), V11_ALLOW_NEW_ACCOUNT='1')
    def tearDown(self):
        self.temp.cleanup()

    def test_requires_private_password_durable_mount_and_fresh_account_authorization(self):
        with patch.object(cloud.os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(ValueError, 'persistent'): cloud.check_settings(self.env)
        with patch.object(cloud.os.path, 'ismount', return_value=True):
            with self.assertRaisesRegex(ValueError, 'password|PASSWORD'):
                cloud.check_settings({**self.env, 'V11_DASHBOARD_PASSWORD': ''})
            with self.assertRaisesRegex(ValueError, 'fresh'):
                cloud.check_settings({**self.env, 'V11_ALLOW_NEW_ACCOUNT': '0'})
            with self.assertRaisesRegex(ValueError, 'ephemeral'):
                cloud.check_settings({**self.env, 'PAPER_V11_STATE_DIR': '/tmp/some-other-ledger'})
            directory, existing = cloud.check_settings(self.env)
        self.assertEqual(directory, self.directory)
        self.assertFalse(existing)
        self.assertFalse(directory.exists())  # Validation itself creates no account.

    def test_existing_account_requires_no_new_account_flag_and_is_not_changed(self):
        self.directory.mkdir()
        path = self.directory / 'ledger.sqlite3'
        path.write_bytes(b'unchanged account sentinel')
        with patch.object(cloud.os.path, 'ismount', return_value=True):
            directory, existing = cloud.check_settings({**self.env, 'V11_ALLOW_NEW_ACCOUNT': '0'})
        self.assertTrue(existing)
        self.assertEqual(path.read_bytes(), b'unchanged account sentinel')

    def test_private_dashboard_health_and_no_other_engines_or_writes(self):
        sys.path.insert(0, str(Path(__file__).parent / 'dashboard'))
        # A fresh dashboard app keeps auth hooks isolated from runtime tests
        # that have already sent requests through the local dashboard.
        spec = importlib.util.spec_from_file_location('isolated_cloud_dashboard', Path(__file__).parent / 'dashboard' / 'app.py')
        dashboard = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'isolated_cloud_dashboard': dashboard}):
            spec.loader.exec_module(dashboard)
        old_root = dashboard.paper_v11_view.ROOT
        self.addCleanup(setattr, dashboard.paper_v11_view, 'ROOT', old_root)
        with patch.dict(os.environ, self.env), patch.dict(sys.modules, {'app': dashboard, 'isolated_cloud_dashboard': dashboard}):
            web = importlib.import_module('cloud_v11_web')
        client = web.app.test_client()
        auth = {'Authorization': 'Basic ' + base64.b64encode(b'nikhil:' + b'x'*40).decode()}
        self.assertEqual(client.get('/healthz').status_code, 200)
        self.assertNotIn('balance', client.get('/healthz').get_data(as_text=True))
        for path in ('/', '/api/snapshot', '/api/paper-v11', '/static/dashboard.css'):
            self.assertEqual(client.get(path).status_code, 401)
        self.assertEqual(client.get('/', headers=auth).status_code, 200)
        response = client.get('/api/paper-v11', headers=auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(client.get('/api/snapshot?engine=v1', headers=auth).status_code, 400)
        self.assertEqual(client.get('/api/paper-v10', headers=auth).status_code, 404)
        self.assertEqual(client.post('/api/paper-v11', headers=auth).status_code, 405)
        self.assertEqual(client.get('/', headers={'Authorization': 'Basic '+base64.b64encode(b'nikhil:wrong').decode()}).status_code, 401)
        # Reuse the actual unchanged worker projection and dashboard selection.
        sys.path.insert(0, str(Path(__file__).parent / 'crypto'))
        import paper_v11 as runtime
        import time
        self.directory.mkdir()
        ledger = runtime.Ledger(self.directory / 'ledger.sqlite3', int(time.time()*1000))
        ledger.state.update(status='RUNNING', cycles=1, last_success_ms=int(time.time()*1000))
        ledger.commit()
        runtime.publish(ledger, self.directory, int(time.time()*1000))
        ledger.db.close()
        (self.directory / 'activated').write_text('selected')
        with patch.object(dashboard, '_freq', return_value=(None, 'unconfigured')), patch.object(dashboard, '_alpaca', return_value=(None, 'unconfigured')):
            response = client.get('/api/snapshot', headers=auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['paper_final']['version'], runtime.VERSION)
        self.assertEqual(response.json['crypto']['starting_balance'], 500)
        self.assertEqual(response.json['crypto']['config']['timeframe'], '1d')

    def test_terminal_requires_flat_account_and_results_preserve_state_events(self):
        self.directory.mkdir()
        state = dict(balance=487.25, deadline_ms=123456, entries=2)
        event = dict(kind='CLOSE', net=-12.75)
        with sqlite3.connect(self.directory / 'ledger.sqlite3') as db:
            db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,payload TEXT)')
            db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,payload TEXT)')
            db.execute('INSERT INTO state VALUES(1,?)', (json.dumps(state),))
            db.execute('INSERT INTO events VALUES(1,?)', (json.dumps(event),))
        summary = dict(version='V11-PAPER-500-1', status='SESSION_COMPLETE', crypto={'open_trade_count': 1})
        (self.directory / 'summary.json').write_text(json.dumps(summary))
        self.assertIsNone(cloud.terminal_summary(self.directory))
        summary['crypto']['open_trade_count'] = 0
        (self.directory / 'summary.json').write_text(json.dumps(summary))
        self.assertEqual(cloud.terminal_summary(self.directory), summary)
        cloud.save_results(self.directory)
        with zipfile.ZipFile(self.directory / 'cloud-results.zip') as z:
            self.assertEqual(json.loads(z.read('account.json')), state)
            self.assertEqual(json.loads(z.read('events.json')), [event])
            self.assertNotIn('V11_DASHBOARD_PASSWORD', ' '.join(z.namelist()))

    def test_supervisor_ends_after_terminal_worker_and_terminates_dashboard(self):
        worker, web = Mock(), Mock()
        worker.poll.return_value = 0
        worker.returncode = 0
        web.poll.return_value = None
        final = dict(status='SESSION_COMPLETE', entries=0, crypto=dict(marked_equity=499.8, closed_trade_count=0))
        with patch.dict(os.environ, self.env), patch.object(cloud, 'check_settings', return_value=(self.directory, True)), \
             patch.object(cloud.subprocess, 'Popen', side_effect=[worker, web]), patch.object(cloud.signal, 'signal'), \
             patch.object(cloud, 'terminal_summary', return_value=final), patch.object(cloud, 'save_results') as save:
            self.assertEqual(cloud.main(), 0)
        save.assert_called_once_with(self.directory)
        web.terminate.assert_called_once()
        worker.terminate.assert_not_called()

    def test_worker_crash_is_not_reported_as_completed_trial(self):
        worker, web = Mock(), Mock()
        worker.poll.return_value = 2
        worker.returncode = 2
        web.poll.return_value = None
        with patch.dict(os.environ, self.env), patch.object(cloud, 'check_settings', return_value=(self.directory, True)), \
             patch.object(cloud.subprocess, 'Popen', side_effect=[worker, web]), patch.object(cloud.signal, 'signal'), \
             patch.object(cloud, 'terminal_summary', return_value=None), patch.object(cloud, 'save_results') as save:
            self.assertEqual(cloud.main(), 1)
        save.assert_not_called()
        web.terminate.assert_called_once()

    def test_dashboard_launch_failure_stops_worker(self):
        worker = Mock()
        with patch.dict(os.environ, self.env), patch.object(cloud, 'check_settings', return_value=(self.directory, True)), \
             patch.object(cloud.subprocess, 'Popen', side_effect=[worker, OSError('fixture')]):
            with self.assertRaises(OSError): cloud.main()
        worker.terminate.assert_called_once()


if __name__ == '__main__':
    unittest.main()
