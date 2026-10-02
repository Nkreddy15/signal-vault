import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, Response

app = Flask(__name__)

FREQTRADE_BASE = os.environ.get("FREQTRADE_API_BASE", "http://crypto:8080/api/v1").rstrip("/")
FREQ_USER = os.environ.get("FREQTRADE__API_SERVER__USERNAME", "")
FREQ_PASS = os.environ.get("FREQTRADE__API_SERVER__PASSWORD", "")
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "")
ALPACA_SECRET = os.environ.get("ALPACA_API_SECRET", "")
ALPACA_BASE = "https://paper-api.alpaca.markets/v2"
STOCK_UNIVERSE = {
    "SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN",
    "META", "GOOGL", "JPM", "V", "AMD", "TSLA",
}


def _safe_get(url, *, auth=None, headers=None, params=None):
    try:
        response = requests.get(
            url, auth=auth, headers=headers, params=params, timeout=5
        )
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _freq(path, params=None):
    auth = (FREQ_USER, FREQ_PASS) if FREQ_USER and FREQ_PASS else None
    return _safe_get(f"{FREQTRADE_BASE}/{path.lstrip('/')}", auth=auth, params=params)


def _alpaca(path, params=None):
    headers = {
        "APCA-API-KEY-ID": ALPACA_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET,
        "accept": "application/json",
    }
    return _safe_get(f"{ALPACA_BASE}/{path.lstrip('/')}", headers=headers, params=params)


def _pick(obj, fields):
    if not isinstance(obj, dict):
        return {}
    return {field: obj.get(field) for field in fields if field in obj}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "mode": "PAPER_ONLY"}


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

    safe_positions = []
    other_positions = []
    position_fields = [
        "symbol", "asset_class", "qty", "market_value", "avg_entry_price",
        "current_price", "unrealized_pl", "unrealized_plpc", "change_today",
    ]
    if isinstance(positions, list):
        for position in positions:
            projected = _pick(position, position_fields)
            if position.get("symbol") in STOCK_UNIVERSE:
                safe_positions.append(projected)
            else:
                other_positions.append(projected)

    safe_orders = []
    if isinstance(orders, list):
        for order in orders:
            if order.get("symbol") in STOCK_UNIVERSE:
                safe_orders.append(
                    _pick(
                        order,
                        [
                            "id", "symbol", "side", "qty", "notional", "type",
                            "status", "filled_qty", "filled_avg_price",
                            "created_at", "filled_at",
                        ],
                    )
                )

    trade_list = []
    seen_trade_ids = set()

    open_trade_list = crypto_open_trades if isinstance(crypto_open_trades, list) else []
    historical_trade_list = []
    if isinstance(crypto_trades, dict):
        historical_trade_list = crypto_trades.get("trades") or []
    elif isinstance(crypto_trades, list):
        historical_trade_list = crypto_trades

    for trade in list(open_trade_list) + list(historical_trade_list):
        if not isinstance(trade, dict):
            continue
        trade_id = trade.get("trade_id") or trade.get("id")
        dedupe_key = str(trade_id) if trade_id is not None else repr(sorted(trade.items()))
        if dedupe_key in seen_trade_ids:
            continue
        seen_trade_ids.add(dedupe_key)
        trade_list.append(trade)

    crypto_state = None
    if isinstance(crypto_config, dict):
        crypto_state = (
            crypto_config.get("state")
            or crypto_config.get("bot_state")
            or crypto_config.get("initial_state")
        )
    if not crypto_state and isinstance(crypto_health, dict) and not crypto_health_err:
        crypto_state = "RUNNING"

    crypto_summary = {
        "health": crypto_health,
        "config": _pick(
            crypto_config,
            ["state", "runmode", "strategy", "timeframe", "exchange", "dry_run"],
        ),
        "bot_state": crypto_state or "UNREACHABLE",
        "profit": _pick(
            crypto_profit,
            [
                "profit_closed_coin", "profit_closed_percent_mean",
                "profit_all_coin", "profit_all_percent_mean",
                "trade_count", "closed_trade_count",
            ],
        ),
        "recent_trades": trade_list[:50],
        "errors": [
            err for err in
            [
                crypto_health_err,
                crypto_config_err,
                crypto_profit_err,
                crypto_open_trades_err,
                crypto_trades_err,
            ]
            if err
        ],
    }

    stock_summary = {
        "account": _pick(
            account,
            [
                "status", "cash", "equity", "last_equity", "buying_power",
                "trading_blocked", "account_blocked", "pattern_day_trader",
            ],
        ),
        "positions": safe_positions,
        "other_positions": other_positions,
        "other_positions_count": len(other_positions),
        "recent_orders": safe_orders[:50],
        "errors": [
            err for err in [account_err, positions_err, orders_err] if err
        ],
    }

    return jsonify(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "PAPER_ONLY",
            "logical_budgets": {"crypto_usd": 100, "stocks_usd": 100},
            "crypto": crypto_summary,
            "stocks": stock_summary,
            "safety": {
                "live_trading": False,
                "crypto_max_open_trades": 4,
                "crypto_stake_usd": 15,
                "crypto_stoploss": "-2%",
                "crypto_drawdown_lock": "5% observed drawdown -> 2h lock after >=6 closes",
                "stock_max_selected_symbols": 2,
                "stock_daily_buy_submission_cap": int(
                    os.environ.get("STOCK_DAILY_BUY_CAP", "16")
                ),
            },
        }
    )


INDEX_HTML = r"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Signal Vault PAPER Control Room</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background:#0d1117; color:#e6edf3; }
    main { max-width: 1200px; margin: 0 auto; padding: 24px; }
    h1 { margin-bottom: 4px; }
    .muted { color:#8b949e; }
    .badge { display:inline-block; padding:4px 8px; border:1px solid #3fb950; border-radius:999px; color:#3fb950; font-weight:700; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-top:18px; }
    .card { background:#161b22; border:1px solid #30363d; border-radius:12px; padding:16px; overflow:auto; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th,td { padding:7px; border-bottom:1px solid #30363d; text-align:left; white-space:nowrap; }
    pre { white-space:pre-wrap; word-break:break-word; font-size:12px; }
    .error { color:#ff7b72; }
  </style>
</head>
<body>
<main>
  <h1>Signal Vault Control Room</h1>
  <div><span class="badge">PAPER ONLY</span> <span class="muted">Auto-refresh every 10 seconds</span></div>
  <div id="stamp" class="muted"></div>

  <div class="grid">
    <section class="card"><h2>Crypto</h2><div id="crypto"></div></section>
    <section class="card"><h2>Stocks</h2><div id="stocks"></div></section>
    <section class="card"><h2>Safety</h2><div id="safety"></div></section>
  </div>

  <div class="grid">
    <section class="card"><h2>Crypto trades</h2><div id="cryptoTrades"></div></section>
    <section class="card"><h2>Managed stock positions</h2><div id="stockPositions"></div></section>
    <section class="card"><h2>Other Alpaca PAPER positions</h2><div id="otherPositions"></div></section>
    <section class="card"><h2>Stock orders</h2><div id="stockOrders"></div></section>
  </div>
</main>
<script>
function table(rows, cols) {
  if (!Array.isArray(rows) || rows.length === 0) return '<span class="muted">No rows.</span>';
  return '<table><thead><tr>' + cols.map(c => '<th>'+c+'</th>').join('') + '</tr></thead><tbody>' +
    rows.map(r => '<tr>' + cols.map(c => '<td>' + (r[c] ?? '') + '</td>').join('') + '</tr>').join('') +
    '</tbody></table>';
}
function kv(obj) {
  return '<table><tbody>' + Object.entries(obj || {}).map(([k,v]) =>
    '<tr><th>'+k+'</th><td>'+String(v ?? '')+'</td></tr>').join('') + '</tbody></table>';
}
async function refresh() {
  try {
    const r = await fetch('/api/snapshot', {cache:'no-store'});
    const d = await r.json();
    document.getElementById('stamp').textContent = 'Updated ' + d.generated_at;
    document.getElementById('crypto').innerHTML = kv({...d.crypto.profit, bot_state:d.crypto.bot_state, ...d.crypto.config}) +
      (d.crypto.errors.length ? '<pre class="error">'+d.crypto.errors.join('\n')+'</pre>' : '');
    document.getElementById('stocks').innerHTML = kv(d.stocks.account) +
      (d.stocks.errors.length ? '<pre class="error">'+d.stocks.errors.join('\n')+'</pre>' : '');
    document.getElementById('safety').innerHTML = kv(d.safety);
    document.getElementById('cryptoTrades').innerHTML = table(
      d.crypto.recent_trades, ['trade_id','pair','is_open','open_rate','close_rate','profit_abs','profit_ratio','enter_tag','exit_reason']
    );
    document.getElementById('stockPositions').innerHTML = table(
      d.stocks.positions, ['symbol','asset_class','qty','market_value','avg_entry_price','current_price','unrealized_pl','unrealized_plpc']
    );
    document.getElementById('otherPositions').innerHTML = table(
      d.stocks.other_positions, ['symbol','asset_class','qty','market_value','avg_entry_price','current_price','unrealized_pl','unrealized_plpc']
    );
    document.getElementById('stockOrders').innerHTML = table(
      d.stocks.recent_orders, ['symbol','side','qty','notional','type','status','filled_qty','filled_avg_price','created_at']
    );
  } catch (e) {
    document.getElementById('stamp').innerHTML = '<span class="error">Dashboard refresh failed: '+e+'</span>';
  }
}
refresh();
setInterval(refresh, 10000);
</script>
</body>
</html>"""


@app.get("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
