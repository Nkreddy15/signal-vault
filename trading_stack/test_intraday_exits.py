"""Owned-quantity exits, net costs, stale data and audited open-account revisions."""
from concurrent.futures import Future
import copy
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError

from trading_stack.cloud_paper.engine import Engine,load_config
from trading_stack.cloud_paper.exits_intraday import net_target_bid,reason,trend_invalidated
from trading_stack.cloud_paper.providers import Alpaca
from trading_stack.cloud_paper.predictarb_bridge import PredictArb
from trading_stack.cloud_paper.store import Store,portfolio
from trading_stack.cloud_paper.supervisor import initialize_store
from trading_stack.test_cloud_paper import FakeKraken,NoKalshi,order,obs
from trading_stack.test_intraday import NOW,candles

ROOT=Path(__file__).parent/'cloud_paper'


class ExitTests(unittest.TestCase):
    def setUp(self):
        self.original=load_config(ROOT/'campaign.intraday.json')
        self.full=load_config(ROOT/'campaign.intraday-exits.json')
        self.cfg=dict(self.full,crypto_symbols=['BTC/USD'],stock_symbols=[],dex_enabled=False,predictarb_enabled=False)
        self.tmp=tempfile.TemporaryDirectory();self.st=Store(self.tmp.name,self.cfg,NOW)
        self.feed=FakeKraken();self.engine=Engine(self.st,self.feed,Alpaca(environ={}),NoKalshi(),clock=lambda:NOW+300)
        self.buy=order('owned',quantity=.5,price=100,fee=self.cfg['crypto_fee_fraction']);self.buy.update(strategy='slow_pullback')
        self.st.prepare(self.buy,NOW);self.st.observe('owned',obs(self.buy),NOW)
        state=self.st.read();state['positions']['owned']['opened_at']=NOW;self.st.save(state)

    def tearDown(self):self.st.db.close();self.tmp.cleanup()

    def quote(self,price,at=NOW+300):
        self.feed.price=price
        self.engine.quotes={'crypto:BTC/USD':self.feed.quotes(['BTC/USD'],at)['BTC/USD']}

    def test_overdue_position_sells_owned_quantity_and_preserves_loss(self):
        self.engine.clock=lambda:NOW+4*3600
        self.quote(99,NOW+4*3600)
        self.engine.exits();s=self.st.read()
        self.assertFalse(s['positions']);self.assertEqual(len(s['closed']),1)
        self.assertEqual(s['closed'][0]['exit_reason'],'INTRADAY_TIME_EXIT')
        sells=[o for o in s['orders'].values() if o['action']=='sell']
        self.assertEqual(sells[0]['quantity'],.5);self.assertEqual(sells[0]['status'],'filled')
        self.assertLess(s['cash'],500);self.assertLess(s['realized'],0)
        self.engine.exits();self.assertEqual(len(self.st.read()['closed']),1)

    def test_small_gross_gain_does_not_pass_net_fee_threshold(self):
        p=self.st.read()['positions']['owned']
        self.assertGreater(net_target_bid(p,self.cfg),101.9)
        self.assertIsNone(reason(p,[],101,self.cfg,NOW+300))
        self.quote(101);self.engine.closed_history=lambda *a:[]
        self.engine.exits();self.assertTrue(self.st.read()['positions'])

    def test_actual_net_threshold_exit_records_positive_net_pnl(self):
        p=self.st.read()['positions']['owned'];target=net_target_bid(p,self.cfg)
        self.quote(target*1.00001);self.engine.closed_history=lambda *a:[]
        self.engine.exits();closed=self.st.read()['closed'][0]
        self.assertEqual(closed['exit_reason'],'INTRADAY_NET_TARGET')
        self.assertGreaterEqual(closed['net_pnl'],self.cfg['crypto_net_take_profit_fraction']*closed['cost']-1e-8)
        self.assertLess(closed['active_target'],closed['target'])

    def test_stale_quotes_and_insufficient_depth_do_not_invent_exits(self):
        self.engine.clock=lambda:NOW+4*3600
        self.quote(99,NOW);self.engine.exits()
        self.assertEqual(len(self.st.read()['orders']),1);self.assertTrue(self.st.read()['positions'])
        self.quote(99,NOW+4*3600);self.feed.depth=False;self.engine.exits()
        self.assertTrue(self.st.read()['positions']);self.assertFalse(self.st.read()['closed'])
        self.assertEqual([o for o in self.st.read()['orders'].values() if o['action']=='sell'][0]['status'],'rejected')

    def test_two_closed_bearish_bars_require_post_entry_confirmation(self):
        data=candles()
        for i,b in enumerate(data):
            value=140-i*.15;b.update(open=value,high=value+.2,low=value-.2,close=value)
        self.assertTrue(trend_invalidated('slow_pullback',NOW-1800,data,NOW,2))
        self.assertFalse(trend_invalidated('slow_pullback',NOW-800,data,NOW,2))
        self.assertFalse(trend_invalidated('range_reclaim',NOW-1800,data,NOW,2))
        self.assertFalse(trend_invalidated('slow_pullback',NOW-1800,data+[dict(data[-1],time=NOW)],NOW,2))
        self.assertFalse(trend_invalidated('slow_pullback',NOW-1800,data,NOW+901,2))
        self.assertFalse(trend_invalidated('slow_pullback',NOW-1800,data[:-6]+data[-5:],NOW,2))

    def test_confirmed_trend_exit_and_reentry_cooldown(self):
        data=candles()
        for i,b in enumerate(data):
            value=140-i*.15;b.update(open=value,high=value+.2,low=value-.2,close=value)
        s=self.st.read();s['positions']['owned']['opened_at']=NOW-1800;self.st.save(s)
        self.engine.closed_history=lambda *args:data
        self.engine.clock=lambda:NOW;self.quote(100,NOW);self.engine.exits()
        self.assertEqual(self.st.read()['closed'][0]['exit_reason'],'INTRADAY_TREND_INVALIDATED')
        candidate=dict(market='crypto',symbol='BTC/USD')
        self.assertIn('cooldown',self.engine.enter(candidate))
        self.assertFalse(self.st.read()['positions'])

    def test_open_account_revision_keeps_positions_cash_stops_and_history(self):
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,self.original,NOW)
            st.prepare(self.buy,NOW);st.observe('owned',obs(self.buy),NOW)
            before=st.read();st.db.close()
            new=initialize_store(path,self.full,{'SV_CONFIG_REVISION_FROM':before['config_hash']},NOW+10)
            after=new.read()
            for key in ('campaign_id','started_at','deadline','cash','positions','closed','orders','fees','signals','realized','peak','cycles'):
                self.assertEqual(before[key],after[key],key)
            self.assertEqual(after['config_revisions'][-1]['existing_position_ids'],['owned'])
            new.db.close();again=initialize_store(path,self.full,{},NOW+20)
            self.assertEqual(len(again.read()['config_revisions']),1);again.db.close()

    def test_exit_revision_refuses_cost_risk_and_pending_order_changes(self):
        for issue in ('fee','risk','entry','hash','pending'):
            with self.subTest(issue=issue),tempfile.TemporaryDirectory() as path:
                st=Store(path,self.original,NOW);before=st.read();cfg=copy.deepcopy(self.full);env={'SV_CONFIG_REVISION_FROM':before['config_hash']}
                if issue=='fee':cfg['crypto_fee_fraction']=.0025
                if issue=='risk':cfg['risk_per_trade']=.05
                if issue=='entry':cfg['strategies']=[]
                if issue=='hash':env['SV_CONFIG_REVISION_FROM']='incorrect'
                if issue=='pending':st.prepare(self.buy,NOW)
                current=st.read();st.db.close()
                with self.assertRaises(ValueError):initialize_store(path,cfg,env,NOW+10)
                st=Store(path);self.assertEqual(st.read(),current);st.db.close()


class ScannerRecoveryTests(unittest.TestCase):
    def test_gamma_offset_error_resets_bounded_scan_without_capital_change(self):
        for url,offset,expected in [('https://gamma-api.polymarket.com/markets?offset=2008',2008,0),('https://clob.polymarket.com/book?token_id=x',2008,2008),('https://gamma-api.polymarket.com/markets?offset=0',0,0)]:
            with self.subTest(url=url),tempfile.TemporaryDirectory() as path:
                cfg=load_config(ROOT/'campaign.intraday-exits.json');st=Store(path,cfg,NOW)
                s=st.read();s.update(predictarb_offset=offset,predictarb_last_scan=NOW);st.save(s)
                bridge=PredictArb(st,clock=lambda:NOW);f=Future();f.set_exception(HTTPError(url,422,'unprocessable',{},None));bridge.future=f
                bridge.tick();after=st.read()
                self.assertEqual(after['predictarb_offset'],expected)
                self.assertEqual(after['cash'],500);self.assertFalse(after['orders']);self.assertFalse(after['positions'])
                self.assertEqual(after['providers']['polymarket']['status'],'UNAVAILABLE')
                bridge.close();st.db.close()


if __name__=='__main__':unittest.main()
