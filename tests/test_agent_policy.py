import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from signal_vault.agent_policy import parse_adviser_vote,resolve_ai_final_choice
from signal_vault.strategy import StrategySignal,Action

T=datetime(2026,9,28,23,0,tzinfo=timezone.utc)
S=StrategySignal(Action.BUY,'a'*64,T.isoformat(),Decimal('1'),Decimal('0.9'),
                 'verified source crossover','test-strategy')

def vote(**overrides):
    data={'evidence_id':S.evidence_id,'action':'buy','confidence':'0.8',
          'model_version':'explicit-mock-model-1','generated_at':(T+timedelta(seconds=5)).isoformat(),
          'rationale':'Bounded selection only; no execution permissions'}
    return parse_adviser_vote({**data,**overrides})

class AIChoiceBoundaryTests(unittest.TestCase):
    def test_no_model_cannot_fake_discretionary_approval(self):
        d=resolve_ai_final_choice(S,None,now=T+timedelta(seconds=10))
        self.assertEqual(d.action,Action.HOLD)
        self.assertFalse(d.adviser_used)
    def test_matched_model_choice_still_explicitly_requires_guardian(self):
        d=resolve_ai_final_choice(S,vote(),now=T+timedelta(seconds=10))
        self.assertEqual(d.action,Action.BUY)
        self.assertIn('Guardian',d.reason)
    def test_adviser_cannot_invent_sell_or_override_hold(self):
        self.assertEqual(resolve_ai_final_choice(S,vote(action='sell'),
             now=T+timedelta(seconds=10)).action,Action.HOLD)
        self.assertEqual(resolve_ai_final_choice(replace(S,action=Action.HOLD),vote(),
             now=T+timedelta(seconds=10)).action,Action.HOLD)
    def test_evidence_confidence_and_freshness_are_hard_gates(self):
        for kwargs in ({'confidence':'0.3'},{'evidence_id':'b'*64},
                       {'generated_at':(T-timedelta(seconds=3)).isoformat()}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(resolve_ai_final_choice(S,vote(**kwargs),
                        now=T+timedelta(seconds=10)).action,Action.HOLD)
        self.assertEqual(resolve_ai_final_choice(S,vote(),
                        now=T+timedelta(seconds=180)).action,Action.HOLD)
    def test_untrusted_json_not_allowed_to_add_tools_or_override_limits(self):
        base={'evidence_id':S.evidence_id,'action':'buy','confidence':'0.8',
          'model_version':'mock','generated_at':(T+timedelta(seconds=1)).isoformat(),
          'rationale':'bounded'}
        with self.assertRaises(ValueError):
            parse_adviser_vote({**base,'api_key':'spoof','max_position_usd':10000})
        for change in ({'confidence':'NaN'},{'action':'transfer_money'},
                       {'rationale':'x'*401}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                parse_adviser_vote({**base,**change})

if __name__=='__main__':unittest.main()
