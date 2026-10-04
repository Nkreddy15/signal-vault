"""Single-writer unattended campaign. Recovery precedes any new entry."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import math
import os
import signal
import shutil
import time
from pathlib import Path
from .store import Store, TERMINAL, digest, portfolio, number
from .providers import Kraken, Alpaca, Kalshi, ProviderError, validate_quote, rounded, timestamp
from .strategies import signals, probability_signal


def load_config(path=None):
    path=Path(path or Path(__file__).with_name("campaign.json"))
    c=json.loads(path.read_text())
    if c["crypto_mode"]!="simulation" or c["stocks_mode"]!="paper" or c["kalshi_mode"]!="demo":
        raise ValueError("Only crypto simulation, Alpaca paper and Kalshi demo are supported")
    for k in ("risk_per_trade","max_position_fraction","max_exposure_fraction","daily_loss_fraction","drawdown_fraction"):
        if not 0<number(c[k])<=1: raise ValueError("Invalid risk configuration")
    if not 1<=c["max_positions"]<=20 or not 10<=c["cycle_seconds"]<=300 or not 1<=c["duration_hours"]<=720:
        raise ValueError("Invalid campaign bounds")
    c["strategy_source_sha256"]=hashlib.sha256(Path(__file__).with_name("strategies.py").read_bytes()).hexdigest()
    if c.get("strategy_pack")=="regime-v2":
        c["strategy_pack_source_sha256"]=hashlib.sha256(Path(__file__).with_name("strategies_v2.py").read_bytes()).hexdigest()
    elif c.get("strategy_pack") is not None:
        raise ValueError("Unknown strategy pack")
    return c


class Engine:
    def __init__(self,store,crypto=None,stocks=None,kalshi=None,clock=time.time,estimates=None):
        self.store=store; self.cfg=store.read()["config"]; self.clock=clock
        self.crypto=crypto or Kraken(); self.stocks=stocks or Alpaca(); self.kalshi=kalshi or Kalshi()
        self.adapters={"stocks":self.stocks,"kalshi":self.kalshi}
        self.estimates=estimates or {}; self.history={}; self.history_at={}; self.quotes={}; self.blocked=set()

    def state_update(self,**fields):
        with self.store.transaction():
            s=self.store.read(); s.update(fields); self.store.save(s)

    def provider(self,market,status,reason=None,**extra):
        with self.store.transaction():
            s=self.store.read(); old=s["providers"].get(market,{})
            if market in self.blocked and status in ("ONLINE","MARKET CLOSED"):
                status="BLOCKED";reason=old.get("reason") or "Order reconciliation blocked"
            s["providers"][market]=dict(old,status=status,reason=reason,checked_at=self.clock(),**extra)
            self.store.save(s)

    def recover(self):
        for oid,o in list(self.store.read()["orders"].items()):
            if o["status"] in TERMINAL: continue
            try:
                if o["market"]=="crypto":
                    # An interrupted synthetic fill has no external side effect: cancel the intent.
                    self.store.order_status(oid,"canceled",self.clock())
                    continue
                adapter=self.adapters[o["market"]]
                if not adapter.configured:
                    self.blocked.add(o["market"]); continue
                if o["status"]=="prepared":
                    # Never sent: cancel rather than execute an old signal after downtime.
                    self.store.order_status(oid,"canceled",self.clock()); continue
                observation=adapter.lookup(o)
                if observation is not None:
                    self.store.observe(oid,observation,self.clock())
                else:
                    self.blocked.add(o["market"])
                    self.provider(o["market"],"BLOCKED","Uncertain order awaiting lookup; never blindly resubmitted")
                    continue
                current=self.store.read(); o=current["orders"][oid]
                cancel=o["status"] not in TERMINAL and (self.clock()-o["created_at"]>self.cfg["order_timeout_seconds"] or
                    (o["action"]=="buy" and (current["paused"] or current["emergency"] or current["halt"])))
                if cancel:
                    adapter.cancel(o); self.store.order_status(oid,"pending_cancel",self.clock())
            except Exception as e:
                self.blocked.add(o["market"])
                self.provider(o["market"],"BLOCKED","Order reconciliation: "+type(e).__name__)

    def reconcile_positions(self,market,adapter):
        s=self.store.read(); expected={}
        for p in s["positions"].values():
            if p["market"]==market: expected[p["symbol"]]=expected.get(p["symbol"],0)+p["quantity"]
        actual={}
        for p in adapter.positions():
            symbol=p["symbol"] if market=="stocks" else p["ticker"]
            actual[symbol]=float(p["qty"] if market=="stocks" else p["position_fp"])
        managed=set(expected)
        universe=set(self.cfg["stock_symbols"]) if market=="stocks" else set(self.estimates)|managed
        conflicts=[sym for sym in universe if abs(actual.get(sym,0)-expected.get(sym,0))>1e-6]
        known=set(s["orders"])
        external=[o for o in adapter.open_orders() if o.get("client_order_id") not in known and
            (o.get("symbol",o.get("ticker")) in universe or str(o.get("client_order_id","")).startswith("svcp_"))]
        if conflicts or external:
            self.blocked.add(market)
            self.provider(market,"BLOCKED","Position/order mismatch; other account positions are never adopted or liquidated",
                          conflicts=conflicts,external_orders=len(external))
        with self.store.transaction():
            s=self.store.read(); s["reconciliation"][market]=dict(at=self.clock(),matched=not(conflicts or external),conflicts=conflicts)
            self.store.save(s)

    def market_data(self):
        self.quotes={}
        now=self.clock()
        try:
            q=self.crypto.quotes(self.cfg["crypto_symbols"],now)
            self.quotes.update({"crypto:"+k:v for k,v in q.items()})
            self.provider("crypto","ONLINE",mode=self.crypto.mode,last_success=now,symbols=len(q))
        except Exception as e:
            self.blocked.add("crypto"); self.provider("crypto","UNAVAILABLE",type(e).__name__,mode=self.crypto.mode)
        try:
            account,clock=self.stocks.refresh()
            self.provider("stocks","ONLINE" if clock["is_open"] else "MARKET CLOSED",mode=self.stocks.mode,last_success=now,
                clock=clock,account=dict(status=account.get("status"),buying_power=account.get("buying_power"),
                trading_blocked=account.get("trading_blocked"),account_blocked=account.get("account_blocked")))
            self.reconcile_positions("stocks",self.stocks)
            if clock["is_open"]:
                # The broker calendar handles holidays/early closes; UTC date is valid during the core US session.
                day=time.strftime("%Y-%m-%d",time.gmtime(now))
                if not self.stocks.calendar(day): raise ProviderError("No broker calendar session")
                q=self.stocks.quotes(self.cfg["stock_symbols"],now)
                self.quotes.update({"stocks:"+k:v for k,v in q.items()})
        except Exception as e:
            self.blocked.add("stocks")
            reason=str(e) if isinstance(e,ProviderError) else type(e).__name__
            self.provider("stocks","BLOCKED",reason,mode=self.stocks.mode)
        try:
            if self.kalshi.configured:
                self.kalshi.account()
            discovery=self.kalshi.discover()
            self.provider("kalshi","ONLINE" if self.kalshi.configured else "BLOCKED",
                None if self.kalshi.configured else "Set KALSHI_DEMO_KEY_ID and KALSHI_DEMO_PRIVATE_KEY_PEM; independent probability evidence also required",
                mode=self.kalshi.mode,last_success=now,discovery=[{k:m.get(k) for k in ("ticker","title","status","close_time")} for m in discovery[:8]])
            if self.kalshi.configured:
                self.settlements()
                self.reconcile_positions("kalshi",self.kalshi)
                symbols=set(self.estimates)|{p["symbol"] for p in self.store.read()["positions"].values() if p["market"]=="kalshi"}
                for sym in sorted(symbols)[:10]:
                    try: self.quotes["kalshi:"+sym]=self.kalshi.quote(sym,self.clock())
                    except Exception: continue
        except Exception as e:
            self.blocked.add("kalshi"); self.provider("kalshi","UNAVAILABLE",type(e).__name__,mode=self.kalshi.mode)
        with self.store.transaction():
            s=self.store.read(); s["marks"].update(self.quotes); self.store.save(s)
            self.store.db.executemany("INSERT OR IGNORE INTO quotes VALUES(?,?,?,?,?)",
                [(key.split(":",1)[0],key.split(":",1)[1],q["at"],q["bid"],q["ask"]) for key,q in self.quotes.items() if key.startswith("kalshi:")])

    def settlements(self):
        for tid,p in list(self.store.read()["positions"].items()):
            if p["market"]!="kalshi": continue
            market=self.kalshi.market(p["symbol"])
            if market.get("status")!="settled": continue
            receipts=self.kalshi.settlement(p["symbol"])
            receipt=next((r for r in receipts if timestamp(r["settled_time"])>=p["opened_at"]),None)
            if not receipt: continue
            quantity=float(receipt["yes_count_fp"])
            if abs(quantity-p["quantity"])>1e-6 or float(receipt["no_count_fp"])!=0 or receipt["market_result"] not in ("yes","no"):
                raise ProviderError("Settlement holdings/type mismatch")
            revenue=number(receipt["revenue"])/100
            if abs(revenue-quantity*(receipt["market_result"]=="yes"))>.011:
                raise ProviderError("Nonbinary or adjusted settlement needs review")
            with self.store.transaction():
                s=self.store.read(); p=s["positions"].pop(tid)
                p["proceeds"]+=revenue
                p.update(closed_at=timestamp(receipt["settled_time"]),exit_price=revenue/quantity,
                         exit_reason="EXCHANGE_SETTLEMENT",settlement=receipt,quantity=0)
                p["net_pnl"]=p["proceeds"]-p["cost"]-p["entry_fee"]-p["exit_fee"]
                s["cash"]+=revenue; s["realized"]+=p["net_pnl"]; s["closed"].append(p)
                self.store.event("SETTLEMENT",dict(trade_id=tid,receipt=receipt),self.clock());self.store.save(s)

    def risk(self):
        now=self.clock()
        with self.store.transaction():
            s=self.store.read(); pf=portfolio(s,now)
            if not pf["marks_stale"]:
                s["peak"]=max(s["peak"],pf["equity"])
                if int(now//86400)!=s["day"]:
                    s.update(day=int(now//86400),day_equity=pf["equity"],daily_halt=False)
                if pf["equity"]<=s["day_equity"]*(1-self.cfg["daily_loss_fraction"]): s["daily_halt"]=True
                if pf["equity"]<=s["peak"]*(1-self.cfg["drawdown_fraction"]): s["halt"]="DRAWDOWN_LIMIT"
            if now>=s["deadline"] and not s["halt"]: s["halt"]="CAMPAIGN_COMPLETE"
            self.store.save(s)

    def send(self,oid):
        o=self.store.read()["orders"][oid]
        self.store.order_status(oid,"submitting",self.clock())
        try:
            if o["market"]=="crypto":
                q=self.quotes["crypto:"+o["symbol"]]; validate_quote(q,self.clock(),self.cfg["max_quote_age_seconds"])
                self.crypto.liquidity(o["symbol"],o["quantity"],o["limit_price"],o["action"])
                price=q["ask"]*(1+self.cfg["slippage_fraction"]) if o["action"]=="buy" else q["bid"]*(1-self.cfg["slippage_fraction"])
                if (o["action"]=="buy" and price>o["limit_price"]+1e-9) or (o["action"]=="sell" and price<o["limit_price"]-1e-9):
                    raise ProviderError("Quote moved outside simulated limit",422)
                value=o["quantity"]*price
                observation=dict(client_id=oid,provider_id="sim-"+oid,status="filled",filled_qty=o["quantity"],filled_value=value,fee=value*o["fee_rate"],filled_at=self.clock())
            else: observation=self.adapters[o["market"]].submit(o)
            self.store.observe(oid,observation,self.clock())
        except Exception as e:
            # Simulation has no hidden exchange side effect. External ambiguous writes stay UNKNOWN.
            status="rejected" if o["market"]=="crypto" or isinstance(e,ProviderError) and e.status in (400,401,403,422) else "unknown"
            self.store.order_status(oid,status,self.clock())
            if status=="unknown": self.blocked.add(o["market"])

    def exits(self):
        self.risk(); s=self.store.read(); now=self.clock()
        for tid,p in list(s["positions"].items()):
            key=p["market"]+":"+p["symbol"]; q=self.quotes.get(key)
            if not q: continue
            try: validate_quote(q,now,self.cfg["max_quote_age_seconds"])
            except ProviderError: continue
            if p["market"] in self.blocked: continue
            # A partially filled entry must finish/cancel before an exit can flatten its final quantity.
            pending=[o for o in s["orders"].values() if o["trade_id"]==tid and o["status"] not in TERMINAL]
            reason=p.get("exit_requested") or ("EMERGENCY_FLATTEN" if s["emergency"] else None) or s["halt"] or ("DAILY_LOSS_LIMIT" if s["daily_halt"] else None)
            if p["market"]!="kalshi":
                if p["stop"] is not None and q["bid"]<=p["stop"]: reason=reason or "PROTECTIVE_STOP"
                if p["target"] is not None and q["bid"]>=p["target"]: reason=reason or "TARGET"
                hold=6 if p["symbol"] in ("SH","PSQ") else self.cfg["max_hold_hours"]
                if now-p["opened_at"]>=hold*3600: reason=reason or "TIME_EXIT"
                if p["symbol"] in ("SH","PSQ") and self.stocks.clock.get("next_close"):
                    if timestamp(self.stocks.clock["next_close"])-now<900: reason=reason or "INVERSE_ETF_SESSION_EXIT"
                peak=max(p.get("peak",0),q["bid"])
                stop=p["stop"]
                if peak>=p["entry_price"]+p["stop_distance"]: stop=max(stop,peak-p["stop_distance"])
                with self.store.transaction():
                    fresh=self.store.read(); fresh["positions"][tid].update(peak=peak,stop=stop); self.store.save(fresh)
            if not reason: continue
            if pending:
                for o in pending:
                    if o["action"]=="buy" and o["market"]!="crypto" and o.get("provider_id"):
                        try:
                            self.adapters[o["market"]].cancel(o); self.store.order_status(o["id"],"pending_cancel",now)
                        except ProviderError: pass
                continue
            limit=q["bid"]*(1-self.cfg["slippage_fraction"])
            if p["market"]=="stocks": limit=rounded(limit,2)
            if p["market"]=="kalshi": limit=rounded(q["bid"],2)
            oid="svcp_"+digest([s["campaign_id"],tid,"exit",len(s["orders"])])[:32]
            fee=self.cfg["crypto_fee_fraction"] if p["market"]=="crypto" else self.cfg["stock_fee_fraction"]
            o=dict(id=oid,trade_id=tid,market=p["market"],symbol=p["symbol"],mode=p["mode"],action="sell",quantity=p["quantity"],
                   limit_price=limit,reserve=0,fee_rate=fee,signal="exit",strategy=p["strategy"],signal_at=now,reason=reason)
            if self.store.prepare(o,now): self.send(oid)

    def candidates(self):
        candidates=[]; diagnostics=[]; now=self.clock()
        for market,adapter,symbols in (("crypto",self.crypto,self.cfg["crypto_symbols"]),("stocks",self.stocks,self.cfg["stock_symbols"])):
            for sym in symbols:
                key=market+":"+sym; reason=None; found=[]
                if market in self.blocked: reason=self.store.read()["providers"].get(market,{}).get("reason") or "Provider/reconciliation blocked"
                elif market=="stocks" and not self.stocks.clock.get("is_open"): reason="Market closed"
                elif key not in self.quotes: reason="No valid current quote or unsupported venue asset"
                else:
                    try:
                        if key not in self.history or now-self.history_at[key]>=300:
                            bars=adapter.bars(sym,now)
                            self.history[key]=bars;self.history_at[key]=now
                            self.store.put_candles(market,sym,"1h",bars)
                            self.state_update(heartbeat=self.clock())
                        found,reason=signals(self.history[key],market,sym,now,self.cfg)
                        if market=="stocks" and self.history[key] and now-self.history[key][-1]["time"]>96*3600:
                            found=[];reason="Stale stock history"
                        if found: candidates.append(found[0])
                    except Exception as e: reason="History unavailable: "+type(e).__name__
                diagnostics.append(dict(market=market,pair=sym,reason=reason,execution="CANDIDATE" if found else "WAITING"))
        if self.kalshi.configured and "kalshi" not in self.blocked:
            for sym,estimate in sorted(self.estimates.items())[:10]:
                try:
                    q=self.quotes.get("kalshi:"+sym)
                    candidate,reason=probability_signal(self.kalshi.entry_market(sym,now),q,estimate,now,self.cfg) if q else (None,"No valid contract quote")
                    if candidate: candidates.append(candidate)
                except Exception as e: candidate=None;reason=type(e).__name__
                diagnostics.append(dict(market="kalshi",pair=sym,reason=reason,execution="CANDIDATE" if candidate else "WAITING"))
        if not self.estimates:
            diagnostics.append(dict(market="kalshi",pair="Prediction contracts",reason="Missing independent probability model and calibration evidence",execution="BLOCKED"))
        return sorted(candidates,key=lambda c:(-c["score"],c["market"],c["symbol"])),diagnostics

    def enter(self,c):
        now=self.clock(); s=self.store.read(); market=c["market"]; sym=c["symbol"]
        if shutil.disk_usage(self.store.directory).free<32*1024*1024: return "Persistent storage low; entries blocked, exits active"
        if market in self.blocked: return "Provider or reconciliation blocked"
        # Bootstrap can take time. Refresh quotes before first entry; no historical-price fills.
        if market=="crypto": self.quotes.update({"crypto:"+k:v for k,v in self.crypto.quotes([sym],now).items()})
        elif market=="stocks": self.quotes.update({"stocks:"+k:v for k,v in self.stocks.quotes([sym],now).items()})
        elif market=="kalshi":
            fresh_market=self.kalshi.entry_market(sym,self.clock())
            self.quotes["kalshi:"+sym]=self.kalshi.quote(sym,self.clock())
            fresh,reason=probability_signal(fresh_market,self.quotes["kalshi:"+sym],self.estimates.get(sym),self.clock(),self.cfg)
            if not fresh: return reason
            c=fresh
        q=self.quotes.get(market+":"+sym)
        if not q: return "Current quote unavailable"
        validate_quote(q,self.clock(),self.cfg["max_quote_age_seconds"])
        if s["paused"] or s["emergency"]: return "Entries paused; protective exits remain active"
        if s["halt"] or s["daily_halt"]: return s["halt"] or "Daily loss limit"
        if portfolio(s,now)["marks_stale"]: return "Portfolio has stale position marks"
        if (q["ask"]-q["bid"])/q["ask"]>self.cfg["max_spread_fraction"] and market!="kalshi": return "Spread too wide"
        if market=="crypto" and q["volume_usd"]<self.cfg["minimum_daily_volume_usd"]: return "Insufficient 24-hour liquidity"
        if market!="kalshi" and abs(q["ask"]/c["reference"]-1)>.03: return "Price moved over 3% from closed-bar signal"
        pf=portfolio(s,now); fee=self.cfg["crypto_fee_fraction"] if market=="crypto" else self.cfg["stock_fee_fraction"]
        limit=q["ask"]*(1+self.cfg["slippage_fraction"])
        if market=="stocks": limit=rounded(limit,2,True)
        if market=="kalshi": limit=rounded(q["ask"],2,True);fee=.07*(1-limit)
        target=c.get("target")
        if market!="kalshi" and self.cfg.get("strategy_pack")=="regime-v2":
            target=c["target"] if c.get("target_anchored") else limit+c["target"]-c["reference"]
            if target/limit-1<c["cost_break_even_fraction"]+.01:
                return "Fresh entry price leaves insufficient target room after costs"
        spread_reserve=self.cfg["max_spread_fraction"] if self.cfg.get("strategy_pack")=="regime-v2" else 0
        risk_qty=pf["equity"]*self.cfg["risk_per_trade"]/(c["stop_distance"]+limit*(2*fee+2*self.cfg["slippage_fraction"]+spread_reserve))
        cost=min(pf["available_cash"],pf["equity"]*self.cfg["max_position_fraction"],
                 pf["equity"]*self.cfg["max_exposure_fraction"]-pf["exposure"]-pf["reserved"])
        quantity=min(risk_qty,max(0,cost)/(limit*(1+fee)))
        if market=="kalshi": quantity=math.floor(min(quantity,self.cfg["kalshi_max_cost"]/limit,q["ask_size"]))
        else: quantity=(self.crypto if market=="crypto" else self.stocks).size(sym,quantity,limit)
        if quantity<=0 or market!="kalshi" and quantity*limit<self.cfg["minimum_order_usd"]: return "Insufficient risk budget, cash, or venue minimum"
        if market=="stocks" and quantity>q.get("ask_size",0): return "Insufficient IEX displayed liquidity"
        if market=="kalshi":
            balance=number(self.kalshi.account()["balance"])/100
            if quantity*limit*(1+fee)+.01>balance: return "Insufficient Kalshi demo balance"
        reserve=quantity*limit*(1+fee)+(.01 if market=="kalshi" else 0)
        oid="svcp_"+digest([s["campaign_id"],c["signal"]])[:32]
        o=dict(c,id=oid,trade_id=oid,action="buy",quantity=quantity,limit_price=limit,reserve=reserve,fee_rate=fee,
               mode={"crypto":self.crypto.mode,"stocks":self.stocks.mode,"kalshi":self.kalshi.mode}[market])
        if market!="kalshi": o.update(stop=limit-c["stop_distance"],target=target if self.cfg.get("strategy_pack")=="regime-v2" else limit+(c["target"]-c["reference"]))
        if self.store.prepare(o,now): self.send(oid); return "Order "+self.store.read()["orders"][oid]["status"]
        return "Duplicate signal, owned asset, or shared portfolio limit"

    def cycle(self):
        now=self.clock(); self.blocked=set()
        self.state_update(heartbeat=now)
        self.store.apply_commands(now)
        self.recover(); self.market_data(); self.exits()
        candidates,diagnostics=self.candidates()
        for c in candidates:
            try: reason=self.enter(c)
            except Exception as e: reason="Entry blocked: "+type(e).__name__
            for d in diagnostics:
                if d["market"]==c["market"] and d["pair"]==c["symbol"]: d.update(reason=reason,execution="CHECKED")
        now=self.clock()
        with self.store.transaction():
            s=self.store.read();s.update(heartbeat=now,last_cycle=now,cycles=s["cycles"]+1,diagnostics=diagnostics)
            pf=portfolio(s,now);self.store.save(s)
            self.store.db.execute("INSERT OR REPLACE INTO equity VALUES(?,?,?,?,?)",(now,pf["equity"],pf["cash"],pf["exposure"],pf["drawdown"]))
        if int(now//3600)!=int((s.get("last_backup") or 0)//3600):
            try:
                self.store.backup(now); self.state_update(last_backup=now,backup_error=None)
            except OSError:
                self.state_update(backup_error="Persistent backup failed; inspect volume capacity")
        return dict(cycles=s["cycles"],equity=pf["equity"],open=len(s["positions"]),closed=len(s["closed"]),providers={k:v["status"] for k,v in s["providers"].items()})


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--once",action="store_true");args=parser.parse_args()
    if os.environ.get("SIGNAL_VAULT_MODE","paper").lower()!="paper": raise SystemExit("PAPER ONLY")
    directory=Path(os.environ.get("SV_STATE_DIR",".data/cloud-paper"));directory.mkdir(parents=True,exist_ok=True)
    lock=(directory/"worker.lock").open("a+");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cfg=load_config(os.environ.get("SV_CONFIG"));store=Store(directory,cfg)
    estimates=json.loads(Path(os.environ["SV_PROBABILITIES_FILE"]).read_text()) if os.environ.get("SV_PROBABILITIES_FILE") else {}
    engine=Engine(store,estimates=estimates);stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        while not stopping:
            result=engine.cycle();print(json.dumps(result,allow_nan=False),flush=True)
            if args.once: break
            deadline=time.monotonic()+cfg["cycle_seconds"]
            while not stopping and time.monotonic()<deadline: time.sleep(.5)
    finally:
        store.backup(time.time());store.db.close();lock.close()


if __name__=="__main__": main()
