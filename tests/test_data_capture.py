import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.data_capture import capture_dataset
from signal_vault.market_data import Bar, load_csv

START=datetime(2026,1,1,tzinfo=timezone.utc)


class FakeProvider:
    def fetch(self,*,start,end,as_of):
        rows=[]; cur=start
        while cur<end:
            rows.append(Bar(cur,Decimal("100"),Decimal("101"),Decimal("99"),Decimal("100.5"),
                            Decimal("3"),"fake-read-only"))
            cur += timedelta(hours=1)
        return rows


class DataCaptureTests(unittest.TestCase):
    def test_capture_is_reproducible_fingerprinted_and_owner_only(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"btc.csv"; end=START+timedelta(hours=40)
            manifest=capture_dataset(FakeProvider(),start=START,end=end,as_of=end,
                                     output_csv=path,captured_at=end)
            self.assertEqual(manifest.row_count,40)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),manifest.csv_sha256)
            saved=json.loads((Path(str(path)+".manifest.json")).read_text())
            self.assertEqual(saved["csv_sha256"],manifest.csv_sha256)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            bars=load_csv(path,as_of=end,min_count=40)
            self.assertEqual(len(bars),40)

    def test_incomplete_provider_interval_rejected(self):
        class Broken(FakeProvider):
            def fetch(self,**kwargs): return super().fetch(**kwargs)[1:]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,"incomplete"):
                capture_dataset(Broken(),start=START,end=START+timedelta(hours=3),
                                as_of=START+timedelta(hours=3),output_csv=Path(td)/"x.csv")
