"""Single-attempt Kalshi DEMO V2 executor.

Consumes a durable multi-market draft, shared-risk receipt, exact Kalshi demo
acknowledgement, and an injected signer. SUBMISSION_PENDING is committed before
the network POST. The host is hardcoded to Kalshi's demo environment.

A V2 create-order response does not report average fill price. Therefore an
immediate fill is never fabricated into the shared fill state machine: it is
kept UNKNOWN_RESULT until a later authenticated order/fill reconciliation can
supply authoritative execution details. Zero-fill resting acceptance can be
recorded as BROKER_ACCEPTED.

There is no production Kalshi host in this module.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Mapping
from urllib.request import Request, build_opener

from .alpaca_paper import _NoRedirects
from .kalshi_demo_signing import build_kalshi_demo_signed_order_request, Signer
from .multimarket_execution_journal import (
    MultiMarketExecutionJournal,
    MultiMarketOrderDraft,
)
from .multimarket_paper_router import (
    KALSHI_DEMO_ACK,
    KALSHI_DEMO_ROOT,
    KALSHI_ORDER_PATH,
    route_paper_execution,
)
from .paper_order_state import BrokerObservation, PaperOrderState, Stage


Transport = Callable[
    [str, Mapping[str, str], Mapping[str, str]], Mapping[str, object]
]


def _post_demo_json(
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, str],
) -> Mapping[str, object]:
    if url != KALSHI_DEMO_ROOT + KALSHI_ORDER_PATH:
        raise PermissionError("Kalshi executor is demo-host only")
    req = Request(
        url,
        method="POST",
        data=json.dumps(dict(payload), separators=(",", ":")).encode("utf-8"),
        headers=dict(headers),
    )
    with build_opener(_NoRedirects).open(req, timeout=12) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Kalshi demo response too large")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("malformed Kalshi demo response")
    return decoded


def _decimal(value: object, name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid Kalshi {name}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"invalid Kalshi {name}")
    return number


@dataclass(frozen=True)
class KalshiCreateReceipt:
    order_id: str
    client_order_id: str
    fill_count: Decimal
    remaining_count: Decimal


def parse_kalshi_v2_create_response(
    data: Mapping[str, object],
    *,
    expected_client_id: str,
    expected_count: Decimal,
) -> KalshiCreateReceipt:
    if not isinstance(data, Mapping):
        raise ValueError("invalid Kalshi V2 create response")
    order_id = data.get("order_id")
    client_id = data.get("client_order_id")
    if not isinstance(order_id, str) or not order_id:
        raise ValueError("missing Kalshi order id")
    if client_id != expected_client_id:
        raise ValueError("Kalshi client order id mismatch")
    fill = _decimal(data.get("fill_count"), "fill_count")
    remaining = _decimal(data.get("remaining_count"), "remaining_count")
    if fill + remaining != expected_count:
        raise ValueError("Kalshi create counts do not equal submitted count")
    return KalshiCreateReceipt(order_id, expected_client_id, fill, remaining)


@dataclass(frozen=True)
class KalshiDemoSubmissionOutcome:
    stage: Stage
    explanation: str
    state: PaperOrderState
    demo_post_attempted: bool
    immediate_fill_requires_reconciliation: bool


class KalshiDemoOnceExecutor:
    """Exactly one Kalshi DEMO POST attempt, never a production order."""

    def __init__(
        self,
        *,
        key_id: str,
        signer: Signer,
        journal: MultiMarketExecutionJournal,
        transport: Transport = _post_demo_json,
    ) -> None:
        if not isinstance(key_id, str) or not key_id.strip() or key_id != key_id.strip():
            raise ValueError("Kalshi demo key id required")
        if not callable(signer):
            raise TypeError("Kalshi demo signer required")
        self._key_id = key_id
        self._signer = signer
        self._journal = journal
        self._transport = transport

    def submit_once(
        self,
        draft: MultiMarketOrderDraft,
        *,
        risk_assessment: Mapping[str, object],
        acknowledgement: str,
        timestamp_ms: int,
        at: datetime,
    ) -> KalshiDemoSubmissionOutcome:
        route = route_paper_execution(
            draft,
            risk_assessment=risk_assessment,
            acknowledgement=acknowledgement,
        )
        if (
            route.provider != "kalshi"
            or route.environment != "demo"
            or route.endpoint != KALSHI_DEMO_ROOT + KALSHI_ORDER_PATH
            or acknowledgement != KALSHI_DEMO_ACK
        ):
            raise PermissionError("exact Kalshi DEMO V2 route required")

        request = build_kalshi_demo_signed_order_request(
            route,
            key_id=self._key_id,
            timestamp_ms=timestamp_ms,
            signer=self._signer,
            acknowledgement=acknowledgement,
        )
        expected_count = Decimal(route.payload["count"])

        self._journal.begin_submission(draft, at=at)
        try:
            response = self._transport(request.url, request.headers, request.payload)
            receipt = parse_kalshi_v2_create_response(
                response,
                expected_client_id=draft.client_order_id,
                expected_count=expected_count,
            )
            if receipt.fill_count != 0:
                state = self._journal.mark_unknown(draft.client_order_id, at=at)
                state = self._journal.attach_uncertain_provider_identity(
                    draft.client_order_id, receipt.order_id, at=at)
                return KalshiDemoSubmissionOutcome(
                    state.stage,
                    "Kalshi DEMO order immediately filled in whole or part; "
                    "create response lacks authoritative average fill price, so "
                    "authenticated reconciliation is required before new execution",
                    state,
                    True,
                    True,
                )
            if receipt.remaining_count <= 0:
                raise ValueError("zero-fill Kalshi response has no resting quantity")
            observation = BrokerObservation(
                draft.client_order_id,
                receipt.order_id,
                "accepted",
                Decimal("0"),
                None,
            )
            state = self._journal.observe_provider(observation, at=at)
            return KalshiDemoSubmissionOutcome(
                state.stage,
                "Kalshi DEMO zero-fill create response recorded as accepted/resting; "
                "later authenticated provider lookup still required",
                state,
                True,
                False,
            )
        except Exception:
            current = self._journal.get_state(draft.client_order_id)
            if current.stage is Stage.SUBMISSION_PENDING:
                current = self._journal.mark_unknown(draft.client_order_id, at=at)
            return KalshiDemoSubmissionOutcome(
                current.stage,
                "UNCERTAIN KALSHI DEMO POST: authenticated provider lookup required "
                "before any further execution",
                current,
                True,
                False,
            )
