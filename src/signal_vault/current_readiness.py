"""Conservative current multi-market readiness baseline for the operator UI.

This baseline only marks evidence that is already present in the repository or
production research state. Unknown or incomplete work remains False. It is not
an order authorization and intentionally does not infer live credentials.
"""
from __future__ import annotations

from .multimarket_readiness import LANES, LaneEvidence, multimarket_readiness


def current_readiness_baseline() -> dict[str, object]:
    evidence={
        "crypto": LaneEvidence(
            historical_dataset_verified=True,
            historical_walk_forward_complete=False,
            frozen_model_or_ruleset=True,
            prospective_or_shadow_complete=False,
            paper_or_demo_execution_validated=False,
            restart_and_unknown_result_recovery_validated=True,
            provider_reconciliation_validated=False,
            shared_risk_governor_validated=True,
            live_credentials_configured=False,
            owner_live_authorization_recorded=False,
        ),
        "us_equity": LaneEvidence(
            historical_dataset_verified=True,
            historical_walk_forward_complete=False,
            frozen_model_or_ruleset=False,
            prospective_or_shadow_complete=False,
            paper_or_demo_execution_validated=False,
            restart_and_unknown_result_recovery_validated=False,
            provider_reconciliation_validated=False,
            shared_risk_governor_validated=True,
            live_credentials_configured=False,
            owner_live_authorization_recorded=False,
        ),
        "kalshi_event_contract": LaneEvidence(
            historical_dataset_verified=False,
            historical_walk_forward_complete=False,
            frozen_model_or_ruleset=False,
            prospective_or_shadow_complete=False,
            paper_or_demo_execution_validated=False,
            restart_and_unknown_result_recovery_validated=False,
            provider_reconciliation_validated=False,
            shared_risk_governor_validated=True,
            live_credentials_configured=False,
            owner_live_authorization_recorded=False,
        ),
    }
    if set(evidence)!=set(LANES):
        raise AssertionError("readiness baseline must cover every market lane")
    report=multimarket_readiness(evidence)
    report["source"]="CONSERVATIVE_CODE_AND_RESEARCH_CHECKPOINT_BASELINE"
    report["live_state_inferred_from_credentials"]=False
    return report
