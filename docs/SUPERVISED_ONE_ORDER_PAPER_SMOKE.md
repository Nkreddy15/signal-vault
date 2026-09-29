# Phase 3: One-time supervised Alpaca PAPER smoke (NOT approved or deployed)

This separate, opt-in module prepares the first **actual broker-system engineering acceptance test**: one $15 BTC/USD PAPER market BUY. It must never be put in the installed :07 market-data LaunchAgent, cron or any unattended process. It cannot reach the live trading host, cancel, transfer, fund, or start an automatic strategy loop.

**Important: adding this feature to GitHub is NOT the owner's authorization to use it, and development/test CI NEVER contacts Alpaca or sends a real order.** The existing Keychain entries were originally installed for read-only paper-data collection. Using those PAPER credentials for a one-time paper ORDER requires explicit owner approval in chat plus a second exact owner-local interactive TTY acknowledgement. No pipe, scheduler, environment-only flag, partial phrase, or implied approval is accepted. Do not paste credentials into chat, shell history, files or logs.

Developer-only entry points (DO NOT execute real submit until separate owner approval):
- `python -m signal_vault.paper_smoke_once --execute`: exact confirmation phrase `AUTHORIZE ONE $15 BTC/USD ALPACA PAPER BUY`. If confirmed, it checks the **existing** private, intact initial $100 logical ledger before reading Keychain. It requires no previous order or draft, no BTC, no cash reservation, no operator halt and no unresolved state. It holds the same exclusive lock as the normal PAPER worker.
- It then rechecks the real hardcoded PAPER account, current BTC asset metadata, no external positions/open orders, ≥$15 buying power, and obtains a fresh BTC/USD bid/ask from the strict no-redirect DATA GET. Guardian uses the initial logical $100 (not Alpaca's default paper balance) and exactly $15. The $15 amount is subject both to an internal conservative $10 notional floor and to fresh provider-reported dynamic minimum. Stale/crossed/wide quote, provider drift, invalid rules, available buying power or Guardian rejection block before POST.
- It generates a new diagnostic-only client order ID, writes Guardian-approved draft durably, then invokes `PaperOnceExecutor.submit_once` exactly once, which persists SUBMISSION_PENDING BEFORE invoking fixed `https://paper-api.alpaca.markets/v2/orders` POST. A timeout/unexpected response means UNKNOWN_RESULT with full reservation retained and **NO BLIND RETRY**. A broker "accepted" or "filled" response is not a verified reconciled position.
- `python -m signal_vault.paper_smoke_once --reconcile` is a distinct READ-ONLY BROKER GET / local-audit operation (it can update local state after a provider-confirmed audit but cannot submit any further POST even by injected executor transport). It looks up the exact previously persisted client ID, handles restart SUBMISSION_PENDING as UNKNOWN, polls accepted/partially filled, audits terminal fill, fee, account and provider inventory via existing reconciliation components. If not yet confirmed, keep blocked and preserve evidence. Delayed crypto buy fee audits are reported as pending.
- NO auto-sell or subsequent trade is authorized. A $15 notional market buy can fill at a different price than the preview, and cryptocurrency PAPER fills are not evidence of future real-market execution quality.

Existing standalone `paper_smoke_preview --preview` remains a zero-write, GET-only diagnostic. Owner-reported 2026-09-29 preview: `BASIC_SMOKE_PREVIEW_PASSED_NO_ORDER` at 18:38:45Z, observed ask 83569.9, spread 2.864bps, calculated provider-metadata minimum ~1.00668 USD. Official Alpaca crypto documentation (https://docs.alpaca.markets/us/docs/crypto-trading-1) describes roughly $10 dynamic USD pair minimum; this discrepancy warrants caution, never a relaxed internal rule. The diagnostic $15 floor is intentionally unchanged, and all broker/account/quote inputs are rechecked freshly immediately before any authorized POST.

All tests use new fake-only in-memory or temporary private SQLite, injection of fake HTTP transports and a blocked production HTTP opener. They do NOT run a real broker order, access Keychain or alter the owner's Mac observer.

## Reconciled with deferred provider crypto fee (2026-09-29)

The operator completed the first real Alpaca PAPER diagnostic BUY:
`svsmk-20260929T184805Z-8ff526d8`, $15 notional. Broker initially accepted;
`paper_smoke_once --reconcile` subsequently returned
`PAPER_ORDER_RECONCILED` and `pending_fee_audits: 1`. This means the real
provider order, fill and net BTC inventory were audited and the buy fee was
inferred provisionally from physical net inventory. It does **not** mean the
later provider CFEE/FEE activity has yet been finalized or that P&L is final.
No second order is authorized.

A corrected manual `--reconcile` invocation, if already reconciled with one
pending fee, now performs GET-only re-verification of the **same** filled
broker order (exact client ID, broker ID, quantity and average price), PAPER
account active status, absence of external open orders or positions and exact
BTC inventory against the logical ledger. It then reads only this order's
provider fee activities. If no fee activity is available it reports
`PAPER_ORDER_RECONCILED_FEE_STILL_PENDING` and **does not** interpret missing
activity as a zero fee or change the provisional accounting. If CFEE/FEE
arrives with exact base-asset amount matching the position-inferred BTC fee,
the existing atomic fee settlement adjusts only the USD-equivalent valuation
and emits `PAPER_ORDER_RECONCILED_FEE_FINALIZED` with zero pending audits.
If any provider state or fee amount conflicts, it fails closed, preserves the
pending ledger entry, and requires manual review. Subsequent no-pending calls
return `ALREADY_RECONCILED_FEES_FINAL` without accessing Keychain.

Fee finalization is **not** a broker POST, sell, second trade or autonomous
loop. The code and tests use only injected fake transports in CI; owner chooses
if/when to run the GET-only command on their Mac. Do not rerun `--execute`.
