"""Deterministic behavioral scenarios. Synthetic prices are never performance evidence."""
import json
import math
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'crypto'))
sys.path.insert(0, str(ROOT/'dashboard'))
import paper_v10 as m
import paper_v10_view as view
import paper_final_view as v9view
import app as web

NOW = 1_791_014_460_000 // m.BAR*m.BAR+60_000


def prices(direction=1, now=NOW, count=360):
    end = now//m.BAR*m.BAR
    rows = []
    for i in range(count):
        c = 100 * math.exp(direction*(i*.00065 + .004*math.sin(i*.8)))
        o = c*math.exp(-direction*.0003)
        rows.append([end-(count-1-i)*m.BAR, o, max(o,c)*1.0014, min(o,c)*.9986, c, 100+(i%7)*5])
    return rows


def quotes(price=100, now=NOW):
    return {p:dict(bid=price, ask=price*1.001, observed_ms=now) for p in m.PAIRS}


def setup_signal(side='LONG', close=100):
    return dict(signal=True, side=side, regime='UPTREND' if side=='LONG' else 'DOWNTREND',
        tag='trend_continuation', score=3.0, target_pct=.027, stop_pct=.008,
        reason='Deterministic test signal', close=close, atr_pct=.003, rsi=55,
        momentum_pct=.005, volume_ratio=1.0)


class Feed:
    def __init__(self, now=NOW):
        self.now = now
        self.candle_calls = 0
        self.bad_candles = set()
        self.bad_quotes = set()
        self.bid = 100
    def fetch_tickers(self, pairs):
        return {p:dict(bid=self.bid, ask=self.bid*1.001) for p in pairs if p not in self.bad_quotes}
    def fetch_ohlcv(self, pair, timeframe, limit):
        assert timeframe == '15m'
        self.candle_calls += 1
        if pair in self.bad_candles:
            raise OSError('test candle outage')
        return prices(1 if pair in m.PAIRS[:3] else -1, self.now)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = m.Ledger(self.root/'ledger.sqlite3', NOW)
        self.frames = {p:m.validate_frame(prices(now=NOW), NOW,p) for p in m.PAIRS}
        self.q = quotes()
    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()
    def enter(self, sides=None, now=NOW):
        self.ledger.state['boundaries'] = {p:now//m.BAR*m.BAR-2*m.BAR for p in m.PAIRS}
        sides = sides or ['LONG','LONG','LONG','SHORT','SHORT','SHORT']
        results = [setup_signal(side) for side in sides]
        with patch.object(m,'signal_for', side_effect=results):
            m.evaluate(self.ledger,self.frames,self.q,now)

    def test_first_scan_only_records_forward_boundary(self):
        with patch.object(m,'signal_for', return_value=setup_signal()):
            m.evaluate(self.ledger,self.frames,self.q,NOW)
        self.assertEqual(self.ledger.state['entries'],0)
        self.assertEqual(self.ledger.state['intervals_evaluated'],0)
        self.assertTrue(all('Forward boundary' in r['execution'] for r in self.ledger.state['diagnostics']))

    def test_long_and_short_fill_sides_and_direction_caps(self):
        self.enter()
        ps=self.ledger.state['positions']
        self.assertEqual(len(ps),3)
        self.assertEqual(sum(not p['is_short'] for p in ps.values()),2)
        for p in ps.values():
            self.assertEqual(p['open_rate'],100 if p['is_short'] else 100.1)
            self.assertLess(p['target_price'],p['open_rate']) if p['is_short'] else self.assertGreater(p['target_price'],p['open_rate'])
        self.assertEqual(sum(p['stake_amount'] for p in ps.values()),45)

    def test_restart_retains_deadline_and_consumed_signals(self):
        self.enter()
        resumed=m.Ledger(self.root/'ledger.sqlite3',NOW+1000)
        try:
            with patch.object(m,'signal_for',side_effect=AssertionError('rescan')):
                m.evaluate(resumed,self.frames,self.q,NOW+1000)
            self.assertEqual(resumed.state['entries'],3)
            self.assertEqual(resumed.state['deadline_ms'],NOW+7*m.DAY)
            events=[json.loads(r[0]) for r in resumed.db.execute('SELECT payload FROM events')]
            self.assertEqual(sum(e['kind']=='OPEN' for e in events),3)
        finally:
            resumed.db.close()

    def test_long_short_accounting_cost_charged_once(self):
        self.enter()
        expected=100
        for pair,p in list(self.ledger.state['positions'].items()):
            q=dict(bid=89.9,ask=90) if p['is_short'] else dict(bid=110,ask=110.1)
            price=90 if p['is_short'] else 110
            gross=(price/p['open_rate']-1)*(-1 if p['is_short'] else 1)
            cost=m.SPEC['taker_fee_per_side']*(1+price/p['open_rate'])+2*m.SPEC['slippage_per_side']
            expected+=15*(gross-cost)
            m.close(self.ledger,pair,q,NOW+30_000,'TEST')
        self.assertAlmostEqual(self.ledger.state['balance'],expected)
        summary=m.publish(self.ledger,self.root,NOW+30_000)
        self.assertAlmostEqual(summary['crypto']['closed_pnl_usd'],expected-100)
        self.assertEqual(summary['crypto']['open_pnl_usd'],0)

    def test_targets_close_both_sides_at_observed_quotes(self):
        self.enter()
        q=quotes()
        for pair,p in self.ledger.state['positions'].items():
            x=p['target_price']-1 if p['is_short'] else p['target_price']+1
            q[pair]=dict(bid=x-.1 if p['is_short'] else x,ask=x if p['is_short'] else x+.1,observed_ms=NOW+30_000)
        m.manage(self.ledger,q,NOW+30_000)
        self.assertFalse(self.ledger.state['positions'])
        self.assertTrue(all(p['exit_reason']=='GROSS_TARGET' for p in self.ledger.state['closed']))

    def test_gap_loss_uses_observed_prices_not_stop_prices(self):
        self.enter()
        q=quotes()
        for pair,p in self.ledger.state['positions'].items():
            x=120 if p['is_short'] else 80
            q[pair]=dict(bid=x,ask=x,observed_ms=NOW+30_000)
        m.manage(self.ledger,q,NOW+30_000)
        self.assertEqual(self.ledger.state['halt_reason'],'SESSION_LOSS_LIMIT')
        self.assertFalse(self.ledger.state['positions'])
        self.assertTrue(all(p['close_rate'] != p['stop_price'] for p in self.ledger.state['closed']))

    def test_daily_halt_resets_on_utc_day_without_resetting_balance(self):
        s=self.ledger.state
        s.update(balance=97.9,daily_entries=10)
        m.manage(self.ledger,self.q,NOW)
        self.assertTrue(s['daily_halt'])
        self.assertIsNone(s['halt_reason'])
        next_day=(NOW//m.DAY+1)*m.DAY+60_000
        m.manage(self.ledger,quotes(now=next_day),next_day)
        self.assertFalse(s['daily_halt'])
        self.assertEqual(s['daily_entries'],0)
        self.assertEqual(s['balance'],97.9)
        self.assertEqual(s['day_start_equity'],97.9)

    def test_daily_halt_closes_held_positions_and_blocks_entries(self):
        self.enter()
        self.ledger.state['day_start_equity']=103
        m.manage(self.ledger,self.q,NOW)
        self.assertTrue(self.ledger.state['daily_halt'])
        self.assertFalse(self.ledger.state['positions'])
        before=self.ledger.state['entries']
        self.enter()
        self.assertEqual(self.ledger.state['entries'],before)

    def test_stale_held_mark_blocks_utc_day_reset(self):
        self.enter()
        self.ledger.state['daily_halt']=True
        next_day=(NOW//m.DAY+1)*m.DAY+60_000
        partial=quotes(now=next_day)
        partial.pop(next(iter(self.ledger.state['positions'])))
        m.manage(self.ledger,partial,next_day)
        self.assertTrue(self.ledger.state['daily_halt'])
        self.assertEqual(self.ledger.state['risk_day'],NOW//m.DAY)

    def test_timeout_and_campaign_expiry_are_restart_safe(self):
        self.enter()
        now=NOW+8*m.HOUR
        m.manage(self.ledger,quotes(now=now),now)
        self.assertFalse(self.ledger.state['positions'])
        self.assertTrue(all(p['exit_reason']=='TIME_EXIT' for p in self.ledger.state['closed']))
        now=NOW+7*m.DAY
        m.manage(self.ledger,quotes(now=now),now)
        self.assertEqual(self.ledger.state['halt_reason'],'SESSION_COMPLETE')

    def test_missing_quote_does_not_fabricate_expiry_fill(self):
        self.enter()
        now=NOW+7*m.DAY
        m.manage(self.ledger,{},now)
        self.assertEqual(len(self.ledger.state['positions']),3)
        s=m.publish(self.ledger,self.root,now)
        self.assertEqual(s['status'],'STALE_MARKS')
        m.manage(self.ledger,quotes(now=now+30_000),now+30_000)
        self.assertFalse(self.ledger.state['positions'])

    def test_drift_spread_daily_cap_and_cash_each_block_entry(self):
        for case in ('spread','drift','cap','cash'):
            with self.subTest(case=case):
                s=self.ledger.state
                s.update(positions={},boundaries={},daily_entries=0,balance=100)
                self.q=quotes()
                if case=='spread':self.q=quotes(100); [q.update(ask=101) for q in self.q.values()]
                if case=='drift':self.q=quotes(110)
                if case=='cap':s['daily_entries']=12
                if case=='cash':s['balance']=10
                self.enter()
                self.assertFalse(s['positions'])
                self.assertTrue(any(r['execution']!='WAITING' for r in s['diagnostics']))

    def test_cooldown_and_late_window_no_fill(self):
        s=self.ledger.state
        s['cooldowns']={p:NOW for p in m.PAIRS}
        self.enter()
        self.assertFalse(s['positions'])
        s['cooldowns']={}
        self.enter(now=NOW+4*60_000)
        self.assertFalse(s['positions'])

    def test_drain_blocks_entries_but_keeps_exits(self):
        self.ledger.state['drain']=True
        self.enter()
        self.assertFalse(self.ledger.state['positions'])
        self.ledger.state['drain']=False
        self.enter()
        self.ledger.state['drain']=True
        m.manage(self.ledger,quotes(now=NOW+8*m.HOUR),NOW+8*m.HOUR)
        self.assertFalse(self.ledger.state['positions'])

    def test_bad_single_quote_is_isolated(self):
        ticks=Feed().fetch_tickers(m.PAIRS)
        ticks['BTC/USD']=dict(bid=102,ask=101)
        q,errs=m.validate_quotes(ticks,NOW)
        self.assertEqual(len(q),5)
        self.assertEqual(len(errs),1)
        for bad in (dict(bid=float('nan'),ask=1),dict(bid=1,ask=2,timestamp=NOW-100_000)):
            ticks['BTC/USD']=bad
            q,errs=m.validate_quotes(ticks,NOW)
            self.assertNotIn('BTC/USD',q)

    def test_unclosed_bar_and_gaps_rejected(self):
        rows=prices()
        f=m.validate_frame(rows,NOW,'BTC/USD')
        self.assertEqual(int(f.ts.iloc[-1]),NOW//m.BAR*m.BAR-m.BAR)
        with self.assertRaisesRegex(ValueError,'missing or duplicate'):
            m.validate_frame(rows[:200]+rows[201:],NOW,'BTC/USD')

    def test_prefix_indicators_and_signals_are_causal(self):
        rows=prices(count=400)[:-1]
        frame=m.indicators(__import__('pandas').DataFrame(rows,columns=['ts','open','high','low','close','volume']))
        for i in (180,250,350):
            prefix=m.indicators(frame[['ts','open','high','low','close','volume']].iloc[:i+1])
            self.assertEqual(m.signal_for(frame,i),m.signal_for(prefix))

    def test_real_signal_functions_generate_both_sides_on_price_fixtures(self):
        for direction,side in ((1,'LONG'),(-1,'SHORT')):
            f=m.validate_frame(prices(direction),NOW,'BTC/USD')
            results=[m.signal_for(f,i) for i in range(160,len(f))]
            signals=[r for r in results if r['signal']]
            self.assertGreater(len(signals),5)
            self.assertTrue(all(r['side']==side for r in signals))

    def test_range_reversal_needs_room_after_costs(self):
        f=self.frames['BTC/USD'].copy()
        idx=f.index[-1]
        prev=f.index[-2]
        f.loc[idx,['fast','slow','slope','atr','vol_ratio','ret4','rsi']]=[100,100,0,.01,1,.001,50]
        f.loc[prev,['z','close']]=[-2,99]
        f.loc[idx,['close','open','mean']]=[100,99.5,103]
        self.assertTrue(m.signal_for(f)['signal'])
        self.assertEqual(m.signal_for(f)['tag'],'range_reversal')
        f.loc[idx,'mean']=100.4
        r=m.signal_for(f)
        self.assertFalse(r['signal'])
        self.assertIn('costs',r['reason'])

    def test_zero_volume_diagnostics_are_json_serializable(self):
        rows=prices()
        for r in rows:r[5]=0
        f=m.validate_frame(rows,NOW,'BTC/USD')
        json.dumps(m.signal_for(f),allow_nan=False)
        self.assertFalse(m.signal_for(f)['signal'])

    def test_runner_isolates_candle_outage_and_caches_successes(self):
        feed=Feed()
        feed.bad_candles={'BTC/USD'}
        runner=m.Runner(self.ledger,self.root,feed)
        with patch.object(m.time,'time',return_value=NOW/1000):
            a=runner.cycle()
            b=runner.cycle()
        self.assertEqual(a['status'],'DEGRADED')
        self.assertEqual(feed.candle_calls,7)
        self.assertEqual(len(runner.frames),5)
        self.assertEqual(b['cycles'],2)
        self.assertEqual(b['crypto']['open_trade_count'],0)

    def test_quote_stops_survive_total_candle_outage(self):
        self.enter(['LONG']*6)
        feed=Feed()
        feed.bid=97
        feed.bad_candles=set(m.PAIRS)
        runner=m.Runner(self.ledger,self.root,feed)
        with patch.object(m.time,'time',return_value=NOW/1000):s=runner.cycle()
        self.assertFalse(self.ledger.state['positions'])
        self.assertEqual(s['status'],'DEGRADED')

    def test_no_network_no_success_claim(self):
        feed=Feed()
        feed.fetch_tickers=lambda _: (_ for _ in ()).throw(OSError('test offline'))
        with patch.object(m.time,'time',return_value=NOW/1000):
            s=m.Runner(self.ledger,self.root,feed).cycle()
        self.assertIsNone(s['last_success_ms'])
        self.assertEqual(s['status'],'DEGRADED')

    def test_activity_counts_never_create_ledger_profit(self):
        report=m.activity_report(self.frames)
        self.assertGreater(report['total_signals'],0)
        self.assertEqual(self.ledger.state['balance'],100)
        self.assertEqual(self.ledger.state['entries'],0)

    def test_forward_runner_trades_real_signal_logic_on_price_fixtures(self):
        class MovingFeed(Feed):
            def rows(self,pair):
                step=(self.now-NOW)//m.BAR
                return prices(1 if pair in m.PAIRS[:3] else -1,self.now,360+step)
            def fetch_ohlcv(self,pair,timeframe,limit):
                return self.rows(pair)
            def fetch_tickers(self,pairs):
                return {p:dict(bid=self.rows(p)[-2][4]*.9995,ask=self.rows(p)[-2][4]*1.0005) for p in pairs}
        feed=MovingFeed()
        runner=m.Runner(self.ledger,self.root,feed)
        with patch.object(m.time,'time',return_value=NOW/1000):
            first=runner.cycle()
        self.assertEqual(first['entries'],0)
        for step in range(1,13):
            feed.now=NOW+step*m.BAR
            with patch.object(m.time,'time',return_value=feed.now/1000):
                s=runner.cycle()
            self.assertEqual(s['status'],'RUNNING')
        self.assertGreater(s['entries'],0)
        seen=list(self.ledger.state['positions'].values())+self.ledger.state['closed']
        self.assertEqual({p['is_short'] for p in seen},{False,True})
        self.assertEqual(s['intervals_evaluated'],12)

    def test_archives_survive_rolling_candle_cache(self):
        self.enter()
        m.archive_charts(self.ledger,self.frames)
        trade=next(iter(self.ledger.state['positions'].values()))
        original=self.ledger.db.execute('SELECT payload FROM charts WHERE trade_id=?',(trade['trade_id'],)).fetchone()[0]
        later=NOW+8*m.DAY
        later_frames={p:m.validate_frame(prices(now=later),later,p) for p in m.PAIRS}
        m.archive_charts(self.ledger,later_frames)
        after=self.ledger.db.execute('SELECT payload FROM charts WHERE trade_id=?',(trade['trade_id'],)).fetchone()[0]
        self.assertEqual(original,after)

    def test_corrupt_or_different_spec_ledger_never_resets(self):
        self.ledger.state['spec']={}
        self.ledger.commit()
        with self.assertRaises(ValueError):m.Ledger(self.root/'ledger.sqlite3',NOW)
        self.ledger.db.execute("UPDATE state SET payload='broken' WHERE id=1")
        self.ledger.db.commit()
        with self.assertRaises(ValueError):m.Ledger(self.root/'ledger.sqlite3',NOW)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.patch=patch.object(view,'ROOT',self.root/'v10')
        self.oldpatch=patch.object(v9view,'ROOT',self.root/'v9')
        self.patch.start();self.oldpatch.start()
        view.ROOT.mkdir();v9view.ROOT.mkdir()
        now=int(time.time()*1000)
        ledger=m.Ledger(view.ROOT/'ledger.sqlite3',now)
        ledger.state.update(status='RUNNING',last_success_ms=now,heartbeat_ms=now)
        m.publish(ledger,view.ROOT,now)
        ledger.db.close()
        (view.ROOT/'activated').touch()
        old=dict(version='V9-OVERNIGHT-1',status='SESSION_COMPLETE',last_success_ms=now,
            crypto=dict(bot_state='SESSION_COMPLETE',open_trades=[],closed_trades=[],
                open_trade_count=0,closed_trade_count=0,closed_pnl_usd=-.12,open_pnl_usd=0,
                config=dict(timeframe='1h')),safety={})
        m.atomic_json(v9view.ROOT/'summary.json',old)
        (v9view.ROOT/'activated').touch()
        self.client=web.app.test_client()
    def tearDown(self):
        self.patch.stop();self.oldpatch.stop();self.tmp.cleanup()
    @staticmethod
    def freq(path,params=None):
        return ({'strategy':'V1','state':'RUNNING'} if path=='show_config' else {'profit_closed_coin':7} if path=='profit' else [],None)

    def test_three_views_have_separate_pnl_and_timeframes(self):
        with patch.object(web,'_freq',side_effect=self.freq),patch.object(web,'_alpaca',return_value=({},None)):
            latest=self.client.get('/api/snapshot').get_json()
            old=self.client.get('/api/snapshot?engine=v9').get_json()
            legacy=self.client.get('/api/snapshot?engine=v1').get_json()
        self.assertEqual(latest['crypto']['closed_pnl_usd'],0)
        self.assertEqual(latest['crypto']['config']['timeframe'],'15m')
        self.assertEqual(old['crypto']['closed_pnl_usd'],-.12)
        self.assertEqual(old['crypto']['config']['timeframe'],'1h')
        self.assertEqual(legacy['crypto']['closed_pnl_usd'],7)

    def test_archived_candle_route_and_wrong_timeframe(self):
        with __import__('sqlite3').connect(view.ROOT/'ledger.sqlite3') as db:
            db.execute('INSERT INTO charts VALUES(?,?)',('v10-1',json.dumps([dict(time='2026-10-03T12:00:00Z',open=100,high=101,low=99,close=100)])))
        d=self.client.get('/api/candles?pair=BTC/USD&timeframe=15m&trade_id=v10-1').get_json()
        self.assertEqual(len(d['candles']),1)
        self.assertEqual(self.client.get('/api/candles?pair=BTC/USD&timeframe=1h').status_code,400)
        self.assertEqual(self.client.get('/api/paper-v10').get_json()['version'],'V10-PAPER-1')

    def test_stale_and_unavailable_status(self):
        with patch.object(view.time,'time',return_value=time.time()+300):
            self.assertEqual(view.summary()['status'],'STALE')
        (view.ROOT/'summary.json').unlink()
        self.assertEqual(view.summary()['status'],'UNAVAILABLE')


if __name__=='__main__':
    unittest.main(verbosity=2)
