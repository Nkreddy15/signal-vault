import unittest

from signal_vault.paper_worker import PAPER_SUBMISSION_ACK, paper_submission_authorized


class PaperWorkerGateTests(unittest.TestCase):
    def test_submission_is_off_by_default(self):
        self.assertFalse(paper_submission_authorized({}))

    def test_only_exact_paper_ack_enables_submission(self):
        self.assertTrue(paper_submission_authorized({
            "SIGNAL_VAULT_PAPER_ORDER_SUBMISSION": PAPER_SUBMISSION_ACK
        }))
        for value in ("true", "yes", "enabled", "paper"):
            with self.assertRaises(ValueError):
                paper_submission_authorized({"SIGNAL_VAULT_PAPER_ORDER_SUBMISSION": value})

    def test_live_flags_are_rejected_even_with_paper_ack(self):
        for name, value in (("SIGNAL_VAULT_MODE", "live"),
                            ("SIGNAL_VAULT_LIVE", "true"),
                            ("SIGNAL_VAULT_LIVE_TRADING", "1")):
            with self.assertRaisesRegex(ValueError, "live"):
                paper_submission_authorized({
                    "SIGNAL_VAULT_PAPER_ORDER_SUBMISSION": PAPER_SUBMISSION_ACK,
                    name: value,
                })
