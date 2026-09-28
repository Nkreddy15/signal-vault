import unittest

from signal_vault.paper_credentials import PaperCredentials


class PaperCredentialTests(unittest.TestCase):
    def test_loads_only_explicit_paper_names_and_redacts(self):
        c = PaperCredentials.from_environment({
            "ALPACA_PAPER_KEY_ID": "paper-id",
            "ALPACA_PAPER_SECRET_KEY": "paper-secret",
        })
        self.assertEqual(c.key_id, "paper-id")
        self.assertNotIn("paper-id", repr(c))
        self.assertNotIn("paper-secret", str(c))

    def test_missing_paper_credentials_fail(self):
        with self.assertRaises(ValueError):
            PaperCredentials.from_environment({})

    def test_generic_or_live_names_fail_even_when_paper_keys_exist(self):
        base = {"ALPACA_PAPER_KEY_ID": "p", "ALPACA_PAPER_SECRET_KEY": "s"}
        for name in ("ALPACA_API_KEY_ID", "APCA_API_SECRET_KEY", "ALPACA_LIVE_KEY_ID"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "forbidden"):
                PaperCredentials.from_environment({**base, name: "should-not-be-here"})

    def test_control_characters_fail(self):
        with self.assertRaises(ValueError):
            PaperCredentials("abc\n", "secret")
