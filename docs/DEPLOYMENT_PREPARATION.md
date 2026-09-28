# Single-host PAPER deployment preparation — not activated

Scope: example systemd unit templates under `ops/systemd/`; no cloud account,
paid service, broker credentials or external trading has been accessed.
This design is an operator-supervised single-host paper pilot; SQLite WAL and
an OS file lock protect one process but do not provide high availability,
multiple-worker safety, geographic replication or a PostgreSQL replacement.

Before deploying: verify official Alpaca PAPER account constraints via
`python -m signal_vault.paper_smoke` using securely supplied PAPER-only keys;
check source/schema/fee assumptions, dynamic BTC/USD minimum order sizing,
read-only bars/latest-quote shapes, time sync, disk headroom, and persistent
private backup location. **Do not configure the paper-order POST acknowledgment**
during initial integration.

Suggested Linux layout after separate owner approval:

- Unprivileged service user `signalvault`, install source and private Python
  environment under `/opt/signal-vault`, inaccessible to unrelated users.
- `/var/lib/signal-vault` owned by `signalvault`, mode `0700`; SQLite ledger,
  health, lock and alert files are owner-only.
- `/etc/signal-vault/paper.env`: root-owned, mode `0600`, only PAPER credentials;
  `/etc/signal-vault/monitor.env`: separate secret, generated locally, with
  `SIGNAL_VAULT_OPERATOR_TOKEN` 32+ random chars. Neither file is tracked.
- Initialize ledger *once* as `signalvault` using
  `python -m signal_vault.init_paper --db /var/lib/signal-vault/paper.sqlite3`.
- Run `python -m signal_vault.preflight --db ...` before each start. This is
  local read-only; any unresolved orders are flagged for same-ID provider lookup
  by the separate audited recovery module, **never blind resubmission**.
- Review example units before copying them into systemd. The paper worker unit
  defaults to *read-only broker interaction* and stays stopped on intentional
  fail-closed exit. The monitor binds ONLY to 127.0.0.1 with Basic auth.
- Rotate backups under separately restricted storage; do not place backup files
  in public static hosting or append them to GitHub releases.

Go-live gate for genuine PAPER service: (1) authenticated read-only smoke,
(2) current provider metadata and real API schema checks, (3) current risk
limits verified, (4) backup/restore incident drill with execution halted,
(5) completed failure-injection tests, (6) explicit owner cloud authorization.
Live-money trading is not implemented or approved. PostgreSQL critical-ledger
transactional port remains a separate deliverable before any multi-host setup.
