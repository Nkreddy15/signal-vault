"""Explicitly simulated, NO NETWORK, end-to-end developer integration example.

NOT an Alpaca paper fill. It runs the real local journal, guarded execution
state machine and independent audit checks against a fake transport, so a
future credentialed end-to-end test has a reproducible acceptance contract.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping

from .alpaca_paper import PaperAlpacaReadClient
from .domain import PortfolioSnapshot, Side, TradeIntent
from .paper_executor import PaperOnceExecutor
from .paper_store import PersistentPaperOrderStore
from .paper_order_state import Stage

_KEY, _SECRET = "LOCAL_FAKE_NOT_A_CREDENTIAL", "LOCAL_FAKE_NOT_A_SECRET"


class DeliberatelyFakePaperVenue:
    """No URL or network methods. Used only in scripted tests and demos."""
    def __init__(self) -> None:
        self.cash = Decimal("10000")
        self.btc = Decimal("0")
        self.status = "NOT_SUBMITTED"
        self.response: dict[str, object] | None = None
        self.posts = 0

    def read(self, path: str, key: str, secret: str) -> object:
        if (key,secret) != (_KEY,_SECRET):
            raise PermissionError("fake credential mismatch")
        if path == "/v2/account":
            return {"id":"FAKE_ACCOUNT_01", "status":"ACTIVE", "crypto_status":"ACTIVE",
                    "trading_blocked":False, "equity":str(self.cash+self.btc*Decimal("65000")),
                    "cash":str(self.cash), "non_marginable_buying_power":str(self.cash)}
        if path == "/v2/assets/BTC%2FUSD":
            return {"symbol":"BTC/USD", "class":"crypto", "status":"active",
                    "tradable":True,"fractionable":True,"min_order_size":"0.0001",
                    "min_trade_increment":"0.000000001"}
        if path == "/v2/positions":
            return ([{"symbol":"BTC/USD", "side":"long", "qty":str(self.btc)}]
                    if self.btc else [])
        if path == "/v2/orders?status=open":
            return [self.response] if self.status == "accepted" else []
        if path.startswith("/v2/orders:by_client_order_id?client_order_id="):
            if self.response and path.endswith(str(self.response["client_order_id"])):
                return dict(self.response)
            return {"found":False}
        raise AssertionError("No other paths exist on the fake venue")

    def post_fake(self, payload: Mapping[str, str], key: str, secret: str) -> Mapping[str, object]:
        if (key,secret) != (_KEY,_SECRET):
            raise PermissionError("fake credential mismatch")
        if self.response is not None:
            raise AssertionError("second fake POST must never occur")
        self.posts += 1
        self.status = "accepted"
        self.response = {**dict(payload), "id":"FAKE_ORDER_01", "qty":None,
                         "status":"accepted", "filled_qty":"0", "filled_avg_price":None}
        return dict(self.response)

    def simulate_fill(self) -> None:
        if self.status != "accepted" or not self.response:
            raise AssertionError("fake venue order not accepted")
        # Illustrative mock model: $14.95 gross BUY, 0.25% deducted from BTC.
        # This is NOT a real quote, actual fee, or paper-provider confirmation.
        gross_qty, fill_price = Decimal("0.00023"), Decimal("65000")
        self.cash -= gross_qty * fill_price
        self.btc += gross_qty * (Decimal("1") - Decimal("0.0025"))
        self.status = "filled"
        self.response = {**self.response, "status":"filled", "filled_qty":str(gross_qty),
                         "filled_avg_price":str(fill_price)}


def run_fake_scenario() -> dict[str, object]:
    at = datetime(2026, 9, 28, 23, 15, tzinfo=timezone.utc)
    venue = DeliberatelyFakePaperVenue()
    with PersistentPaperOrderStore(":memory:") as book:
        intent = TradeIntent("crypto", "alpaca", "BTC/USD", Side.BUY, Decimal("15"),
                             "fake-e2e-001", "fake-deterministic-signal-not-advice", at)
        portfolio = PortfolioSnapshot(Decimal("100"),Decimal("100"),
                                      Decimal("100"),Decimal("100"))
        draft = book.journal.record(intent, portfolio, checked_at=at,
                                    reference_price=Decimal("65000"))
        reader = PaperAlpacaReadClient(_KEY,_SECRET,transport=venue.read)
        executor = PaperOnceExecutor(paper_key=_KEY,paper_secret=_SECRET,
                                     store=book,transport=venue.post_fake)
        submitted = executor.submit_once(draft,at=at,reader=reader)
        if submitted.stage is not Stage.BROKER_ACCEPTED:
            raise AssertionError("expected accepted fake order, not a fill")
        venue.simulate_fill()
        observed = executor.poll_known_once(draft.client_order_id,
                        at=at+timedelta(seconds=3),reader=reader)
        if observed.stage is not Stage.BROKER_TERMINAL_UNRECONCILED:
            raise AssertionError("filled source record must still require reconciliation")
        completed = executor.reconcile_terminal_once(draft.client_order_id,
                        at=at+timedelta(seconds=5),reader=reader)
        if completed.stage is not Stage.RECONCILED:
            raise AssertionError("reconciler did not verify all expected source facts")
        budget = book.budget_snapshot()
        if venue.posts != 1 or book.journal.total_reserved_usd() != 0:
            raise AssertionError("duplicate simulation or leaked reservations")
        return {"type":"DELIBERATELY_FAKE_OFFLINE_INTEGRATION_TEST",
                "real_broker_connected":False, "broker_paper_orders_sent":0,
                "real_money_orders_sent":0, "mock_POST_count":venue.posts,
                "stages":[submitted.stage.value,observed.stage.value,completed.stage.value],
                "virtual_paper_budget":budget,
                "event_types":[e["type"] for e in book.journal.recent_events()]}


def main() -> None:
    print(json.dumps(run_fake_scenario(),sort_keys=True,indent=2))

if __name__ == "__main__":
    main()
