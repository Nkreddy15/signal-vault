"""Leakage boundaries, fee arithmetic and read-only native data checks."""
import base64
import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from trading_stack.cloud_paper.binance_public import BinancePublic,public_json
from trading_stack.cloud_paper.entry_model import FEATURES,check_history,extract,probability,propose
from trading_stack.cloud_paper.engine import load_config
from trading_stack.cloud_paper.providers import ProviderError
from trading_stack.cloud_paper.store import Store
from trading_stack.cloud_paper.web import create_app
from trading_stack.research.entry_study import levels,outcome,simulate
from trading_stack.research.patient_study import replay

NOW=1786838400


def history():
    bars=[];price=100.
    for i in range(288):
        price+=.012 if i%3 else -.014
        bars.append(dict(time=NOW-(288-i)*300,open=price-.003,high=price+.05,low=price-.05,close=price,
            volume=100.,quote_volume=price*100,taker_buy_base_volume=55.))
    return bars


def cfg():return dict(capital=500.,fee=.0002,slip=.001,halfspread=.00025,net_target=.003,max_positions=4,
    risk=.005,max_position=.2,max_exposure=.6,daily_loss=.02,drawdown=.1,hold=3600,cooldown=600)


class EntryModelTests(unittest.TestCase):
    def test_features_are_closed_contiguous_and_do_not_mutate_inputs(self):
        bars=history();before=copy.deepcopy(bars);x=extract(bars,NOW)
        self.assertEqual(len(x['features']),len(FEATURES));self.assertTrue(all(math.isfinite(v) for v in x['features']))
        self.assertEqual(bars,before)
        self.assertIsNone(extract(bars,NOW-1));self.assertIsNone(extract(bars,NOW+301))
        self.assertIsNone(extract(bars[:-5]+bars[-4:],NOW))
        self.assertIsNone(extract(bars+[dict(bars[-1],time=NOW)],NOW))

    def test_trend_continuation_does_not_require_a_single_crossing(self):
        bars=history();p=propose(bars,NOW)
        self.assertTrue(any(c['family']=='trend_continuation' for c in p))
        self.assertEqual(p,propose(bars,NOW));self.assertEqual(p[0]['signal_at'],NOW)

    def test_bad_features_and_model_parameters_fail_closed(self):
        model=dict(features=list(FEATURES),mean=[0.]*len(FEATURES),scale=[1.]*len(FEATURES),coefficient=[0.]*len(FEATURES),intercept=0.)
        self.assertEqual(probability(model,[0.]*len(FEATURES)),.5)
        for key in ('mean','scale','coefficient'):
            bad=copy.deepcopy(model);bad[key][0]=float('nan')
            with self.assertRaises(ValueError):probability(bad,[0.]*len(FEATURES))
        bad=copy.deepcopy(model);bad['intercept']=float('inf')
        with self.assertRaises(ValueError):probability(bad,[0.]*len(FEATURES))

    def test_profit_target_is_net_and_stop_is_anchored_to_bid(self):
        c=dict(stop_distance=1.)
        entry,stop,target=levels(c,100,cfg())
        self.assertAlmostEqual(stop,100*(1-cfg()['halfspread'])-1)
        profit=target*(1-cfg()['slip'])*(1-cfg()['fee'])-entry*(1+cfg()['fee'])
        self.assertAlmostEqual(profit,entry*.003)

    def test_adverse_same_bar_order_and_future_gap_labels(self):
        rows=[dict(time=NOW+i*300,open=100.,high=102.,low=98.,close=100.) for i in range(13)]
        o=outcome(rows,0,dict(stop_distance=1),cfg())
        self.assertEqual(o['reason'],'STOP');self.assertLess(o['net_fraction'],0)
        self.assertIsNone(outcome(rows[:5]+rows[6:],0,dict(stop_distance=1),cfg()))

    def test_future_outcome_metadata_never_controls_decisions(self):
        rows={'BTCUSD':[dict(time=NOW+i*300,open=100.,high=102.,low=100.,close=101.) for i in range(3)]}
        e=dict(symbol='BTCUSD',at=NOW,score=3,family='trend_continuation',features=[0.]*len(FEATURES),reference=100.,stop_distance=1.,lagged_volume_cap=1.,outcome={'label':0,'net_fraction':-100})
        first=simulate([e],rows,cfg(),NOW,NOW+900,None)
        other=copy.deepcopy(e);other['outcome']={'label':1,'net_fraction':1000000}
        self.assertEqual(first,simulate([other],rows,cfg(),NOW,NOW+900,None))
        self.assertEqual(first['trades'][0]['reason'],'NET_TARGET');self.assertGreater(first['net_realized'],0)


class NativeDataTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def transport(path,params=None):
            self.calls.append(path)
            if path=='exchangeInfo':return {'symbols':[{'symbol':'BTCUSD','baseAsset':'BTC','quoteAsset':'USD','status':'TRADING','isSpotTradingAllowed':True,'filters':[{'filterType':'LOT_SIZE','stepSize':'0.000001','minQty':'0.000001'},{'filterType':'MIN_NOTIONAL','minNotional':'5'}]}]}
            if path=='ticker/24hr':return [{'symbol':'BTCUSD','bidPrice':'99','askPrice':'100','closeTime':NOW*1000,'quoteVolume':'1000000'}]
            if path=='depth':return {'asks':[['100','0.1'],['100.05','0.9']],'bids':[['99','1']]}
            raise AssertionError(path)
        self.feed=BinancePublic(transport,clock=lambda:NOW);self.feed.load_assets()
    def test_sweep_prices_observed_depth_and_refuses_missing_quantity(self):
        s=self.feed.sweep('BTC/USD',.5,100.1,'buy')
        self.assertAlmostEqual(s['estimated_price'],100.04)
        with self.assertRaises(ProviderError):self.feed.sweep('BTC/USD',2,100.1,'buy')
        with self.assertRaises(ProviderError):self.feed.sweep('BTC/USD',.5,100,'buy')
        with self.assertRaises(ProviderError):self.feed.sweep('BTC/USD',.5,float('inf'),'buy')
    def test_current_quotes_use_native_timestamp_not_local_time(self):
        self.assertIn('BTC/USD',self.feed.quotes(['BTC/USD'],NOW))
        self.assertFalse(self.feed.quotes(['BTC/USD'],NOW+91))
        with self.assertRaises(ProviderError):self.feed.size('BTC/USD',.0001,100)
    def test_private_order_paths_cannot_be_called(self):
        for path in ('order','account','myTrades','../depth','https://elsewhere'):
            with self.assertRaises(PermissionError):public_json(path)
    def test_feed_status_preserves_http_failure_without_response_body(self):
        with patch('trading_stack.cloud_paper.binance_public.build_opener') as opener:
            opener.return_value.open.side_effect=HTTPError('https://api.binance.us/api/v3/exchangeInfo',451,'Unavailable',{},None)
            with self.assertRaisesRegex(ProviderError,'HTTP 451'):public_json('exchangeInfo')
    def test_authenticated_probe_route_does_not_edit_account(self):
        class Probe:
            def state(self):return dict(state='UNAVAILABLE',mode='READ_ONLY_PUBLIC_PREFLIGHT',orders_submitted=0)
        with tempfile.TemporaryDirectory() as directory:
            config=load_config(Path(__file__).parent/'cloud_paper/campaign.intraday-exits.json');st=Store(directory,config,NOW);before=st.read();st.db.close()
            app=create_app(directory,'x'*40,venue_probe=Probe());client=app.test_client()
            self.assertEqual(client.get('/api/research/venue-health').status_code,401)
            headers={'Authorization':'Basic '+base64.b64encode(b'nikhil:'+b'x'*40).decode()}
            r=client.get('/api/research/venue-health',headers=headers);self.assertEqual(r.status_code,200);self.assertEqual(r.json['orders_submitted'],0)
            st=Store(directory);self.assertEqual(st.read(),before);self.assertEqual(st.db.execute('SELECT count(*) FROM commands').fetchone()[0],0);st.db.close()


class PatientEntryTests(unittest.TestCase):
    def event(self,symbol='BTCUSD'):
        features=[0.]*len(FEATURES);features[FEATURES.index('atr_fraction')]=.01
        return dict(symbol=symbol,at=NOW,score=3,family='trend_continuation',features=features,reference=100.,lagged_volume_cap=1.,outcome={'label':1})
    def test_entry_bar_cannot_claim_a_target_exit_and_future_labels_are_ignored(self):
        rows={'BTCUSD':[dict(time=NOW,open=100.,low=99.3,high=102.,close=100.),dict(time=NOW+300,open=100.,low=99.5,high=102.,close=100.)]}
        first=replay([self.event()],rows,cfg(),NOW,NOW+300,.5,1800)
        self.assertEqual(first['closed_trades'],0);self.assertEqual(first['open_positions'],1)
        e=self.event();e['outcome']={'label':0,'net_fraction':-100}
        full=replay([e],rows,cfg(),NOW,NOW+600,.5,1800)
        self.assertEqual(full,replay([self.event()],rows,cfg(),NOW,NOW+600,.5,1800))
        self.assertEqual(full['trades'][0]['exit_at'],'2026-08-16T00:09:59Z')
        self.assertAlmostEqual(full['net_realized'],full['trades'][0]['entry']*.003)
    def test_entry_bar_adverse_stop_is_counted_even_when_target_was_also_touched(self):
        rows={'BTCUSD':[dict(time=NOW,open=100.,low=98.,high=102.,close=100.)]}
        result=replay([self.event()],rows,cfg(),NOW,NOW+300,.5,1800)
        self.assertEqual(result['trades'][0]['reason'],'STOP');self.assertLess(result['net_realized'],0)
    def test_unfilled_orders_reserve_cash_and_exposure_without_faking_trades(self):
        symbols=['BTCUSD','ETHUSD','SOLUSD','XRPUSD','DOGEUSD']
        rows={s:[dict(time=NOW+i*300,open=100.,low=100.,high=100.,close=100.) for i in range(3)] for s in symbols}
        result=replay([self.event(s) for s in symbols],rows,cfg(),NOW,NOW+900,.5,1800)
        self.assertLessEqual(result['limits_placed'],3);self.assertEqual(result['unfilled_limits'],0)
        self.assertEqual(result['closed_trades'],0);self.assertEqual(result['modeled_fees'],0);self.assertEqual(result['final_equity'],500.)


if __name__=='__main__':unittest.main()
