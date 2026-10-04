"""Offline behavioral checks for the paper release. Never submits orders."""
import importlib.util
import json
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'crypto'))
sys.path.insert(0, str(ROOT / 'dashboard'))
import paper_final as m
import paper_final_view as view
import app as web

NOW = 1_791_000_120_000 // m.HOUR * m.HOUR + 60_000


def quotes(price=100, now=NOW):
    return {p: dict(bid=price, ask=price+0.1, observed_ms=now) for p in m.PAIRS}


class PublicFeed:
    def __init__(self, now=NOW):
        self.now = now
        self.candle_calls = 0
    def fetch_tickers(self, pairs):
        return {p: dict(bid=100.0, ask=100.1) for p in pairs}
    def fetch_ohlcv(self, pair, timeframe, limit):
        self.candle_calls += 1
        end = self.now // m.HOUR * m.HOUR
        return [[end - (299-i)*m.HOUR, 100, 101, 99, 100, 10] for i in range(300)]


class PaperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = m.Ledger(self.root / 'ledger.sqlite3', NOW)
        self.frames, _, self.closed = m.validated_frames(PublicFeed(), NOW)
        self.q = quotes()
    def tearDown(self):
        self.ledger.db.close()
        self.tmp.cleanup()
    def enter(self):
        self.ledger.state['boundary'] = self.closed - m.HOUR
        with patch.object(m, 'btc_bear', return_value=True), patch.object(m, 'pair_bear', return_value=True), patch.object(m, 'breakdown', return_value=True):
            m.evaluate(self.ledger, self.frames, self.q, self.closed, NOW)

    def test_first_scan_does_not_backfill(self):
        with patch.object(m, 'btc_bear', return_value=True), patch.object(m, 'pair_bear', return_value=True), patch.object(m, 'breakdown', return_value=True):
            m.evaluate(self.ledger, self.frames, self.q, self.closed, NOW)
        self.assertEqual(self.ledger.state['entries'], 0)
        self.assertEqual(len(self.ledger.state['diagnostics']), 6)

    def test_cap_and_no_duplicate_after_restart(self):
        self.enter()
        self.assertEqual(self.ledger.state['entries'], 3)
        self.assertEqual(sum(p['stake_amount'] for p in self.ledger.state['positions'].values()), 45)
        resumed = m.Ledger(self.root / 'ledger.sqlite3', NOW+1000)
        try:
            m.evaluate(resumed, self.frames, self.q, self.closed, NOW+1000)
            self.assertEqual(resumed.state['entries'], 3)
            self.assertEqual(resumed.state['deadline_ms'], NOW+8*m.HOUR)
            self.assertEqual(resumed.db.execute("SELECT count(*) FROM events WHERE payload LIKE '%\"kind\": \"OPEN\"%'").fetchone()[0], 3)
        finally:
            resumed.db.close()

    def test_short_uses_ask_and_cost_once(self):
        self.enter()
        pair = next(iter(self.ledger.state['positions']))
        m.close(self.ledger, pair, dict(ask=90), NOW+60_000, 'TEST')
        expected = 15 * (0.10 - 0.0074)
        self.assertAlmostEqual(self.ledger.state['balance'], 100+expected)
        self.assertAlmostEqual(self.ledger.state['closed'][0]['profit_abs'], expected)
        self.assertFalse(self.ledger.state['closed'][0]['is_open'])

    def test_gap_stop_closes_at_observed_price(self):
        self.enter()
        m.manage(self.ledger, quotes(110), NOW+60_000)
        self.assertFalse(self.ledger.state['positions'])
        self.assertEqual(self.ledger.state['halt_reason'], 'SESSION_LOSS_LIMIT')
        self.assertTrue(all(p['close_rate'] == 110.1 for p in self.ledger.state['closed']))

    def test_session_end_closes_and_cannot_reenter(self):
        self.enter()
        now = NOW+8*m.HOUR
        m.manage(self.ledger, quotes(now=now), now)
        self.assertFalse(self.ledger.state['positions'])
        self.assertEqual(self.ledger.state['halt_reason'], 'SESSION_COMPLETE')
        self.enter()
        self.assertFalse(self.ledger.state['positions'])

    def test_insufficient_unreserved_balance(self):
        self.ledger.state['balance'] = 20
        self.enter()
        self.assertEqual(len(self.ledger.state['positions']), 1)

    def test_wide_spread_skips_entry(self):
        for q in self.q.values(): q['ask'] = 105
        self.enter()
        self.assertEqual(self.ledger.state['entries'], 0)

    def test_late_signal_not_filled(self):
        self.ledger.state['boundary'] = self.closed-m.HOUR
        with patch.object(m, 'btc_bear', return_value=True), patch.object(m, 'pair_bear', return_value=True), patch.object(m, 'breakdown', return_value=True):
            m.evaluate(self.ledger, self.frames, self.q, self.closed, NOW+11*60_000)
        self.assertEqual(self.ledger.state['entries'], 0)

    def test_stale_nonfinite_and_crossed_quotes_rejected(self):
        for bad in [dict(bid=100, ask=101, timestamp=NOW-100_000), dict(bid=float('nan'), ask=101), dict(bid=102, ask=101)]:
            ticks = PublicFeed().fetch_tickers(m.PAIRS)
            ticks['BTC/USD'] = bad
            with self.assertRaises(ValueError): m.validate_quotes(ticks, NOW)

    def test_unclosed_candle_excluded_and_gap_rejected(self):
        self.assertEqual(int(self.frames['BTC/USD'].ts.iloc[-1]), self.closed)
        feed = PublicFeed()
        original = feed.fetch_ohlcv
        feed.fetch_ohlcv = lambda *args, **kw: original(*args, **kw)[1:140]+original(*args, **kw)[141:]
        with self.assertRaisesRegex(ValueError, 'missing or duplicate'): m.validated_frames(feed, NOW)

    def test_stop_survives_candle_download_failure(self):
        self.enter()
        feed = PublicFeed()
        feed.fetch_tickers = lambda _: {p: dict(bid=105, ask=105.1) for p in m.PAIRS}
        feed.fetch_ohlcv = lambda *a, **kw: (_ for _ in ()).throw(OSError('offline candles'))
        runner = m.Runner(self.ledger, self.root, feed)
        with patch.object(m.time, 'time', return_value=NOW/1000): s = runner.cycle()
        self.assertFalse(self.ledger.state['positions'])
        self.assertEqual(s['status'], 'DEGRADED')
        self.assertEqual(len(self.ledger.state['closed']), 3)

    def test_candles_cached_and_scan_not_duplicated(self):
        feed = PublicFeed()
        runner = m.Runner(self.ledger, self.root, feed)
        with patch.object(m.time, 'time', return_value=NOW/1000):
            runner.cycle()
            runner.cycle()
        self.assertEqual(feed.candle_calls, 6)
        self.assertEqual(self.ledger.state['entries'], 0)
        self.assertEqual(self.ledger.state['cycles'], 2)

    def test_failed_network_does_not_claim_success(self):
        feed = PublicFeed()
        feed.fetch_tickers = lambda _: (_ for _ in ()).throw(OSError('offline'))
        runner = m.Runner(self.ledger, self.root, feed)
        with patch.object(m.time, 'time', return_value=NOW/1000): s = runner.cycle()
        self.assertEqual(s['status'], 'DEGRADED')
        self.assertIsNone(s['last_success_ms'])

    def test_corrupt_ledger_is_not_reset(self):
        self.ledger.db.execute("UPDATE state SET payload='broken' WHERE id=1")
        self.ledger.db.commit()
        with self.assertRaises(ValueError): m.Ledger(self.root/'ledger.sqlite3', NOW)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = patch.object(view, 'ROOT', self.root)
        self.patch.start()
        self.client = web.app.test_client()
    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def sample(self):
        ledger = m.Ledger(self.root/'ledger.sqlite3', NOW)
        try:
            ledger.state.update(status='RUNNING', last_success_ms=int(time.time()*1000), heartbeat_ms=int(time.time()*1000))
            m.publish(ledger, self.root, {}, int(time.time()*1000))
        finally: ledger.db.close()
        (self.root/'activated').touch()

    def test_latest_and_v1_ledgers_stay_separate(self):
        self.sample()
        def freq(path, params=None):
            return ({'strategy':'V1','state':'RUNNING'} if path=='show_config' else {'profit_closed_coin':7} if path=='profit' else [], None)
        with patch.object(web, '_freq', side_effect=freq), patch.object(web, '_alpaca', return_value=({}, None)):
            data = self.client.get('/api/snapshot').get_json()
            self.assertEqual(data['crypto']['closed_pnl_usd'], 0)
            self.assertEqual(data['legacy_crypto']['closed_pnl_usd'], 7)
            legacy = self.client.get('/api/snapshot?engine=v1').get_json()
            self.assertEqual(legacy['crypto']['closed_pnl_usd'], 7)

    def test_stale_and_missing_summary(self):
        self.assertEqual(view.summary()['status'], 'UNAVAILABLE')
        self.sample()
        with patch.object(view.time, 'time', return_value=time.time()+300):
            self.assertEqual(view.summary()['crypto']['bot_state'], 'STALE')

    def test_candle_route_and_page_render(self):
        self.sample()
        m.atomic_json(self.root/'candles.json', dict(pairs={'BTC/USD':[dict(time='2026-10-03',open=100,high=101,low=99,close=100,volume=10)]}))
        data=self.client.get('/api/candles?pair=BTC/USD&timeframe=1h').get_json()
        self.assertEqual(len(data['candles']),1)
        self.assertEqual(self.client.get('/').status_code,200)


if __name__=='__main__': unittest.main(verbosity=2)
