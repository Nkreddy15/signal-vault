# Phase 3: Read-only preview for the first supervised PAPER smoke

New **explicitly invoked** diagnostic command (after a reviewed merge/pull):

```sh
PYTHONPATH=src python -m signal_vault.paper_smoke_preview --preview
```

This prepares an ephemeral **hypothetical $15 BTC/USD PAPER market-buy diagnostic preview**. It never places/cancels any order, creates a client order ID, saves a draft, reserves cash, changes the SQLite journal, changes the hourly observer, accesses a live endpoint, or enables future POST.

Safety sequence:

1. Verify existing owner-only SQLite local paper preflight. Independently read the existing local paper snapshot and require an empty initial $100 logical ledger: $100 cash, zero BTC exposure, zero reserves, zero paper order states, operator not halted and zero unresolved orders. Fail **before** touching Keychain or network when missing or inconsistent. This command never initializes a journal.
2. Only after those checks read the existing owner-local Alpaca PAPER-data credentials from the login Keychain (never print/persist them).
3. Four fixed-path PAPER trading-account **GET** reads via the read-only client: account, BTC/USD asset metadata, positions and open orders. Require ACTIVE/unblocked, non-marginable buying power at least $15, no external positions/open orders, valid dynamic provider asset constraints. The actual provider balance is **not** the bot's logical capital.
4. One fixed-host authenticated Alpaca DATA **GET** for the current BTC/USD quote, rejecting redirects. Revalidate quote symbol, finite bid/ask, non-crossed market, quote age up to 90 seconds, spread up to 50 bps. Apply provider-reported dynamic BTC minimum to a fixed $15 hypothetical notional using the latest ask. Never silently upsize above $15 if market rules disallow the preview.
5. Print only sanitized result, checked timestamp, reference ask, spread, calculated current dynamic minimum, and `BASIC_SMOKE_PREVIEW_PASSED_NO_ORDER` or fixed fail reason. No credentials, account IDs, raw response, exception text or order payload leave via stdout.

This preview is time-sensitive and becomes stale. It is **not** authorization to send a test order, evidence of a fill or strategy edge, a signed Alpaca attestation, or permission to run the existing opt-in paper worker. A future separately approved supervised actual broker-paper smoke must rerun account, venue, quote, Guardian and final current-state checks immediately before its sole order POST, persist a durable state before sending and reconcile actual provider status/fees/positions before any follow-on action.

The hourly Mac `mac_forward_agent` job is unchanged. Source and tests stay isolated in `src/signal_vault/paper_smoke_preview.py` and `tests/test_paper_smoke_preview.py`. Tests inject fake clients, prevent real network, check read-only boundaries and invalid/stale quotes, local/remote position drift, missing Keychain, insufficient paper buying power and changing BTC order minimum.
