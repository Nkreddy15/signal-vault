"""NO-LOOKAHEAD diagnostics for two independently validated historic market clocks.

The July-Aug six-crypto dataset and Sep14-25 six-stock IEX dataset belong to
DISJOINT periods. Their separately computed $100 PnL must NEVER be summed,
joined as a twelve-asset portfolio, or advertised as a synchronized
experiment. This pure module makes that precondition machine-checkable.

This tests time coverage ONLY; it is not authorization to combine a 24/7
crypto market with a regular-session stock market, claim fractional shares
are executable, interpolate after-hours data, or send an order.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

HOUR=timedelta(hours=1)


def _utc(instant: datetime) -> datetime:
    if (not isinstance(instant,datetime) or instant.tzinfo is None or
            instant.utcoffset() is None):
        raise ValueError("historic market timestamps require timezone-aware UTC")
    return instant.astimezone(timezone.utc)


def historical_clock_compatibility(
    *,
    continuous_crypto_start_utc: datetime,
    continuous_crypto_end_utc_exclusive: datetime,
    independently_verified_stock_core_opens_utc: Sequence[datetime],
    minimum_shared_core_hours: int=48,
) -> dict[str,object]:
    """Return a NO-TRADE common-UTC-clock readiness check, never merged PnL.

    Crypto's [start,end) bounds are supplied only after verified contiguous
    immutable source-archive reads. Stock core hours are supplied only after
    independent XNYS calendar and matching IEX SHA source verification.
    Merely overlapping time periods cannot establish strategy-edge evidence.
    """
    crypto_start=_utc(continuous_crypto_start_utc)
    crypto_end=_utc(continuous_crypto_end_utc_exclusive)
    equity=tuple(_utc(x) for x in independently_verified_stock_core_opens_utc)
    if (not crypto_start<crypto_end or
            crypto_end-crypto_start>timedelta(days=420) or
            any(t.minute or t.second or t.microsecond
                for t in (crypto_start,crypto_end))):
        raise ValueError("invalid source-verified continuous crypto UTC history")
    if (type(minimum_shared_core_hours) is not int or
            not 24<=minimum_shared_core_hours<=250):
        raise ValueError("explicit nontrivial synchronized core-history requirement")
    if (not equity or len(equity)>250 or
            equity!=tuple(sorted(set(equity))) or
            any(t.minute or t.second or t.microsecond for t in equity)):
        raise ValueError("stock core-open timestamps must be sorted, unique and exact UTC hours")
    shared=tuple(t for t in equity if crypto_start<=t and t+HOUR<=crypto_end)
    common=len(shared)
    if common==0:
        reason="NO_COMMON_HISTORICAL_UTC_HOURS"
    elif common<minimum_shared_core_hours:
        reason="INSUFFICIENT_ALIGNED_STOCK_CORE_HOURS"
    else:
        reason="BASIC_CLOCK_ALIGNMENT_POSSIBLE_REQUIRES_SEPARATE_MODEL_AUDIT"
    return {
        "kind":"OFFLINE_CROSS_ASSET_HISTORICAL_CLOCK_COMPATIBILITY_NOT_A_PORTFOLIO",
        "crypto_complete_history_start_utc":crypto_start.isoformat(),
        "crypto_complete_history_end_utc_exclusive":crypto_end.isoformat(),
        "stock_verified_core_hour_count":len(equity),
        "stock_first_core_open_utc":equity[0].isoformat(),
        "stock_last_core_close_utc":(equity[-1]+HOUR).isoformat(),
        "common_source_closed_bar_open_hours":common,
        "minimum_required_common_stock_core_hours":minimum_shared_core_hours,
        "common_fraction_of_stock_core_history":
            str(common/len(equity)),
        "common_core_hour_starts_utc":[t.isoformat() for t in shared],
        "basic_clock_alignment_ready":common>=minimum_shared_core_hours,
        "reason_code":reason,
        "twelve_asset_backtest_ran":False,
        "cross_market_capital_combined":False,
        "portfolio_PnL_comparable_across_disjoint_histories":False,
        "no_future_bar_or_cross_market_afterhours_imputation":True,
        "history_alone_proves_strategy_edge":False,
        "broker_order_submission":"DISABLED",
        "live_trading":"UNAVAILABLE",
    }
