"""Fixed bear-rule timing and financing fixtures, not market returns."""
from types import SimpleNamespace
import unittest

import bear_regime_lab as b
import multi_strategy_lab as m
import regime_swing_lab as r
from test_multi_strategy_lab import START,frame


class BearTests(unittest.TestCase):
    def rows(self):
        fields=dict(age=50,volume=100,r7=-.05,r28=-.2,ema21=110,close=100,
            volatility=.02,atr=.02,stop=.06,prev_close=102,rebound2=.04,low7=101)
        return {p:SimpleNamespace(**fields) for p in ['BTC/USD','ETH/USD']}

    def test_closed_btc_gate_and_failed_rebound_conditions(self):
        rows=self.rows()
        monday=1772409600000
        choices=b.decisions(rows,monday)
        self.assertEqual(set(choices['failed_rebound'][0]),{'BTC/USD','ETH/USD'})
        self.assertEqual(set(choices['bear_channel7'][0]),{'BTC/USD','ETH/USD'})
        rows['ETH/USD'].rebound2=.02
        self.assertNotIn('ETH/USD',b.decisions(rows,monday)['failed_rebound'][0])
        rows['BTC/USD'].close=120
        off=b.decisions(rows,monday)
        self.assertTrue(all(not entries and not desired for entries,desired in off.values()))

    def test_weekly_hold_is_retained_between_reviews_and_gate_failure_exits_daily(self):
        rows=self.rows()
        monday=1772409600000
        self.assertIn('bear_gate_weekly',b.decisions(rows,monday))
        self.assertNotIn('bear_gate_weekly',b.decisions(rows,monday+m.DAY))
        rows['BTC/USD'].r28=-.01
        self.assertEqual(b.decisions(rows,monday+m.DAY)['bear_gate_weekly'],({},{}))

    def test_actual_compilation_is_causal_and_only_includes_supported_short_assets(self):
        raw=frame(90*96)
        bear=raw.copy()
        bear['open'],bear['high'],bear['low'],bear['close']=10000/raw.open,10000/raw.low,10000/raw.high,10000/raw.close
        frames={'BTC/USD':bear,'ETH/USD':bear.copy(),'TAO/USD':raw}
        market,exits,_,pairs=b.compile_research(frames)
        self.assertEqual(set(pairs),{'BTC/USD','ETH/USD'})
        signals=[s for ts,rows in market for bar,candidates in rows.values() for s in candidates]
        self.assertTrue(signals)
        self.assertTrue(all(s.side==-1 and s.target is None for s in signals))
        cutoff=START+70*m.DAY
        changed={p:raw.copy() for p,raw in frames.items()}
        for raw in changed.values():
            raw.loc[raw.ts>=cutoff,['open','high','low','close']]*=10
        later,other,_,_=b.compile_research(changed)
        self.assertEqual([row for row in market if row[0]<cutoff],[row for row in later if row[0]<cutoff])
        self.assertEqual({t:v for t,v in exits.items() if t<cutoff},{t:v for t,v in other.items() if t<cutoff})
        result=m.simulate(market,m.Config(family='bear_gate_weekly',risk='aggressive',mode='synthetic_long_short',
            short_carry_per_day=0,short_opening_fee=.0001,short_rollover_per_4h=.0001),
            start=r.START,allowed_families=b.FAMILIES,scheduled_exits=exits)
        self.assertTrue(result['trades'])
        self.assertAlmostEqual(result['summary']['ending_equity'],100+sum(t['pnl'] for t in result['trades']))


if __name__=='__main__':
    unittest.main()
