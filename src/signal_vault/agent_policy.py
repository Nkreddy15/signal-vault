"""Typed AI committee decision boundary, with zero broker/order capabilities.

An AI can choose between HOLD and an EXISTING reproducible signal. It cannot
invent a new asset, side, order size, venue, API call or override Guardian.
No model provider, external network call or AI subscription is used here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from typing import Mapping

from .strategy import StrategySignal,Action


@dataclass(frozen=True)
class AdviserVote:
    evidence_id: str
    action: Action
    confidence: Decimal
    model_version: str
    generated_at: datetime
    rationale: str


def parse_adviser_vote(payload: Mapping[str,object]) -> AdviserVote:
    """Treat model JSON as untrusted DATA. No prompts or tool instructions."""
    fields={'evidence_id','action','confidence','model_version','generated_at','rationale'}
    if not isinstance(payload,Mapping) or set(payload)!=fields:
        raise ValueError('AI vote must have only the six allowlisted fields')
    if any(not isinstance(payload[x],str) or not payload[x].strip() for x in
           ('evidence_id','action','confidence','model_version','generated_at','rationale')):
        raise ValueError('missing or malformed AI vote fields')
    if len(payload['rationale'])>400 or len(payload['model_version'])>80 or len(payload['evidence_id'])!=64:
        raise ValueError('invalid AI vote text lengths')
    try:
        action=Action(payload['action'])
        confidence=Decimal(payload['confidence'])
        stamp=datetime.fromisoformat(payload['generated_at'].replace('Z','+00:00'))
    except (ValueError,ArithmeticError,TypeError) as exc:
        raise ValueError('unsupported AI action, confidence or time') from exc
    if not confidence.is_finite() or not 0<=confidence<=1:
        raise ValueError('AI confidence must be finite within 0..1')
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('AI vote needs an aware timestamp')
    return AdviserVote(payload['evidence_id'],action,confidence,payload['model_version'],
                       stamp,payload['rationale'])


@dataclass(frozen=True)
class CommitteeDecision:
    action: Action
    signal_id: str
    reason: str
    adviser_used: bool


def resolve_ai_final_choice(signal: StrategySignal, adviser: AdviserVote|None, *,
                            now: datetime, require_ai: bool=True,
                            minimum_confidence: Decimal=Decimal('0.65')) -> CommitteeDecision:
    """AI decides whether a qualifying baseline signal may reach the Guardian.

    A model cannot directly APPROVE an order. Guardian remains the independent
    final safety gate, while this is the final discretionary selection gate.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('UTC-aware review time required')
    if not isinstance(minimum_confidence,Decimal) or not minimum_confidence.is_finite() or not 0<=minimum_confidence<=1:
        raise ValueError('invalid confidence policy')
    if signal.action is Action.HOLD:
        return CommitteeDecision(Action.HOLD,signal.evidence_id,'Baseline identified no qualified trade',False)
    if not require_ai:
        return CommitteeDecision(signal.action,signal.evidence_id,
                'Deterministic baseline paper-only selection; model optional',False)
    if adviser is None:
        return CommitteeDecision(Action.HOLD,signal.evidence_id,'AI adviser unavailable; fail closed to HOLD',False)
    try:
        bar=datetime.fromisoformat(signal.bar_closed_at.replace('Z','+00:00'))
        valid= (isinstance(adviser,AdviserVote) and adviser.evidence_id==signal.evidence_id and
               adviser.generated_at.tzinfo is not None and adviser.generated_at.utcoffset() is not None and
               bar.tzinfo is not None and bar.utcoffset() is not None and
               bar<=adviser.generated_at<=now and
               now-bar<=timedelta(seconds=90) and
               adviser.confidence.is_finite() and 0<=adviser.confidence<=1)
    except (ValueError,TypeError,ArithmeticError):
        valid=False
    if not valid:
        return CommitteeDecision(Action.HOLD,signal.evidence_id,
                    'Unverified/stale/mismatched model advice; HOLD',False)
    if adviser.action is Action.HOLD or adviser.action is not signal.action:
        return CommitteeDecision(Action.HOLD,signal.evidence_id,
                    'AI selection declined qualified candidate',True)
    if adviser.confidence<minimum_confidence:
        return CommitteeDecision(Action.HOLD,signal.evidence_id,
                    'AI vote below declared confidence gate',True)
    return CommitteeDecision(signal.action,signal.evidence_id,
                 'AI selected existing evidence-bound candidate; Guardian must still independently approve',True)
