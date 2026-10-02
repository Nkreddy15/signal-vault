import os
from decimal import Decimal

from lumibot.brokers import Alpaca
from lumibot.strategies import Strategy
from lumibot.traders import Trader


UNIVERSE = [
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN",
    "META", "GOOGL", "JPM", "V", "AMD", "TSLA",
]


class SignalVaultStockPaperExecutionV1(Strategy):
    """Multi-signal US-equity PAPER execution harness.

    Runs every 15 minutes while the US market is open. It scores a liquid
    universe using independent trend, momentum, breakout and mean-reversion
    evidence, then allocates the fixed logical PAPER budget to the strongest
    positive candidates. This is execution evidence collection, not a claim
    of validated profitability.
    """

    parameters = {
        "universe": UNIVERSE,
        "top_n": 2,
        "logical_budget_usd": Decimal(os.environ.get("STOCK_LOGICAL_BUDGET_USD", "100")),
        "cash_buffer_ratio": Decimal("0.10"),
    }

    def initialize(self):
        self.sleeptime = "15M"
        self.minutes_before_closing = 10

    def _score_symbol(self, symbol):
        intraday = self.get_historical_prices(
            symbol, 50, timestep="15m", include_after_hours=False
        )
        daily = self.get_historical_prices(
            symbol, 25, timestep="day", include_after_hours=False
        )
        if intraday is None or daily is None:
            return None

        ic = intraday.df["close"].dropna()
        dc = daily.df["close"].dropna()
        if len(ic) < 35 or len(dc) < 20:
            return None

        ema5 = ic.ewm(span=5, adjust=False).mean()
        ema13 = ic.ewm(span=13, adjust=False).mean()
        ema34 = ic.ewm(span=34, adjust=False).mean()

        last = Decimal(str(ic.iloc[-1]))
        prev = Decimal(str(ic.iloc[-2]))
        ret3 = Decimal(str(ic.iloc[-1] / ic.iloc[-4] - 1))
        ret12 = Decimal(str(ic.iloc[-1] / ic.iloc[-13] - 1))
        daily20 = Decimal(str(dc.iloc[-1] / dc.iloc[-20] - 1))

        prior_high20 = Decimal(str(ic.iloc[-21:-1].max()))
        mean20 = Decimal(str(ic.iloc[-20:].mean()))
        std20 = Decimal(str(ic.iloc[-20:].std()))
        z20 = Decimal("0") if std20 == 0 else (last - mean20) / std20

        score = 0
        reasons = []

        if ema5.iloc[-1] > ema13.iloc[-1] > ema34.iloc[-1]:
            score += 2
            reasons.append("trend")
        if ret3 > Decimal("0.002") and ret12 > 0:
            score += 2
            reasons.append("momentum")
        if last > prior_high20:
            score += 2
            reasons.append("breakout")
        if z20 < Decimal("-1.25") and last > prev:
            score += 2
            reasons.append("mean_reversion_bounce")
        if daily20 > 0:
            score += 1
            reasons.append("daily_tailwind")
        if ema5.iloc[-1] < ema13.iloc[-1] and ret3 < Decimal("-0.002"):
            score -= 2
            reasons.append("short_term_weakness")

        return {
            "symbol": symbol,
            "score": score,
            "ret3": ret3,
            "last": last,
            "reasons": reasons,
        }

    def on_trading_iteration(self):
        budget = Decimal(self.parameters["logical_budget_usd"])
        if budget <= 0 or budget > Decimal("100"):
            raise ValueError("logical stock paper budget must be within (0, 100]")

        scored = []
        for symbol in self.parameters["universe"]:
            result = self._score_symbol(symbol)
            if result is not None:
                scored.append(result)

        scored.sort(key=lambda row: (row["score"], row["ret3"]), reverse=True)
        winners = [
            row for row in scored
            if row["score"] >= 2
        ][: int(self.parameters["top_n"])]

        winner_symbols = [row["symbol"] for row in winners]
        self.log_message(
            "PAPER stock scores="
            + str([(r["symbol"], r["score"], r["reasons"]) for r in scored])
            + f"; selected={winner_symbols}"
        )

        universe = list(self.parameters["universe"])
        for symbol in universe:
            position = self.get_position(symbol)
            if position is not None and symbol not in winner_symbols:
                qty = abs(float(position.quantity))
                if qty > 0:
                    self.submit_order(self.create_order(symbol, qty, "sell"))

        if not winners:
            self.log_message("No positive multi-signal stock setup; remaining in cash.")
            return

        investable = budget * (Decimal("1") - Decimal(self.parameters["cash_buffer_ratio"]))
        target_value = investable / Decimal(len(winners))

        for row in winners:
            symbol = row["symbol"]
            price_raw = self.get_last_price(symbol)
            if price_raw is None:
                continue
            price = Decimal(str(price_raw))
            if price <= 0:
                continue

            target_qty = float((target_value / price).quantize(Decimal("0.0001")))
            position = self.get_position(symbol)
            current_qty = float(position.quantity) if position is not None else 0.0
            diff = round(target_qty - current_qty, 4)

            if abs(diff) * float(price) < 1.0:
                continue
            side = "buy" if diff > 0 else "sell"
            self.submit_order(self.create_order(symbol, abs(diff), side))


def main():
    if os.environ.get("ALPACA_IS_PAPER", "true").lower() != "true":
        raise RuntimeError("Signal Vault stock harness is PAPER-only.")

    key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        raise RuntimeError("Alpaca PAPER API key and secret are required.")

    broker = Alpaca({"API_KEY": key, "API_SECRET": secret, "PAPER": True})
    strategy = SignalVaultStockPaperExecutionV1(broker=broker)
    trader = Trader()
    trader.add_strategy(strategy)
    trader.run_all()


if __name__ == "__main__":
    main()
