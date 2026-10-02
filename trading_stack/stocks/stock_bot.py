import os
from decimal import Decimal

from lumibot.brokers import Alpaca
from lumibot.strategies import Strategy
from lumibot.traders import Trader


UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "JPM", "V"]


class SafeDailyMomentumRotation(Strategy):
    """Rules-based PAPER-only stock momentum rotation on top of Lumibot.

    Ranks a fixed large-cap universe by 20-trading-day momentum once per day,
    holds the top 3, and uses only a $100 logical budget regardless of the
    provider's much larger simulated account balance.
    """

    parameters = {
        "universe": UNIVERSE,
        "top_n": 3,
        "lookback_days": 20,
        "logical_budget_usd": Decimal(os.environ.get("STOCK_LOGICAL_BUDGET_USD", "100")),
        "cash_buffer_ratio": Decimal("0.10"),
    }

    def initialize(self):
        self.sleeptime = "1D"
        self.vars.last_rebalance_date = None

    def on_trading_iteration(self):
        today = self.get_datetime().date()
        if self.vars.last_rebalance_date == today:
            return

        universe = list(self.parameters["universe"])
        lookback = int(self.parameters["lookback_days"])
        top_n = int(self.parameters["top_n"])
        budget = Decimal(self.parameters["logical_budget_usd"])
        buffer_ratio = Decimal(self.parameters["cash_buffer_ratio"])

        if budget <= 0 or budget > Decimal("100"):
            raise ValueError("logical stock paper budget must be within (0, 100]")

        scores = {}
        for symbol in universe:
            bars = self.get_historical_prices(symbol, lookback + 5, timestep="day")
            if bars is None or len(bars.df) < lookback:
                continue
            closes = bars.df["close"].dropna()
            if len(closes) < lookback:
                continue
            first = Decimal(str(closes.iloc[-lookback]))
            last = Decimal(str(closes.iloc[-1]))
            if first > 0 and last > 0:
                scores[symbol] = last / first - Decimal("1")

        if len(scores) < top_n:
            self.log_message("Not enough momentum data; no rebalance.")
            return

        winners = [
            symbol for symbol, _ in
            sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_n]
        ]
        investable = budget * (Decimal("1") - buffer_ratio)
        target_value = investable / Decimal(top_n)

        self.log_message(
            f"PAPER momentum winners={winners}; logical_budget=${budget}; target_each=${target_value}"
        )

        # Manage ONLY this strategy's stock universe. Never touch crypto or unrelated positions.
        for symbol in universe:
            position = self.get_position(symbol)
            if position is not None and symbol not in winners:
                qty = abs(float(position.quantity))
                if qty > 0:
                    self.submit_order(self.create_order(symbol, qty, "sell"))

        for symbol in winners:
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

        self.vars.last_rebalance_date = today


def main():
    if os.environ.get("ALPACA_IS_PAPER", "true").lower() != "true":
        raise RuntimeError("This one-week stack is PAPER-only; ALPACA_IS_PAPER must be true.")

    key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        raise RuntimeError("Alpaca PAPER API key and secret are required.")

    broker = Alpaca({"API_KEY": key, "API_SECRET": secret, "PAPER": True})
    strategy = SafeDailyMomentumRotation(broker=broker)
    trader = Trader()
    trader.add_strategy(strategy)
    trader.run_all()


if __name__ == "__main__":
    main()
