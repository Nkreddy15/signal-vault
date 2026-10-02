import tempfile
import unittest
from pathlib import Path

from signal_vault.experimental_paper_inventory import inspect_paper_account, _write_once
from signal_vault.paper_credentials import PaperCredentials


class Reader:
    def __init__(self,*args,**kwargs): pass
    def get_positions(self):
        return ({
            "symbol":"BTCUSD",
            "side":"long",
            "qty":"0.00025",
            "market_value":"16.25",
            "avg_entry_price":"60000",
            "current_price":"65000",
            "unrealized_pl":"1.25",
            "account_id":"must-not-leak",
        },)
    def get_open_orders(self):
        return ()


class Phase163PaperInventoryTests(unittest.TestCase):
    def test_sanitized_btc_position_only(self):
        out=inspect_paper_account(
            credentials=PaperCredentials("paper-key","paper-secret"),
            client_factory=Reader,
        )
        self.assertEqual(out["status"],"AVAILABLE")
        self.assertEqual(out["position_count"],1)
        self.assertTrue(out["all_positions_are_btc_only"])
        self.assertEqual(out["positions"][0]["symbol"],"BTCUSD")
        self.assertNotIn("account_id",out["positions"][0])
        self.assertEqual(out["order_submission"],"DISABLED")
        self.assertEqual(out["automatic_close_position"],"DISABLED")
        self.assertEqual(out["live_trading"],"UNAVAILABLE")

    def test_receipt_create_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"inventory.json"
            _write_once(p,{"kind":"fixture"})
            with self.assertRaises(ValueError):
                _write_once(p,{"kind":"overwrite"})


if __name__=="__main__":
    unittest.main()
