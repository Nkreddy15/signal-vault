import unittest
from pathlib import Path


class DeploymentTemplateTests(unittest.TestCase):
    def test_systemd_template_is_paper_only_and_hardened(self):
        text=Path("deploy/systemd/signal-vault-paper.service").read_text()
        self.assertIn("signal_vault.paper_daemon", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("UMask=0077", text)
        self.assertNotIn("api.alpaca.markets/v2/orders", text)
        self.assertNotIn("SIGNAL_VAULT_MODE=live", text)
        self.assertNotIn("I_ACKNOWLEDGE_ALPACA_PAPER_ORDERS_ONLY", text)


    def test_owner_service_uses_separate_secret_file_and_loopback(self):
        text=Path("deploy/systemd/signal-vault-owner.service").read_text()
        self.assertIn("EnvironmentFile=/etc/signal-vault/owner.env",text)
        self.assertIn("SIGNAL_VAULT_OWNER_HOST=127.0.0.1",text)
        self.assertNotIn("ALPACA_PAPER_SECRET_KEY",text)
        env=Path("deploy/systemd/owner.env.example").read_text()
        self.assertNotIn("ALPACA_",env)

    def test_secret_example_does_not_enable_post(self):
        text=Path("deploy/systemd/paper.env.example").read_text()
        enabled=[line for line in text.splitlines() if line.startswith("SIGNAL_VAULT_PAPER_ORDER_SUBMISSION=")]
        self.assertEqual(enabled, [])
