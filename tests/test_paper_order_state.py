import unittest
from decimal import Decimal

from signal_vault.paper_order_state import (
    PaperOrderState, BrokerObservation, Stage,
)


def receipt(status="accepted", qty="0", price=None, *, client="order1", provider="broker-1"):
    return BrokerObservation(client, provider, status, Decimal(qty),
                             None if price is None else Decimal(price))


class PaperLifecycleTests(unittest.TestCase):
    def test_valid_order_state_path_requires_explicit_reconciliation(self):
        draft = PaperOrderState("order1")
        pending = draft.start_submission()
        accepted = pending.observe(receipt())
        self.assertEqual(accepted.stage, Stage.BROKER_ACCEPTED)
        partial = accepted.observe(receipt("partially_filled", "0.0001", "65000"))
        self.assertEqual(partial.stage, Stage.PARTIALLY_FILLED)
        filled = partial.observe(receipt("filled", "0.00023", "65100"))
        self.assertEqual(filled.stage, Stage.BROKER_TERMINAL_UNRECONCILED)
        self.assertTrue(filled.blocks_new_execution)
        with self.assertRaises(ValueError):
            filled.confirm_reconciled(provider_cash_verified=True,
                                      provider_position_verified=False,
                                      provider_order_verified=True)
        reconciled = filled.confirm_reconciled(provider_cash_verified=True,
                                               provider_position_verified=True,
                                               provider_order_verified=True)
        self.assertTrue(reconciled.reconciled)
        self.assertFalse(reconciled.blocks_new_execution)

    def test_timeout_halts_and_never_clears_without_provider_lookup(self):
        unknown = PaperOrderState("order1").start_submission().mark_transport_uncertain()
        self.assertEqual(unknown.stage, Stage.UNKNOWN_RESULT)
        self.assertTrue(unknown.blocks_new_execution)
        with self.assertRaises(ValueError):
            unknown.start_submission()
        recovered = unknown.observe(receipt())
        self.assertEqual(recovered.stage, Stage.BROKER_ACCEPTED)

    def test_repeated_submit_is_forbidden(self):
        pending = PaperOrderState("order1").start_submission()
        with self.assertRaises(ValueError):
            pending.start_submission()

    def test_mismatch_broker_id_forbidden(self):
        pending = PaperOrderState("order1").start_submission()
        with self.assertRaises(ValueError):
            pending.observe(receipt(client="order2"))
        first = pending.observe(receipt())
        with self.assertRaises(ValueError):
            first.observe(receipt(provider="broker-2"))

    def test_unknown_status_and_fill_facts_fail_closed(self):
        pending = PaperOrderState("order1").start_submission()
        for obs in (receipt("unexpected"), receipt("filled"),
                    receipt("partially_filled"), receipt("partially_filled", "1", None),
                    receipt("accepted", "NaN"), receipt("accepted", "0", "700")):
            with self.subTest(obs=obs), self.assertRaises(ValueError):
                pending.observe(obs)

    def test_cumulative_qty_never_regresses(self):
        part = PaperOrderState("order1").start_submission().observe(
            receipt("partially_filled", "0.2", "100"))
        with self.assertRaisesRegex(ValueError, "regressed"):
            part.observe(receipt("partially_filled", "0.1", "100"))
        with self.assertRaisesRegex(ValueError, "regressed from partial"):
            part.observe(receipt("accepted", "0.2", "100"))

    def test_terminal_snapshot_can_repeat_but_cannot_rewrite(self):
        terminal = PaperOrderState("order1").start_submission().observe(
            receipt("rejected"))
        self.assertEqual(terminal.observe(receipt("rejected")), terminal)
        with self.assertRaisesRegex(ValueError, "terminal"):
            terminal.observe(receipt("canceled"))

    def test_cancel_with_partial_fill_still_requires_reconciliation(self):
        partial = PaperOrderState("order1").start_submission().observe(
            receipt("partially_filled", "0.1", "65000"))
        closed = partial.observe(receipt("canceled", "0.1", "65000"))
        self.assertTrue(closed.blocks_new_execution)
        self.assertEqual(closed.provider_status, "canceled")


if __name__ == "__main__":
    unittest.main()
