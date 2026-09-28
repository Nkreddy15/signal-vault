import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.research_runner import main,one_cycle,_single_writer

START=datetime(2026,9,27,0,tzinfo=timezone.utc)

class ResearchRunnerTests(unittest.TestCase):
    def setup_db_csv(self,folder):
        db=folder/'paper.sqlite3';data=folder/'realistic_hourly.csv'
        with PersistentPaperOrderStore(db):pass
        lines=['timestamp,open,high,low,close,volume']
        for h in range(30):
            at=START+timedelta(hours=h)
            lines.append(f'{at.isoformat()},65000,65100,64900,65000,100')
        data.write_text('\n'.join(lines)+'\n')
        return db,data

    def test_operator_csv_is_unverified_research_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,data=self.setup_db_csv(Path(tmp))
            at=START+timedelta(hours=30,seconds=3)
            first=one_cycle(db,as_of=at,csv_path=data)
            second=one_cycle(db,as_of=at,csv_path=data)
            self.assertEqual(first['status'],'HOLD')
            self.assertFalse(first['repeat_cycle'])
            self.assertTrue(second['repeat_cycle'])
            self.assertEqual(first['external_orders_submitted'],0)
            self.assertEqual(first['source'],'UNVERIFIED_OPERATOR_SUPPLIED_CSV')

    def test_flag_gate_and_live_mode_hard_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,data=self.setup_db_csv(Path(tmp))
            with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
                main(['--db',str(db),'--public-data'],env={})
            with self.assertRaises(ValueError):
                main(['--db',str(db),'--csv',str(data),'--as-of',
                      '2026-09-28T06:00:03Z'],env={'SIGNAL_VAULT_MODE':'live'})

    def test_two_workers_are_not_allowed_in_one_sqlite_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            db,_=self.setup_db_csv(Path(tmp))
            with _single_writer(db):
                with self.assertRaises(PermissionError):
                    with _single_writer(db):pass

if __name__=='__main__':unittest.main()
