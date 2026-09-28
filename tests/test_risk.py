import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.domain import PortfolioSnapshot, Side, TradeIntent
from signal_vault.risk import RiskEngine


NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def proposal(**changes):
    obj = TradeIntent(
        market="crypto", venue="alpaca", symbol="BTC/USD", side=Side.BUY,
        notional_usd=Decimal("15"), client_order_id="test-order-1",
        signal_id="test-signal-1", quote_timestamp=NOW,
    )
    return replace(obj, **changes)


def snapshot(**changes):
    obj = PortfolioSnapshot(
        equity_usd=Decimal("100"), cash_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        session_start_equity_usd=Decimal("100"),
    )
    return replace(obj, **changes)


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RiskEngine()

    def decision(self, order=None, portfolio=None):
        return self.engine.evaluate(order or proposal(), portfolio or snapshot(), now=NOW)

    def test_fresh_small_buy_approved(self):
        self.assertTrue(self.decision().approved)

    def test_single_order_limit(self):
        self.assertIn("single-buy allocation exceeded",
                      self.decision(proposal(notional_usd=Decimal("16"))).reasons)

    def test_portfolio_exposure_includes_pending_orders(self):
        p = snapshot(equity_usd=Decimal("100"), cash_usd=Decimal("80"),
                     long_positions_usd={"BTC/USD": Decimal("25")},
                     open_buy_notional_usd=Decimal("2"))
        self.assertFalse(self.decision(portfolio=p).approved)

    def test_daily_equity_loss_rejects_new_buy(self):
        p = snapshot(equity_usd=Decimal("97"), cash_usd=Decimal("97"))
        self.assertIn("daily equity-loss pause triggered", self.decision(portfolio=p).reasons)

    def test_peak_to_current_drawdown_rejects_new_buy(self):
        p = snapshot(equity_usd=Decimal("90"), cash_usd=Decimal("90"))
        self.assertIn("portfolio drawdown pause triggered", self.decision(portfolio=p).reasons)

    def test_stale_quote_rejected(self):
        stale = proposal(quote_timestamp=NOW - timedelta(seconds=120))
        self.assertIn("missing or stale quote", self.decision(order=stale).reasons)

    def test_unknown_venue_rejected(self):
        self.assertFalse(self.decision(proposal(venue="other")).approved)

    def test_unknown_symbol_rejected(self):
        self.assertFalse(self.decision(proposal(symbol="ETH/USD")).approved)

    def test_no_shorts(self):
        self.assertIn("shorting disabled", self.decision(
            proposal(side=Side.SELL, notional_usd=Decimal("10"))).reasons[0])

    def test_risk_reducing_sell_during_daily_loss_pause(self):
        p = snapshot(equity_usd=Decimal("97"), cash_usd=Decimal("82"),
                     long_positions_usd={"BTC/USD": Decimal("15")})
        self.assertTrue(self.decision(proposal(side=Side.SELL), p).approved)

    def test_operator_emergency_halt_stops_all(self):
        self.assertFalse(self.decision(portfolio=snapshot(halted=True)).approved)

    def test_reject_invalid_nan_input(self):
        self.assertFalse(self.decision(proposal(notional_usd=Decimal("NaN"))).approved)

    def test_reject_invalid_portfolio_snapshot(self):
        p = snapshot(cash_usd=Decimal("NaN"))
        self.assertFalse(self.decision(portfolio=p).approved)

    def test_quote_timestamp_must_be_timezone_aware(self):
        self.assertFalse(self.decision(
            proposal(quote_timestamp=datetime(2026, 9, 28, 12, 0))).approved)

    def test_reject_missing_signal_id(self):
        self.assertFalse(self.decision(proposal(signal_id="")).approved)
