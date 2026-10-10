"""Causality, arbitrage economics, shared-account and native-chart regressions."""
import asyncio
import base64
from concurrent.futures import Future
import copy
import math
from pathlib import Path
import tempfile
import unittest

from trading_stack.cloud_paper.engine import Engine, load_config
from trading_stack.cloud_paper.providers import Kraken, Alpaca
from trading_stack.cloud_paper.store import Store, portfolio
from trading_stack.cloud_paper.strategies import signals
from trading_stack.cloud_paper.web import create_app, snapshot
from trading_stack.cloud_paper.predictarb_bridge import PredictArb, PublicHTTP, audit
from trading_stack.cloud_paper.predictarb.config import Config
from trading_stack.cloud_paper.predictarb.models import Market, Book, D
from trading_stack.cloud_paper.predictarb.scanner import Scanner
from trading_stack.test_cloud_paper import FakeKraken, NoKalshi, order, obs

NOW=150*14400
CONFIG=Path(__file__).parent/'cloud_paper/campaign.integrated.json'


def fixture(family):
    c=[100+.2*i+math.sin(i*.8)*.5 for i in range(150)]
    if family=='slow_breakout':c[-1]=max(c[-56:-1])+1
    elif family=='slow_pullback':c[-2:]=[125,129.5]
    else:
        c=[100+math.sin(i*.7)*2 for i in range(150)];c[-12]=96;c[-2:]=[94,95.8]
    return [dict(time=i*14400,open=x,close=x,high=x+.4,low=x-.4,volume=100000 if i<149 else 150000) for i,x in enumerate(c)]


class IntegratedTests(unittest.TestCase):
    def setUp(self):self.cfg=load_config(CONFIG)

    def test_three_independent_causal_paths(self):
        for family in ('slow_breakout','slow_pullback','range_reclaim'):
            result,reason=signals(fixture(family),'crypto','BTC/USD',NOW,self.cfg)
            self.assertIn(family,[s['strategy'] for s in result],reason)
            self.assertEqual(result[0]['signal_at'],NOW)
            self.assertIn('omniquant_regime',result[0]['indicators'])

    def test_malformed_or_unclosed_bars_cannot_create_signal(self):
        for issue in ('future','gap','negative','nan','duplicate','unaligned'):
            b=fixture('slow_breakout')
            if issue=='future':b[-1]['time']=NOW
            if issue=='gap':b.pop(-8)
            if issue=='negative':b[-1]['volume']=-1
            if issue=='nan':b[-1]['close']=float('nan')
            if issue=='duplicate':b[-1]['time']=b[-2]['time']
            if issue=='unaligned':b[-1]['time']+=1
            self.assertFalse(signals(b,'crypto','BTC/USD',NOW,self.cfg)[0],issue)

    def test_costs_do_not_inflate_target(self):
        b=fixture('slow_pullback')
        low=signals(b,'crypto','BTC/USD',NOW,self.cfg)[0][0]
        high=copy.deepcopy(self.cfg);high['crypto_fee_fraction']=.3
        self.assertFalse(signals(b,'crypto','BTC/USD',NOW,high)[0])
        self.assertAlmostEqual(low['target']-low['reference'],4*low['stop_distance'])

    def test_family_disabled_and_no_future_data_change(self):
        b=fixture('slow_breakout');before=signals(b,'crypto','BTC/USD',NOW,self.cfg)
        extended=b+[dict(b[-1],time=NOW,close=10000,high=10001)]
        self.assertEqual(before,signals(extended[:-1],'crypto','BTC/USD',NOW,self.cfg))
        cfg=dict(self.cfg,strategies=[])
        self.assertFalse(signals(b,'crypto','BTC/USD',NOW,cfg)[0])

    def test_old_gap_stops_poisoning_signals_after_full_rewarm(self):
        b=fixture('slow_breakout')
        with_old_gap=b[:10]+b[11:]
        self.assertEqual(signals(b,'crypto','BTC/USD',NOW,self.cfg),signals(with_old_gap,'crypto','BTC/USD',NOW,self.cfg))
        self.assertFalse(signals(b[:-8]+b[-7:],'crypto','BTC/USD',NOW,self.cfg)[0])

    def test_kraken_legacy_doge_alias(self):
        k=Kraken(lambda *a,**kw:{'error':[],'result':{'XXDGZUSD':{'wsname':'XDG/USD','status':'online'}}})
        self.assertIn('DOGE/USD',k.load_assets())

    def test_research_lane_cannot_enter_and_trailing_parameters_persist(self):
        cfg=dict(self.cfg,predictarb_enabled=False,dex_enabled=False,entry_markets=[])
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,cfg,NOW);feed=FakeKraken()
            e=Engine(st,feed,Alpaca(environ={}),NoKalshi(),clock=lambda:NOW)
            c=signals(fixture('slow_breakout'),'crypto','BTC/USD',NOW,cfg)[0][0]
            self.assertIn('Research-only',e.enter(c));self.assertFalse(st.read()['orders'])
            o=order('trailing');o.update(trailing_activation_multiple=2,trailing_distance_multiple=1.5)
            self.assertTrue(st.prepare(o,NOW));st.observe(o['id'],obs(o),NOW)
            p=st.read()['positions']['trailing']
            self.assertEqual((p['trailing_activation_multiple'],p['trailing_distance_multiple']),(2,1.5))
            st.db.close()

    def test_native_4h_chart_no_fabricated_one_hour_or_gap_day(self):
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,self.cfg,NOW);b=fixture('slow_breakout')
            st.put_candles('crypto','BTC/USD','4h',b);st.db.close()
            pw='fixture-only-password-'+'x'*32
            client=create_app(path,pw).test_client()
            auth={'Authorization':'Basic '+base64.b64encode(('nikhil:'+pw).encode()).decode()}
            self.assertEqual(client.get('/api/opportunities').status_code,401)
            self.assertEqual(client.get('/api/opportunities',headers=auth).json['capital_allocated'],0)
            self.assertEqual(client.get('/api/candles?market=crypto&pair=BTC/USD&timeframe=1h',headers=auth).status_code,400)
            rows=client.get('/api/candles?market=crypto&pair=BTC/USD&timeframe=4h',headers=auth).json['candles']
            self.assertEqual(len(rows),150)
            self.assertEqual(rows[0]['close'],b[0]['close'])


class ArbTests(unittest.TestCase):
    def setUp(self):
        self.c=Config();self.scanner=Scanner(self.c,None)
        self.m=Market('event','condition','yes','no','Test',D('.04'))
        self.y=Book('yes','condition',[(D('.46'),D('100'))],[(D('.45'),D('100'))],100,100,'yes')
        self.n=Book('no','condition',[(D('.50'),D('100'))],[(D('.49'),D('100'))],100,100,'no')

    def test_discount_uses_depth_and_fees_not_midpoints(self):
        o=self.scanner.price(self.m,self.y,self.n)
        self.assertEqual(o.gross_edge,D('.04'));self.assertLess(o.net_edge,o.gross_edge)
        self.assertGreater(o.fees,0);self.assertEqual(o.direction,'buy_complete_set')
        self.y.asks=[(D('.1'),D('.1')),(D('.8'),D('100'))]
        o=self.scanner.price(self.m,self.y,self.n)
        self.assertGreater(o.gross_edge,0);self.assertLess(o.net_edge,0)

    def test_overpriced_direction_requires_split_and_sells_bids(self):
        self.y.bids=[(D('.54'),D('100'))];self.n.bids=[(D('.52'),D('100'))]
        o=self.scanner.price_sale(self.m,self.y,self.n)
        self.assertEqual(o.direction,'split_then_sell');self.assertEqual(o.gross_edge,D('.06'))
        self.assertLess(o.net_edge,D('.06'));self.assertGreaterEqual(o.cost,o.quantity)

    def test_insufficient_depth_is_not_arbitrage(self):
        self.y.asks=[(D('.46'),D('2'))]
        self.assertIsNone(self.scanner.price(self.m,self.y,self.n))

    def test_staleness_skew_and_wrong_identity_block(self):
        for issue in ('stale','future','skew','identity'):
            y,n=copy.deepcopy(self.y),copy.deepcopy(self.n)
            if issue=='stale':y.timestamp=90
            if issue=='future':y.timestamp=101
            if issue=='skew':y.timestamp=99
            if issue=='identity':n.condition='other'
            o=self.scanner.price(self.m,y,n)
            self.assertIsNotNone(audit(o,100,self.c),issue)

    def test_public_transport_has_no_order_or_secret_path(self):
        for url,body in [('https://clob.polymarket.com/order',{'order':1}),('https://evil.example/book',None)]:
            with self.assertRaises(PermissionError):asyncio.run(PublicHTTP().request(url,body=body))

    def test_read_only_bridge_cannot_change_portfolio_cash(self):
        cfg=load_config(CONFIG)
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,cfg,NOW);bridge=PredictArb(st,clock=lambda:NOW)
            f=Future();f.set_result(dict(at=NOW,observations=[{'net_edge':'.03','status':'QUALIFIED_RESEARCH_ONLY'}],coverage={'market_rows':8},next_offset=8));bridge.future=f
            s=st.read();s['predictarb_last_scan']=NOW;st.save(s)
            bridge.tick();s=st.read()
            self.assertEqual(s['cash'],500);self.assertEqual(s['realized'],0);self.assertFalse(s['orders']);self.assertFalse(s['positions'])
            self.assertEqual(s['predictarb_offset'],8);self.assertEqual(st.db.execute('SELECT COUNT(*) FROM arbitrage_observations').fetchone()[0],1)
            bridge.close();st.db.close()


if __name__=='__main__':unittest.main()
