import io
import json
import unittest
from contextlib import redirect_stdout,redirect_stderr
from signal_vault.alpaca_paper import PaperAlpacaReadClient
from signal_vault.paper_onboarding import main,evaluate_paper_read_only

PAPER={'SV_ALPACA_PAPER_KEY':'fake-key','SV_ALPACA_PAPER_SECRET':'fake-secret'}

def fake_factory(k,s):
    def read(path,key,secret):
        assert (key,secret)==('fake-key','fake-secret')
        if path=='/v2/account':
            return {'id':'NOT_REPORTED_TO_USER','status':'ACTIVE','crypto_status':'ACTIVE',
                'equity':'100000','cash':'100000','non_marginable_buying_power':'100000',
                'trading_blocked':False}
        if path=='/v2/assets/BTC%2FUSD':
            return {'symbol':'BTC/USD','class':'crypto','status':'active','tradable':True,
                 'fractionable':True,'min_order_size':'0.0001',
                 'min_trade_increment':'0.000000001','price_increment':'1'}
        if path in ('/v2/positions','/v2/orders?status=open'):
            return []
        raise AssertionError(f'unknown path {path}')
    return PaperAlpacaReadClient(k,s,transport=read)

class PaperOnboardingTests(unittest.TestCase):
    def test_requires_opt_in_flag_and_refuses_missing_or_live_credentials(self):
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main([],env=PAPER,client_factory=fake_factory)
        with self.assertRaises(ValueError):
            main(['--confirm-paper-read-only'],env={},client_factory=fake_factory)
        with self.assertRaises(ValueError):
            main(['--confirm-paper-read-only'],env={**PAPER,'SIGNAL_VAULT_MODE':'live'},
                 client_factory=fake_factory)

    def test_read_only_facts_no_key_or_account_identity_printed(self):
        out=io.StringIO()
        with redirect_stdout(out):
            code=main(['--confirm-paper-read-only'],env=PAPER,client_factory=fake_factory)
        self.assertEqual(code,0)
        raw=out.getvalue()
        self.assertNotIn('fake-secret',raw)
        self.assertNotIn('fake-key',raw)
        self.assertNotIn('NOT_REPORTED_TO_USER',raw)
        result=json.loads(raw)
        self.assertTrue(result['ready_for_later_paper_authorization'])
        self.assertEqual(result['broker_post_orders_sent'],0)
        self.assertEqual(result['virtual_pilot_budget_usd'],'100')

if __name__=='__main__':unittest.main()
