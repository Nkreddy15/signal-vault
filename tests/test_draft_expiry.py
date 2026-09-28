import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from signal_vault.domain import PortfolioSnapshot,Side,TradeIntent
from signal_vault.paper_store import PersistentPaperOrderStore
from signal_vault.paper_audit import PaperHoldings

START=datetime(2026,9,28,23,30,tzinfo=timezone.utc)
P=PortfolioSnapshot(Decimal('100'),Decimal('100'),Decimal('100'),Decimal('100'))

def intent(client_id):
    return TradeIntent('crypto','alpaca','BTC/USD',Side.BUY,Decimal('15'),
                       client_id,'test-evidence',START)

class DraftExpiryTests(unittest.TestCase):
    def test_old_unsent_draft_releases_cash_with_immutable_event(self):
        with PersistentPaperOrderStore(':memory:') as s:
            d=s.journal.record(intent('expire-a'),P,checked_at=START,reference_price=Decimal('65000'))
            self.assertEqual(s.journal.total_reserved_usd(),Decimal('15'))
            before=START+timedelta(seconds=119)
            self.assertEqual(s.journal.expire_unsent_drafts(at=before),())
            later=START+timedelta(seconds=121)
            self.assertEqual(s.journal.expire_unsent_drafts(at=later),(d.client_order_id,))
            self.assertEqual(s.journal.total_reserved_usd(),Decimal('0'))
            self.assertEqual(s.journal.expire_unsent_drafts(at=later),())
            self.assertEqual(s.journal.recent_events()[-1]['type'],'UNSENT_DRAFT_EXPIRED')

    def test_unknown_or_accepted_paper_order_never_expires_with_draft_ttl(self):
        with PersistentPaperOrderStore(':memory:') as s:
            d=s.journal.record(intent('expire-b'),P,checked_at=START,reference_price=Decimal('65000'))
            s.begin_submission(d,at=START,baseline=PaperHoldings('paper-1',Decimal('10000'),Decimal('0'),START))
            s.mark_unknown(d.client_order_id,at=START)
            self.assertEqual(s.journal.expire_unsent_drafts(at=START+timedelta(days=2)),())
            self.assertEqual(s.journal.total_reserved_usd(),Decimal('15'))
            self.assertTrue(s.has_unresolved_provider_order())

if __name__=='__main__':unittest.main()
