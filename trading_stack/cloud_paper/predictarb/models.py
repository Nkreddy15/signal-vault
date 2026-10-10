from dataclasses import dataclass, asdict
from decimal import Decimal
import time
D = Decimal

def decimal(v):
    x = D(str(v))
    if not x.is_finite(): raise ValueError("Non-finite number")
    return x

@dataclass
class Market:
    slug: str
    condition: str
    yes: str
    no: str
    question: str
    fee_rate: Decimal
    min_size: Decimal = D("5")

@dataclass
class Book:
    token: str
    condition: str
    asks: list
    bids: list
    timestamp: float
    received: float
    fingerprint: str
    min_size: Decimal = D("5")
    tick: Decimal = D("0.01")

    def sweep(self, quantity, side="asks", limit=None, haircut=D("1")):
        remaining, cost, filled, worst = quantity, D(0), D(0), D(0)
        levels = sorted(getattr(self, side), key=lambda x:x[0], reverse=side=="bids")
        for price, size in levels:
            if limit is not None and ((side=="asks" and price>limit) or (side=="bids" and price<limit)): break
            take = min(remaining, size*haircut)
            if take<=0: continue
            cost += take*price; filled += take; remaining -= take; worst=price
            if remaining<=0: break
        return filled, cost, worst

@dataclass
class Opportunity:
    market: Market
    yes_book: Book
    no_book: Book
    quantity: Decimal
    yes_ask: Decimal
    no_ask: Decimal
    gross_edge: Decimal
    net_edge: Decimal
    cost: Decimal
    fees: Decimal
    yes_limit: Decimal
    no_limit: Decimal
    key: str
    direction: str = "buy_complete_set"

def encode(obj):
    if isinstance(obj,D): return str(obj)
    if hasattr(obj,"__dataclass_fields__"): return asdict(obj)
    raise TypeError(type(obj).__name__)
