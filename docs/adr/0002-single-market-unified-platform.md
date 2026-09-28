# ADR 0002: Unified platform architecture, one active market initially

Date: 2026-09-28. Status: ACCEPTED.

**Context:** Owner wants Signal Vault, not a disposable BTC bot, but only $100 eventual live capital and a November 1 development target.

**Decision:** Build common domain, risk, event journal, portfolio and execution interfaces with independent venue adapters. First operational route is BTC/USD via Alpaca paper; stocks and event contracts are documented expansion adapters, not falsely advertised working integrations.

**Consequence:** Future venues must implement their own order validity, settlement, minimum size and normalized risk. Do not split the initial $100 across unvalidated venues.
