"""Mechanics and chronology fixtures, never evidence of market profitability."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import multi_strategy_lab as m
import regime_swing_lab as r
from test_multi_strategy_lab import START,frame


def sig(ts=START-m.BAR,side=1):
    return m.Signal('leader_7d',side,3,.06,None,28*96,ts,100,.02,True,.06)


class RegimeTests(unittest.TestCase):
    def test_complete_days_and_gap_reset(self):
        f=frame(65*96)
        daily=r.daily_features(f)
        self.assertEqual(len(daily),65)
        cut=f.drop(index=40*96+5)
        changed=r.daily_features(cut,strict_intervals=True)
        self.assertEqual(len(changed),64)
        after=changed[changed.ts==START+41*m.DAY].iloc[0]
        self.assertEqual(after.age,1)
        self.assertTrue(np.isnan(after.r28))
        prefix=r.daily_features(f.iloc[:50*96+30])
        pd.testing.assert_frame_equal(prefix,daily.iloc[:50])

    def test_rank_buffer_retains_four_but_enters_two(self):
        rows={p:SimpleNamespace(age=40,volume=100,r7=.08-i*.01,r28=.15,
            atr=.02,volatility=.02,close=100,ema21=95) for i,p in enumerate('ABCDE')}
        entries,desired=r.rank_day(rows,'leader_7d','long_only')
        self.assertEqual(set(entries),{'A','B'})
        self.assertEqual(set(desired),{'A','B','C','D'})
        self.assertTrue(all(side==1 for side in desired.values()))

    def test_long_short_compilation_and_future_price_invariance(self):
        f=frame(90*96)
        bearish=f.copy()
        bearish['open']=10000/f.open
        bearish['high']=10000/f.low
        bearish['low']=10000/f.high
        bearish['close']=10000/f.close
        frames={'AAA/USD':f,'BBB/USD':bearish}
        market,exits,receipts=r.compile_research(frames,'synthetic_long_short')
        candidates=[s for ts,rows in market for bar,signals in rows.values() for s in signals]
        self.assertTrue(any(s.side==1 for s in candidates))
        self.assertTrue(any(s.side==-1 for s in candidates))
        self.assertTrue(all(s.target is None and s.trailing_distance==s.stop for s in candidates))
        self.assertTrue(all(s.signal_ms%m.DAY==m.DAY-m.BAR for s in candidates))
        cutoff=START+70*m.DAY
        changed={pair:raw.copy() for pair,raw in frames.items()}
        for raw in changed.values():
            raw.loc[raw.ts>=cutoff,['open','high','low','close']]*=10
        later,other_exits,other_receipts=r.compile_research(changed,'synthetic_long_short')
        self.assertEqual([row for row in market if row[0]<cutoff],
            [row for row in later if row[0]<cutoff])
        self.assertEqual([row for row in receipts if row['entry_ms']<cutoff],
            [row for row in other_receipts if row['entry_ms']<cutoff])
        self.assertEqual({ts:v for ts,v in exits.items() if ts<cutoff},
            {ts:v for ts,v in other_exits.items() if ts<cutoff})
        long,_,_=r.compile_research(frames,'long_only')
        self.assertTrue(all(s.side==1 for ts,rows in long for bar,signals in rows.values() for s in signals))

    def test_unmocked_compilation_reconciles_both_sides(self):
        raw=frame(90*96)
        bear=raw.copy()
        bear['open'],bear['high'],bear['low'],bear['close']=10000/raw.open,10000/raw.low,10000/raw.high,10000/raw.close
        market,exits,_=r.compile_research({'UP':raw,'DOWN':bear},'synthetic_long_short')
        result=m.simulate(market,m.Config(family='blend',mode='synthetic_long_short'),
            start=r.START,allowed_families=r.FAMILIES,scheduled_exits=exits)
        self.assertTrue(any(t['side']==1 for t in result['trades']))
        self.assertTrue(any(t['side']==-1 for t in result['trades']))
        self.assertEqual(result['summary']['pending_positions'],0)
        self.assertAlmostEqual(result['summary']['ending_equity'],100+sum(t['pnl'] for t in result['trades']))
        self.assertTrue(all(t['entry_ms']==t['signal_ms']+m.BAR for t in result['trades']))

    def test_scheduled_exits_free_capacity_before_new_entries(self):
        pairs=['A','B','C']
        first={pair:((100,100,100,100,0.),[sig()]) for pair in pairs}
        second={pair:((100,100,100,100,0.),[]) for pair in pairs}
        second['D']=((100,100,100,100,0.),[sig(START)])
        exits={START+m.BAR:{pair:{'leader_7d':(START,'RANK_EXIT',0)} for pair in pairs}}
        result=m.simulate([(START,first),(START+m.BAR,second)],
            m.Config(family='leader_7d',starting_balance=150),allowed_families=r.FAMILIES,scheduled_exits=exits)
        self.assertEqual(sum(t['reason']=='RANK_EXIT' for t in result['trades']),3)
        self.assertEqual(next(t for t in result['trades'] if t['pair']=='D')['entry_ms'],START+m.BAR)
        self.assertAlmostEqual(result['summary']['ending_equity'],150+sum(t['pnl'] for t in result['trades']))

    def test_missing_quote_keeps_exit_pending(self):
        market=[(START,{'A':((100,100,100,100,0.),[sig()])}),
            (START+m.BAR,{'B':((100,100,100,100,0.),[])}),
            (START+2*m.BAR,{'A':((110,110,110,110,0.),[])})]
        exits={START+m.BAR:{'A':{'leader_7d':(START,'RANK_EXIT',0)}}}
        result=m.simulate(market,m.Config(family='leader_7d'),allowed_families=r.FAMILIES,scheduled_exits=exits)
        trade=result['trades'][0]
        self.assertEqual(trade['exit_ms'],START+2*m.BAR)
        self.assertEqual(trade['exit_signal_ms'],START)
        self.assertEqual(trade['reason'],'RANK_EXIT')
        missing=m.simulate(market[:2],m.Config(family='leader_7d'),allowed_families=r.FAMILIES,scheduled_exits=exits)
        self.assertEqual(missing['summary']['pending_positions'],1)
        self.assertEqual(missing['summary']['trades'],0)
        entire_feed_gap=m.simulate([market[0],market[2]],m.Config(family='leader_7d'),
            allowed_families=r.FAMILIES,scheduled_exits=exits)
        self.assertEqual(entire_feed_gap['trades'][0]['reason'],'RANK_EXIT')
        self.assertEqual(entire_feed_gap['trades'][0]['exit_ms'],START+2*m.BAR)

    def test_strict_policy_excludes_sparse_days_but_retains_market(self):
        raw=frame(40*96).drop(index=np.arange(0,40*96,96))
        daily=r.daily_features(raw)
        self.assertEqual(len(daily),40)
        market,exits,receipts=r.compile_research({'SPARSE':raw},'long_only')
        self.assertEqual(len(market),len(raw))
        strict,_,_=r.compile_research({'SPARSE':raw},'long_only',strict_intervals=True)
        self.assertFalse(any(signals for ts,rows in strict for bar,signals in rows.values()))

    def test_archive_no_trade_intervals_preserve_calendar_history_without_fabricated_quotes(self):
        full=frame(65*96)
        sparse=full.drop(index=[10*96+4,20*96+95,25*96,30*96+2])
        observed=r.daily_features(sparse)
        self.assertEqual(len(observed),65)
        self.assertEqual(observed.age.iloc[-1],65)
        self.assertEqual(observed['count'].sum(),len(sparse))
        day_rows=sparse[(sparse.ts>=START+10*m.DAY)&(sparse.ts<START+11*m.DAY)]
        self.assertEqual(observed[observed.ts==START+10*m.DAY]['volume'].iloc[0],day_rows.volume.sum())
        self.assertEqual(r.daily_features(sparse.iloc[:-1]).ts.iloc[-1],START+63*m.DAY)
        missing_day=sparse[(sparse.ts<START+40*m.DAY)|(sparse.ts>=START+41*m.DAY)]
        changed=r.daily_features(missing_day)
        self.assertEqual(changed[changed.ts==START+41*m.DAY].age.iloc[0],1)
        market,_,_=r.compile_research({'SPARSE':sparse},'long_only')
        self.assertEqual([t for t,rows in market],list(sparse.ts))

    def test_exit_instruction_rejects_current_or_future_candle(self):
        with self.assertRaisesRegex(ValueError,'previous closed'):
            m.simulate([(START,{'A':((100,100,100,100,0.),[sig()])})],
                m.Config(family='leader_7d'),allowed_families=r.FAMILIES,
                scheduled_exits={START:{'A':{'leader_7d':(START,'RANK_EXIT',0)}}})

    def test_no_fixed_target_and_daily_trailing_distance(self):
        self.assertIsNone(m.bar_exit(dict(side=1,stop_price=94,target_price=None),
            (100,1000,99,500,0.),m.Config(spread_bps=0,slippage=0)))
        result=m.simulate([(START,{'A':((100,110,100,110,.001),[sig()])}),
            (START+m.BAR,{'A':((110,111,109,110,.001),[])})],
            m.Config(family='leader_7d',spread_bps=0,slippage=0),allowed_families=r.FAMILIES)
        trade=result['trades'][0]
        self.assertEqual(trade['reason'],'WINDOW_END')
        self.assertAlmostEqual(trade['stop_price'],111*.94)
        self.assertIsNone(trade['target_price'])

    def test_exit_route_matches_original_family_and_side(self):
        market=[(START,{'A':((100,100,100,100,0.),[sig()])}),
            (START+m.BAR,{'A':((100,100,100,100,0.),[])})]
        routes={START+m.BAR:{'A':{'channel_7d':(START,'CHANNEL_EXIT',0),
            'leader_7d':(START,'RANK_EXIT',1)}}}
        result=m.simulate(market,m.Config(family='leader_7d'),allowed_families=r.FAMILIES,scheduled_exits=routes)
        self.assertEqual(result['trades'][0]['reason'],'WINDOW_END')

    def test_full_matrix_writes_64_separate_accounts_and_reports(self):
        first=r.START
        market=[]
        timestamps=[first+i*6*3_600_000 for i in range(92*4)]+[first+92*m.DAY-m.BAR]
        for i,ts in enumerate(timestamps):
            signals=[m.Signal(family,1,3,.06,None,28*96,ts-m.BAR,100,.02,True,.06)
                for family in r.FAMILIES[:-1]] if i==0 else []
            price=100 if i==0 else 110
            market.append((ts,{'A':((price,price,price,price,0.),signals)}))
        with tempfile.TemporaryDirectory() as out,patch.object(r,'compile_research',return_value=(market,{},[])),\
                contextlib.redirect_stdout(io.StringIO()):
            summary=r.run({'A':frame(100)},dict(selected=[dict(pair='A')]),[dict(kind='TEST_FIXTURE')],out)
            self.assertEqual(len(summary['reports']),64)
            self.assertTrue(all(row['starting_balance']==100 for row in summary['reports']))
            self.assertIsNone(summary['profit_ceiling'])
            self.assertEqual(len(list(Path(out).glob('*-trades.csv'))),64)
            saved=json.loads((Path(out)/'regime-summary.json').read_text())
            self.assertEqual(saved['status'],'DEVELOPMENT_ONLY_NO_ACTIVATION')
            self.assertTrue((Path(out)/'regime-results.md').exists())


if __name__=='__main__':
    unittest.main(verbosity=2)
