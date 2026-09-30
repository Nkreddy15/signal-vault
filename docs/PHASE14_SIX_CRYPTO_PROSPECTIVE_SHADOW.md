# Phase 14 — six-crypto SHA-bound shadow evaluator (NO trading)

Phase 13 introduced a separate **unactivated** source collector for six
cryptocurrencies with its own private persistent-volume root. Its first
72h-per-asset DATA GET is retrospectively labeled HISTORY, and only the
next genuinely observed, contiguous UTC hourly capture can add
**six prospective asset-bars / one independent prospective UTC hour**.

This phase adds `six_crypto_shadow.py`. It reads and independently verifies
the complete append-only Phase 13 SHA-linked source receipt chain WITHOUT
credentials, provider requests, secrets, account state, active portfolio,
broker endpoints, execution paths or changes to original historical bars.

**A historical bootstrap alone can NEVER generate a new shadow receipt.**
After at least one genuinely prospective captured UTC close, the evaluator
uses only the current contiguous collector segment: 72 retrospective
indicator warmup bars + each independently timestamp-validated one-hour
prospective source record. It revalidates per-symbol OHLCV, provenance,
feed, historical-vs-forward capture-time eligibility, final closed-hour
boundaries and original source receipt SHA before computing any signal.

The four unchanged fixed research hypotheses (cash, passive, EMA12/26
and 24-hour momentum) each produce *two entirely hypothetical*
next-open decisions for each of the six symbols: a flat account state
and an already-held account state (6 x 4 x 2 = **48 distinct research
state-dependent decisions**, including HOLD). These are not observed
provider positions, trade instructions, validated forecasts or
permission to submit orders.

Each shadow is bound to the original source receipt SHA, source batch
SHA, per-symbol full segment dataset SHA and evidence SHA. It is
archived create-only as a private 0600 JSON source under
`immutable-six-crypto-shadows/shadow-hour-YYYYMMDDTHHMMZ.json`.
An identical same-hour retry is safe and idempotent; any competing or
tampered destination FAILS CLOSED without overwriting prior evidence.

The unactivated six-market Railway adapter invokes this **keyless**
shadow step only AFTER a genuinely new source receipt has durably
committed. An identical same-UTC-hour duplicate can retry an interrupted
shadow write, with ZERO new provider DATA requests. If a shadow fails
after source commit, its status explicitly reads
`SOURCE_COMMITTED_SHADOW_ARCHIVE_BLOCKED_SAFE_TO_RETRY`: it must NEVER
falsely claim the source observation was not created. A source data
gap starts a new retrospective-only segment and does not produce
hindsight BUY/SELL signals.

All real and prospective source observations remain independent of
the original currently running BTC-only Railway journal. This phase
does not create or deploy a second Railway service, attach a volume,
change an existing cron, copy credentials, purchase SIP, send PAPER
orders or activate LIVE execution. Source and shadow security tests
cover no-retrospective signals, 48 fully closed hypothetical state
decisions, audit-bound output, same-hour idempotency, missed-hour
rebootstrap, immutable tamper refusal and source/analysis crash
separation.
