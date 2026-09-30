import unittest

from signal_vault.kalshi_final_readiness import (
    compose_kalshi_final_technical_readiness,
)


CANDIDATE="market-favorite-6h-hold-v1-predeclared"


def historical():
    return {
        "kind":"KALSHI_RESEARCH_READINESS_RECEIPT_NOT_ORDER_AUTHORIZATION",
        "historical_depth_ready":True,
        "historical_walk_forward_complete":True,
        "historically_confirmed_fixed_candidates":[CANDIDATE],
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
        "automatic_live_activation":"DISABLED",
    }


def prospective(passed=True):
    return {
        "kind":"KALSHI_PROSPECTIVE_SHADOW_GATE_NO_ORDER",
        "candidates_passing_prospective_shadow":
            [CANDIDATE] if passed else [],
        "candidate_added_by_prospective_results":False,
        "candidate_ranking_performed":False,
        "automatic_candidate_selection":"DISABLED",
        "prospective_or_shadow_complete":passed,
        "demo_order_submission":"DISABLED",
        "live_order_submission":"DISABLED",
    }


def demo(passed=True):
    return {
        "kind":"KALSHI_DEMO_EXECUTION_ACCEPTANCE_NO_LIVE_AUTHORITY",
        "demo_execution_validated":passed,
        "restart_and_unknown_result_recovery_validated":passed,
        "provider_reconciliation_validated":passed,
        "automatic_live_activation":"DISABLED",
        "live_credentials_configured":False,
        "owner_live_authorization_recorded":False,
        "live_order_submission":"DISABLED",
    }


class KalshiFinalTechnicalReadinessTests(unittest.TestCase):
    def test_all_technical_evidence_can_open_review_but_not_live_activation(self):
        result=compose_kalshi_final_technical_readiness(
            historical(),prospective(),demo()
        )
        self.assertEqual(
            result[
                "fixed_candidates_surviving_historical_and_prospective_gates"
            ],
            [CANDIDATE],
        )
        lane=result["shared_lane_readiness"]
        self.assertTrue(
            lane["technically_ready_for_live_activation_review"]
        )
        self.assertFalse(lane["live_activation_permitted"])
        self.assertTrue(
            result[
                "technically_ready_for_separate_live_activation_review"
            ]
        )
        self.assertFalse(result["live_credentials_configured"])
        self.assertFalse(result["owner_live_authorization_recorded"])
        self.assertFalse(result["live_activation_permitted"])
        self.assertEqual(result["automatic_live_activation"],"DISABLED")
        self.assertEqual(result["live_order_submission"],"DISABLED")
        self.assertEqual(
            result["next_action"],
            "SEPARATE_OWNER_LIVE_ACTIVATION_REVIEW_REQUIRED",
        )

    def test_missing_shadow_or_demo_evidence_keeps_technical_review_closed(self):
        for p,d in ((prospective(False),demo()),(prospective(),demo(False))):
            with self.subTest(p=p,d=d):
                result=compose_kalshi_final_technical_readiness(
                    historical(),p,d
                )
                self.assertFalse(
                    result[
                        "technically_ready_for_separate_live_activation_review"
                    ]
                )
                self.assertEqual(
                    result["next_action"],
                    "TECHNICAL_EVIDENCE_INCOMPLETE",
                )
                self.assertFalse(result["live_activation_permitted"])

    def test_prospective_candidate_not_in_historical_survivors_is_rejected(self):
        p=prospective()
        p["candidates_passing_prospective_shadow"]=["not-historical"]
        with self.assertRaises(ValueError):
            compose_kalshi_final_technical_readiness(
                historical(),p,demo()
            )

    def test_receipt_cannot_smuggle_live_credentials_or_authorization(self):
        item=demo()
        item["live_credentials_configured"]=True
        with self.assertRaises(ValueError):
            compose_kalshi_final_technical_readiness(
                historical(),prospective(),item
            )


if __name__=="__main__":
    unittest.main()
