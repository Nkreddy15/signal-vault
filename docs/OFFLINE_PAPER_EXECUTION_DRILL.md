# Phase 3 — isolated synthetic paper execution drill

New opt-in command:

```sh
PYTHONPATH=src python -m signal_vault.paper_execution_drill
```

This runs five synthetic acceptance scenarios using **fresh in-memory SQLite journals** and injected fake transports. It uses no macOS Keychain, account/network access, persisted source journal, trading credential or actual Alpaca POST, and does **not** modify the installed minute :07 collector.

Scenarios:
1. Approved $15 draft is durably transitioned to SUBMISSION_PENDING before fake transport. An accepted response is **not** misrepresented as a fill; duplicate same-ID submission is rejected.
2. An injected timeout becomes UNKNOWN_RESULT with reservation retained; missing read-only lookup never triggers a POST retry; a later matching lookup can recover the order's accepted state.
3. Mismatched broker-returned client ID remains UNKNOWN, never fabricated as a fill.
4. An invalid $100 payload is rejected before even fake transport and does not advance an approved draft's state.
5. Even a fake broker terminal "filled" response remains BROKER_TERMINAL_UNRECONCILED with reservation retained until independent provider audit (which this drill does NOT simulate as completed).

Expected result: `PASS_FAKE_PROVIDER_STATE_TRANSITIONS_ONLY`. These are fake-provider engineering tests and **not** a genuine paper order, paper fill, P&L, strategy promotion, provider permission to trade, or production restoration.

The separate offline `phase3_readiness` report formerly showed `SEPARATE_PAPER_TRADING_ACCOUNT_GET_PREFLIGHT_NOT_PERFORMED` even after an owner had run the successful separate `paper_account_get_preflight`. That was semantically wrong: the offline report simply cannot observe a standalone GET unless its result is independently tracked. It now reports `SEPARATE_PAPER_ACCOUNT_GET_RESULT_NOT_TRACKED_BY_OFFLINE_REPORT`, while preserving `provider_trading_account_checked: false` scoped to the current **offline** invocation. An owner-reported successful PAPER account GET is a real operational milestone; the offline report does not attest it or permit orders.

Owner-reported September 29 milestones (not independently executable from GitHub): automatic Mac LaunchAgent bootstrap at 18:07:45Z, isolated auto journal with 0 prospective observations (correct); separate PAPER ledger initialization and offline preflight PASS, 0 unresolved orders; separate `paper_account_get_preflight` result `BASIC_PAPER_ACCOUNT_GET_CHECK_PASSED`, no reason codes and no order POST. First **consecutive** unattended observation remains to be shown with its own subsequent tick receipt.

Next paper-order engineering milestone remains a separately authorized **supervised actual Alpaca PAPER smoke**, following exact order-size/current-quote/venue-rule checks, with no autonomous strategy order promotion. No real-money connector exists.
