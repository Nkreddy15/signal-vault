from __future__ import annotations

import unittest
from decimal import Decimal

from signal_vault.candidate_registry import (
    DEPLOYABLE_CRYPTO_FEATURES,
    CandidateState,
    PHASE162_CANDIDATES,
    active_shadow_candidates,
    candidate_by_id,
)
from signal_vault.crypto_universe_forward import BOOTSTRAP_HOURS


class Phase162CandidateRegistryTests(unittest.TestCase):
    def test_registry_has_two_evidence_bound_crypto_candidates(self):
        self.assertEqual(len(PHASE162_CANDIDATES), 2)
        self.assertTrue(all(x.market_lane == "crypto" for x in PHASE162_CANDIDATES))
        self.assertTrue(all(x.paper_order_authorized is False for x in PHASE162_CANDIDATES))

    def test_candidates_fit_existing_forward_bootstrap(self):
        self.assertEqual(BOOTSTRAP_HOURS, 72)
        for candidate in PHASE162_CANDIDATES:
            self.assertLessEqual(candidate.maximum_feature_lookback_hours, BOOTSTRAP_HOURS)
            self.assertEqual(candidate.feature_names, DEPLOYABLE_CRYPTO_FEATURES)

    def test_primary_candidate_matches_frozen_receipt(self):
        candidate = candidate_by_id("crypto-rf-48h-return15bps-v1-phase162")
        self.assertEqual(candidate.model_family, "random_forest_regressor")
        self.assertEqual(candidate.horizon_hours, 48)
        self.assertEqual(candidate.entry_threshold_return, Decimal("0.015"))
        self.assertEqual(candidate.validation_trade_count, 26)
        self.assertEqual(candidate.state, CandidateState.SHADOW)
        self.assertLess(
            candidate.descriptive_holdout_base_pnl_usd,
            candidate.passive_holdout_base_pnl_usd,
        )

    def test_only_shadow_states_are_active(self):
        active = active_shadow_candidates("crypto")
        self.assertEqual(
            {x.state for x in active},
            {CandidateState.SHADOW, CandidateState.SECONDARY_SHADOW},
        )

    def test_unknown_candidate_fails_closed(self):
        with self.assertRaises(ValueError):
            candidate_by_id("does-not-exist")


if __name__ == "__main__":
    unittest.main()
