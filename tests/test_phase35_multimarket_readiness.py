import unittest

from signal_vault.multimarket_readiness import (
    LANES,
    LaneEvidence,
    assess_lane_readiness,
    multimarket_readiness,
)


def complete(**changes):
    base=dict(
        historical_dataset_verified=True,
        historical_walk_forward_complete=True,
        frozen_model_or_ruleset=True,
        prospective_or_shadow_complete=True,
        paper_or_demo_execution_validated=True,
        restart_and_unknown_result_recovery_validated=True,
        provider_reconciliation_validated=True,
        shared_risk_governor_validated=True,
        live_credentials_configured=False,
        owner_live_authorization_recorded=False,
    )
    base.update(changes)
    return LaneEvidence(**base)


class MultiMarketReadinessTests(unittest.TestCase):
    def test_complete_technical_evidence_still_does_not_activate_live(self):
        result=assess_lane_readiness("crypto",complete())
        self.assertTrue(result["technically_ready_for_live_activation_review"])
        self.assertFalse(result["live_activation_permitted"])
        self.assertEqual(result["automatic_live_activation"],"DISABLED")

    def test_missing_paper_and_reconciliation_are_explicit_blockers(self):
        result=assess_lane_readiness(
            "us_equity",
            complete(
                paper_or_demo_execution_validated=False,
                provider_reconciliation_validated=False,
            ),
        )
        self.assertFalse(result["technically_ready_for_live_activation_review"])
        self.assertIn(
            "paper_or_demo_execution_validated",
            result["technical_blockers_before_live_activation_review"],
        )
        self.assertIn(
            "provider_reconciliation_validated",
            result["technical_blockers_before_live_activation_review"],
        )

    def test_live_permission_requires_evidence_credentials_and_owner_authorization(self):
        result=assess_lane_readiness(
            "kalshi_event_contract",
            complete(
                live_credentials_configured=True,
                owner_live_authorization_recorded=True,
            ),
        )
        self.assertTrue(result["live_activation_permitted"])
        blocked=assess_lane_readiness(
            "kalshi_event_contract",
            complete(
                paper_or_demo_execution_validated=False,
                live_credentials_configured=True,
                owner_live_authorization_recorded=True,
            ),
        )
        self.assertFalse(blocked["live_activation_permitted"])

    def test_multimarket_report_requires_exact_three_lanes(self):
        evidence={lane:complete() for lane in LANES}
        result=multimarket_readiness(evidence)
        self.assertTrue(
            result["all_lanes_technically_ready_for_live_activation_review"]
        )
        self.assertFalse(result["any_live_activation_permitted"])
        with self.assertRaises(ValueError):
            multimarket_readiness({"crypto":complete()})

    def test_bad_lane_or_non_boolean_evidence_fails_closed(self):
        with self.assertRaises(ValueError):
            assess_lane_readiness("forex",complete())
        with self.assertRaises(ValueError):
            LaneEvidence(
                historical_dataset_verified=1,  # type: ignore[arg-type]
                historical_walk_forward_complete=True,
                frozen_model_or_ruleset=True,
                prospective_or_shadow_complete=True,
                paper_or_demo_execution_validated=True,
                restart_and_unknown_result_recovery_validated=True,
                provider_reconciliation_validated=True,
                shared_risk_governor_validated=True,
            )


if __name__=="__main__":
    unittest.main()
