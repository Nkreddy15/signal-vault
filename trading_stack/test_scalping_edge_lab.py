"""Scalping research mechanics; synthetic fixtures are not profit evidence."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import multi_strategy_lab as m
import scalping_edge_lab as s

START=1772323200000


def frame(n=384):
    i=np.arange(n);c=100*np.exp(.025*np.sin(i/5)+.0001*i)
    return pd.DataFrame(dict(ts=START+i*m.BAR,open=c,high=c*1.003,low=c*.997,
        close=c,volume=100.+50*(i%9==0)))


class ScalpingTests(unittest.TestCase):
    def test_causal_features_and_gap_do_not_invent_signals(self):
        raw=frame();_,prefix=s.candidates(raw.iloc[:256]);_,full=s.candidates(raw)
        self.assertEqual(prefix,{t:v for t,v in full.items() if t<START+256*m.BAR})
        changed=raw.copy();changed.loc[256:,['open','high','low','close']]*=9
        self.assertEqual(prefix,{t:v for t,v in s.candidates(changed)[1].items() if t<START+256*m.BAR})
        gapped=raw.drop(index=200);f,signals=s.candidates(gapped)
        self.assertEqual(len(f),len(gapped))
        self.assertFalse(any(START+201*m.BAR<=t<START+264*m.BAR for t in signals))
        market,_=s.compile_research({'A':gapped})
        for ts,rows in market:
            self.assertTrue(all(v.signal_ms==ts-m.BAR for v in rows['A'][1]))

    def test_cost_guard_is_preserved_and_opt_out_records_actual_loss(self):
        sig=m.Signal('scalp_breakout',1,1,.005,.005,4,START-m.BAR,trailing=False)
        market=[(START,{'A':((100,100,100,100,.001),[sig])})]
        guarded=m.simulate(market,m.Config(family='scalp_breakout'),allowed_families=s.FAMILIES)
        self.assertEqual(guarded['summary']['trades'],0)
        charged=m.simulate(market,m.Config(family='scalp_breakout',allow_subcost_targets=True),allowed_families=s.FAMILIES)
        self.assertEqual(charged['summary']['trades'],1)
        self.assertLess(charged['trades'][0]['pnl'],0)
        self.assertAlmostEqual(charged['summary']['ending_equity'],100+charged['trades'][0]['pnl'])

    def test_control_really_compiles_high_frequency_but_blend_excludes_it(self):
        market,_=s.compile_research({'A':frame(),'B':frame()})
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            summary=s.run({'A':frame(),'B':frame()},{},[],tmp)
            self.assertEqual(len(summary['reports']),60)
            control=json.loads((Path(tmp)/'turnover_control-zero_cost_control-trigger-cost0.json').read_text())
            self.assertGreaterEqual(control['frequency']['max_entries_in_utc_day'],100)
            self.assertTrue(all(t['family']=='turnover_control' for t in control['trades']))
            blended=json.loads((Path(tmp)/'blend-zero_cost_control-trigger-cost0.json').read_text())
            self.assertFalse(any(t['family']=='turnover_control' for t in blended['trades']))
            for row in summary['reports']:
                self.assertFalse(row['activation_eligible'])
                report=json.loads((Path(tmp)/(row['name']+'.json')).read_text())
                self.assertAlmostEqual(row['ending_equity'],100+sum(t['pnl'] for t in report['trades'])-row['operating_cost_usd'])
                self.assertLessEqual(row['max_reserved_notional'],.8*row['peak_equity']+1e-8)

    def test_capital_parameter_replays_shared_cash_instead_of_scaling_profit(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            summary=s.run({'A':frame(),'B':frame()},{},[],tmp,starting_balance=500)
            self.assertEqual(summary['starting_balance'],500)
            for row in summary['reports']:
                report=json.loads((Path(tmp)/(row['name']+'.json')).read_text())
                self.assertEqual(row['starting_balance'],500)
                self.assertAlmostEqual(row['ending_equity'],500+sum(t['pnl'] for t in report['trades'])-row['operating_cost_usd'])
                self.assertFalse(row['activation_eligible'])


if __name__=='__main__': unittest.main()
