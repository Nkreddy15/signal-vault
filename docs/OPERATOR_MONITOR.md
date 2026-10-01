# Signal Vault private operator monitor (Phase 2G)

This is a **local-only**, authenticated, **read-only** observation page over the
PAPER SQLite ledger. It cannot place, cancel or approve broker orders; it cannot
halt/resume trading (use `signal_vault.control` in the terminal with local access).
It has no broker imports, broker tokens, model subscriptions, or external API calls.

## Offline local demonstration (no Alpaca connection)

```bash
mkdir -p ./data  # for private host use: chmod 700 ./data
chmod 700 ./data
PYTHONPATH=src python3 -m signal_vault.init_paper --db ./data/signal-vault-paper.sqlite3
PYTHONPATH=src python3 -m signal_vault.preflight --db ./data/signal-vault-paper.sqlite3
# Generate a strong token locally; never paste it in this chat or commit it.
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
# Export SIGNAL_VAULT_OPERATOR_TOKEN privately in the local shell (32+ chars).
PYTHONPATH=src python3 -m signal_vault.operator_server --db ./data/signal-vault-paper.sqlite3
```

Open `http://127.0.0.1:8766` on that machine and authenticate as username
`operator` with your generated token as password. JSON snapshot is available at
`/api/status` behind the exact same HTTP Basic authentication. Do not place
credentials in URL query parameters, source code, screenshots, tracked .env or
shell histories. Token-based Basic authentication is only acceptable here because
requests cannot bind beyond IPv4 loopback: it is **not an HTTPS public service**.
For remote viewing, use trusted SSH port forwarding and host security instead
of directly exposing port 8766 (e.g. `ssh -L 8766:127.0.0.1:8766 user@trusted-host`).
The deployment has not been performed or authorized.

The page displays only: local logical cash, reserved/unreserved cash, BTC units,
realized ledger P&L, accumulated fee equivalents, order-state counts and event
types/timestamps. It intentionally omits provider account IDs, raw event JSON,
client order IDs, secrets, quotes and any claim of current market equity/returns.
Balances may be stale if the writer is not running; the ledger update timestamp
makes that visible. It cannot establish genuine brokerage paper fills or gains.

Health snapshots from the paper daemon are a distinct locally written file;
this monitor does not trust unaudited HTTP inputs as financial records.

## Snapshot backups

After an initialized local paper ledger exists:

```bash
PYTHONPATH=src python3 -m signal_vault.local_backup \
 --db ./data/signal-vault-paper.sqlite3 \
 --destination ./data/backups/paper-YYYYMMDD-HHMM.sqlite3
```

Backups use SQLite's online backup API (not a raw `.db` file copy), check
integrity, use owner-only mode 0600, and cannot overwrite an existing filename.
**Never automatically resume trading by restoring an old snapshot:** an order
may have been sent after that backup. Emergency recovery must keep execution
halted until broker orders, fills, cash and position are reconciled independently.

The private read-only HTML monitor deliberately uses local port **8766**. A
separate optional owner-control JSON API uses local port **8765**; it can
persistently halt/resume PAPER operation with a different Bearer token. Neither
should be placed directly on a public Internet listener. The owner-control
GET endpoints use the read-only snapshot path and cannot silently create a new
ledger if the real journal is missing.


## All-market forward dashboard

When the forward evidence root is available, start the same private monitor with:

```bash
PYTHONPATH=src python3 -m signal_vault.operator_server \
  --db ./data/signal-vault-paper.sqlite3 \
  --forward-root /var/lib/signal-vault/forward
```

Authenticated routes:
- `/all-markets` — read-only HTML for six-crypto, US equities and Kalshi.
- `/api/all-markets` — the same safe snapshot as JSON.

The all-market routes read only persisted forward evidence. They make no provider
requests, read no API credentials, and cannot submit PAPER, DEMO or LIVE orders.
The monitor still binds only to literal `127.0.0.1`; remote/public exposure needs
a separately reviewed authenticated TLS gateway and is not part of this phase.
