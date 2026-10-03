"""Causal strategy fixtures, not evidence of market profitability."""
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
import durable_trend_lab as d
import multi_strategy_lab as m
import regime_swing_lab as r
from test_multi_strategy_lab import START,frame


class DurableTests(unittest.TestCase):
    def test_rank_loss_does_not_exit_trend_holder_and_weekly_review_is_monday_close(self):
        rows={p:SimpleNamespace(age=50,volume=100,r7=.08-i*.005,r28=.2-i*.01,
            atr=.02,volatility=.02,close=110,ema21=100,high28=109,low28=90,stop=.06)
            for i,p in enumerate('ABCDE')}
        monday=int(pd.Timestamp('2026-03-02',tz='UTC').value//1_000_000)
        decisions=d.decisions(rows,monday,'long_only')
        self.assertEqual(set(decisions['trend_hold_28d'][0]),{'A','B'})
        self.assertIn('E',decisions['trend_hold_28d'][1])
        self.assertNotIn('E',decisions['weekly_leader_28d'][1])
        self.assertNotIn('weekly_leader_28d',d.decisions(rows,monday+m.DAY,'long_only'))
        self.assertIn('E',decisions['channel_28d'][0])
        rows['E'].close=99
        self.assertNotIn('E',d.decisions(rows,monday,'long_only')['trend_hold_28d'][1])

    def test_closed_decisions_and_observed_quotes_are_future_invariant(self):
        raw=frame(90*96)
        bear=raw.copy()
        for col in ['open','close']:
            bear[col]=10000/raw[col]
        bear['high'],bear['low']=10000/raw.low,10000/raw.high
        frames={'UP':raw,'DOWN':bear}
        market,exits,receipts=d.compile_research(frames,'synthetic_long_short')
        candidates=[s for _,rows in market for bar,signals in rows.values() for s in signals]
        self.assertEqual({s.side for s in candidates},{1,-1})
        self.assertTrue(all(s.target is None and s.hold_bars==56*96 for s in candidates))
        for timestamp,routes in exits.items():
            if any('weekly_leader_28d' in families for families in routes.values()):
                self.assertEqual(pd.Timestamp(timestamp-m.DAY,unit='ms',tz='UTC').weekday(),0)
        cutoff=START+70*m.DAY
        changed={p:raw.copy() for p,raw in frames.items()}
        for raw in changed.values():
            raw.loc[raw.ts>=cutoff,['open','high','low','close']]*=10
        later,later_exits,later_receipts=d.compile_research(changed,'synthetic_long_short')
        self.assertEqual([row for row in market if row[0]<cutoff],[row for row in later if row[0]<cutoff])
        self.assertEqual({t:v for t,v in exits.items() if t<cutoff},{t:v for t,v in later_exits.items() if t<cutoff})
        result=m.simulate(market,m.Config(family='blend',mode='synthetic_long_short'),
            start=r.START,allowed_families=d.FAMILIES,scheduled_exits=exits)
        self.assertEqual({t['side'] for t in result['trades']},{1,-1})
        self.assertAlmostEqual(result['summary']['ending_equity'],100+sum(t['pnl'] for t in result['trades']))
        self.assertTrue(all(t['entry_ms']==t['signal_ms']+m.BAR for t in result['trades']))

    def test_previous_28_day_channel_resets_only_after_absent_day(self):
        raw=frame(70*96).drop(index=10*96+4)
        cutoff=int(raw.ts.iloc[-1])+m.BAR
        daily=d.daily_features(raw,cutoff)
        self.assertEqual(daily.age.iloc[-1],70)
        self.assertEqual(daily.high28.iloc[29],daily.high.iloc[1:29].max())
        raw=raw[(raw.ts<START+40*m.DAY)|(raw.ts>=START+41*m.DAY)]
        daily=d.daily_features(raw,cutoff)
        after=daily[daily.ts==START+41*m.DAY].iloc[0]
        self.assertEqual(after.age,1)
        self.assertTrue(pd.isna(after.high28))

    def test_full_report_pipeline_keeps_experiment_identity_and_shared_account(self):
        market=[]
        times=[r.START+i*6*3_600_000 for i in range(92*4)]+[r.START+92*m.DAY-m.BAR]
        for i,ts in enumerate(times):
            signals=[m.Signal(family,1,3,.06,None,56*96,ts-m.BAR,100,.02,True,.06)
                for family in d.FAMILIES[:-1]] if i==0 else []
            price=100 if i==0 else 110
            market.append((ts,{'A':((price,price,price,price,0.),signals)}))
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'compile_research',return_value=(market,{},[])),contextlib.redirect_stdout(io.StringIO()):
            summary=d.run({'A':frame(100)},dict(kind='FIXTURE'),[dict(kind='FIXTURE')],tmp)
            self.assertEqual(summary['version'],d.VERSION)
            self.assertEqual(summary['spec'],d.SPEC)
            self.assertEqual(len(summary['reports']),64)
            for row in summary['reports']:
                self.assertIn(row['config']['family'],d.FAMILIES)
                self.assertEqual(row['starting_balance'],100)
                result=json.loads((Path(tmp)/(row['name']+'.json')).read_text())
                self.assertAlmostEqual(row['ending_equity'],100+sum(t['pnl'] for t in result['trades']))
            self.assertEqual((Path(tmp)/'replay-strategy.py').read_bytes(),Path(d.__file__).read_bytes())
            self.assertEqual((Path(tmp)/'replay-runner.py').read_bytes(),Path(r.__file__).read_bytes())

    def test_stress_includes_cash_days_operating_costs_and_separate_fee_cases(self):
        market=[(r.START+i*m.DAY,{'A':((100,100,100,100,0.),[])}) for i in range(20)]
        with tempfile.TemporaryDirectory() as tmp,patch.object(d,'compile_research',return_value=(market,{},[])),contextlib.redirect_stdout(io.StringIO()):
            summary=d.execution_stress({'A':frame(100)},tmp)
            self.assertEqual(len(summary['reports']),12)
            for row in summary['reports']:
                self.assertEqual(row['trades'],0)
                self.assertAlmostEqual(row['ending_equity'],100-row['operating_cost_usd'])
                self.assertEqual(row['by_side']['-1']['pnl'],0)
            running=[v for v in summary['reports'] if v['config']['daily_operating_cost_usd']>0]
            self.assertEqual(len(running),4)
            self.assertTrue(all(v['operating_cost_usd']>1.9 for v in running))


if __name__=='__main__':
    unittest.main()
