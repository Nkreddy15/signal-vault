import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from signal_vault.market_data import Bar
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.operations import LocalResearchSupervisor

START=datetime(2026,9,27,0,tzinfo=timezone.utc)

def flat_bars():
    return tuple(Bar(START+timedelta(hours=i),Decimal('65000'),Decimal('65100'),
                     Decimal('64900'),Decimal('65000'),Decimal('100'),
                     'unittest_hourly_mock') for i in range(30))

class ResearchSupervisorTests(unittest.TestCase):
    def test_no_forced_trading_and_once_per_hour_tracking(self):
        bars=flat_bars();now=bars[-1].close_time+timedelta(seconds=3)
        with PersistentPaperOrderStore(':memory:') as store:
            worker=LocalResearchSupervisor(store)
            first=worker.run_once(bars,at=now)
            second=worker.run_once(bars,at=now)
            self.assertEqual(first.status,'HOLD')
            self.assertFalse(first.repeated)
            self.assertTrue(second.repeated)
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0],1)
            self.assertEqual([e['type'] for e in store.journal.recent_events()],['RESEARCH_CYCLE'])

    def test_halted_research_never_generates_a_draft(self):
        bars=flat_bars();now=bars[-1].close_time+timedelta(seconds=3)
        with PersistentPaperOrderStore(':memory:') as store:
            worker=LocalResearchSupervisor(store)
            store.set_operator_halt(True,reason='owner paused',at=now)
            self.assertEqual(worker.run_once(bars,at=now).status,'OPERATOR_HALT')
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM drafts').fetchone()[0],0)

    def test_stale_closed_bar_does_not_enter_trading_pipeline(self):
        bars=flat_bars();now=bars[-1].close_time+timedelta(minutes=4)
        with PersistentPaperOrderStore(':memory:') as store:
            worker=LocalResearchSupervisor(store)
            self.assertEqual(worker.run_once(bars,at=now).status,'STALE_WINDOW')
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM research_cycles').fetchone()[0],0)

if __name__=='__main__':unittest.main()
