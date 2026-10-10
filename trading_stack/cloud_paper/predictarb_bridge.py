"""Bounded read-only PredictArb scans; no wallet, orders, merges or extra capital."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, ROUND_CEILING
import json
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .providers import NoRedirect, ProviderError
from .store import encoded
from .predictarb.config import Config
from .predictarb.scanner import Scanner


class PublicHTTP:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(4)

    async def request(self, url, body=None, headers=None):
        parsed = urlsplit(url)
        if body is not None or headers or parsed.scheme != "https" or parsed.netloc not in ("gamma-api.polymarket.com", "clob.polymarket.com"):
            raise PermissionError("PredictArb integration permits public GET requests only")
        def get():
            with build_opener(NoRedirect).open(Request(url, headers={"Accept": "application/json", "User-Agent": "SignalVault-Research/3"}), timeout=4) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ProviderError("PredictArb response too large")
            return json.loads(raw)
        async with self.semaphore:
            return await asyncio.to_thread(get)


def audit(opportunity, now, config):
    y, n = opportunity.yes_book, opportunity.no_book
    if y.condition != n.condition or y.token == n.token:
        return "Non-complementary book identity"
    ages = [now-y.timestamp, now-n.timestamp]
    if max(ages) > config.MAX_BOOK_AGE or min(ages) < -.25:
        return "Stale or future source timestamps"
    if abs(y.timestamp-n.timestamp) > config.MAX_BOOK_SKEW:
        return "Asynchronous source snapshots"
    if opportunity.net_edge < config.MIN_NET_EDGE:
        return "Edge below threshold after depth, fees and operational allowances"
    return None


class PredictArb:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        self.cfg = store.read()["config"]
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="predictarb-read")
        self.future = None
        self.store.db.execute("CREATE TABLE IF NOT EXISTS arbitrage_observations(id INTEGER PRIMARY KEY, at REAL NOT NULL, payload TEXT NOT NULL)")

    def scan(self, offset=0):
        async def run():
            c = Config(MARKET_PAGES=1, MARKET_LIMIT=self.cfg["predictarb_market_limit"])
            scanner = Scanner(c, PublicHTTP())
            scanner.offset = offset
            queue = await scanner.scan()
            now = self.clock()
            rows = []
            for o in queue:
                rejection = audit(o, now, c)
                rows.append(dict(condition=o.market.condition, slug=o.market.slug, question=o.market.question,
                    direction=o.direction, yes_price=str(o.yes_ask), no_price=str(o.no_ask), price_side="bid" if o.direction=="split_then_sell" else "ask", quantity=str(o.quantity),
                    gross_edge=str(o.gross_edge), net_edge=str(o.net_edge), modeled_cost=str(o.cost),
                    modeled_fees=str(o.fees), source_times=[o.yes_book.timestamp,o.no_book.timestamp],
                    snapshot_key=o.key, status="REJECTED" if rejection else "QUALIFIED_RESEARCH_ONLY",
                    reason=rejection or "Execution, leg risk and collateral conversion unverified; no orders submitted"))
            return dict(at=now, observations=rows, coverage=scanner.metrics, next_offset=getattr(scanner,"next_offset",0))
        return asyncio.run(run())

    def tick(self):
        now = self.clock()
        if self.future and self.future.done():
            try:
                result = self.future.result()
                status = dict(status="RESEARCH", mode="READ-ONLY PUBLIC BOOKS", checked_at=now,
                    last_success=result["at"], opportunities=len(result["observations"]), coverage=result["coverage"],
                    reason="No execution or capital allocation; quoted edges are hypotheses")
                with self.store.transaction():
                    for row in result["observations"]:
                        self.store.db.execute("INSERT INTO arbitrage_observations(at,payload) VALUES(?,?)",(result["at"],encoded(row)))
                    self.store.db.execute("DELETE FROM arbitrage_observations WHERE id NOT IN (SELECT id FROM arbitrage_observations ORDER BY id DESC LIMIT 5000)")
                    s=self.store.read();s["providers"]["polymarket"]=status;s["predictarb_offset"]=result["next_offset"];self.store.save(s)
            except Exception as error:
                with self.store.transaction():
                    s=self.store.read();s["providers"]["polymarket"]=dict(status="UNAVAILABLE",mode="READ-ONLY PUBLIC BOOKS",checked_at=now,
                        reason="Public scan failed: "+type(error).__name__+ (" HTTP "+str(error.code) if hasattr(error,"code") else ""));self.store.save(s)
            self.future=None
        s=self.store.read()
        if self.future is None and now-s.get("predictarb_last_scan",0)>=self.cfg["predictarb_scan_interval_seconds"]:
            self.future=self.pool.submit(self.scan,s.get("predictarb_offset",0))
            with self.store.transaction():
                s=self.store.read();s["predictarb_last_scan"]=now
                s["providers"].setdefault("polymarket",dict(status="SCANNING",mode="READ-ONLY PUBLIC BOOKS",checked_at=now))
                self.store.save(s)
        p=self.store.read()["providers"].get("polymarket",{})
        return [dict(market="polymarket",pair="YES/NO complete sets",execution=p.get("status","SCANNING"),
            reason=p.get("reason","Public book research in progress; no orders or extra account"))]

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)
