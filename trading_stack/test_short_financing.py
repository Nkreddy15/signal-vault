"""Financing timing and accounting fixtures, not broker or market evidence."""
import math
import unittest
from unittest.mock import patch
import multi_strategy_lab as m

START=1772323200000
FOUR_HOURS=4*3_600_000


def market(times,side=-1,price=100):
    return [(ts,{'A':((price,price,price,price,0.),[m.Signal('weekly_leader_28d',side,3,.2,None,56*96,
        ts-m.BAR,None,0,False)] if i==0 else [])}) for i,ts in enumerate(times)]


def run(rows,**changes):
    cfg=m.Config(family='weekly_leader_28d',mode='synthetic_long_short',risk='aggressive',
        spread_bps=0,slippage=0,short_carry_per_day=0,**changes)
    return m.simulate(rows,cfg,allowed_families=('weekly_leader_28d',))


class FinancingTests(unittest.TestCase):
    def test_opening_charge_and_rollover_reconcile_without_double_debit(self):
        result=run(market([START,START+FOUR_HOURS,START+2*FOUR_HOURS]),
            short_opening_fee=.001,short_rollover_per_4h=.002)
        t=result['trades'][0];events=result['financing_events']
        self.assertEqual([e['kind'] for e in events],['OPENING','ROLLOVER','ROLLOVER'])
        self.assertAlmostEqual(t['opening_financing_fee'],t['stake']*.001)
        self.assertAlmostEqual(t['carry'],t['stake']*.004)
        self.assertAlmostEqual(t['pnl'],-t['entry_fee']-t['exit_fee']-t['carry']-t['opening_financing_fee'])
        self.assertAlmostEqual(result['summary']['ending_equity'],100+t['pnl'])
        self.assertAlmostEqual(sum(e['amount_usd'] for e in events),t['opening_financing_fee']+t['carry'])
        self.assertAlmostEqual(result['summary']['short_rollover_fees'],t['carry'])

    def test_first_tick_boundary_and_long_position_are_not_charged(self):
        for ts,expected in [(START+FOUR_HOURS-m.BAR,0),(START+FOUR_HOURS,1)]:
            result=run(market([START,ts]),short_rollover_per_4h=.001)
            self.assertEqual(len(result['financing_events']),expected)
        long=run(market([START,START+2*FOUR_HOURS],side=1),short_opening_fee=.01,short_rollover_per_4h=.01)
        self.assertFalse(long['financing_events'])
        self.assertEqual(long['trades'][0]['carry'],0)
        self.assertEqual(long['summary']['short_opening_fees'],0)

    def test_borrowed_asset_valuation_and_stale_quote_provenance(self):
        rows=market([START,START+FOUR_HOURS])
        rows[1]=(START+FOUR_HOURS,{'A':((90,90,90,90,0.),[])})
        result=run(rows,short_rollover_per_4h=.001)
        fee=result['financing_events'][0]
        self.assertAlmostEqual(fee['amount_usd'],result['trades'][0]['stake']*.9*.001)
        self.assertEqual(fee['quote_ms'],fee['assessed_ms'])
        missing=[rows[0],(START+FOUR_HOURS,{'B':((100,100,100,100,0.),[])})]
        pending=run(missing,short_rollover_per_4h=.001)
        event=pending['financing_events'][0]
        self.assertEqual(event['quote_ms'],START+m.BAR-1)
        self.assertEqual(event['assessed_ms'],START+FOUR_HOURS)
        self.assertEqual(pending['summary']['pending_positions'],1)
        self.assertGreater(pending['summary']['short_rollover_fees'],0)

    def test_feed_gap_assesses_due_ticks_when_observation_returns(self):
        result=run(market([START,START+3*FOUR_HOURS]),short_rollover_per_4h=.001)
        events=result['financing_events']
        self.assertEqual([e['due_ms'] for e in events],[START+i*FOUR_HOURS for i in (1,2,3)])
        self.assertTrue(all(e['assessed_ms']==START+3*FOUR_HOURS for e in events))
        self.assertAlmostEqual(result['summary']['ending_equity'],100+sum(t['pnl'] for t in result['trades']))

    def test_finance_does_not_count_toward_trading_volume_and_legacy_rate_is_preserved(self):
        old=run(market([START,START+FOUR_HOURS]))
        zero=run(market([START,START+FOUR_HOURS]),short_rollover_per_4h=0)
        self.assertEqual(old['summary']['ending_equity'],zero['summary']['ending_equity'])
        # Financing would cross this deliberately small tier if mistakenly
        # added to fill volume. Only the first trade notional precedes exit.
        with patch.dict(m.FEE_PROFILES, {'fixture':((0,.008),(20,.004))}):
            charged=run(market([START,START+3*m.DAY]),fee_profile='fixture',
                short_opening_fee=.001,short_rollover_per_4h=.05)
        t=charged['trades'][0]
        self.assertLess(t['stake'],20)
        self.assertGreater(t['stake']+t['carry']+t['opening_financing_fee'],20)
        self.assertAlmostEqual(t['exit_fee']/t['stake'],.008)
        self.assertEqual(charged['summary']['lowest_taker_fee_pct'],.8)
        self.assertFalse(old['financing_events'])

    def test_invalid_rates_are_rejected(self):
        for k in ['short_opening_fee','short_rollover_per_4h']:
            for value in [-.001,.1,math.nan,math.inf]:
                with self.assertRaisesRegex(ValueError,'financing'):
                    run(market([START,START+m.BAR]),**{k:value})


if __name__=='__main__':
    unittest.main()
