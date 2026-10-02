from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.cross_market_risk import assess_new_risk
from signal_vault.execution_drafts import (
    EventExecutionQuote,
    compile_paper_draft,
)
from signal_vault.multimarket_cycle import PlannedExecutionIntent
from signal_vault.multimarket_paper_router import route_paper_execution
from signal_vault.opportunity_engine import Direction, Market


NOW = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)


def intent(
    market,
    direction,
    instrument,
    *,
    notional="15",
    reserved="0.75",
    ident="sv162-test-intent",
):
    return PlannedExecutionIntent(
        client_intent_id=ident,
        market=market,
        instrument=instrument,
        direction=direction,
        route_id="phase162-test-route",
        notional_usd=Decimal(notional),
        reserved_max_loss_usd=Decimal(reserved),
        candidate_id="candidate:test",
        evidence_id="evidence:test",
        generated_utc=NOW,
        expected_net_return=Decimal("0.02"),
    )


def risk_for(draft):
    return assess_new_risk(
        lane=draft.market_lane,
        proposed_max_loss_usd=draft.max_loss_usd,
        exposure_by_lane={},
        open_positions=0,
        marked_equity_usd=Decimal("100"),
        daily_anchor_equity_usd=Decimal("100"),
        peak_equity_usd=Decimal("100"),
        operator_halted=False,
    )


class Phase162ExecutionDraftTests(unittest.TestCase):
    def test_crypto_and_equity_long_intents_compile_to_bounded_market_orders(self):
        crypto = compile_paper_draft(
            intent(Market.CRYPTO, Direction.LONG, "BTC/USD"),
            as_of=NOW,
        )
        stock = compile_paper_draft(
            intent(
                Market.US_EQUITY,
                Direction.LONG,
                "NVDA",
                ident="sv162-stock-test",
            ),
            as_of=NOW,
        )
        self.assertEqual(crypto.payload["side"], "buy")
        self.assertEqual(crypto.payload["notional"], "15")
        self.assertEqual(crypto.payload["time_in_force"], "gtc")
        self.assertEqual(stock.payload["side"], "buy")
        self.assertEqual(stock.payload["time_in_force"], "day")
        # The existing paper router independently validates the compiled shape
        # and the exact maximum-loss risk receipt.
        self.assertEqual(
            route_paper_execution(
                crypto,
                risk_assessment=risk_for(crypto),
            ).environment,
            "paper",
        )
        self.assertEqual(
            route_paper_execution(
                stock,
                risk_assessment=risk_for(stock),
            ).environment,
            "paper",
        )

    def test_event_yes_compiles_to_v2_bid_with_risk_bounded_count(self):
        planned = intent(
            Market.EVENT_CONTRACT,
            Direction.YES,
            "KXTEST",
            notional="10",
            reserved="10",
            ident="sv162-event-yes",
        )
        quote = EventExecutionQuote(
            ticker="KXTEST",
            yes_ask_probability=Decimal("0.55"),
            no_ask_probability=Decimal("0.47"),
            captured_utc=NOW - timedelta(seconds=2),
            fractional_trading_enabled=True,
        )
        draft = compile_paper_draft(
            planned,
            as_of=NOW,
            event_quote=quote,
        )
        self.assertEqual(draft.payload["side"], "bid")
        self.assertEqual(draft.payload["price"], "0.55")
        self.assertLessEqual(draft.max_loss_usd, Decimal("10"))
        self.assertLessEqual(Decimal(draft.payload["count"]), Decimal("100"))
        self.assertEqual(
            route_paper_execution(
                draft,
                risk_assessment=risk_for(draft),
            ).environment,
            "demo",
        )

    def test_event_no_maps_to_yes_book_ask_at_one_minus_no_ask(self):
        planned = intent(
            Market.EVENT_CONTRACT,
            Direction.NO,
            "KXTEST",
            notional="10",
            reserved="10",
            ident="sv162-event-no",
        )
        quote = EventExecutionQuote(
            ticker="KXTEST",
            yes_ask_probability=Decimal("0.58"),
            no_ask_probability=Decimal("0.44"),
            captured_utc=NOW - timedelta(seconds=2),
            fractional_trading_enabled=False,
        )
        draft = compile_paper_draft(
            planned,
            as_of=NOW,
            event_quote=quote,
        )
        self.assertEqual(draft.payload["side"], "ask")
        self.assertEqual(draft.payload["price"], "0.56")
        self.assertEqual(
            Decimal(draft.payload["count"]),
            Decimal(draft.payload["count"]).to_integral_value(),
        )
        self.assertLessEqual(draft.max_loss_usd, Decimal("10"))

    def test_stale_event_quote_never_becomes_order_draft(self):
        planned = intent(
            Market.EVENT_CONTRACT,
            Direction.YES,
            "KXTEST",
            notional="10",
            reserved="10",
            ident="sv162-event-stale",
        )
        quote = EventExecutionQuote(
            ticker="KXTEST",
            yes_ask_probability=Decimal("0.55"),
            no_ask_probability=Decimal("0.47"),
            captured_utc=NOW - timedelta(minutes=2),
            fractional_trading_enabled=True,
        )
        with self.assertRaises(ValueError):
            compile_paper_draft(
                planned,
                as_of=NOW,
                event_quote=quote,
            )

    def test_stock_or_crypto_short_cannot_sneak_through_long_entry_compiler(self):
        short = intent(
            Market.US_EQUITY,
            Direction.SHORT,
            "SPY",
            ident="sv162-stock-short",
        )
        with self.assertRaises(PermissionError):
            compile_paper_draft(short, as_of=NOW)


if __name__ == "__main__":
    unittest.main()
