"""Deterministic V11 fixtures; not observations of market performance."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).parent/'crypto'))
sys.path.insert(0,str(Path(__file__).parent/'dashboard'))
import paper_v11 as v
import paper_v11_view as view
import app as web

NOW=int(pd.Timestamp('2026-10-04',tz='UTC').timestamp()*1000)+30000


def quotes(now=NOW,price=100):return {p:dict(bid=price,ask=price*1.001,observed_ms=now) for p in v.PAIRS}


def features(now=NOW):
    row=dict(ts=now//v.m.DAY*v.m.DAY-v.m.DAY,age=90,volume=100.,r7=-.05,r28=-.2,ema21=110.,close=100.,
        volatility=.02,atr=.02,stop=.06,prev_close=102.,rebound2=.04,low7=101.)
    return {p:pd.DataFrame([row]) for p in v.PAIRS}


def start(ledger):
    v.evaluate(ledger,features(NOW-v.m.DAY),quotes(NOW-v.m.DAY),NOW-v.m.DAY)
    v.evaluate(ledger,features(),quotes(),NOW)


class V11Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.ledger=v.Ledger(self.root/'ledger.sqlite3',NOW-v.m.DAY)
        self.output=contextlib.redirect_stdout(io.StringIO());self.output.__enter__()
    def tearDown(self):
        self.ledger.db.close();self.output.__exit__(None,None,None);self.temp.cleanup()

    def test_new_account_and_resume_never_resets_or_inherits_v10(self):
        self.assertEqual(self.ledger.state['balance'],500)
        deadline=self.ledger.state['deadline_ms'];start(self.ledger);self.ledger.commit()
        restored=v.Ledger(self.root/'ledger.sqlite3',NOW+100000)
        self.assertEqual(restored.state['deadline_ms'],deadline)
        self.assertEqual(restored.state['balance'],self.ledger.state['balance'])
        self.assertEqual(restored.state['positions'],self.ledger.state['positions']);restored.db.close()
        with self.ledger.db:self.ledger.db.execute('UPDATE state SET payload=?',(json.dumps(dict(version='V10-PAPER-1',spec={})),))
        with self.assertRaisesRegex(ValueError,'no reset'):v.Ledger(self.root/'ledger.sqlite3',NOW)

    def test_cutover_detects_nested_old_forward_campaign_positions(self):
        self.assertTrue(v.has_held_positions({'candidates':{'candidate_a':{'positions':{'BTC/USD':{'stake':15}}}}}))
        self.assertTrue(v.has_held_positions({'positions':{'ETH/USD':{'stake':15}}}))
        self.assertFalse(v.has_held_positions({'candidates':{'candidate_a':{'positions':{}}},'closed':[{'is_open':False}]}))

    def test_initial_boundary_and_restart_do_not_backfill_or_duplicate(self):
        v.evaluate(self.ledger,features(NOW-v.m.DAY),quotes(NOW-v.m.DAY),NOW-v.m.DAY)
        self.assertEqual(self.ledger.state['entries'],0)
        v.evaluate(self.ledger,features(),quotes(),NOW);self.assertEqual(self.ledger.state['entries'],2)
        self.ledger.commit();restored=v.Ledger(self.root/'ledger.sqlite3',NOW+60000)
        v.evaluate(restored,features(),quotes(NOW+60000),NOW+60000)
        self.assertEqual(restored.state['entries'],2)
        self.assertLessEqual(sum(t['stake_amount'] for t in restored.state['positions'].values()),400)
        self.assertTrue(all(t['signal_ms']<t['open_ms'] for t in restored.state['positions'].values()));restored.db.close()

    def test_partial_universe_late_entry_and_stale_quotes_do_not_fill(self):
        v.evaluate(self.ledger,dict(list(features().items())[:2]),quotes(),NOW)
        self.assertIsNone(self.ledger.state['boundary'])
        v.evaluate(self.ledger,features(NOW-v.m.DAY),quotes(NOW-v.m.DAY),NOW-v.m.DAY)
        v.evaluate(self.ledger,features(),quotes(NOW-100000),NOW)
        self.assertEqual(self.ledger.state['entries'],0)
        self.ledger.state['boundary']=NOW//v.m.DAY*v.m.DAY-2*v.m.DAY
        v.evaluate(self.ledger,features(NOW+700000),quotes(NOW+700000),NOW+700000)
        self.assertEqual(self.ledger.state['entries'],0)

    def test_fees_rollover_and_final_cash_reconcile_without_double_charge(self):
        start(self.ledger);s=self.ledger.state;now=NOW+4*3600000
        v.manage(self.ledger,quotes(now),now)
        roll=sum(p['rollover_paid'] for p in s['positions'].values());self.assertGreater(roll,0)
        v.manage(self.ledger,quotes(now),now);self.assertAlmostEqual(sum(p['rollover_paid'] for p in s['positions'].values()),roll)
        for p in list(s['positions']):v.close(self.ledger,p,quotes(now,95)[p],now,'TEST_END')
        self.assertAlmostEqual(s['balance'],500+sum(t['profit_abs'] for t in s['closed'])-s['operating_cost_usd'])
        self.assertAlmostEqual(s['operating_cost_usd'],v.SPEC['operating_cost_per_day']*(now-s['started_ms'])/v.m.DAY)

    def test_end_waits_for_fresh_quotes_and_preserves_pending_positions(self):
        start(self.ledger);s=self.ledger.state;deadline=s['deadline_ms']
        v.manage(self.ledger,{},deadline);self.assertTrue(s['positions']);self.assertEqual(s['halt_reason'],'SESSION_COMPLETE')
        v.manage(self.ledger,quotes(deadline+1000),deadline+1000);self.assertFalse(s['positions'])
        self.assertTrue(all(t['exit_reason']=='SESSION_COMPLETE' for t in s['closed']))
        self.assertAlmostEqual(s['balance'],500+sum(t['profit_abs'] for t in s['closed'])-.2)

    def test_quote_gap_stop_and_closed_daily_regime_exit(self):
        start(self.ledger);now=NOW+30000
        v.manage(self.ledger,quotes(now,120),now)
        self.assertFalse(self.ledger.state['positions'])
        self.assertTrue(all(t['exit_reason']=='HARD_STOP' and t['close_rate']>120 for t in self.ledger.state['closed']))

    def test_closed_daily_regime_failure_closes_existing_positions(self):
        start(self.ledger);now=NOW+v.m.DAY
        daily=features(now);daily['BTC/USD']['close']=120.
        v.evaluate(self.ledger,daily,quotes(now),now)
        self.assertTrue(all(p.get('pending_exit')=='BEAR_REGIME_OR_TREND_EXIT' for p in self.ledger.state['positions'].values()))
        v.manage(self.ledger,quotes(now),now)
        self.assertFalse(self.ledger.state['positions'])

    def test_runner_handles_quotes_before_candle_outage_and_stop_marker(self):
        start(self.ledger)
        class Feed:
            def fetch_tickers(self,pairs):return {p:dict(bid=120,ask=120.12) for p in pairs}
            def fetch_ohlcv(self,*args,**kwargs):raise OSError('fixture outage')
        with patch.object(v.time,'time',return_value=(NOW+30000)/1000):
            result=v.Runner(self.ledger,self.root,Feed()).cycle()
        self.assertFalse(self.ledger.state['positions']);self.assertEqual(result['status'],'DEGRADED')
        self.assertTrue(self.ledger.state['closed'])
        (self.root/'stop').write_text('stop')
        with patch.object(v.time,'time',return_value=(NOW+60000)/1000):
            result=v.Runner(self.ledger,self.root,Feed()).cycle()
        self.assertEqual(result['status'],'USER_STOP')

    def test_daily_parser_excludes_incomplete_candle_and_matches_research_features(self):
        day=NOW//v.m.DAY*v.m.DAY;i=np.arange(120);c=100*np.exp(-.003*i+.02*np.sin(i/5))
        rows=[[int(day-(119-j)*v.m.DAY),float(x),float(x*1.01),float(x*.99),float(x),100.] for j,x in enumerate(c)]
        f=v.daily_rows(rows,NOW,'BTC/USD');self.assertEqual(int(f.ts.iloc[-1]),day-v.m.DAY)
        raw=pd.DataFrame(rows[:-1],columns=['ts','open','high','low','close','volume'])
        expected=v.d.daily_features(raw,day)
        for col in ['ema21','r28','atr','stop','low7']:np.testing.assert_allclose(f[col],expected[col],equal_nan=True)
        with self.assertRaisesRegex(ValueError,'stale'):v.daily_rows(rows[:-2],NOW,'BTC/USD')

    def test_runner_caches_daily_history_and_publishes_without_historical_orders(self):
        class Feed:
            calls=0
            def fetch_tickers(self,pairs):return {p:dict(bid=100,ask=100.1) for p in pairs}
            def fetch_ohlcv(self,pair,timeframe,limit):
                self.calls+=1;day=NOW//v.m.DAY*v.m.DAY
                return [[day-(119-i)*v.m.DAY,100.,101.,99.,100.,100.] for i in range(120)]
        feed=Feed();runner=v.Runner(self.ledger,self.root,feed)
        with patch.object(v.time,'time',return_value=NOW/1000):
            result=runner.cycle();self.assertEqual(result['status'],'RUNNING')
            modified=(self.root/'candles.json').stat().st_mtime_ns
            runner.cycle()
        self.assertEqual(feed.calls,len(v.PAIRS));self.assertEqual(self.ledger.state['entries'],0)
        self.assertEqual(modified,(self.root/'candles.json').stat().st_mtime_ns)

    def test_dashboard_selects_new_account_and_daily_chart_without_private_requests(self):
        s=self.ledger.state;s['last_success_ms']=NOW;s['status']='RUNNING';v.publish(self.ledger,self.root,NOW)
        (self.root/'activated').write_text('selected')
        (self.root/'candles.json').write_text(json.dumps(dict(pairs={'BTC/USD':[dict(time=v.iso(NOW-v.m.DAY),open=100,high=101,low=99,close=100,volume=100)]})))
        with patch.object(view,'ROOT',self.root),patch.object(view.time,'time',return_value=NOW/1000),patch.object(web,'_freq',return_value=({},None)),patch.object(web,'_alpaca',return_value=({},None)):
            client=web.app.test_client();snapshot=client.get('/api/snapshot').get_json()
            self.assertEqual(snapshot['crypto']['starting_balance'],500)
            self.assertEqual(snapshot['crypto']['marked_equity'],500)
            self.assertEqual(snapshot['paper_final']['version'],v.VERSION)
            chart=client.get('/api/candles?pair=BTC/USD&timeframe=1d').get_json();self.assertEqual(len(chart['candles']),1)
            self.assertEqual(client.get('/api/paper-v11').get_json()['version'],v.VERSION)

    def test_completed_main_exits_without_another_poll_or_reset(self):
        directory=self.root/'completed-main';calls=[]
        def terminal(runner):
            calls.append(1);runner.ledger.state['status']='SESSION_COMPLETE'
            runner.ledger.state['halt_reason']='SESSION_COMPLETE';runner.ledger.commit()
            return dict(status='SESSION_COMPLETE')
        with patch.object(sys,'argv',['paper_v11','--state-dir',str(directory)]),patch('ccxt.kraken',return_value=object()),patch.object(v.Runner,'cycle',terminal),patch.object(v.time,'sleep',side_effect=AssertionError('unexpected sleep')):
            self.assertEqual(v.main(),0)
        self.assertEqual(len(calls),1)
        with sqlite3.connect(directory/'ledger.sqlite3') as db:state=json.loads(db.execute('SELECT payload FROM state WHERE id=1').fetchone()[0])
        self.assertEqual(state['balance'],500);self.assertEqual(state['status'],'SESSION_COMPLETE')


if __name__=='__main__':unittest.main()
