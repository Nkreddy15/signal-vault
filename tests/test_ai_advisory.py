"""Fake-only advisory tests. Never fetches network or gives an AI broker tools."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from signal_vault.ai_advisory import BoundedAdvisoryGate, build_public_signal_frame
from signal_vault.market_data import CryptoQuote
from signal_vault.strategy import Action, StrategySignal

NOW = datetime(2026, 9, 28, 20, tzinfo=timezone.utc)


def signal(**changes):
    return replace(StrategySignal(Action.BUY, "a" * 64, NOW.isoformat(), Decimal("65001"),
                                  Decimal("65000"), "not sent to model", "btc-hourly-v1"), **changes)


def quote(**changes):
    return replace(CryptoQuote("BTC/USD", Decimal("69990"), Decimal("70010"), NOW), **changes)


class AdvisorySafetyTests(unittest.TestCase):
    def test_public_frame_contains_only_whitelisted_features(self):
        frame = build_public_signal_frame(signal(), quote())
        self.assertEqual(frame["candidate_action"], "buy")
        self.assertNotIn("account", str(frame).lower())
        self.assertNotIn("api_key", str(frame).lower())
        self.assertNotIn("not sent to model", str(frame))
        self.assertEqual(len(frame["strategy_evidence_sha256"]), 64)

    def test_no_objection_does_not_execute_orders(self):
        seen = []
        gate = BoundedAdvisoryGate(lambda frame: (seen.append(frame) or {
            "verdict": "NO_OBJECTION", "reason_code": "TREND_CONFIRMED"}))
        result = gate.review(signal=signal(), quote=quote())
        self.assertTrue(result.continue_to_guardian)
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(result.evidence_hash), 64)

    def test_invalid_or_tool_call_response_fails_closed(self):
        for reply in ({"verdict": "BUY", "reason_code": "TREND_CONFIRMED"},
                      {"verdict": "NO_OBJECTION", "reason_code": "NO_EDGE"},
                      {"verdict": "NO_OBJECTION", "reason_code": "TREND_CONFIRMED", "withdraw": True},
                      "just buy please", None):
            with self.subTest(reply=reply):
                result = BoundedAdvisoryGate(lambda _: reply).review(signal=signal(), quote=quote())
                self.assertFalse(result.continue_to_guardian)

    def test_model_unavailable_holds_and_does_not_leak_exception(self):
        def broken(_): raise RuntimeError("private provider credential must not be echoed")
        result = BoundedAdvisoryGate(broken).review(signal=signal(), quote=quote())
        self.assertEqual(result.verdict, "HOLD")
        self.assertEqual(result.reason_code, "ADVISOR_UNAVAILABLE")
        self.assertNotIn("credential", repr(result))

    def test_negative_quotes_nan_and_unqualified_evidence_rejected(self):
        for modified in (quote(bid=Decimal("NaN")), quote(ask=Decimal("0")),
                         quote(symbol="ETH/USD")):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                build_public_signal_frame(signal(), modified)
        with self.assertRaises(ValueError):
            build_public_signal_frame(signal(evidence_id="not hash"), quote())

    def test_sell_is_never_vetoed_or_sent_to_model(self):
        def no_model_call(_): raise AssertionError("SELL must bypass model")
        result = BoundedAdvisoryGate(no_model_call).review(signal=signal(action=Action.SELL), quote=quote())
        self.assertTrue(result.continue_to_guardian)
        self.assertFalse(result.transport_used)
        self.assertEqual(result.reason_code, "RISK_REDUCING_EXIT")


if __name__ == "__main__": unittest.main()
