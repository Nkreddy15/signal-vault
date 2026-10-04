"""Causality, separate strategy paths and fresh-price/risk rejection tests."""
import copy
import math
from pathlib import Path
import tempfile
import unittest
from trading_stack.cloud_paper.engine import Engine,load_config
from trading_stack.cloud_paper.store import Store,portfolio
from trading_stack.cloud_paper.strategies import signals
from trading_stack.cloud_paper.strategies_v2 import indicators
from trading_stack.test_cloud_paper import FakeKraken,NoKalshi
from trading_stack.cloud_paper.providers import Alpaca

NOW=540000
CONFIG=Path(__file__).parent/'cloud_paper/campaign.regime-v2.json'


def fixture(family):
    c=[100+i*.1+math.sin(i*.8)*.5 for i in range(150)]
    if family=='breakout':c[-1]=max(c[-25:-1])+.8
    if family=='pullback':c[-5:]=[114,113.5,113,112.9,114.5]
    if family=='range_reversion':
        c=[100+math.sin(i*.7)*3 for i in range(150)];c[-2:]=[91,92]
    return [dict(time=i*3600,open=x,close=x,high=x+.4,low=x-.4,volume=100000 if i<149 else 150000) for i,x in enumerate(c)]


class RegimeTests(unittest.TestCase):
    def setUp(self):self.cfg=load_config(CONFIG)
    def test_three_distinct_entry_paths_without_failed_rebound(self):
        for family in ('breakout','pullback','range_reversion'):
            result,reason=signals(fixture(family),'crypto','BTC/USD',NOW,self.cfg)
            self.assertEqual([s['strategy'] for s in result],[family],reason)
            self.assertEqual(result[0]['signal_at'],NOW)
            self.assertIn('rsi',result[0]['indicators'])
    def test_wilder_directional_and_flat_reference_values(self):
        for flat in (True,False):
            b=[dict(time=i*3600,open=100 if flat else 100+i,close=100 if flat else 100+i,
                    high=101 if flat else 101+i,low=99 if flat else 99+i,volume=1000) for i in range(100)]
            x=indicators(b)
            self.assertAlmostEqual(x['atr'],2)
            self.assertAlmostEqual(x['rsi'],50 if flat else 100)
            self.assertAlmostEqual(x['adx'],0 if flat else 100)
    def test_costs_can_block_entry_instead_of_inventing_target(self):
        b=fixture('breakout');self.cfg['crypto_fee_fraction']=.04
        self.assertEqual(signals(b,'crypto','BTC/USD',NOW,self.cfg)[0],[])
    def test_invalid_open_future_gap_and_nonchronological_refused(self):
        for change in ('future','gap','ohlc','nan','duplicate'):
            b=fixture('pullback')
            if change=='future':b[-1]['time']=NOW
            elif change=='gap':b.pop(-10)
            elif change=='ohlc':b[-1]['high']=1
            elif change=='nan':b[-1]['volume']=float('nan')
            else:b[-1]['time']=b[-2]['time']
            self.assertFalse(signals(b,'crypto','BTC/USD',NOW,self.cfg)[0])
    def test_future_suffix_does_not_change_prefix_signal(self):
        b=fixture('pullback');expected=signals(b,'crypto','BTC/USD',NOW,self.cfg)
        extended=b+[dict(b[-1],time=NOW,close=1000,high=1001)]
        self.assertEqual(expected,signals(extended[:-1],'crypto','BTC/USD',NOW,self.cfg))
        self.assertFalse(signals(extended,'crypto','BTC/USD',NOW,self.cfg)[0])
    def test_family_disable_and_inverse_etf_label(self):
        b=fixture('pullback');self.cfg['strategies']=['breakout']
        self.assertFalse(signals(b,'crypto','BTC/USD',NOW,self.cfg)[0])
        self.cfg['strategies']=['inverse_trend']
        self.assertEqual(signals(b,'stocks','SH',NOW,self.cfg)[0][0]['strategy'],'inverse_trend')
    def test_candidate_source_is_frozen_and_unknown_pack_refused(self):
        self.assertEqual(len(self.cfg['strategy_pack_source_sha256']),64)
        with tempfile.TemporaryDirectory() as d:
            store=Store(d,self.cfg,NOW);store.db.close()
            changed=dict(self.cfg,strategy_pack_source_sha256='x'*64)
            with self.assertRaises(ValueError):Store(d,changed,NOW)
    def test_fresh_price_keeps_mean_target_and_risk_cash_shared(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d,self.cfg,NOW)
            feed=FakeKraken();feed.price=92
            engine=Engine(store,feed,Alpaca(environ={}),NoKalshi(),clock=lambda:NOW)
            candidate=signals(fixture('range_reversion'),'crypto','BTC/USD',NOW,self.cfg)[0][0]
            result=engine.enter(candidate);self.assertEqual(result,'Order filled')
            state=store.read();position=next(iter(state['positions'].values()))
            self.assertAlmostEqual(position['target'],candidate['target'])
            self.assertLessEqual(position['quantity']*(candidate['stop_distance']+position['entry_price']*(.016+.002+.003)),2.5+1e-5)
            count=len(state['orders']);engine.enter(candidate)
            self.assertEqual(len(store.read()['orders']),count)
            self.assertLessEqual(portfolio(state,NOW)['exposure'],100)
            store.db.close()
    def test_fresh_price_cannot_erase_cost_cleared_room(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d,self.cfg,NOW);feed=FakeKraken()
            candidate=signals(fixture('range_reversion'),'crypto','BTC/USD',NOW,self.cfg)[0][0]
            candidate=copy.deepcopy(candidate);candidate['target']=candidate['reference']*1.032
            feed.price=candidate['reference']*1.025
            engine=Engine(store,feed,Alpaca(environ={}),NoKalshi(),clock=lambda:NOW)
            self.assertIn('insufficient target room',engine.enter(candidate))
            self.assertFalse(store.read()['orders']);store.db.close()


if __name__=='__main__':unittest.main()
