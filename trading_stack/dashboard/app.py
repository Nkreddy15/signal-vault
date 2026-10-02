import os
from datetime import datetime, timezone

import requests
from flask import Flask, Response, jsonify

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
    return _pick(
        trade,
        [
            "trade_id", "id", "pair", "is_open", "stake_amount", "amount",
            "open_rate", "current_rate", "close_rate", "profit_abs",
            "profit_ratio", "open_date", "close_date", "enter_tag",
            "exit_reason", "stop_loss_abs", "stop_loss_ratio",
        ],
    )


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

    trades = []
    seen = set()
    for raw in list(raw_open) + list(raw_history):
        trade = _normalize_trade(raw)
        if not trade:
            continue
        trade_id = trade.get("trade_id") or trade.get("id")
        key = (
            str(trade_id)
            if trade_id is not None
            else repr(sorted(trade.items()))
        )
        if key in seen:
            continue
        seen.add(key)
        trades.append(trade)

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
                "crypto_drawdown_lock": "5% / 288 candles",
                "stock_max_selected_symbols": 2,
                "stock_daily_buy_submission_cap": int(
                    os.environ.get("STOCK_DAILY_BUY_CAP", "16")
                ),
                "stock_logical_budget_usd": 100,
            },
        }
    )


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Signal Vault — PAPER Control Room</title>
  <style>
    :root{
      --bg:#070b12; --panel:#0d131d; --panel2:#101824; --border:#1d2938;
      --text:#f3f7fb; --muted:#8190a5; --green:#2bd67b; --red:#ff5f6d;
      --amber:#ffb547; --blue:#4aa8ff; --cyan:#37d5ff; --shadow:0 18px 45px rgba(0,0,0,.28);
    }
    *{box-sizing:border-box}
    html,body{margin:0;background:radial-gradient(circle at 20% -10%,#142236 0,#070b12 34%);color:var(--text);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
    body{min-height:100vh}
    .wrap{max-width:1450px;margin:auto;padding:28px 28px 60px}
    .topbar{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:26px}
    .brand{display:flex;align-items:center;gap:14px}
    .logo{width:43px;height:43px;border-radius:13px;background:linear-gradient(135deg,#3b82f6,#22d3ee);display:grid;place-items:center;font-weight:900;box-shadow:0 8px 25px rgba(55,213,255,.16)}
    h1{font-size:26px;line-height:1;margin:0 0 7px}
    .subtitle{font-size:13px;color:var(--muted)}
    .top-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end}
    .pill{border:1px solid var(--border);background:#0b111a;padding:7px 10px;border-radius:999px;font-size:12px;color:var(--muted)}
    .pill.good{color:var(--green);border-color:rgba(43,214,123,.35);background:rgba(43,214,123,.07)}
    .pill.bad{color:var(--red);border-color:rgba(255,95,109,.35);background:rgba(255,95,109,.07)}
    .linkbtn{color:var(--text);text-decoration:none;border:1px solid var(--border);padding:8px 11px;border-radius:9px;font-size:12px;background:#0b111a}
    .section-title{font-size:12px;text-transform:uppercase;letter-spacing:.14em;color:#62738b;margin:24px 0 11px}
    .kpis{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px}
    .kpi,.panel{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--border);border-radius:15px;box-shadow:var(--shadow)}
    .kpi{padding:16px;min-height:105px}
    .kpi-label{font-size:12px;color:var(--muted);margin-bottom:10px}
    .kpi-value{font-size:25px;font-weight:750;letter-spacing:-.03em}
    .kpi-sub{font-size:11px;color:var(--muted);margin-top:8px}
    .positive{color:var(--green)!important}.negative{color:var(--red)!important}.neutral{color:var(--text)!important}
    .market-grid{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}
    .panel{padding:17px;overflow:hidden}
    .panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:14px}
    .panel h2{font-size:17px;margin:0 0 4px}
    .panel-sub{font-size:12px;color:var(--muted)}
    .status-dot{width:8px;height:8px;border-radius:999px;display:inline-block;margin-right:6px;background:var(--green);box-shadow:0 0 12px rgba(43,214,123,.5)}
    .position-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
    .position{background:#0a1018;border:1px solid #182433;border-radius:12px;padding:13px}
    .position-top{display:flex;justify-content:space-between;gap:12px;align-items:center}
    .symbol{font-size:16px;font-weight:750}.tag{font-size:10px;padding:4px 7px;border-radius:7px;background:#152234;color:#9ecfff}
    .metric-row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
    .mini-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}.mini-value{font-size:13px;margin-top:3px}
    .pnl{font-weight:750}
    .sparkbox{height:46px;margin-top:10px}
    #spark{width:100%;height:46px;display:block}
    .tables{display:grid;grid-template-columns:1fr 1fr;gap:14px}
    .table-wrap{overflow:auto;max-height:340px}
    table{width:100%;border-collapse:collapse;font-size:12px}
    th{position:sticky;top:0;background:#101823;color:#71839a;text-align:left;text-transform:uppercase;letter-spacing:.08em;font-size:9px;padding:9px 8px;border-bottom:1px solid var(--border);z-index:1}
    td{padding:10px 8px;border-bottom:1px solid #151f2c;white-space:nowrap}
    tr:last-child td{border-bottom:none}
    .empty{padding:28px 8px;text-align:center;color:#5f6f84;font-size:12px}
    .health-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
    .health{background:#0a1018;border:1px solid #182433;border-radius:11px;padding:12px}
    .health strong{display:block;margin-top:5px;font-size:13px}
    details{margin-top:12px;border-top:1px solid #192434;padding-top:12px}
    summary{cursor:pointer;color:#7f90a5;font-size:12px}
    pre{font-size:11px;white-space:pre-wrap;color:#a8b5c5}
    .foot{margin-top:20px;color:#54657c;font-size:11px;text-align:center}
    @media (max-width:1100px){.kpis{grid-template-columns:repeat(3,1fr)}.market-grid,.tables{grid-template-columns:1fr}}
    @media (max-width:650px){.wrap{padding:18px 14px 45px}.topbar{align-items:flex-start}.kpis{grid-template-columns:repeat(2,1fr)}.top-actions{display:none}.health-grid{grid-template-columns:repeat(2,1fr)}}
  </style>
</head>
<body>
<div class="wrap">
  <header class="topbar">
    <div class="brand">
      <div class="logo">SV</div>
      <div>
        <h1>Signal Vault</h1>
        <div class="subtitle">Autonomous PAPER trading control room</div>
      </div>
    </div>
    <div class="top-actions">
      <span id="paperBadge" class="pill good">● PAPER ONLY</span>
      <span id="updated" class="pill">Connecting…</span>
      <a class="linkbtn" href="http://127.0.0.1:8080/dashboard" target="_blank">Open FreqUI ↗</a>
    </div>
  </header>

  <div class="section-title">Portfolio pulse</div>
  <section class="kpis">
    <div class="kpi"><div class="kpi-label">Crypto open P&L</div><div id="cryptoPnl" class="kpi-value">—</div><div id="cryptoPnlSub" class="kpi-sub">Waiting for engine</div></div>
    <div class="kpi"><div class="kpi-label">Crypto exposure</div><div id="cryptoExposure" class="kpi-value">—</div><div id="cryptoExposureSub" class="kpi-sub">0 / 4 positions</div></div>
    <div class="kpi"><div class="kpi-label">Stock equity</div><div id="stockEquity" class="kpi-value">—</div><div id="stockCash" class="kpi-sub">Cash —</div></div>
    <div class="kpi"><div class="kpi-label">Managed stock P&L</div><div id="stockPnl" class="kpi-value">—</div><div id="stockExposure" class="kpi-sub">Exposure —</div></div>
    <div class="kpi"><div class="kpi-label">Completed crypto trades</div><div id="closedTrades" class="kpi-value">—</div><div id="closedPnl" class="kpi-sub">Closed P&L —</div></div>
    <div class="kpi"><div class="kpi-label">US market</div><div id="marketState" class="kpi-value">—</div><div id="marketNext" class="kpi-sub">Checking clock</div></div>
  </section>

  <div class="section-title">Markets</div>
  <section class="market-grid">
    <div class="panel">
      <div class="panel-head">
        <div>
          <h2><span class="status-dot"></span>Crypto engine</h2>
          <div id="cryptoMeta" class="panel-sub">Loading strategy…</div>
        </div>
        <span id="cryptoState" class="pill">—</span>
      </div>
      <div id="cryptoPositions" class="position-grid"></div>
      <div class="sparkbox"><svg id="spark" viewBox="0 0 500 46" preserveAspectRatio="none"></svg></div>
    </div>

    <div class="panel">
      <div class="panel-head">
        <div>
          <h2><span class="status-dot"></span>Stocks / Alpaca PAPER</h2>
          <div id="stockMeta" class="panel-sub">Loading broker…</div>
        </div>
        <span id="stockState" class="pill">—</span>
      </div>
      <div id="stockPositions" class="position-grid"></div>
      <details>
        <summary>Other Alpaca PAPER positions</summary>
        <div id="otherPositions" style="margin-top:10px"></div>
      </details>
    </div>
  </section>

  <div class="section-title">Activity</div>
  <section class="tables">
    <div class="panel">
      <div class="panel-head"><div><h2>Crypto trade history</h2><div class="panel-sub">Open + recently closed</div></div></div>
      <div id="cryptoTable" class="table-wrap"></div>
    </div>
    <div class="panel">
      <div class="panel-head"><div><h2>Stock orders</h2><div class="panel-sub">Managed-universe Alpaca PAPER orders</div></div></div>
      <div id="stockOrders" class="table-wrap"></div>
    </div>
  </section>

  <div class="section-title">System</div>
  <section class="panel">
    <div class="health-grid">
      <div class="health"><div class="mini-label">Dashboard</div><strong id="hDash">—</strong></div>
      <div class="health"><div class="mini-label">Crypto engine</div><strong id="hCrypto">—</strong></div>
      <div class="health"><div class="mini-label">Stock broker</div><strong id="hStock">—</strong></div>
      <div class="health"><div class="mini-label">Live trading</div><strong id="hLive">DISABLED</strong></div>
    </div>
    <details>
      <summary>Safety & configuration</summary>
      <div id="safety" style="margin-top:12px"></div>
    </details>
    <div id="errors"></div>
  </section>

  <div class="foot">Signal Vault · PAPER evidence only · No live-money execution path</div>
</div>

<script>
const pnlHistory = [];
const MAX_POINTS = 90;

function num(v){ const n=Number(v); return Number.isFinite(n)?n:0; }
function money(v){ const n=num(v); return (n<0?'-$':'$')+Math.abs(n).toFixed(2); }
function pct(v){ const n=num(v)*100; return (n>=0?'+':'')+n.toFixed(2)+'%'; }
function cls(v){ return num(v)>0?'positive':num(v)<0?'negative':'neutral'; }
function esc(s){ return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
function shortDate(s){ if(!s)return '—'; try{return new Date(s).toLocaleString([], {month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});}catch{return s;} }

function statusPill(el, text, ok){
  el.textContent=text;
  el.className='pill '+(ok?'good':'bad');
}
function positionCard(t, kind='crypto'){
  const symbol = kind==='crypto' ? t.pair : t.symbol;
  const pnlAbs = kind==='crypto' ? num(t.profit_abs) : num(t.unrealized_pl);
  const pnlRatio = kind==='crypto' ? num(t.profit_ratio) : num(t.unrealized_plpc);
  const exposure = kind==='crypto' ? num(t.stake_amount) : Math.abs(num(t.market_value));
  const entry = kind==='crypto' ? t.open_rate : t.avg_entry_price;
  const current = kind==='crypto' ? t.current_rate : t.current_price;
  const tag = kind==='crypto' ? (t.enter_tag||'signal') : (t.asset_class||'equity');
  return `
    <article class="position">
      <div class="position-top"><div class="symbol">${esc(symbol)}</div><span class="tag">${esc(tag)}</span></div>
      <div class="metric-row">
        <div><div class="mini-label">P&L</div><div class="mini-value pnl ${cls(pnlAbs)}">${money(pnlAbs)} · ${pct(pnlRatio)}</div></div>
        <div><div class="mini-label">Exposure</div><div class="mini-value">${money(exposure)}</div></div>
        <div><div class="mini-label">Entry</div><div class="mini-value">${esc(entry??'—')}</div></div>
        <div><div class="mini-label">Current</div><div class="mini-value">${esc(current??'—')}</div></div>
      </div>
    </article>`;
}
function simpleTable(rows, cols){
  if(!rows?.length) return '<div class="empty">Nothing here yet.</div>';
  return '<table><thead><tr>'+cols.map(c=>'<th>'+c[0]+'</th>').join('')+'</tr></thead><tbody>'+
    rows.map(r=>'<tr>'+cols.map(c=>'<td>'+c[1](r)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
}
function drawSpark(value){
  pnlHistory.push(num(value));
  if(pnlHistory.length>MAX_POINTS) pnlHistory.shift();
  const svg=document.getElementById('spark');
  if(pnlHistory.length<2){ svg.innerHTML=''; return; }
  const min=Math.min(...pnlHistory), max=Math.max(...pnlHistory);
  const span=(max-min)||1;
  const pts=pnlHistory.map((v,i)=>{
    const x=i/(pnlHistory.length-1)*500;
    const y=42-((v-min)/span)*36;
    return x.toFixed(1)+','+y.toFixed(1);
  }).join(' ');
  const last=pnlHistory[pnlHistory.length-1];
  const color=last>=0?'#2bd67b':'#ff5f6d';
  svg.innerHTML=`<polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/>`;
}
function kvTable(obj){
  return '<table><tbody>'+Object.entries(obj||{}).map(([k,v])=>'<tr><td>'+esc(k)+'</td><td>'+esc(v)+'</td></tr>').join('')+'</tbody></table>';
}

async function refresh(){
  try{
    const r=await fetch('/api/snapshot',{cache:'no-store'});
    const d=await r.json();
    const c=d.crypto, s=d.stocks;

    document.getElementById('updated').textContent='Updated '+new Date(d.generated_at).toLocaleTimeString();

    const cp=num(c.open_pnl_usd);
    const sp=num(s.managed_unrealized_pnl_usd);
    const cpEl=document.getElementById('cryptoPnl');
    cpEl.textContent=money(cp); cpEl.className='kpi-value '+cls(cp);
    document.getElementById('cryptoPnlSub').textContent=c.open_trade_count+' open position'+(c.open_trade_count===1?'':'s');

    document.getElementById('cryptoExposure').textContent=money(c.open_exposure_usd);
    document.getElementById('cryptoExposureSub').textContent=c.open_trade_count+' / '+d.safety.crypto_max_open_trades+' slots used';

    document.getElementById('stockEquity').textContent=money(s.account?.equity);
    document.getElementById('stockCash').textContent='Cash '+money(s.account?.cash);

    const spEl=document.getElementById('stockPnl');
    spEl.textContent=money(sp); spEl.className='kpi-value '+cls(sp);
    document.getElementById('stockExposure').textContent='Exposure '+money(s.managed_exposure_usd);

    document.getElementById('closedTrades').textContent=c.profit?.closed_trade_count ?? c.closed_trade_count ?? 0;
    document.getElementById('closedPnl').textContent='Closed P&L '+money(c.closed_pnl_usd);

    const marketOpen=!!s.clock?.is_open;
    const ms=document.getElementById('marketState');
    ms.textContent=marketOpen?'OPEN':'CLOSED';
    ms.className='kpi-value '+(marketOpen?'positive':'neutral');
    document.getElementById('marketNext').textContent=marketOpen
      ? 'Next close '+shortDate(s.clock?.next_close)
      : 'Next open '+shortDate(s.clock?.next_open);

    document.getElementById('cryptoMeta').textContent=
      (c.config?.strategy||'Strategy')+' · '+(c.config?.timeframe||'—')+' · '+(c.config?.exchange||'—');
    statusPill(document.getElementById('cryptoState'), String(c.bot_state||'unknown').toUpperCase(), String(c.bot_state).toUpperCase()==='RUNNING');

    document.getElementById('cryptoPositions').innerHTML=
      c.open_trades?.length ? c.open_trades.map(t=>positionCard(t,'crypto')).join('') : '<div class="empty">No open crypto positions.</div>';
    drawSpark(cp);

    document.getElementById('stockMeta').textContent=
      'Alpaca PAPER · '+(marketOpen?'Market open':'Waiting for regular session');
    statusPill(document.getElementById('stockState'), s.account?.status||'UNKNOWN', s.account?.status==='ACTIVE');
    document.getElementById('stockPositions').innerHTML=
      s.managed_positions?.length ? s.managed_positions.map(p=>positionCard(p,'stock')).join('') : '<div class="empty">No managed stock positions.</div>';

    document.getElementById('otherPositions').innerHTML=simpleTable(
      s.other_positions,
      [['Symbol',r=>esc(r.symbol)],['Class',r=>esc(r.asset_class)],['Qty',r=>esc(r.qty)],['Value',r=>money(r.market_value)],['P&L',r=>'<span class="'+cls(r.unrealized_pl)+'">'+money(r.unrealized_pl)+'</span>']]
    );

    const allCrypto=[...(c.open_trades||[]),...(c.closed_trades||[])];
    document.getElementById('cryptoTable').innerHTML=simpleTable(
      allCrypto,
      [['Pair',r=>'<strong>'+esc(r.pair)+'</strong>'],['State',r=>r.is_open?'<span class="positive">OPEN</span>':'CLOSED'],['Stake',r=>money(r.stake_amount)],['P&L',r=>'<span class="'+cls(r.profit_abs)+'">'+money(r.profit_abs)+'</span>'],['Return',r=>'<span class="'+cls(r.profit_ratio)+'">'+pct(r.profit_ratio)+'</span>'],['Signal',r=>esc(r.enter_tag||'—')],['Opened',r=>shortDate(r.open_date)]]
    );
    document.getElementById('stockOrders').innerHTML=simpleTable(
      s.recent_orders,
      [['Symbol',r=>'<strong>'+esc(r.symbol)+'</strong>'],['Side',r=>esc(r.side)],['Qty',r=>esc(r.qty||r.filled_qty||'—')],['Status',r=>esc(r.status)],['Fill',r=>esc(r.filled_avg_price||'—')],['Created',r=>shortDate(r.created_at)]]
    );

    document.getElementById('hDash').textContent=d.system.dashboard;
    document.getElementById('hCrypto').textContent=d.system.crypto_engine;
    document.getElementById('hStock').textContent=d.system.stock_broker;
    document.getElementById('hLive').textContent=d.safety.live_trading?'ENABLED':'DISABLED';
    document.getElementById('safety').innerHTML=kvTable(d.safety);

    const errs=[...(c.errors||[]),...(s.errors||[])];
    document.getElementById('errors').innerHTML=errs.length
      ? '<details open><summary class="negative">Runtime warnings ('+errs.length+')</summary><pre>'+esc(errs.join('\n'))+'</pre></details>' : '';
  }catch(e){
    document.getElementById('updated').textContent='Dashboard error';
    document.getElementById('updated').className='pill bad';
  }
}
refresh();
setInterval(refresh,10000);
</script>
</body>
</html>"""


@app.get("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
