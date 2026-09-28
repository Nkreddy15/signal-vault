import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.domain import PortfolioSnapshot
from signal_vault.market_data import Bar
from signal_vault.journal import OfflineDraftJournal
from signal_vault.offline_pipeline import plan_latest_closed_bar
from signal_vault.strategy import Action, StrategyConfig, generate_signal

START = datetime(2026, 8, 1, tzinfo=timezone.utc)


def samples():
    return [Bar(START + timedelta(hours=i), Decimal(x), Decimal(x+1),
                Decimal(x-1), Decimal(x), Decimal("4"), "test-synthetic")
            for i,x in enumerate([100]*8 + [90]*8 + [120]*12)]


def portfolio():
    return PortfolioSnapshot(Decimal("100"), Decimal("100"), Decimal("100"), Decimal("100"))


class OfflinePipelineTests(unittest.TestCase):
    def test_signal_becomes_single_non_executable_local_draft(self):
        bars = samples()
        cfg = StrategyConfig(3, 5)
        prefix = next(bars[:i] for i in range(7, len(bars)+1)
                      if generate_signal(bars[:i], cfg).action is Action.BUY)
        clock = prefix[-1].close_time + timedelta(seconds=5)
        with OfflineDraftJournal(":memory:") as journal:
            a = plan_latest_closed_bar(prefix, now=clock, portfolio=portfolio(),
                                       journal=journal, strategy=cfg)
            self.assertEqual(a.state, "DRAFT_APPROVED_NOT_SUBMITTED")
            self.assertEqual(a.draft.payload["notional"], "15")
            b = plan_latest_closed_bar(prefix, now=clock, portfolio=portfolio(),
                                       journal=journal, strategy=cfg)
            self.assertEqual(b, a)
            self.assertEqual(len(journal.recent_events()), 1)

    def test_stale_price_fails_closed(self):
        bars = samples()
        cfg = StrategyConfig(3, 5)
        prefix = next(bars[:i] for i in range(7, len(bars)+1)
                      if generate_signal(bars[:i], cfg).action is Action.BUY)
        with OfflineDraftJournal(":memory:") as journal:
            result = plan_latest_closed_bar(prefix, now=prefix[-1].close_time + timedelta(minutes=4),
                                            portfolio=portfolio(), journal=journal, strategy=cfg)
            self.assertEqual(result.state, "REJECTED")
            self.assertEqual(journal.total_reserved_usd(), Decimal("0"))

    def test_no_forced_trade_when_no_signal(self):
        data = samples()[:8]
        with OfflineDraftJournal(":memory:") as journal:
            result = plan_latest_closed_bar(data, now=data[-1].close_time,
                                            portfolio=portfolio(), journal=journal,
                                            strategy=StrategyConfig(3, 5))
            self.assertEqual(result.state, "HOLD")
            self.assertEqual(journal.recent_events(), [])


if __name__ == "__main__":
    unittest.main()
