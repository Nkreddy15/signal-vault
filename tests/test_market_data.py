import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from signal_vault.market_data import (
    Bar, HOUR, AlpacaPublicCryptoBars, load_csv, parse_bar, validate_bars,
)

START = datetime(2026, 8, 1, tzinfo=timezone.utc)
AS_OF = START + timedelta(hours=12)


def record(i, price="100"):
    return {"t": (START + timedelta(hours=i)).isoformat(), "o": price,
            "h": str(Decimal(price) + 2), "l": str(Decimal(price) - 2),
            "c": price, "v": "8"}


def bar(i):
    return parse_bar(record(i), source="fixture")


class MarketDataTests(unittest.TestCase):
    def test_strict_closed_contiguous_bars(self):
        result = validate_bars([bar(i) for i in range(3)], as_of=AS_OF)
        self.assertEqual(len(result), 3)
        with self.assertRaisesRegex(ValueError, "missing hourly"):
            validate_bars([bar(0), bar(2)], as_of=AS_OF)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_bars([bar(0), bar(0)], as_of=AS_OF)

    def test_gap_diagnostic_reports_exact_source_timestamps(self):
        with self.assertRaisesRegex(
            ValueError,
            r"missing hourly bar: expected 2026-08-01T01:00:00\\+00:00, "
            r"next returned 2026-08-01T03:00:00\\+00:00"
        ):
            validate_bars([bar(0), bar(3)], as_of=AS_OF)

        with self.assertRaisesRegex(
            ValueError, r"duplicate hourly bar: 2026-08-01T01:00:00\\+00:00"
        ):
            validate_bars([bar(0), bar(1), bar(1)], as_of=AS_OF)

        with self.assertRaisesRegex(
            ValueError, r"out-of-order hourly bar: expected 2026-08-01T02:00:00"
        ):
            validate_bars([bar(0), bar(1), bar(0)], as_of=AS_OF)

    def test_open_bar_cannot_enter_signal(self):
        with self.assertRaisesRegex(ValueError, "open / future"):
            validate_bars([bar(0)], as_of=START + timedelta(minutes=30))

    def test_invalid_prices_and_timestamp(self):
        for value in ("0", "-5", "NaN", "Infinity", "garbage"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_bar({**record(0), "c": value}, source="fixture")
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            parse_bar({**record(0), "h": "99"}, source="fixture")
        with self.assertRaisesRegex(ValueError, "timezone"):
            parse_bar({**record(0), "t": "2026-08-01T00:00:00"}, source="fixture")
        with self.assertRaises(ValueError):
            validate_bars([replace(bar(0), close=Decimal("NaN"))], as_of=AS_OF)

    def test_read_only_pagination_requires_complete_interval(self):
        urls = []
        def fetch(url):
            urls.append(url)
            params = parse_qs(urlsplit(url).query)
            if "page_token" not in params:
                return {"bars": {"BTC/USD": [record(0), record(1)]}, "next_page_token": "page2"}
            return {"bars": {"BTC/USD": [record(2)]}, "next_page_token": None}
        candles = AlpacaPublicCryptoBars(fetch).fetch(
            start=START, end=START + timedelta(hours=3), as_of=AS_OF)
        self.assertEqual(len(candles), 3)
        self.assertEqual(len(urls), 2)
        self.assertTrue(all(urlsplit(url).netloc == "data.alpaca.markets" for url in urls))
        self.assertEqual(parse_qs(urlsplit(urls[0]).query)["symbols"], ["BTC/USD"])

    def test_alpaca_inclusive_end_is_excluded_without_weakening_validation(self):
        # Alpaca's API end parameter is inclusive, but our desired closed-hour
        # interval is [start, end), with no candle beginning exactly at end.
        end = START + timedelta(hours=3)
        seen = []

        def fetch(url):
            seen.append(parse_qs(urlsplit(url).query))
            return {"bars": {"BTC/USD": [record(i) for i in range(3)]},
                    "next_page_token": None}

        result = AlpacaPublicCryptoBars(fetch).fetch(start=START, end=end, as_of=AS_OF)
        self.assertEqual(len(result), 3)
        self.assertEqual(seen[0]["start"], [START.isoformat()])
        self.assertEqual(seen[0]["end"], [(end - timedelta(seconds=1)).isoformat()])

        # If a provider violates our requested boundary, fail closed rather
        # than silently accepting or dropping its unexpected additional row.
        def unexpected_boundary_bar(_url):
            return {"bars": {"BTC/USD": [record(i) for i in range(4)]},
                    "next_page_token": None}

        with self.assertRaisesRegex(ValueError, "outside requested closed interval"):
            AlpacaPublicCryptoBars(unexpected_boundary_bar).fetch(
                start=START, end=end, as_of=AS_OF)

    def test_broken_pagination_and_partial_data_fail_closed(self):
        one = {"bars": {"BTC/USD": [record(0)]}, "next_page_token": None}
        with self.assertRaisesRegex(ValueError, "incomplete at a boundary"):
            AlpacaPublicCryptoBars(lambda _: one).fetch(start=START, end=START + timedelta(hours=2), as_of=AS_OF)
        with self.assertRaisesRegex(ValueError, "repeated"):
            AlpacaPublicCryptoBars(lambda _: {"bars": {"BTC/USD": [record(0)]}, "next_page_token": "loop"}).fetch(
                start=START, end=START + timedelta(hours=2), as_of=AS_OF)

    def test_csv_import_rejects_unclosed_last_bar(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "tiny.csv"
            file.write_text("timestamp,open,high,low,close,volume\n" +
                            "2026-08-01T00:00:00Z,100,102,98,100,8\n")
            self.assertEqual(len(load_csv(file, as_of=AS_OF)), 1)
            with self.assertRaises(ValueError):
                load_csv(file, as_of=START + timedelta(minutes=30))


if __name__ == "__main__":
    unittest.main()

class LatestCryptoQuoteTests(unittest.TestCase):
    def test_fresh_quote_parses_and_uses_conservative_side_price(self):
        from signal_vault.market_data import parse_latest_crypto_quote
        now = datetime(2026, 9, 29, 0, 0, 30, tzinfo=timezone.utc)
        q = parse_latest_crypto_quote({"quotes":{"BTC/USD":{
            "bp":"64990", "ap":"65010", "t":"2026-09-29T00:00:00Z"}}}, as_of=now)
        self.assertEqual(q.execution_reference("buy"), Decimal("65010"))
        self.assertEqual(q.execution_reference("sell"), Decimal("64990"))
        self.assertEqual(q.mid, Decimal("65000"))

    def test_stale_crossed_or_wide_quote_fails_closed(self):
        from signal_vault.market_data import parse_latest_crypto_quote
        now = datetime(2026, 9, 29, 0, 2, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "stale"):
            parse_latest_crypto_quote({"quotes":{"BTC/USD":{
                "bp":"64990", "ap":"65010", "t":"2026-09-28T23:59:00Z"}}}, as_of=now)
        with self.assertRaisesRegex(ValueError, "crossed"):
            parse_latest_crypto_quote({"quotes":{"BTC/USD":{
                "bp":"65010", "ap":"64990", "t":"2026-09-29T00:01:59Z"}}}, as_of=now)
        with self.assertRaisesRegex(ValueError, "spread"):
            parse_latest_crypto_quote({"quotes":{"BTC/USD":{
                "bp":"60000", "ap":"70000", "t":"2026-09-29T00:01:59Z"}}}, as_of=now)

    def test_authenticated_quote_client_has_one_fixed_data_url(self):
        from signal_vault.market_data import AlpacaAuthenticatedLatestQuote, CRYPTO_LATEST_QUOTES_ENDPOINT
        now = datetime(2026, 9, 29, 0, 0, 30, tzinfo=timezone.utc)
        seen = []
        def transport(url, key, secret):
            seen.append((url, key, secret))
            return {"quotes":{"BTC/USD":{"bp":"64990","ap":"65010","t":"2026-09-29T00:00:00Z"}}}
        client = AlpacaAuthenticatedLatestQuote("paper-key", "paper-secret", transport=transport)
        client.latest_btc_usd(as_of=now)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0][0].startswith(CRYPTO_LATEST_QUOTES_ENDPOINT + "?"))
        self.assertNotIn("orders", seen[0][0])

class AuthenticatedHistoricalBarsTests(unittest.TestCase):
    def test_current_historical_adapter_carries_credentials_only_to_fixed_data_endpoint(self):
        from signal_vault.market_data import AlpacaAuthenticatedCryptoBars, CRYPTO_BARS_ENDPOINT
        now = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
        start = now - timedelta(hours=2)
        seen = []
        def transport(url, key, secret):
            seen.append((url, key, secret))
            return {"bars":{"BTC/USD":[
                {"t":"2026-09-28T22:00:00Z","o":"1","h":"1","l":"1","c":"1","v":"1"},
                {"t":"2026-09-28T23:00:00Z","o":"1","h":"1","l":"1","c":"1","v":"1"},
            ]},"next_page_token":None}
        bars = AlpacaAuthenticatedCryptoBars("paper-key","paper-secret",transport=transport).fetch(
            start=start,end=now,as_of=now)
        self.assertEqual(len(bars), 2)
        self.assertTrue(seen[0][0].startswith(CRYPTO_BARS_ENDPOINT + "?"))
        self.assertEqual(seen[0][1:], ("paper-key","paper-secret"))

    def test_legacy_unauthenticated_default_now_fails_closed(self):
        from signal_vault.market_data import AlpacaPublicCryptoBars
        now = datetime(2026, 9, 29, 0, 0, tzinfo=timezone.utc)
        with self.assertRaisesRegex(ValueError, "authenticated"):
            AlpacaPublicCryptoBars().fetch(start=now-timedelta(hours=1),end=now,as_of=now)
