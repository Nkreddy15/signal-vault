import unittest
from decimal import Decimal
from signal_vault.fake_paper_scenario import run_fake_scenario

class FakeEndToEndScenarioTests(unittest.TestCase):
    def test_single_fake_order_round_trip_and_three_way_audit(self):
        r=run_fake_scenario()
        self.assertEqual(r["type"],"DELIBERATELY_FAKE_OFFLINE_INTEGRATION_TEST")
        self.assertFalse(r["real_broker_connected"])
        self.assertEqual(r["broker_paper_orders_sent"],0)
        self.assertEqual(r["real_money_orders_sent"],0)
        self.assertEqual(r["mock_POST_count"],1)
        self.assertEqual(r["stages"],["broker_accepted","broker_terminal_unreconciled","reconciled"])
        self.assertEqual(Decimal(r["virtual_paper_budget"]["virtual_cash"]),Decimal("85.05"))
        self.assertEqual(Decimal(r["virtual_paper_budget"]["virtual_btc"]),Decimal("0.000229425"))
        self.assertIn("PROVIDER_EVIDENCE_RECONCILED",r["event_types"])

if __name__ == "__main__":unittest.main()
