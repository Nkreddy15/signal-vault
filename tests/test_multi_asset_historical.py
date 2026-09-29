"""Entirely synthetic multi-asset Alpaca research GET contract tests.

No real Alpaca credentials, network, broker account, order or cloud volume.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from signal_vault.multi_asset_historical import (
    BoundedAlpacaHistoricalBatch, CRYPTO_ENDPOINT, EQUITY_ENDPOINT,
    HistoricalDataBatch, _read_historical_data_no_redirect,
    archive_historical_batch,
)
from signal_vault.research_universe import candidate

UTC = timezone.utc
END = datetime(2026, 9, 29, 19, tzinfo=UTC)
HOUR = timedelta(hours=1)
Q = timedelta(minutes=7)


def fake_row(at: datetime, price: str = "100") -> dict[str, object]:
    p = Decimal(price)
    return {
        "t": at.isoformat().replace("+00:00", "Z"),
        "o": str(p), "h": str(p+1), "l": str(p-1),
        "c": str(p), "v": "20",
    }


class PageServer:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []
        self.key_id_seen = []

    def __call__(self, url, key, secret):
        self.urls.append(url)
        self.key_id_seen.append((key, secret))
        token = parse_qs(urlsplit(url).query).get("page_token", ["first"])[0]
        if token not in self.pages:
            raise AssertionError("unexpected pagination request " + token)
        return self.pages[token]


class HistoricalBatchTests(unittest.TestCase):
    def client(self, pages, max_pages=40):
        provider = PageServer(pages)
        return BoundedAlpacaHistoricalBatch(
            "FAKE_DATA_KEY", "FAKE_DATA_SECRET",
            transport=provider, max_pages=max_pages), provider

    def test_crypto_multi_symbol_api_pagination_can_return_first_symbol_only(self):
        start = END - 2*HOUR
        cli, provider = self.client({
            "first": {"bars": {"BTC/USD": [fake_row(start),
                                          fake_row(start+HOUR)]},
                      "next_page_token": "page-two"},
            "page-two": {"bars": {"ETH/USD": [fake_row(start, "2000"),
                                            fake_row(start+HOUR, "2100")]},
                         "next_page_token": None},
        })
        batch = cli.fetch(specs=(candidate("ETH/USD"), candidate("BTC/USD")),
                          start=start, end=END, as_of=END+Q)
        self.assertEqual(batch.symbols, ("BTC/USD", "ETH/USD"))
        self.assertEqual(batch.page_count, 2)
        self.assertEqual(batch.feed, "alpaca_crypto_us")
        self.assertEqual({k:len(v) for k,v in batch.bars.items()},
                         {"BTC/USD": 2, "ETH/USD":2})
        self.assertTrue(all(not bar.prospective for rows in batch.bars.values()
                            for bar in rows))
        self.assertEqual(batch.canonical()["prospective_observations_verified"], 0)
        self.assertEqual(batch.canonical()["broker_order_submission"], "DISABLED")
        self.assertTrue(all(url.startswith(CRYPTO_ENDPOINT+"?") for url in provider.urls))
        self.assertEqual(parse_qs(urlsplit(provider.urls[0]).query)["symbols"],
                         ["BTC/USD,ETH/USD"])
        self.assertEqual(provider.key_id_seen, [
            ("FAKE_DATA_KEY","FAKE_DATA_SECRET"),
            ("FAKE_DATA_KEY","FAKE_DATA_SECRET"),
        ])
        self.assertNotIn("FAKE_DATA_KEY", batch.canonical_bytes().decode("utf-8"))

    def test_stocks_explicit_iex_all_adjusted_and_half_hour_calendar(self):
        start = datetime(2026, 9, 29, 13, 30, tzinfo=UTC)
        end = start+2*HOUR
        cli, provider = self.client({
            "first": {
                "bars": {"AAPL": [fake_row(start, "200"), fake_row(start+HOUR,"201")],
                         "SPY": [fake_row(start,"700"), fake_row(start+HOUR,"701")]},
                "next_page_token": None,
            },
        })
        expected={"SPY": (start,start+HOUR), "AAPL":(start,start+HOUR)}
        batch = cli.fetch(
            specs=(candidate("SPY"),candidate("AAPL")), start=start,
            end=end, as_of=end+Q, equity_feed="iex",
            equity_expected_open_minutes=expected)
        self.assertEqual(batch.asset_class, "us_equity")
        self.assertEqual(batch.feed, "alpaca_equity_iex")
        self.assertEqual(batch.adjustment, "all")
        q=parse_qs(urlsplit(provider.urls[0]).query)
        self.assertEqual(q["feed"],["iex"])
        self.assertEqual(q["adjustment"],["all"])
        self.assertEqual(q["end"],[(end-timedelta(seconds=1)).isoformat()])
        self.assertEqual(batch.bars["AAPL"][0].feed,"alpaca_equity_iex|adjustment=all")

    def test_wrong_calendar_or_no_equity_feed_blocks_before_network(self):
        start = datetime(2026, 9, 29, 13, 30, tzinfo=UTC)
        pages={"first":{"bars":{"SPY":[fake_row(start)]},"next_page_token":None}}
        cli, provider=self.client(pages)
        with self.assertRaises(ValueError):
            cli.fetch(specs=(candidate("SPY"),),start=start,end=start+HOUR,
                      as_of=start+HOUR+Q)
        with self.assertRaises(ValueError):
            cli.fetch(specs=(candidate("SPY"),),start=start,end=start+HOUR,
                      as_of=start+HOUR+Q,equity_feed="sip")
        self.assertEqual(provider.urls,[])
        with self.assertRaises(ValueError):
            cli.fetch(specs=(candidate("SPY"),),start=start,end=start+HOUR,
                      as_of=start+HOUR+Q,equity_feed="iex",
                      equity_expected_open_minutes={"SPY":(start+HOUR,)})
        self.assertEqual(len(provider.urls),1)

    def test_crypto_gap_missing_symbol_and_duplicate_protect_provenance(self):
        start=END-3*HOUR
        cases=[
            {"bars":{"BTC/USD":[fake_row(start),fake_row(start+2*HOUR)]},
             "next_page_token":None},
            {"bars":{"BTC/USD":[fake_row(start),fake_row(start)]},
             "next_page_token":None},
            {"bars":{"BTC/USD":[fake_row(start),fake_row(start+HOUR)],
                     "ETH/USD":[fake_row(start)]},
             "next_page_token":None},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                cli,_=self.client({"first":case})
                cli.fetch(specs=(candidate("BTC/USD"),),start=start,
                          end=END,as_of=END+Q)

    def test_bad_token_or_page_cap_fails_without_partial_result(self):
        start=END-HOUR
        cli,_=self.client({"first":{"bars":{"BTC/USD":[fake_row(start)]},
                                     "next_page_token":"x"},
                           "x":{"bars":{},"next_page_token":"x"}})
        with self.assertRaises(ValueError):
            cli.fetch(specs=(candidate("BTC/USD"),),start=start,end=END,as_of=END+Q)
        cli,_=self.client({"first":{"bars":{"BTC/USD":[fake_row(start)]},
                                     "next_page_token":"x"}},max_pages=1)
        with self.assertRaises(ValueError):
            cli.fetch(specs=(candidate("BTC/USD"),),start=start,end=END,as_of=END+Q)

    def test_bounded_request_and_crypto_equity_mixing_forbidden(self):
        cli,provider=self.client({"first":{"bars":{},"next_page_token":None}})
        attempts=[
            dict(specs=(candidate("BTC/USD"),candidate("SPY")),
                 start=END-HOUR,end=END,as_of=END+Q),
            dict(specs=(candidate("BTC/USD"),),
                 start=END-timedelta(days=20),end=END,as_of=END+Q),
            dict(specs=(candidate("BTC/USD"),),
                 start=END,end=END+HOUR,as_of=END+Q),
            dict(specs=(candidate("BTC/USD"),candidate("BTC/USD")),
                 start=END-HOUR,end=END,as_of=END+Q),
            dict(specs=(candidate("BTC/USD"),),
                 start=END-HOUR,end=END,as_of=END+Q,equity_feed="iex"),
        ]
        for request in attempts:
            with self.subTest(request=request),self.assertRaises(ValueError):
                cli.fetch(**request)
        self.assertFalse(provider.urls)

    def test_strict_transport_blocks_host_symbols_feed_and_query_injection_before_network(self):
        root=CRYPTO_ENDPOINT+"?"
        valid=("symbols=BTC%2FUSD&timeframe=1Hour&start=2026-09-29T17%3A00%3A00%2B00%3A00"
               "&end=2026-09-29T18%3A59%3A59%2B00%3A00&limit=1000&sort=asc")
        bad=[
            "https://api.alpaca.markets/v2/orders?"+valid,
            "http://data.alpaca.markets/v1beta3/crypto/us/bars?"+valid,
            root+valid.replace("BTC%2FUSD","../../"),
            root+valid+"&redirect=https%3A%2F%2Fevil.example",
            root+valid+"&timeframe=5Min",
            root+valid.replace("BTC%2FUSD","UNKNOWN"),
            root+valid.replace("limit=1000","limit=999999"),
            root+valid.replace("end=2026-09-29T18%3A59%3A59",
                               "end=2026-11-29T18%3A59%3A59"),
            EQUITY_ENDPOINT+"?"+valid+"&feed=unknown&adjustment=all",
        ]
        for url in bad:
            with self.subTest(url=url),self.assertRaises(ValueError):
                _read_historical_data_no_redirect(url,"K","S")

    def test_immutable_archival_is_one_file_with_content_fingerprint(self):
        start=END-HOUR
        cli,_=self.client({"first":{"bars":{"BTC/USD":[fake_row(start)]},
                                    "next_page_token":None}})
        batch=cli.fetch(specs=(candidate("BTC/USD"),),start=start,end=END,
                        as_of=END+Q)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"archive"
            root.mkdir(mode=0o700)
            path=archive_historical_batch(batch,output_folder=root)
            before=path.read_bytes()
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            self.assertEqual(archive_historical_batch(batch,output_folder=root),path)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(json.loads(before)["prospective_observations_verified"],0)
            self.assertNotIn(b"FAKE_DATA_KEY",before)
            path.write_bytes(before+b"tampered")
            with self.assertRaises(ValueError):
                archive_historical_batch(batch,output_folder=root)
            self.assertIn(b"tampered",path.read_bytes())

    def test_invalid_archive_root_or_live_root_fails_without_mkdir(self):
        start=END-HOUR
        cli,_=self.client({"first":{"bars":{"BTC/USD":[fake_row(start)]},
                                    "next_page_token":None}})
        batch=cli.fetch(specs=(candidate("BTC/USD"),),start=start,end=END,as_of=END+Q)
        with tempfile.TemporaryDirectory() as d:
            missing=Path(d)/"absent"
            with self.assertRaises(ValueError):
                archive_historical_batch(batch,output_folder=missing)
            self.assertFalse(missing.exists())
            public=Path(d)/"public"
            public.mkdir(mode=0o755)
            with self.assertRaises(ValueError):
                archive_historical_batch(batch,output_folder=public)
            link=Path(d)/"link";link.symlink_to(public)
            with self.assertRaises(ValueError):
                archive_historical_batch(batch,output_folder=link)


if __name__=="__main__":
    unittest.main()
