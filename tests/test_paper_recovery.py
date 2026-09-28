import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from signal_vault.domain import PortfolioSnapshot,TradeIntent,Side
from signal_vault.alpaca_paper import PaperAlpacaReadClient
from signal_vault.paper_executor import PaperOnceExecutor
from signal_vault.paper_order_state import Stage
from signal_vault.paper_recovery import PaperRecoverySupervisor
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_audit import PaperHoldings
from signal_vault.fake_paper_scenario import DeliberatelyFakePaperVenue

AT=datetime(2026,9,28,23,15,tzinfo=timezone.utc)
KEY,SECRET='LOCAL_FAKE_NOT_A_CREDENTIAL','LOCAL_FAKE_NOT_A_SECRET'


def setup():
    venue=DeliberatelyFakePaperVenue()
    store=PersistentPaperOrderStore(':memory:')
    d=store.journal.record(TradeIntent('crypto','alpaca','BTC/USD',Side.BUY,
          Decimal('15'),'recover-one','source-recovery',AT),
          PortfolioSnapshot(Decimal('100'),Decimal('100'),Decimal('100'),Decimal('100')),
          checked_at=AT,reference_price=Decimal('65000'))
    reader=PaperAlpacaReadClient(KEY,SECRET,transport=venue.read)
    executor=PaperOnceExecutor(paper_key=KEY,paper_secret=SECRET,
                               store=store,transport=venue.post_fake)
    executor.submit_once(d,at=AT,reader=reader)
    return venue,store,d,reader,executor

class RecoveryTests(unittest.TestCase):
    def test_accepted_to_terminal_to_audited_without_any_second_post(self):
        venue,store,d,reader,executor=setup()
        with store:
            manager=PaperRecoverySupervisor(store=store,executor=executor,reader=reader)
            venue.simulate_fill()
            one=manager.recover_once(at=AT+timedelta(seconds=3))
            self.assertFalse(one.safe_for_new_submission)
            self.assertEqual(one.items[0].after,Stage.BROKER_TERMINAL_UNRECONCILED)
            two=manager.recover_once(at=AT+timedelta(seconds=5))
            self.assertTrue(two.safe_for_new_submission)
            self.assertEqual(two.items[0].after,Stage.RECONCILED)
            self.assertEqual(venue.posts,1)
            self.assertEqual(store.journal.total_reserved_usd(),Decimal('0'))

    def test_unknown_order_stays_blocked_if_source_lookup_not_found(self):
        # Simulate a crash after the durable SUBMISSION_PENDING commit, where
        # the external POST may or may not have reached the provider.
        venue=DeliberatelyFakePaperVenue()
        store=PersistentPaperOrderStore(':memory:')
        d=store.journal.record(TradeIntent('crypto','alpaca','BTC/USD',Side.BUY,
             Decimal('15'),'unknown-one','source-recovery',AT),
             PortfolioSnapshot(Decimal('100'),Decimal('100'),Decimal('100'),Decimal('100')),
             checked_at=AT,reference_price=Decimal('65000'))
        reader=PaperAlpacaReadClient(KEY,SECRET,transport=venue.read)
        executor=PaperOnceExecutor(paper_key=KEY,paper_secret=SECRET,
                                   store=store,transport=venue.post_fake)
        with store:
            store.begin_submission(d,at=AT,baseline=PaperHoldings('FAKE_ACCOUNT_01',
                                   Decimal('10000'),Decimal('0'),AT))
            store.mark_unknown(d.client_order_id,at=AT)
            manager=PaperRecoverySupervisor(store=store,executor=executor,reader=reader)
            result=manager.recover_once(at=AT+timedelta(seconds=3))
            self.assertFalse(result.safe_for_new_submission)
            self.assertEqual(result.items[0].after,Stage.UNKNOWN_RESULT)
            self.assertEqual(store.journal.total_reserved_usd(),Decimal('15'))
            self.assertEqual(venue.posts,0)

    def test_different_account_reader_is_never_accepted_for_recovery(self):
        venue,store,d,reader,executor=setup()
        with store:
            wrong=PaperAlpacaReadClient('unrelated-paper-key','different-secret',transport=venue.read)
            with self.assertRaises(PermissionError):
                PaperRecoverySupervisor(store=store,executor=executor,reader=wrong)
            self.assertEqual(venue.posts,1)

if __name__=='__main__':unittest.main()
