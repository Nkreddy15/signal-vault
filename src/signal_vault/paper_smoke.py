"""Explicit authenticated READ-ONLY paper smoke check.

Running this module performs GET requests to Alpaca PAPER only. It never imports
the order executor and cannot submit/cancel/transfer anything. It is not invoked
by the default Signal Vault CLI or tests.
"""
from __future__ import annotations

import json

from .alpaca_paper import PaperAlpacaReadClient
from .paper_credentials import PaperCredentials


def main() -> int:
    credentials = PaperCredentials.from_environment()
    reader = PaperAlpacaReadClient(credentials.key_id, credentials.secret_key)
    readiness = reader.readiness()
    rules = reader.get_btc_rules()
    # Never print account identifiers, balances or credentials here.
    print(json.dumps({
        "mode": "alpaca-paper-read-only",
        "ready": readiness.ready,
        "reasons": list(readiness.reasons),
        "logical_cap_usd": str(readiness.logical_cap_usd),
        "symbol": rules.symbol,
        "min_order_size": str(rules.min_order_size),
        "min_trade_increment": str(rules.min_trade_increment),
        "price_increment": str(rules.price_increment),
        "order_submission": "DISABLED_IN_THIS_COMMAND",
    }, sort_keys=True))
    return 0 if readiness.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
