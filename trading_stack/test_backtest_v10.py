"""Backtest mechanics tests; fixture outcomes are not market performance."""
import contextlib
import io
import json
import unittest
import pandas as pd
import test_v10 as t
import backtest_v10 as b


class ReplayTests(unittest.TestCase):
    def test_date_column_resolutions_produce_identical_millisecond_candles(self):
        f=pd.DataFrame(t.prices(count=180),columns=['ts','open','high','low','close','volume'])
        expected=b.prepare(f,'BTC/USD')
        for unit in ['s','ms','us','ns']:
            with self.subTest(unit=unit):
                dated=f.drop(columns='ts').copy()
                dated['date']=pd.to_datetime(f.ts,unit='ms',utc=True).astype(
                    f'datetime64[{unit}, UTC]')
                pd.testing.assert_frame_equal(b.prepare(dated,'BTC/USD'),expected)

    def test_duplicate_dates_are_still_rejected(self):
        f=pd.DataFrame(t.prices(count=180),columns=['ts','open','high','low','close','volume'])
        f['date']=pd.to_datetime(f.pop('ts'),unit='ms',utc=True).astype('datetime64[s, UTC]')
        f.loc[1,'date']=f.loc[0,'date']
        with self.assertRaisesRegex(ValueError,'duplicate candles'):
            b.prepare(f,'BTC/USD')

    def test_causal_fills_costs_and_independent_accounting(self):
        frames={p:b.prepare(pd.DataFrame(t.prices(1 if i<3 else -1,count=360),
            columns=['ts','open','high','low','close','volume']),p) for i,p in enumerate(t.m.PAIRS)}
        with contextlib.redirect_stdout(io.StringIO()):
            result=b.replay(frames,5)
        self.assertGreater(result['summary']['trades'],0)
        self.assertGreater(result['summary']['long_trades'],0)
        self.assertGreater(result['summary']['short_trades'],0)
        for trade in result['trades']:
            opened=pd.Timestamp(trade['open_date']).value//1_000_000
            self.assertEqual(opened,trade['signal_ms']+t.m.BAR)
            gross=(trade['close_rate']/trade['open_rate']-1)*(-1 if trade['is_short'] else 1)
            fee=t.m.SPEC['taker_fee_per_side']*(1+trade['close_rate']/trade['open_rate'])
            expected=trade['stake_amount']*(gross-fee-2*t.m.SPEC['slippage_per_side'])
            self.assertAlmostEqual(trade['profit_abs'],expected)
        self.assertAlmostEqual(sum(x['profit_abs'] for x in result['trades']),
            result['summary']['summed_independent_session_pnl_usd'])
        self.assertTrue(all(s['starting_balance']==100 for s in result['sessions']))
        json.dumps(result,allow_nan=False)

    def test_missing_candles_are_preserved_not_filled(self):
        f=pd.DataFrame(t.prices(count=360),columns=['ts','open','high','low','close','volume']).drop(index=200)
        out=b.prepare(f,'BTC/USD')
        self.assertEqual(len(out),359)
        self.assertEqual(int(out.block_age.iloc[200]),1)

    def test_invalid_data_is_rejected(self):
        f=pd.DataFrame(t.prices(count=360),columns=['ts','open','high','low','close','volume'])
        f.loc[20,'low']=-1
        with self.assertRaises(ValueError):b.prepare(f,'BTC/USD')


if __name__=='__main__':
    unittest.main(verbosity=2)
