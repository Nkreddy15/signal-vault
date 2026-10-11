"""Native 15m causality, complete chart bars and loss-preserving revision checks."""
import base64
import copy
import fcntl
import json
from pathlib import Path
import tempfile
import unittest

from trading_stack.cloud_paper.engine import Engine, load_config
from trading_stack.cloud_paper.providers import Alpaca
from trading_stack.cloud_paper.store import Store, digest, portfolio
from trading_stack.cloud_paper.strategies import signals
from trading_stack.cloud_paper.supervisor import initialize_store
from trading_stack.cloud_paper.web import create_app
from trading_stack.test_cloud_paper import FakeKraken, NoKalshi, order, obs
from trading_stack.test_integrated import fixture

ROOT=Path(__file__).parent/'cloud_paper'
NOW=150*900


def candles(family='slow_breakout'):
    return [dict(b,time=b['time']//16) for b in fixture(family)]


class IntradayTests(unittest.TestCase):
    def setUp(self):
        self.old=load_config(ROOT/'campaign.integrated.json')
        self.cfg=load_config(ROOT/'campaign.intraday.json')

    def test_native_paths_need_no_four_hour_close(self):
        for family in ('slow_breakout','slow_pullback','range_reclaim'):
            result,reason=signals(candles(family),'crypto','BTC/USD',NOW,self.cfg)
            self.assertIn(family,[c['strategy'] for c in result],reason)
            self.assertEqual(result[0]['signal_at'],NOW)
            self.assertIn('15m',result[0]['reason'])

    def test_partial_gapped_duplicate_and_misaligned_quarter_hours_refused(self):
        for issue in ('partial','gap','duplicate','misaligned'):
            rows=candles()
            if issue=='partial':rows[-1]['time']=NOW
            if issue=='gap':rows.pop(-8)
            if issue=='duplicate':rows[-1]['time']=rows[-2]['time']
            if issue=='misaligned':rows[-1]['time']+=1
            self.assertFalse(signals(rows,'crypto','BTC/USD',NOW,self.cfg)[0],issue)

    def test_wrong_interval_and_fee_shortfall_refused(self):
        with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as f:
            wrong=json.loads((ROOT/'campaign.intraday.json').read_text());wrong['bar_seconds']=14400
            json.dump(wrong,f);f.flush()
            with self.assertRaisesRegex(ValueError,'native complete 15m'):load_config(f.name)
        expensive=dict(self.cfg,crypto_fee_fraction=.3)
        self.assertFalse(signals(candles('slow_pullback'),'crypto','BTC/USD',NOW,expensive)[0])

    def test_native_chart_and_gap_aware_hour_aggregation(self):
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,self.cfg,NOW)
            rows=candles()[:12]
            st.put_candles('crypto','BTC/USD','15m',rows)
            st.put_candles('crypto','BTC/USD','4h',fixture('slow_breakout'))
            password='isolated-intraday-fixture-'+'x'*32
            client=create_app(path,password).test_client()
            auth={'Authorization':'Basic '+base64.b64encode(('nikhil:'+password).encode()).decode()}
            native=client.get('/api/candles?market=crypto&pair=BTC/USD&timeframe=15m',headers=auth).json['candles']
            self.assertEqual(native,rows)
            hourly=client.get('/api/candles?market=crypto&pair=BTC/USD&timeframe=1h',headers=auth).json['candles']
            self.assertEqual(len(hourly),3)
            self.assertEqual(hourly[0]['close'],rows[3]['close'])
            self.assertEqual(hourly[0]['volume'],sum(r['volume'] for r in rows[:4]))
            st.db.execute("DELETE FROM candles WHERE market='crypto' AND symbol='BTC/USD' AND timeframe='15m' AND at=900")
            hourly=client.get('/api/candles?market=crypto&pair=BTC/USD&timeframe=1h',headers=auth).json['candles']
            self.assertEqual([r['time'] for r in hourly],[3600,7200])
            self.assertEqual(client.get('/api/candles?market=stocks&pair=SPY&timeframe=15m',headers=auth).status_code,400)
            st.db.close()

    def test_closed_quarter_hour_refreshes_before_five_minute_cache_expiry(self):
        class Feed(FakeKraken):
            def __init__(self):super().__init__();self.requested=[]
            def bars(self,symbol,now,timeframe='1h'):
                self.requested.append((now,timeframe))
                data=candles();offset=int(now//900)*900-NOW
                return [dict(b,time=b['time']+offset) for b in data]
        cfg=dict(self.cfg,crypto_symbols=['BTC/USD'],dex_enabled=False,predictarb_enabled=False)
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,cfg,NOW);feed=Feed();clock=[NOW+850]
            e=Engine(st,feed,Alpaca(environ={}),NoKalshi(),clock=lambda:clock[0])
            e.quotes={'crypto:BTC/USD':feed.quotes(['BTC/USD'],clock[0])['BTC/USD']}
            e.candidates();clock[0]+=60;e.candidates()
            self.assertEqual([tf for _,tf in feed.requested],['15m','15m'])
            self.assertEqual(e.history['crypto:BTC/USD'][-1]['time'],NOW)
            st.db.close()

    def test_revision_preserves_prior_losses_ledger_history_and_deadline(self):
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,self.old,NOW)
            buy=order('past');st.prepare(buy,NOW);st.observe(buy['id'],obs(buy),NOW)
            sell=order('past-exit',action='sell',tid='past',price=96)
            st.prepare(sell,NOW+1);st.observe(sell['id'],obs(sell),NOW+1)
            st.put_candles('crypto','BTC/USD','4h',fixture('slow_breakout'))
            st.db.execute('INSERT INTO equity VALUES(?,?,?,?,?)',(NOW,portfolio(st.read(),NOW)['equity'],st.read()['cash'],0,.01))
            before=st.read();self.assertLess(before['cash'],500);st.db.close()
            revised=initialize_store(path,self.cfg,{'SV_CONFIG_REVISION_FROM':before['config_hash']},NOW+2)
            after=revised.read()
            for key in ('cash','realized','fees','turnover','closed','orders','signals','started_at','deadline','campaign_id','peak','daily_halt'):
                self.assertEqual(before[key],after[key],key)
            self.assertEqual(after['config_hash'],digest(self.cfg))
            self.assertEqual(len(after['config_revisions']),1)
            self.assertEqual(revised.db.execute("SELECT count(*) FROM events WHERE kind='CONFIGURATION_REVISION'").fetchone()[0],1)
            self.assertEqual(revised.db.execute('SELECT count(*) FROM equity').fetchone()[0],1)
            self.assertEqual(len(revised.candles('crypto','BTC/USD','4h',1000)),150)
            revised.db.close()
            restarted=initialize_store(path,self.cfg,{},NOW+3)
            self.assertEqual(len(restarted.read()['config_revisions']),1)
            self.assertEqual(restarted.read()['cash'],before['cash'])
            restarted.db.close()

    def test_revision_permission_risk_changes_and_nonflat_accounts_refused(self):
        for issue in ('missing_permission','wrong_hash','capital','risk','positions','pending','commands'):
            with self.subTest(issue=issue),tempfile.TemporaryDirectory() as path:
                st=Store(path,self.old,NOW);before=st.read();cfg=copy.deepcopy(self.cfg)
                env={'SV_CONFIG_REVISION_FROM':before['config_hash']}
                if issue=='missing_permission':env={}
                if issue=='wrong_hash':env['SV_CONFIG_REVISION_FROM']='wrong'
                if issue=='capital':cfg['capital']=1000
                if issue=='risk':cfg['risk_per_trade']=.05
                if issue=='positions':
                    o=order();st.prepare(o,NOW);st.observe(o['id'],obs(o),NOW)
                if issue=='pending':st.prepare(order(),NOW)
                if issue=='commands':st.command('pause','isolated-command',now=NOW)
                current=st.read();st.db.close()
                with self.assertRaises(ValueError):initialize_store(path,cfg,env,NOW+1)
                st=Store(path)
                self.assertEqual(current,st.read());st.db.close()

    def test_running_worker_lock_prevents_revision(self):
        with tempfile.TemporaryDirectory() as path:
            st=Store(path,self.old,NOW);expected=st.read()['config_hash'];st.db.close()
            with (Path(path)/'worker.lock').open('a+') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaises(BlockingIOError):initialize_store(path,self.cfg,{'SV_CONFIG_REVISION_FROM':expected},NOW+1)


if __name__=='__main__':unittest.main()
