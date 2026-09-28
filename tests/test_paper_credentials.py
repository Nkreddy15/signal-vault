import unittest
from signal_vault.paper_credentials import PaperCredentials
from signal_vault.paper_onboarding import main

class PaperCredentialSafetyTests(unittest.TestCase):
    def test_no_secrets_in_repr_or_str(self):
        key=PaperCredentials('realistic-SANDBOX-id','highly-secret-paper-token')
        for rendered in (repr(key),str(key)):
            self.assertNotIn('realistic-SANDBOX-id',rendered)
            self.assertNotIn('highly-secret-paper-token',rendered)
            self.assertIn('<redacted>',rendered)

    def test_paper_only_names_and_forbidden_generic_keys(self):
        env={'SV_ALPACA_PAPER_KEY':'paper-id','SV_ALPACA_PAPER_SECRET':'paper-secret'}
        self.assertEqual(PaperCredentials.from_environment(env).key_id,'paper-id')
        for name in ('ALPACA_API_KEY_ID','APCA_API_SECRET_KEY','ALPACA_LIVE_KEY_ID'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                PaperCredentials.from_environment({**env,name:'could-be-a-live-key'})

    def test_newline_injection_refused(self):
        for value in ('paper\nheader','paper\rheader','paper\x00header'):
            with self.assertRaises(ValueError):
                PaperCredentials(value,'valid-secret')

if __name__=='__main__':unittest.main()
