# ADR 0001: Paper-only Phase 1 with no live escape hatch

Date: 2026-09-28. Status: ACCEPTED.

**Context:** Owner authorized architecture and initial build, expressly limiting all execution to paper. An `.env` toggle from `paper` to `live` can cause accidental financial harm.

**Decision:** Phase 1 supports only offline dry-run and refuses a non-paper mode, non-local broker or requested network order submission. No live API endpoint or live broker adapter is present. A later *paper broker* adapter requires its own integration review and hard-pinned sandbox endpoint. A potential live runtime would be separately coded, independently deployed and require fresh owner authorization.

**Consequence:** External brokerage paper orders are intentionally not placed by the Phase 1 CLI. Dry-run receipts are never fills.
