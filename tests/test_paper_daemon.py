import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from signal_vault.paper_daemon import StopFlag, run_loop
from signal_vault.paper_runtime import PaperCycleResult
from signal_vault.paper_store import PersistentPaperOrderStore


class FakeRunner:
    def __init__(self, states):
        self.states = iter(states)
        self.calls = []

    def run_once(self, *, now, allow_paper_submission=False):
        self.calls.append((now, allow_paper_submission))
        return PaperCycleResult(next(self.states), "test")


class RaisingRunner:
    def run_once(self, *, now, allow_paper_submission=False):
        raise RuntimeError("provider body contains SECRET")


class PaperDaemonTests(unittest.TestCase):
    def test_loop_writes_health_and_uses_policy_sleep(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            health = root / "health.json"
            sleeps = []
            now = datetime(2026, 9, 28, 22, 37, 10, tzinfo=timezone.utc)
            with PersistentPaperOrderStore(root / "paper.db") as store:
                runner = FakeRunner(["HOLD", "HOLD_BAD_MARKET_DATA"])
                results = run_loop(runner=runner, store=store, allow_submission=False,
                                   health_path=health, stop=StopFlag(), clock=lambda: now,
                                   sleeper=sleeps.append, max_cycles=2)
            self.assertEqual([x.state for x in results], ["HOLD", "HOLD_BAD_MARKET_DATA"])
            self.assertEqual(len(sleeps), 1)
            self.assertEqual(sleeps[0], 1378.0)
            self.assertIn('"state":"HOLD_BAD_MARKET_DATA"', health.read_text())
            self.assertFalse(runner.calls[0][1])


    def test_unexpected_cycle_failure_is_secret_free_and_stops(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            now = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)
            stop = StopFlag()
            with PersistentPaperOrderStore(root / "paper.db") as store:
                results = run_loop(runner=RaisingRunner(), store=store, allow_submission=False,
                                   health_path=root / "health.json", stop=stop, clock=lambda: now,
                                   sleeper=lambda _: self.fail("must not sleep after fatal runtime fault"))
            self.assertTrue(stop.requested)
            self.assertEqual(results[-1].state, "BLOCKED_RUNTIME_EXCEPTION")
            self.assertNotIn("SECRET", (root / "health.json").read_text())

    def test_loop_passes_explicit_paper_submission_authority(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            now = datetime(2026, 9, 28, 22, 0, tzinfo=timezone.utc)
            with PersistentPaperOrderStore(root / "paper.db") as store:
                runner = FakeRunner(["HOLD"])
                run_loop(runner=runner, store=store, allow_submission=True,
                         health_path=root / "health.json", stop=StopFlag(), clock=lambda: now,
                         sleeper=lambda _: None, max_cycles=1)
            self.assertTrue(runner.calls[0][1])
