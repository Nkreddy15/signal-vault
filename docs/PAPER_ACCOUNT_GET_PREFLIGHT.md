# Phase 3: Explicit read-only PAPER account check

`PYTHONPATH=src python -m signal_vault.paper_account_get_preflight`

This is a **separate, explicit owner-initiated** diagnostic, NOT the hourly observer and NOT order submission. It checks the EXISTING local `data/signal-vault-paper.sqlite3` ledger first (private mode, SQLite integrity/WAL, not halted, zero unresolved orders). A missing ledger is reported as BLOCKED **without creating a replacement, requesting secrets or making provider requests**.

Only after passing the local check does the command read the existing owner-local `signal-vault-forward` Alpaca PAPER credentials from macOS Keychain. It then invokes the existing fixed-host `PaperAlpacaReadClient.readiness()`, issuing up to four Alpaca `https://paper-api.alpaca.markets` GET requests: `/v2/account`, `/v2/assets/BTC%2FUSD`, `/v2/positions`, and `/v2/orders?status=open`. Any missing/bad venue metadata, non-active/blocked account, unexpected positions/open orders, or provider response failure blocks readiness. Redirects refused. No generic/live credential fallback.

No order POST, cancel, deposit, fund, or account mutation exists in the module. It does not log keys, account IDs, balances, raw provider responses, exception messages or journal contents. Printed fields are fixed status/reason categories and generic exception classes. The existing Keychain items were originally configured for PAPER DATA GET; if this account GET is unauthorized by those same keys, it fails closed and the operator should review the account (not paste keys in chat or modify the collector).

A successful `BASIC_PAPER_ACCOUNT_GET_CHECK_PASSED` is **only basic account read eligibility**, not final affordability for a specific order, current executable quote, fees/fills, strategy performance, autonomous permission or approval to POST. The logical Signal Vault $100 initial capital is not replaced by Alpaca's much larger default paper balance.

Tested with injected fixed-path GET transport and fake credentials in `tests/test_paper_account_get_preflight.py`. The installed `mac_forward_agent` plist/worker is unchanged.

Suggested local sequence after receiving/pulling a reviewed merge to main:
```sh
PYTHONPATH=src python -m signal_vault.init_paper
PYTHONPATH=src python -m signal_vault.preflight
PYTHONPATH=src python -m signal_vault.phase3_readiness
# Optional, explicit four PAPER broker GETs; never a trade:
PYTHONPATH=src python -m signal_vault.paper_account_get_preflight
```
Do not initialize a new ledger over an existing disputed/unreconciled one. Do not use the generic `paper_worker` for this account GET diagnostic because it may separately create a paper draft.
