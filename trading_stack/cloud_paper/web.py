"""Authenticated API using the accepted Signal Vault HTML/CSS and components."""
import hashlib
import hmac
import json
import math
import os
import sqlite3
import time
from pathlib import Path
from flask import Flask, Response, jsonify, render_template, request, send_file
from werkzeug.middleware.proxy_fix import ProxyFix
from .providers import iso
from .store import Store, portfolio, TERMINAL

ROOT=Path(__file__).resolve().parents[1]/"dashboard"


def trade_view(p,s,now,closed=False):
    market=p["market"]; q=s["marks"].get(market+":"+p["symbol"])
    current=p.get("exit_price") if closed else q["bid"] if q else None
    stale=not closed and (not q or now-q["at"]>s["config"]["max_quote_age_seconds"])
    rate=s["config"]["crypto_fee_fraction"] if market=="crypto" else s["config"]["stock_fee_fraction"]
    exit_fee=0 if closed or current is None else (math.ceil(100*.07*p["quantity"]*current*(1-current))/100 if market=="kalshi" else p["quantity"]*current*rate)
    net=p.get("net_pnl") if closed else (None if stale else p["proceeds"]+p["quantity"]*current-exit_fee-p["cost"]-p["entry_fee"]-p["exit_fee"])
    return dict(trade_id=p["id"],pair=p["symbol"],market=market,mode=p["mode"],is_open=not closed,is_short=False,
        open_rate=p["entry_price"],current_rate=current,close_rate=p.get("exit_price"),amount=p["bought_qty"] if closed else p["quantity"],
        stake_amount=p["cost"],profit_abs=net,profit_ratio=net/p["cost"] if net is not None and p["cost"] else None,
        open_date=iso(p["opened_at"]),close_date=iso(p["closed_at"]) if closed else None,enter_tag=p["strategy"],
        signal_time=iso(p["signal_at"]),signal_reason=p["reason"],exit_reason=p.get("exit_reason"),
        stop_price=p.get("stop"),target_price=p.get("target"),trailing_stop=p.get("stop") if p.get("stop")!=p.get("initial_stop") else None,
        fee_usd=p["entry_fee"]+p["exit_fee"]+exit_fee,paid_fees=p["entry_fee"]+p["exit_fee"],estimated_exit_fee=exit_fee,
        fee_basis="Actual demo order fees" if market=="kalshi" else "Modeled cost allowance; paper fills do not prove live costs",
        slippage_fraction=s["config"]["slippage_fraction"],mark_stale=stale,
        target_rule="Settlement payout; no stock-style price target" if market=="kalshi" else "Frozen cost-aware target",
        exit_logic="Owner exit, campaign drain, or exchange-confirmed binary settlement" if market=="kalshi" else "Stop, target, trailing stop, time limit, daily/drawdown guard, owner exit or campaign drain",
        contract=p.get("contract"),settlement=p.get("settlement"),fills=p["fills"],
        orders=[o for o in s["orders"].values() if o["trade_id"]==p["id"]])


def snapshot(store,now):
    s=store.read(); pf=portfolio(s,now)
    opened=[trade_view(p,s,now) for p in s["positions"].values()]
    closed=[trade_view(p,s,now,True) for p in reversed(s["closed"])]
    cp=[t for t in opened if t["market"]=="crypto"]; cc=[t for t in closed if t["market"]=="crypto"]
    sp=[t for t in opened if t["market"]=="stocks"]
    providers=s["providers"];stock=providers.get("stocks",{})
    alive=bool(s["heartbeat"] and now-s["heartbeat"]<240)
    status="WORKER STALE"
    # Explicit precedence; campaign completion and entry pause do not turn protective exits off.
    if alive:
        status="EMERGENCY DRAIN" if s["emergency"] else s["halt"] or ("DAILY LOSS HALT" if s["daily_halt"] else "PAUSED" if s["paused"] else "RUNNING")
    curve=[dict(at=r[0],equity=r[1],cash=r[2],exposure=r[3],drawdown=r[4]) for r in store.db.execute("SELECT * FROM equity ORDER BY at")]
    if len(curve)>1500:
        stride=math.ceil(len(curve)/1499);curve=curve[::stride]+[curve[-1]]
    crypto=dict(bot_state=providers.get("crypto",{}).get("status","STARTING"),
        config=dict(exchange="Kraken public data",runmode="INTERNAL SIMULATION",strategy="Trend / breakout / range",timeframe="1h"),
        starting_balance=s["config"]["capital"],marked_equity=pf["equity"],open_pnl_usd=None if any(t["mark_stale"] for t in cp) else sum(t["profit_abs"] or 0 for t in cp),
        closed_pnl_usd=sum(t["profit_abs"] or 0 for t in cc),open_exposure_usd=sum((t["current_rate"] or t["open_rate"])*t["amount"] for t in cp),
        open_trade_count=len(cp),closed_trade_count=len(cc),open_trades=cp,closed_trades=cc,profit=dict(closed_trade_count=len(cc)),
        marks_stale=any(t["mark_stale"] for t in cp),errors=[providers["crypto"]["reason"]] if providers.get("crypto",{}).get("reason") else [])
    stocks=dict(account=dict(stock.get("account",{}),equity=pf["equity"],cash=pf["available_cash"]),clock=stock.get("clock",{}),
        managed_positions=[dict(symbol=t["pair"],trade_id=t["trade_id"],qty=t["amount"],market_value=(t["current_rate"] or t["open_rate"])*t["amount"],unrealized_pl=t["profit_abs"]) for t in sp],
        other_positions=[],managed_unrealized_pnl_usd=sum(t["profit_abs"] or 0 for t in sp),managed_exposure_usd=sum(t["stake_amount"] for t in sp),
        recent_orders=[dict(o,symbol=o["symbol"],side=o["action"],qty=o["quantity"],type="limit",filled_avg_price=o["filled_value"]/o["filled_qty"] if o["filled_qty"] else None,created_at=iso(o["created_at"])) for o in reversed(list(s["orders"].values())) if o["market"]=="stocks"],
        errors=[stock["reason"]] if stock.get("reason") else [])
    return dict(generated_at=iso(now),system=dict(dashboard="ONLINE",crypto_engine=providers.get("crypto",{}).get("status","STARTING"),stock_broker=stock.get("status","BLOCKED")),
        safety=dict(live_trading=False,crypto_max_open_trades=s["config"]["max_positions"],total_virtual_capital=s["config"]["capital"],
                    max_exposure=s["config"]["max_exposure_fraction"],risk_per_trade=s["config"]["risk_per_trade"],drawdown_limit=s["config"]["drawdown_fraction"],
                    protective_exits="ACTIVE WHILE ENTRIES PAUSED; require valid quote and open venue"),
        crypto=crypto,stocks=stocks,cloud=dict(campaign_id=s["campaign_id"],version=s["config"]["version"],config_hash=s["config_hash"],
        evidence=s["config"]["evidence"],status=status,started_at=iso(s["started_at"]),deadline=iso(s["deadline"]),elapsed_seconds=max(0,now-s["started_at"]),
        heartbeat=iso(s["heartbeat"]) if s["heartbeat"] else None,last_cycle=iso(s["last_cycle"]) if s["last_cycle"] else None,cycles=s["cycles"],
        paused=s["paused"],emergency=s["emergency"],halt=s["halt"],providers=providers,portfolio=pf,diagnostics=s["diagnostics"],
        open_trades=opened,closed_trades=closed,equity_curve=curve,reconciliation=s["reconciliation"],last_backup=s.get("last_backup")))


def create_app(directory=None,password=None):
    directory=Path(directory or os.environ.get("SV_STATE_DIR",".data/cloud-paper"))
    password=password or os.environ.get("SV_DASHBOARD_PASSWORD","")
    if len(password)<32: raise ValueError("SV_DASHBOARD_PASSWORD must contain at least 32 characters")
    user=os.environ.get("SV_DASHBOARD_USER","nikhil")
    app=Flask(__name__,static_folder=str(ROOT/"static"),template_folder=str(ROOT/"templates"))
    app.wsgi_app=ProxyFix(app.wsgi_app,x_proto=1)
    app.config["MAX_CONTENT_LENGTH"]=4096
    token=hmac.new(password.encode(),b"Signal Vault paper control CSRF v1",hashlib.sha256).hexdigest()
    failures={}

    @app.before_request
    def authenticate():
        if request.path=="/healthz": return None
        ip=request.remote_addr or "unknown"; now=time.time()
        # Bound memory and throttle failed logins; no passwords or auth headers are logged.
        if len(failures)>1000: failures.clear()
        attempts,until=failures.get(ip,(0,0))
        if now<until and attempts>=10: return Response("Login rate limited",429)
        auth=request.authorization
        if not auth or not hmac.compare_digest(auth.username or "",user) or not hmac.compare_digest(auth.password or "",password):
            failures[ip]=(attempts+1 if now<until else 1,now+60)
            return Response("Owner login required",401,{"WWW-Authenticate":'Basic realm="Signal Vault"'})
        failures.pop(ip,None)
        if request.method not in ("GET","HEAD"):
            if request.headers.get("Origin")!=request.host_url.rstrip("/") or not hmac.compare_digest(request.headers.get("X-CSRF-Token",""),token):
                return Response("Same-origin paper control required",403)
            if not request.is_json: return Response("JSON required",415)

    @app.after_request
    def secure(response):
        response.headers.update({"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer",
            "X-Frame-Options":"DENY","Content-Security-Policy":"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
        if request.is_secure: response.headers["Strict-Transport-Security"]="max-age=31536000"
        return response

    def db(): return Store(directory)

    @app.get("/healthz")
    def health():
        try:
            st=db(); s=st.read();st.db.close()
            alive=bool(s["heartbeat"] and time.time()-s["heartbeat"]<240)
            return {"status":"ok" if alive else "worker_stale","mode":"PAPER_ONLY"},200 if alive else 503
        except Exception: return {"status":"not_ready"},503

    @app.get("/")
    def index(): return render_template("index.html",cloud_campaign=True)

    @app.get("/api/snapshot")
    def state():
        st=db()
        try: result=snapshot(st,time.time());result["cloud"]["csrf_token"]=token;return jsonify(result)
        finally: st.db.close()

    @app.post("/api/control")
    def control():
        payload=request.get_json(); st=db()
        try:
            if payload.get("action")=="close" and payload.get("trade_id") not in st.read()["positions"]:
                return {"error":"Open paper position not found"},404
            cid=st.command(payload.get("action"),request.headers.get("Idempotency-Key"),payload.get("trade_id"))
            return {"command_id":cid,"status":"queued","meaning":"Worker applies durable command; exits require fresh executable prices. Pause leaves exits active."},202
        except (ValueError,TypeError): return {"error":"Invalid paper control"},400
        finally: st.db.close()

    @app.get("/api/candles")
    def candles():
        market=request.args.get("market","crypto");symbol=request.args.get("pair","");tf=request.args.get("timeframe","1h")
        if market not in ("crypto","stocks","kalshi") or tf not in ("1h","4h","1d"):
            return {"error":"Unsupported market or timeframe","candles":[]},400
        st=db()
        try:
            s=st.read();rows=st.candles(market,symbol,"1h",10000)
            if market=="kalshi":
                return {"candles":[],"error":"Contract quote history is shown separately; no OHLC candles are fabricated.","kind":"contract"}
            if tf!="1h":
                seconds={"4h":14400,"1d":86400}[tf];groups={}
                for r in rows: groups.setdefault(int(r["time"]//seconds)*seconds,[]).append(r)
                rows=[dict(time=t,open=rs[0]["open"],high=max(r["high"] for r in rs),low=min(r["low"] for r in rs),close=rs[-1]["close"],volume=sum(r["volume"] for r in rs))
                      for t,rs in sorted(groups.items()) if t+seconds<=time.time()]
            tid=request.args.get("trade_id")
            p=s["positions"].get(tid) or next((p for p in s["closed"] if p["id"]==tid),None)
            if p and (p["market"]!=market or p["symbol"]!=symbol): return {"candles":[],"error":"Trade identity mismatch"},400
            # Keep older trade context, instead of falsely snapping an old fill to today's bars.
            if p:
                lo=p["opened_at"]-24*3600;hi=p.get("closed_at",time.time())+24*3600
                rows=[r for r in rows if lo<=r["time"]<=hi]
            return {"candles":rows[-1500:],"pair":symbol,"timeframe":tf,"market":market,"source":"Stored provider closed bars","error":None}
        finally: st.db.close()

    @app.get("/api/export")
    def export():
        st=db()
        try: path=st.backup(time.time())
        finally: st.db.close()
        return send_file(path,as_attachment=True,download_name=path.name,mimetype="application/vnd.sqlite3")

    return app
