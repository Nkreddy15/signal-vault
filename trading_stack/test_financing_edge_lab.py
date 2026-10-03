"""Policy/matrix fixtures; no fixture return is market evidence."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import financing_edge_lab as f
import multi_strategy_lab as m
import regime_swing_lab as r
from test_multi_strategy_lab import frame


class FinancingLabTests(unittest.TestCase):
    def test_eligibility_is_applied_before_ranking_and_only_short_entries_survive(self):
        now=r.START
        signals=[m.Signal('weekly_leader_28d',side,3,.2,None,96,now-m.BAR) for side in (1,-1)]
        base=[(now,{'BTC/USD':((100,100,100,100,0.),signals)})]
        with patch.object(f.d,'compile_research',return_value=(base,{},[])) as compile_fn:
            market,_,_,pairs=f.compile_research({'BTC/USD':frame(100),'TAO/USD':frame(100)},
                'current_us_supported_sensitivity','short_only')
            self.assertEqual(set(compile_fn.call_args.args[0]),{'BTC/USD'})
            self.assertEqual(pairs,['BTC/USD'])
            self.assertEqual([s.side for s in market[0][1]['BTC/USD'][1]],[-1])

    def test_complete_matrix_reconciles_and_zero_cost_does_not_duplicate_cases(self):
        times=[r.START+i*6*3_600_000 for i in range(92*4)]+[r.START+92*m.DAY-m.BAR]
        market=[(ts,{'BTC/USD':((100,100,100,100,0.),
            [m.Signal('weekly_leader_28d',-1,3,.2,None,56*96,ts-m.BAR,None,0,False)] if i==0 else [])})
            for i,ts in enumerate(times)]
        with tempfile.TemporaryDirectory() as tmp,patch.object(f,'compile_research',return_value=(market,{},[],['BTC/USD'])),contextlib.redirect_stdout(io.StringIO()):
            summary=f.run({'BTC/USD':frame(100)},dict(kind='FIXTURE'),[],tmp)
            self.assertEqual(len(summary['reports']),128)
            self.assertEqual(len(set(row['name'] for row in summary['reports'])),128)
            for row in summary['reports']:
                self.assertFalse(row['activation_eligible'])
                result=json.loads((Path(tmp)/(row['name']+'.json')).read_text())
                self.assertAlmostEqual(row['ending_equity'],100+sum(t['pnl'] for t in result['trades'])-row['operating_cost_usd'])
                self.assertAlmostEqual(sum(v['amount_usd'] for v in result['financing_events']),
                    row['short_opening_fees']+row['short_rollover_fees'])
            fewer=f.run({'BTC/USD':frame(100)},dict(kind='FIXTURE'),[],tmp,daily_cost=0)
            self.assertEqual(len(fewer['reports']),64)
            self.assertEqual(len(set(row['name'] for row in fewer['reports'])),64)


if __name__=='__main__':
    unittest.main()
