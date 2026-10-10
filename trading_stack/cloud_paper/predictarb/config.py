"""Scanner parameters only: no second account, execution or metered AI settings."""
from dataclasses import dataclass
from decimal import Decimal as D

@dataclass(frozen=True)
class Config:
    DATA_SOURCE: str = "PUBLIC"
    GAMMA_URL: str = "https://gamma-api.polymarket.com"
    CLOB_URL: str = "https://clob.polymarket.com"
    MARKET_LIMIT: int = 8
    MARKET_PAGES: int = 1
    PAIR_SHARES: D = D("10")
    MIN_NET_EDGE: D = D("0.02")
    MAX_SLIPPAGE: D = D("0.002")
    MERGE_COST: D = D("0.01")
    MAX_BOOK_AGE: float = 2.0
    MAX_BOOK_SKEW: float = 0.5
    DEMO_PARTIAL_LEG: bool = False
