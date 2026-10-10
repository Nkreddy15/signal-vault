"""Transactional ledger and durable commands. All financial writes have one worker."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
import shutil
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

TERMINAL = {"filled", "canceled", "rejected", "expired"}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def number(value, minimum=0):
    n = float(value)
    if not math.isfinite(n) or n < minimum:
        raise ValueError("Invalid nonnegative finite amount")
    return n


class Store:
    def __init__(self, directory, config=None, now=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "campaign.sqlite3"
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS commands(id INTEGER PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, at REAL NOT NULL, action TEXT NOT NULL, trade_id TEXT, handled REAL);
          CREATE TABLE IF NOT EXISTS candles(market TEXT, symbol TEXT, timeframe TEXT, at REAL, payload TEXT NOT NULL, PRIMARY KEY(market,symbol,timeframe,at));
          CREATE TABLE IF NOT EXISTS equity(at REAL PRIMARY KEY, value REAL NOT NULL, cash REAL NOT NULL, exposure REAL NOT NULL, drawdown REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS quotes(market TEXT, symbol TEXT, at REAL, bid REAL NOT NULL, ask REAL NOT NULL, PRIMARY KEY(market,symbol,at));
        """)
        self.path.chmod(0o600)
        if not self.db.execute("SELECT 1 FROM state").fetchone():
            if config is None:
                raise ValueError("Campaign is not initialized")
            now = time.time() if now is None else now
            capital = number(config["capital"], 1)
            self.save(dict(config=config, config_hash=digest(config), campaign_id=os.urandom(8).hex(),
                started_at=now, deadline=now+config["duration_hours"]*3600, cash=capital,
                peak=capital, day=int(now//86400), day_equity=capital, paused=False, emergency=False,
                halt=None, daily_halt=False, positions={}, closed=[], orders={}, signals=[],
                heartbeat=None, last_cycle=None, cycles=0, providers={}, diagnostics=[],
                marks={}, realized=0, fees=0, turnover=0, reconciliation={}, errors=[]))
        state = self.read()
        if config is not None and state["config_hash"] != digest(config):
            raise ValueError("Frozen campaign configuration changed; existing account is never reset")

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def read(self):
        return json.loads(self.db.execute("SELECT payload FROM state WHERE id=1").fetchone()[0])

    def save(self, state):
        self.db.execute("INSERT OR REPLACE INTO state VALUES(1,?)", (encoded(state),))

    def event(self, kind, payload, now):
        self.db.execute("INSERT INTO events(at,kind,payload) VALUES(?,?,?)", (now, kind, encoded(payload)))

    def command(self, action, request_id, trade_id=None, now=None):
        if action not in ("pause", "resume", "flatten", "close"):
            raise ValueError("Unknown paper control")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 80:
            raise ValueError("Idempotency key required")
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO commands(request_id,at,action,trade_id) VALUES(?,?,?,?)",
                            (request_id, now or time.time(), action, trade_id))
        return self.db.execute("SELECT id FROM commands WHERE request_id=?", (request_id,)).fetchone()[0]

    def apply_commands(self, now):
        with self.transaction():
            s = self.read()
            for c in self.db.execute("SELECT * FROM commands WHERE handled IS NULL ORDER BY id").fetchall():
                action = c["action"]
                if action == "pause": s["paused"] = True
                if action == "resume" and not s["halt"] and not s["emergency"] and now < s["deadline"]:
                    s["paused"] = False
                if action == "flatten":
                    s.update(paused=True, emergency=True)
                    for p in s["positions"].values(): p["exit_requested"] = "EMERGENCY_FLATTEN"
                if action == "close" and c["trade_id"] in s["positions"]:
                    s["positions"][c["trade_id"]]["exit_requested"] = "OWNER_CLOSE"
                self.event("CONTROL", dict(action=action, trade_id=c["trade_id"]), now)
                self.db.execute("UPDATE commands SET handled=? WHERE id=?", (now, c["id"]))
            self.save(s)

    def prepare(self, order, now):
        """Commit intent before network I/O. Atomic portfolio reservations."""
        if order["action"] not in ("buy", "sell"):
            raise ValueError("Only owned long buys/sells are supported")
        number(order["quantity"], 1e-12); number(order["limit_price"], 1e-12)
        number(order["reserve"]); number(order["fee_rate"])
        if order["action"] == "buy" and order["reserve"]+1e-8 < order["quantity"]*order["limit_price"]:
            raise ValueError("Order must reserve at least its full notional")
        with self.transaction():
            s = self.read()
            if order["id"] in s["orders"]:
                return False
            if order["action"] == "buy":
                if s["paused"] or s["emergency"] or s["halt"] or s["daily_halt"] or now >= s["deadline"]:
                    return False
                if order["signal"] in s["signals"]:
                    return False
                if any(p["market"] == order["market"] and p["symbol"] == order["symbol"] for p in s["positions"].values()):
                    return False
                pending = [o for o in s["orders"].values() if o["action"] == "buy" and o["status"] not in TERMINAL]
                if any(o["market"] == order["market"] and o["symbol"] == order["symbol"] for o in pending):
                    return False
                reserve = sum(o["reserve"] for o in pending)
                exposure = sum(p["quantity"]*p["entry_price"] for p in s["positions"].values())
                cfg = s["config"]
                equity = portfolio(s, now)["equity"]
                if len(s["positions"])+len(pending) >= cfg["max_positions"]:
                    return False
                if order["reserve"] > min(s["cash"]-reserve, equity*cfg["max_position_fraction"], equity*cfg["max_exposure_fraction"]-exposure-reserve)+1e-8:
                    return False
                s["signals"].append(order["signal"])
            else:
                p = s["positions"].get(order["trade_id"])
                if not p or order["quantity"] > p["quantity"]+1e-8:
                    return False
                if any(o["trade_id"] == order["trade_id"] and o["action"] == "sell" and o["status"] not in TERMINAL for o in s["orders"].values()):
                    return False
            s["orders"][order["id"]] = dict(order, status="prepared", filled_qty=0, filled_value=0, fee=0,
                                              created_at=now, updated_at=now, provider_id=None)
            self.event("ORDER_PREPARED", s["orders"][order["id"]], now)
            self.save(s)
            return True

    def order_status(self, oid, status, now, provider_id=None):
        with self.transaction():
            s = self.read(); o = s["orders"][oid]
            if o["status"] in TERMINAL: return
            o.update(status=status, updated_at=now)
            if provider_id: o["provider_id"] = provider_id
            self.event("ORDER_STATUS", dict(id=oid, status=status, provider_id=provider_id), now)
            self.save(s)

    def observe(self, oid, observation, now):
        """Apply cumulative fills once, including partial fills on terminal orders."""
        with self.transaction():
            s = self.read(); o = s["orders"][oid]
            if observation["client_id"] != oid:
                raise ValueError("Provider order identity mismatch")
            if o["provider_id"] and observation.get("provider_id") != o["provider_id"]:
                raise ValueError("Provider order ID changed")
            fq = number(observation["filled_qty"]); fv = number(observation["filled_value"])
            fee = number(observation["fee"]); status = observation["status"]
            if fq > o["quantity"]+1e-8 or status not in TERMINAL | {"accepted", "partial", "pending_cancel", "unknown"}:
                raise ValueError("Invalid provider fill/status")
            if fq < o["filled_qty"]-1e-8 or fv < o["filled_value"]-1e-8 or fee < o["fee"]-1e-8:
                raise ValueError("Non-monotonic provider observation")
            if status == "filled" and abs(fq-o["quantity"]) > 1e-8:
                raise ValueError("Filled status with incomplete quantity")
            if o["status"] in TERMINAL and (fq != o["filled_qty"] or fv != o["filled_value"] or fee != o["fee"] or status != o["status"]):
                raise ValueError("Terminal order changed; reconciliation required")
            dq, dv, df = fq-o["filled_qty"], fv-o["filled_value"], fee-o["fee"]
            if (dq > 0 and dv <= 0) or (dq == 0 and dv != 0):
                raise ValueError("Missing or inconsistent fill cost")
            tid = o["trade_id"]
            if o["action"] == "buy":
                s["cash"] -= dv+df
                if dq:
                    p = s["positions"].setdefault(tid, dict(id=tid, market=o["market"], symbol=o["symbol"],
                        mode=o["mode"], quantity=0, bought_qty=0, cost=0, entry_fee=0, exit_fee=0, proceeds=0,
                        opened_at=now, strategy=o["strategy"], signal_at=o["signal_at"], reason=o["reason"],
                        stop=o.get("stop"), initial_stop=o.get("stop"), target=o.get("target"), peak=0,
                        stop_distance=o.get("stop_distance"), contract=o.get("contract"), fills=[]))
                    p.setdefault("trailing_activation_multiple",o.get("trailing_activation_multiple",1))
                    p.setdefault("trailing_distance_multiple",o.get("trailing_distance_multiple",1))
                    p["quantity"] += dq; p["bought_qty"] += dq; p["cost"] += dv
                    p["entry_price"] = p["cost"]/p["bought_qty"]
                if tid in s["positions"]: s["positions"][tid]["entry_fee"] += df
            else:
                p = s["positions"].get(tid)
                if dq and (not p or dq > p["quantity"]+1e-8):
                    raise ValueError("Sell exceeds owned position")
                s["cash"] += dv-df
                if p:
                    p["quantity"] = max(0, p["quantity"]-dq)
                    p["proceeds"] += dv; p["exit_fee"] += df
            p = s["positions"].get(tid)
            if p and dq:
                receipts=observation.get("executions")
                if receipts is not None:
                    recorded={f.get("provider_fill_id") for f in p["fills"]}
                    fresh=[f for f in receipts if f["provider_fill_id"] not in recorded]
                    if abs(sum(f["quantity"] for f in fresh)-dq)>1e-8:
                        raise ValueError("Execution receipts do not match incremental quantity")
                    p["fills"].extend(dict(f,order_id=oid,observed_at=now,action=o["action"],time_basis="provider execution") for f in fresh)
                else:
                    p["fills"].append(dict(order_id=oid, at=observation.get("filled_at") or now, observed_at=now,
                        time_basis="quote-derived simulated fill; no on-chain transaction" if o["market"]=="dex" else "internal simulation execution" if o["market"]=="crypto" else "provider completed order" if observation.get("filled_at") else "cumulative fill observed; exact execution time unavailable",
                        action=o["action"], quantity=dq, price=dv/dq, fee=df))
            if p and p["quantity"] <= 1e-9:
                p.update(closed_at=now, exit_reason=o["reason"], exit_price=p["proceeds"]/p["bought_qty"],
                         net_pnl=p["proceeds"]-p["cost"]-p["entry_fee"]-p["exit_fee"])
                s["closed"].append(p); s["realized"] += p["net_pnl"]; del s["positions"][tid]
            o.update(status=status, filled_qty=fq, filled_value=fv, fee=fee, updated_at=now,
                     provider_id=observation.get("provider_id") or o["provider_id"])
            o["reserve"] = 0 if status in TERMINAL else max(0, (o["quantity"]-fq)*o["limit_price"]*(1+o["fee_rate"]))
            s["fees"] += df; s["turnover"] += dv
            if s["cash"] < -1e-6: s["halt"] = "CASH_DEFICIT_RECONCILIATION"
            self.event("ORDER_OBSERVED", dict(id=oid, **observation), now)
            self.save(s)

    def put_candles(self, market, symbol, timeframe, rows):
        with self.transaction():
            self.db.executemany("INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?)",
                [(market, symbol, timeframe, r["time"], encoded(r)) for r in rows])

    def candles(self, market, symbol, timeframe, limit=400):
        return [json.loads(r[0]) for r in reversed(self.db.execute(
            "SELECT payload FROM candles WHERE market=? AND symbol=? AND timeframe=? ORDER BY at DESC LIMIT ?",
            (market, symbol, timeframe, limit)).fetchall())]

    def backup(self, now):
        dest = self.directory / "backups"; dest.mkdir(exist_ok=True, mode=0o700)
        name = dest / ("campaign-"+time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))+".sqlite3")
        if name.exists(): return name
        # Only rotate this new campaign's own snapshots; never touch old V11/research files.
        older=sorted(dest.glob("campaign-????????T??????Z.sqlite3"))
        while len(older)>2 and (len(older)>=8 or sum(p.stat().st_size for p in older)>120*1024*1024):
            older.pop(0).unlink()
        if shutil.disk_usage(self.directory).free < self.path.stat().st_size+32*1024*1024:
            raise OSError("Insufficient free persistent storage for verified backup")
        temp = name.with_suffix(".tmp")
        with sqlite3.connect(temp) as db:
            self.db.backup(db)
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok": raise ValueError("Backup invalid")
        temp.chmod(0o600); os.replace(temp, name)
        return name


def portfolio(s, now):
    market_value=0; unrealized=0; stale=False; exposure=0
    for p in s["positions"].values():
        q=s["marks"].get(p["market"]+":"+p["symbol"])
        stale |= not q or now-q["at"] > s["config"]["max_quote_age_seconds"]
        mark=q["bid"] if q else p["entry_price"]
        value=p["quantity"]*mark
        rate=s["config"]["crypto_fee_fraction"] if p["market"]=="crypto" else s["config"]["stock_fee_fraction"]
        exit_fee=s["config"]["dex_network_allowance_usd"] if p["market"]=="dex" else math.ceil(100*.07*p["quantity"]*mark*(1-mark))/100 if p["market"]=="kalshi" else value*rate
        market_value += value-exit_fee; exposure += value
        unrealized += p["proceeds"]+value-exit_fee-p["cost"]-p["entry_fee"]-p["exit_fee"]
    reserved=sum(o["reserve"] for o in s["orders"].values() if o["action"]=="buy" and o["status"] not in TERMINAL)
    eq=s["cash"]+market_value
    return dict(equity=eq,cash=s["cash"],available_cash=s["cash"]-reserved,reserved=reserved,
                unrealized=unrealized,realized=s["realized"],net_pnl=eq-s["config"]["capital"],
                exposure=exposure,drawdown=max(0,1-eq/s["peak"]),marks_stale=stale,fees=s["fees"],turnover=s["turnover"])
