# Threat model and security requirements

**Current deployment state:** offline dry run only. A reviewed-in-progress paper-host-only POST module now exists but has NEVER run with real credentials; no authenticated broker calls, hosting or funded account.

| Failure / attacker scenario | Mandatory control / test |
|---|---|
| An environment variable enables live trading | Phase 1 refuses anything except `paper` and `local_dry_run`; CI negative tests. Live must be separate future code/release. |
| AI prompt injection tells executor to exceed limits | AI has no broker tool or credential; schema-validated `TradeIntent` is checked by the deterministic Guardian. |
| API request times out but exchange accepted order | Persist unique client order ID; reconcile with provider *before* retry; no blind retry. |
| Two workers buy simultaneously | Owner-only OS file leadership lock plus SQLite transaction lock, reserve funds, durable unique order id and pending-order exposure included in risk check. One-cycle worker and daemon share the same lock path. |
| Quote is delayed or missing | Age threshold; fail closed and pause new entries. |
| Price gaps or insufficient liquidity | Conservative position/exposure caps, slippage check, acknowledge stops cannot guarantee a loss ceiling. |
| Startup after process crash | Recover unresolved orders; reconcile broker state before scanning or new buys. |
| Keys published in repo or chat | Gitignore `.env` and secrets; env/secret-manager retrieval in deployment; rotate upon leak; do not ask user to paste key into chat. |
| Withdrawal / account takeover | Never request withdrawal scopes, bank credentials or wallet seed phrase; restrict broker authorization wherever the provider allows. |
| Fake performance metrics | Fills and fees are the source of realized P&L; submit != fill; label dry-run/paper/live prominently. |
| Unexpected costs | User must approve paid services; cloud/API budgets and alerts; no autonomous purchasing. |
| Model drift / self-modification | Immutable versioned live strategy, shadow testing, separate operator approval for promotion. |

## Operator actions planned

- Emergency halt is durable, auditable and stops new order submissions. The unattended scheduler rechecks it at least once per minute while halted.
- It does **not** automatically liquidate positions; liquidation is its own controlled function subject to actual provider status.
- Alerts for account reconciliation drift, API authorization failure, missing data, and a breached limit.
- Every proposed order linked to market-data timestamp, strategy version, risk policy version and source signal.

- Runtime health is written atomically to an owner-only JSON file with logical portfolio metrics only; provider account IDs, credentials and raw exception/provider bodies are excluded.
- Local alert JSONL records only classified state transitions and safe identifiers; external notification integrations remain unconfigured until separately authorized.
- An unexpected scheduler exception writes `BLOCKED_RUNTIME_EXCEPTION`, stops the loop, and requires operator review rather than continuing in an unknown state.

## Security gate before activating the paper broker writer

Test invalid `mode`, unexpected API hostname, missing credentials, stale quote, concurrent duplicate IDs, unknown submission status, partial fills, disconnect during submit and a recovery loop. No live API URL or trading credential should appear in Phase 1 code or tracked examples.
