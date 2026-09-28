import unittest

from signal_vault.config import RuntimeConfig


class RuntimeSafetyTests(unittest.TestCase):
    def test_defaults_are_offline_paper_only(self):
        cfg = RuntimeConfig.from_environment({})
        self.assertEqual((cfg.mode, cfg.broker, cfg.network_orders_enabled),
                         ("paper", "local_dry_run", False))

    def test_live_mode_cannot_be_enabled(self):
        with self.assertRaisesRegex(ValueError, "PAPER ONLY"):
            RuntimeConfig.from_environment({"SIGNAL_VAULT_MODE": "live"})

    def test_network_order_submission_cannot_be_enabled(self):
        with self.assertRaisesRegex(ValueError, "disabled"):
            RuntimeConfig.from_environment({
                "SIGNAL_VAULT_ENABLE_NETWORK_ORDER_SUBMISSION": "true"
            })

    def test_unknown_broker_is_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeConfig.from_environment({"SIGNAL_VAULT_BROKER": "alpaca_live"})

    def test_unknown_symbol_is_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeConfig.from_environment({"SIGNAL_VAULT_SYMBOL": "ETH/USD"})
