"""Explicit, read-only authenticated Alpaca PAPER account onboarding.

NEVER called from the default CLI or any test against real credentials.
No order submission, balance change, cancellation, funding or transfer routes.
Credentials come from the local process environment, never Git or ChatGPT.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Callable

from .alpaca_paper import PAPER_ROOT, PaperAlpacaReadClient
from .config import RuntimeConfig
from .venue_rules import BtcVenueRules
from .paper_credentials import PaperCredentials


@dataclass(frozen=True)
class ReadOnlyOnboardingResult:
    ready: bool
    issues: tuple[str,...]
    inspected_host: str
    proposed_virtual_budget_usd: Decimal
    initial_min_btc_qty: str | None
    initial_trade_increment: str | None


def evaluate_paper_read_only(client: PaperAlpacaReadClient) -> ReadOnlyOnboardingResult:
    """Fail closed; do not trust default paper balance as authorized capital."""
    issues=[]
    constraints=None
    try:
        status=client.readiness()
        issues.extend(status.reasons)
    except (ValueError,KeyError,TypeError,ArithmeticError):
        issues.append('provider paper account readiness response invalid')
    try:
        constraints=BtcVenueRules.from_asset(client.get_btc_asset())
    except (ValueError,KeyError,TypeError,ArithmeticError):
        issues.append('provider BTC/USD minimum, price step or quantity step is unknown')
    try:
        acct=client.get_account()
        if (not isinstance(acct.get('id'),str) or not acct['id'].strip() or
            acct.get('crypto_status') not in ('ACTIVE',)):
            issues.append('paper account ID or crypto trading eligibility is not confirmed')
        cash=Decimal(str(acct['cash']))
        nonmargin=Decimal(str(acct['non_marginable_buying_power']))
        if not cash.is_finite() or not nonmargin.is_finite() or cash<100 or nonmargin<100:
            issues.append('paper account cannot support isolated virtual $100 cash-only test')
    except (ValueError,KeyError,TypeError,ArithmeticError):
        issues.append('paper cash or non-marginable balance response invalid')
    return ReadOnlyOnboardingResult(not issues,tuple(issues),PAPER_ROOT,Decimal('100'),
          str(constraints.minimum_base_qty) if constraints else None,
          str(constraints.base_trade_step) if constraints else None)


def main(argv: list[str]|None=None, *, env: Mapping[str,str]|None=None,
         client_factory: Callable[[str,str],PaperAlpacaReadClient]=PaperAlpacaReadClient) -> int:
    parser=argparse.ArgumentParser(description='Inspect only the immutable Alpaca PAPER trading endpoint')
    parser.add_argument('--confirm-paper-read-only',action='store_true',
        help='I authorize paper-only account/asset/position/open order GET requests; no orders')
    args=parser.parse_args(argv)
    if not args.confirm_paper_read_only:
        parser.error('an explicit --confirm-paper-read-only flag is mandatory')
    settings=os.environ if env is None else env
    RuntimeConfig.from_environment(settings)  # mode must be paper; no live toggles
    paper=PaperCredentials.from_environment(settings)
    client=client_factory(paper.key_id,paper.secret_key)
    outcome=evaluate_paper_read_only(client)
    # Only redacted facts are printed. No raw provider JSON, IDs, tokens or secrets.
    print(json.dumps({'kind':'ALPACA_PAPER_READ_ONLY_ONBOARDING',
      'paper_host':outcome.inspected_host,'ready_for_later_paper_authorization':outcome.ready,
      'virtual_pilot_budget_usd':str(outcome.proposed_virtual_budget_usd),
      'asset_minimum_base_qty':outcome.initial_min_btc_qty,
      'base_trade_increment':outcome.initial_trade_increment,
      'issues':outcome.issues,'broker_post_orders_sent':0,'real_money_orders_sent':0},sort_keys=True))
    return 0 if outcome.ready else 2

if __name__=='__main__':raise SystemExit(main())
