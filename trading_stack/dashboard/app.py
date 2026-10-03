import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

FREQTRADE_BASE = os.environ.get(
    "FREQTRADE_API_BASE", "http://crypto:8080/api/v1"
).rstrip("/")
FREQ_USER = os.environ.get("FREQTRADE__API_SERVER__USERNAME", "")
FREQ_PASS = os.environ.get("FREQTRADE__API_SERVER__PASSWORD", "")
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_API_SECRET", "")
ALPACA_BASE = "https://paper-api.alpaca.markets/v2"

STOCK_UNIVERSE = {
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN",
    "META", "GOOGL", "JPM", "V", "AMD", "TSLA",
}

V1_CRYPTO_ROI_TARGET = 0.004
V1_CRYPTO_STOPLOSS = -0.02
V2_MIN_PROFIT_TARGET = 0.022
V2_CRYPTO_STOPLOSS = -0.018


def _safe_get(url, *, auth=None, headers=None, params=None):
    try:
        response = requests.get(
            url, auth=auth, headers=headers, params=params, timeout=7
        )
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _freq(path, params=None):
    auth = (FREQ_USER, FREQ_PASS) if FREQ_USER and FREQ_PASS else None
    return _safe_get(
        f"{FREQTRADE_BASE}/{path.lstrip('/')}", auth=auth, params=params
    )


def _alpaca(path, params=None):
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "accept": "application/json",
    }
    return _safe_get(
        f"{ALPACA_BASE}/{path.lstrip('/')}", headers=headers, params=params
    )


def _pick(obj, fields):
    if not isinstance(obj, dict):
        return {}
    return {field: obj.get(field) for field in fields if field in obj}


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_trade(trade):
    if not isinstance(trade, dict):
        return {}
    out = _pick(
        trade,
        [
            "trade_id", "id", "pair", "is_open", "stake_amount", "amount",
            "open_rate", "current_rate", "close_rate", "profit_abs",
            "profit_ratio", "open_date", "close_date", "enter_tag",
            "exit_reason", "stop_loss_abs", "stop_loss_ratio", "leverage",
        ],
    )
    if "trade_id" not in out and out.get("id") is not None:
        out["trade_id"] = out["id"]
    return out


def _signal_explanation(tag):
    explanations = {
        "trend": (
            "Trend stack confirmed: EMA 5 > EMA 13 > EMA 34, price above the "
            "fast EMA, and short-term return positive."
        ),
        "momentum": (
            "Momentum trigger: fast EMA above slow EMA, 3-bar return above "
            "0.3%, and 12-bar return positive."
        ),
        "breakout": (
            "Breakout trigger: price exceeded the prior 20-bar high with "
            "volume at or above its 20-bar average."
        ),
        "mean_reversion_bounce": (
            "Mean-reversion bounce: price was statistically stretched lower "
            "and then turned upward with the fast EMA."
        ),
        "v2_trend_momentum": (
            "V2 trend regime plus momentum confirmation. Entry also passed "
            "the cost-aware movement-capacity gate."
        ),
        "v2_trend_breakout": (
            "V2 trend regime plus a volume-confirmed breakout. Entry also "
            "passed the cost-aware movement-capacity gate."
        ),
        "v2_trend_pullback": (
            "V2 bullish regime with a pullback-and-reclaim continuation. "
            "Entry also passed the cost-aware movement-capacity gate."
        ),
        "v2_trend_continuation": (
            "V2 bullish regime with continued positive 3-hour momentum. "
            "Entry also passed the cost-aware movement-capacity gate."
        ),
        "v2_multi_confirmed": (
            "V2 entry had multiple confirmations inside a bullish regime and "
            "enough recent movement capacity to clear the friction buffer."
        ),
    }
    if not tag:
        return "Signal details are not available for this trade."
    return explanations.get(tag, f"Strategy entry tag: {tag}.")


def _decorate_trade(trade, strategy_name=""):
    trade = dict(trade or {})
    entry = _f(trade.get("open_rate"))
    current = _f(trade.get("current_rate")) or _f(trade.get("close_rate"))

    is_v2 = strategy_name == "SignalVaultPaperExecutionV2"
    roi_reference = V2_MIN_PROFIT_TARGET if is_v2 else V1_CRYPTO_ROI_TARGET
    stoploss_reference = V2_CRYPTO_STOPLOSS if is_v2 else V1_CRYPTO_STOPLOSS

    stop = _f(trade.get("stop_loss_abs"))
    if entry > 0 and stop <= 0:
        stop = entry * (1 + stoploss_reference)
    target = entry * (1 + roi_reference) if entry > 0 else 0.0
    risk = max(entry - stop, 0.0)
    reward = max(target - entry, 0.0)
    rr = reward / risk if risk > 0 else None

    if is_v2:
        target_rule = (
            "V2 adaptive target: minimum +2.20% gross; may rise with volatility"
        )
        exit_logic = (
            "Adaptive volatility target, cost-cleared profit protection, "
            "regime-failure exit, or -1.8% hard stop."
        )
    else:
        target_rule = "ROI reference +0.40%"
        exit_logic = (
            "Exit on +0.40% ROI reference, strategy exit signal, or -2% "
            "stop loss. Protective locks can pause new entries."
        )

    trade.update(
        {
            "current_rate": current,
            "target_price": target,
            "target_rule": target_rule,
            "stop_price": stop,
            "risk_reward": rr,
            "signal_reason": _signal_explanation(trade.get("enter_tag")),
            "exit_logic": exit_logic,
        }
    )
    return trade


def _normalize_candles(payload):
    if payload is None:
        return []

    columns = None
    rows = None
    if isinstance(payload, dict):
        columns = payload.get("columns")
        rows = payload.get("data")
        if rows is None and isinstance(payload.get("candles"), list):
            rows = payload.get("candles")
    elif isinstance(payload, list):
        rows = payload

    if not isinstance(rows, list):
        return []

    result = []
    for row in rows:
        item = None
        if isinstance(row, dict):
            item = row
        elif isinstance(row, (list, tuple)) and isinstance(columns, list):
            item = dict(zip(columns, row))
        elif isinstance(row, (list, tuple)) and len(row) >= 6:
            item = {
                "date": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
            }

        if not isinstance(item, dict):
            continue

        date = (
            item.get("date")
            or item.get("timestamp")
            or item.get("time")
            or item.get("datetime")
        )
        try:
            candle = {
                "time": date,
                "open": float(item.get("open")),
                "high": float(item.get("high")),
                "low": float(item.get("low")),
                "close": float(item.get("close")),
                "volume": float(item.get("volume") or 0),
            }
        except (TypeError, ValueError):
            continue
        result.append(candle)

    return result


@app.get("/healthz")
def healthz():
    return {"status": "ok", "mode": "PAPER_ONLY"}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/candles")
def candles():
    pair = (request.args.get("pair") or "").strip()
    timeframe = (request.args.get("timeframe") or "5m").strip()
    try:
        limit = min(max(int(request.args.get("limit", "120")), 30), 300)
    except ValueError:
        limit = 120

    allowed_timeframes = {"5m", "15m", "1h"}
    if not pair:
        return jsonify({"candles": [], "error": "pair is required"}), 400
    if timeframe not in allowed_timeframes:
        return jsonify(
            {
                "candles": [],
                "error": "Requested timeframe is not enabled for the dashboard.",
            }
        ), 400

    payload, error = _freq(
        "pair_candles",
        {"pair": pair, "timeframe": timeframe, "limit": limit},
    )
    normalized = _normalize_candles(payload)
    return jsonify(
        {
            "pair": pair,
            "timeframe": timeframe,
            "candles": normalized,
            "error": error,
        }
    )


@app.get("/api/snapshot")
def snapshot():
    crypto_health, crypto_health_err = _freq("health")
    crypto_config, crypto_config_err = _freq("show_config")
    crypto_profit, crypto_profit_err = _freq("profit")
    crypto_open_trades, crypto_open_trades_err = _freq("status")
    crypto_trades, crypto_trades_err = _freq("trades", {"limit": 100})

    account, account_err = _alpaca("account")
    positions, positions_err = _alpaca("positions")
    orders, orders_err = _alpaca(
        "orders", {"status": "all", "limit": 100, "direction": "desc"}
    )
    clock, clock_err = _alpaca("clock")

    managed_positions = []
    other_positions = []
    position_fields = [
        "symbol", "asset_class", "qty", "market_value", "avg_entry_price",
        "current_price", "unrealized_pl", "unrealized_plpc", "change_today",
    ]
    if isinstance(positions, list):
        for position in positions:
            projected = _pick(position, position_fields)
            if position.get("symbol") in STOCK_UNIVERSE:
                managed_positions.append(projected)
            else:
                other_positions.append(projected)

    managed_orders = []
    if isinstance(orders, list):
        for order in orders:
            if order.get("symbol") in STOCK_UNIVERSE:
                managed_orders.append(
                    _pick(
                        order,
                        [
                            "id", "symbol", "side", "qty", "notional", "type",
                            "status", "filled_qty", "filled_avg_price",
                            "created_at", "filled_at",
                        ],
                    )
                )

    raw_open = crypto_open_trades if isinstance(crypto_open_trades, list) else []
    raw_history = []
    if isinstance(crypto_trades, dict):
        raw_history = crypto_trades.get("trades") or []
    elif isinstance(crypto_trades, list):
        raw_history = crypto_trades

    strategy_name = (
        str((crypto_config or {}).get("strategy") or "")
        if isinstance(crypto_config, dict)
        else ""
    )

    trades = []
    seen = set()
    for raw in list(raw_open) + list(raw_history):
        trade = _normalize_trade(raw)
        if not trade:
            continue
        trade_id = trade.get("trade_id")
        key = (
            str(trade_id)
            if trade_id is not None
            else repr(sorted(trade.items()))
        )
        if key in seen:
            continue
        seen.add(key)
        trades.append(_decorate_trade(trade, strategy_name))

    open_trades = [t for t in trades if t.get("is_open") is True]
    closed_trades = [t for t in trades if t.get("is_open") is False]

    crypto_state = None
    if isinstance(crypto_config, dict):
        crypto_state = (
            crypto_config.get("state")
            or crypto_config.get("bot_state")
            or crypto_config.get("initial_state")
        )
    if not crypto_state and isinstance(crypto_health, dict) and not crypto_health_err:
        crypto_state = "RUNNING"

    crypto_open_pnl = sum(_f(t.get("profit_abs")) for t in open_trades)
    crypto_open_exposure = sum(_f(t.get("stake_amount")) for t in open_trades)
    crypto_closed_pnl = _f(
        (crypto_profit or {}).get("profit_closed_coin")
        if isinstance(crypto_profit, dict) else 0
    )

    managed_stock_unrealized = sum(
        _f(p.get("unrealized_pl")) for p in managed_positions
    )
    managed_stock_exposure = sum(
        abs(_f(p.get("market_value"))) for p in managed_positions
    )

    crypto_errors = [
        err for err in [
            crypto_health_err,
            crypto_config_err,
            crypto_profit_err,
            crypto_open_trades_err,
            crypto_trades_err,
        ] if err
    ]
    stock_errors = [
        err for err in [account_err, positions_err, orders_err, clock_err] if err
    ]

    return jsonify(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "PAPER_ONLY",
            "system": {
                "dashboard": "ONLINE",
                "crypto_engine": (
                    "ONLINE"
                    if str(crypto_state).upper() == "RUNNING" and not crypto_errors
                    else "DEGRADED"
                ),
                "stock_broker": (
                    "ONLINE"
                    if isinstance(account, dict)
                    and account.get("status") == "ACTIVE"
                    and not account_err
                    else "DEGRADED"
                ),
                "stock_market_open": (
                    bool(clock.get("is_open"))
                    if isinstance(clock, dict) else None
                ),
            },
            "crypto": {
                "bot_state": crypto_state or "UNREACHABLE",
                "config": _pick(
                    crypto_config,
                    [
                        "state", "runmode", "strategy", "timeframe",
                        "exchange", "dry_run",
                    ],
                ),
                "profit": _pick(
                    crypto_profit,
                    [
                        "profit_closed_coin", "profit_closed_percent_mean",
                        "profit_all_coin", "profit_all_percent_mean",
                        "trade_count", "closed_trade_count",
                    ],
                ),
                "open_pnl_usd": crypto_open_pnl,
                "closed_pnl_usd": crypto_closed_pnl,
                "open_exposure_usd": crypto_open_exposure,
                "open_trade_count": len(open_trades),
                "closed_trade_count": len(closed_trades),
                "open_trades": open_trades,
                "closed_trades": closed_trades[:50],
                "errors": crypto_errors,
            },
            "stocks": {
                "account": _pick(
                    account,
                    [
                        "status", "cash", "equity", "last_equity",
                        "buying_power", "trading_blocked", "account_blocked",
                        "pattern_day_trader",
                    ],
                ),
                "clock": _pick(
                    clock,
                    ["is_open", "timestamp", "next_open", "next_close"],
                ),
                "managed_positions": managed_positions,
                "other_positions": other_positions,
                "recent_orders": managed_orders[:50],
                "managed_unrealized_pnl_usd": managed_stock_unrealized,
                "managed_exposure_usd": managed_stock_exposure,
                "errors": stock_errors,
            },
            "safety": {
                "live_trading": False,
                "crypto_max_open_trades": 4,
                "crypto_stake_usd": 15,
                "crypto_stoploss": "-2%",
                "crypto_roi_reference": "+0.40%",
                "crypto_drawdown_lock": "5% / 288 candles",
                "stock_max_selected_symbols": 2,
                "stock_daily_buy_submission_cap": int(
                    os.environ.get("STOCK_DAILY_BUY_CAP", "16")
                ),
                "stock_logical_budget_usd": 100,
            },
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
