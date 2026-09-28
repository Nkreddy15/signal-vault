import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from signal_vault.alpaca_paper import PaperAlpacaReadClient
from signal_vault.market_data import Bar, CryptoQuote
from signal_vault.paper_executor import PaperOnceExecutor
from signal_vault.paper_runtime import PaperCycleRunner
from signal_vault.paper_store import PersistentPaperOrderStore

NOW = datetime(2026, 9, 29, 0, 0, 30, tzinfo=timezone.utc)
ORDER = "11111111-2222-3333-4444-555555555555"


def crossover_bars():
    end = NOW.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=72)
    rows = []
    for i in range(72):
        # Equal prices until the last bar creates a fresh upward cross.
        px = Decimal("65000") if i < 71 else Decimal("70000")
        rows.append(Bar(start + timedelta(hours=i), px, px, px, px, Decimal("1"),
                        "alpaca_crypto_us", 3600, "BTC/USD"))
    return tuple(rows)


class FakeBars:
    def __init__(self, values=None): self.values = values or crossover_bars()
    def fetch(self, **_): return self.values


class FakeQuotes:
    def __init__(self, bid="69990", ask="70010", stamp=NOW - timedelta(seconds=10)):
        self.quote = CryptoQuote("BTC/USD", Decimal(bid), Decimal(ask), stamp)
    def latest_btc_usd(self, **_): return self.quote


def reader_transport(path, *_):
    if path == "/v2/account":
        return {"equity":"100000", "status":"ACTIVE", "trading_blocked":False,
                "non_marginable_buying_power":"100000"}
    if path == "/v2/positions": return []
    if path == "/v2/orders?status=open": return []
    if path.startswith("/v2/orders:by_client_order_id?client_order_id="):
        client_id = path.split("=", 1)[1]
        return {"id":ORDER,"client_order_id":client_id,"status":"accepted",
                "filled_qty":"0","filled_avg_price":None}
    if path == "/v2/assets/BTC%2FUSD":
        return {"symbol":"BTC/USD","class":"crypto","status":"active","tradable":True,
                "fractionable":True,"min_order_size":"0.0001",
                "min_trade_increment":"0.000000001","price_increment":"0.01"}
    raise AssertionError(path)


class PaperRuntimeTests(unittest.TestCase):
    def build(self, *, post=None, quotes=None, bars=None):
        store = PersistentPaperOrderStore(":memory:")
        reader = PaperAlpacaReadClient("p", "s", transport=reader_transport)
        calls = []
        def default_post(payload, *_):
            calls.append(dict(payload))
            return {"id":ORDER,"client_order_id":payload["client_order_id"],
                    "status":"accepted","filled_qty":"0","filled_avg_price":None}
        executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                     transport=post or default_post)
        runner = PaperCycleRunner(store=store, reader=reader, executor=executor,
                                  bars=bars or FakeBars(), quotes=quotes or FakeQuotes())
        return store, runner, calls

    def test_default_cycle_records_draft_but_never_posts(self):
        store, runner, calls = self.build()
        try:
            result = runner.run_once(now=NOW)
            self.assertEqual(result.state, "PAPER_DRAFT_READY")
            self.assertFalse(result.paper_post_attempted)
            self.assertEqual(calls, [])
            self.assertFalse(store.has_unresolved_provider_order())
        finally: store.close()

    def test_explicit_paper_cycle_posts_once_and_blocks_duplicate(self):
        store, runner, calls = self.build()
        try:
            first = runner.run_once(now=NOW, allow_paper_submission=True)
            self.assertEqual(first.state, "PAPER_SUBMISSION_RECORDED")
            self.assertEqual(len(calls), 1)
            # Accepted provider order is unresolved, so second cycle only polls/recovery.
            second = runner.run_once(now=NOW + timedelta(seconds=5), allow_paper_submission=True)
            self.assertIn(second.state, {"BLOCKED_PROVIDER_ORDER", "BLOCKED_RECONCILIATION"})
            self.assertEqual(len(calls), 1)
        finally: store.close()

    def test_stale_quote_holds_without_draft_or_post(self):
        store, runner, calls = self.build(quotes=FakeQuotes(stamp=NOW - timedelta(minutes=10)))
        try:
            # FakeQuotes itself does not validate age, but Guardian sees the stale quote.
            result = runner.run_once(now=NOW)
            self.assertEqual(result.state, "REJECTED")
            self.assertEqual(calls, [])
        finally: store.close()

    def test_external_provider_position_drift_blocks_before_market_scan(self):
        def drift(path, *_):
            if path == "/v2/account":
                return {"equity":"100000","status":"ACTIVE","trading_blocked":False,
                        "non_marginable_buying_power":"100000"}
            if path == "/v2/positions": return [{"symbol":"BTCUSD","qty":"0.01"}]
            if path == "/v2/orders?status=open": return []
            if path == "/v2/assets/BTC%2FUSD": return reader_transport(path)
            raise AssertionError(path)
        store = PersistentPaperOrderStore(":memory:")
        try:
            reader = PaperAlpacaReadClient("p","s",transport=drift)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda *_: (_ for _ in ()).throw(AssertionError("no POST")))
            runner = PaperCycleRunner(store=store, reader=reader, executor=executor,
                                      bars=FakeBars(), quotes=FakeQuotes())
            result = runner.run_once(now=NOW, allow_paper_submission=True)
            self.assertEqual(result.state, "BLOCKED_PROVIDER_DRIFT")
        finally: store.close()

class PaperRuntimeOperatorHaltTests(unittest.TestCase):
    def test_operator_halt_prevents_draft_and_post_but_still_allows_provider_checks(self):
        store = PersistentPaperOrderStore(":memory:")
        calls = []
        try:
            store.set_operator_halt(True, reason="maintenance", at=NOW)
            reader = PaperAlpacaReadClient("p", "s", transport=reader_transport)
            executor = PaperOnceExecutor(paper_key="p", paper_secret="s", store=store,
                                         transport=lambda payload,*_: calls.append(payload) or {})
            runner = PaperCycleRunner(store=store, reader=reader, executor=executor,
                                      bars=FakeBars(), quotes=FakeQuotes())
            result = runner.run_once(now=NOW, allow_paper_submission=True)
            self.assertEqual(result.state, "OPERATOR_HALTED")
            self.assertEqual(calls, [])
            self.assertEqual(store.list_states(), ())
        finally: store.close()
