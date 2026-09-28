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
