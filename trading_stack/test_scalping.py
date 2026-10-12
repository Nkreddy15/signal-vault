"""Closed-data-only scalp hypotheses and exact net-of-cost arithmetic."""
import copy
import unittest
from trading_stack.cloud_paper.strategies_scalp import required_reference_ratio,signals
from trading_stack.research.screen_scalp_20261012 import candidate_config

NOW=1791816600


def rebound(start=120,drop=.3,rise=.3):
    values=[start-i*drop for i in range(72)]
    values[-2]=values[-3]+rise;values[-1]=values[-2]+rise
    return [dict(time=NOW-(72-i)*300,open=v,high=v+.05,low=v-.05,close=v,volume=100) for i,v in enumerate(values)]


class ScalpingTests(unittest.TestCase):
    def setUp(self):self.cfg=candidate_config()

    def test_oversold_recovery_can_signal_without_the_old_rising_long_trend(self):
        found,_=signals(rebound(),'crypto','BTC/USD',NOW,self.cfg)
        self.assertEqual([c['strategy'] for c in found],['scalp_rebound'])
        self.assertEqual(found[0]['signal_at'],NOW)
        self.assertGreater(found[0]['target']/found[0]['reference'],required_reference_ratio(self.cfg))

    def test_exact_target_covers_both_fees_slippage_and_spread(self):
        for fee in (.008,.0025):
            cfg=dict(self.cfg,crypto_fee_fraction=fee)
            friction=cfg['slippage_fraction']+cfg['max_spread_fraction']/2
            entry=100*(1+friction);cost=.5*entry
            sale=.5*100*required_reference_ratio(cfg)*(1-friction)*(1-fee)
            self.assertAlmostEqual(sale-cost-cost*fee,cost*cfg['crypto_net_take_profit_fraction'])

    def test_small_gross_moves_are_blocked_by_actual_cost_headroom(self):
        bars=rebound(start=104,drop=.025,rise=.05)
        found,why=signals(bars,'crypto','BTC/USD',NOW,self.cfg)
        self.assertFalse(found);self.assertIn('headroom',why)

    def test_unclosed_stale_and_gapped_history_never_qualifies(self):
        bars=rebound()
        cases=[bars+[dict(bars[-1],time=NOW)],bars[:-3]+bars[-2:],bars[:-1]+[dict(bars[-1],time=bars[-2]['time'])]]
        for data in cases:self.assertFalse(signals(data,'crypto','BTC/USD',NOW,self.cfg)[0])
        self.assertFalse(signals(bars,'crypto','BTC/USD',NOW+301,self.cfg)[0])

    def test_invalid_candles_and_thin_volume_never_qualify(self):
        for key,value in [('close',float('nan')),('low',0),('volume',-1),('volume',1)]:
            bars=rebound();bars[-1][key]=value
            self.assertFalse(signals(bars,'crypto','BTC/USD',NOW,self.cfg)[0])

    def test_repeat_evaluation_is_identical_and_preserves_inputs(self):
        bars=rebound();before=copy.deepcopy(bars);config=copy.deepcopy(self.cfg)
        first=signals(bars,'crypto','BTC/USD',NOW,self.cfg)
        self.assertEqual(first,signals(bars,'crypto','BTC/USD',NOW,self.cfg))
        self.assertEqual(bars,before);self.assertEqual(self.cfg,config)


if __name__=='__main__':unittest.main()
