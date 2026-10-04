"""Fixed-host public data and paper/demo execution; redirects are refused."""
from __future__ import annotations
import base64
import json
import math
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, HTTPRedirectHandler, build_opener
from .store import number

ALPACA = "https://paper-api.alpaca.markets"
DATA = "https://data.alpaca.markets"
KRAKEN = "https://api.kraken.com"
KALSHI_DEMO = "https://external-api.demo.kalshi.co"
KALSHI_PUBLIC = "https://external-api.kalshi.com"


class ProviderError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message); self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def request_json(host, path, method="GET", params=None, body=None, headers=None):
    if host not in (ALPACA, DATA, KRAKEN, KALSHI_DEMO, KALSHI_PUBLIC):
        raise PermissionError("Unapproved provider host")
    if method != "GET" and host not in (ALPACA, KALSHI_DEMO):
        raise PermissionError("Only paper/demo hosts accept writes")
    if not path.startswith("/") or ".." in path or "://" in path:
        raise PermissionError("Invalid provider path")
    url=host+path+("?"+urlencode(params) if params else "")
    h={"Accept":"application/json", "User-Agent":"SignalVault-Paper/1", **(headers or {})}
    data=None if body is None else json.dumps(body,allow_nan=False).encode()
    if data: h["Content-Type"]="application/json"
    for attempt in range(2 if method=="GET" else 1):
        try:
            with build_opener(NoRedirect).open(Request(url, data=data, headers=h, method=method), timeout=8) as r:
                raw=r.read(8_000_001)
            if len(raw)>8_000_000: raise ProviderError("Provider response exceeded bound")
            try: return json.loads(raw) if raw else {}
            except (ValueError,UnicodeDecodeError): raise ProviderError("Provider did not return JSON") from None
        except HTTPError as e:
            if method=="GET" and attempt==0 and e.code in (429,500,502,503,504): continue
            raise ProviderError("Provider HTTP "+str(e.code), e.code) from None
        except (URLError, TimeoutError, OSError):
            if method=="GET" and attempt==0: continue
            raise ProviderError("Provider connection failed; no write retry") from None


def timestamp(value):
    if isinstance(value,(float,int)): return float(value)
    return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()


def iso(value):
    return datetime.fromtimestamp(value,timezone.utc).isoformat().replace("+00:00","Z")


def rounded(value, digits, up=False):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_UP if up else ROUND_DOWN))


def validate_quote(q, now, max_age=90):
    bid,ask=number(q["bid"],1e-12),number(q["ask"],1e-12)
    age=now-number(q["at"])
    if ask<bid or not -5<=age<=max_age: raise ProviderError("Invalid or stale quote")
    return q


class Kraken:
    mode="INTERNAL SIMULATION / KRAKEN PUBLIC DATA"
    def __init__(self, transport=request_json): self.http=transport; self.assets={}
    def get(self,path,params=None):
        data=self.http(KRAKEN,"/0/public/"+path,params=params)
        if data.get("error"): raise ProviderError("Kraken rejected public data request")
        return data["result"]
    def load_assets(self):
        for key,a in self.get("AssetPairs").items():
            name=a.get("wsname","").replace("XBT/","BTC/")
            if name.endswith("/USD") and a.get("status")=="online": self.assets[name]=dict(a,key=key)
        return self.assets
    def quotes(self, symbols, now):
        if not self.assets: self.load_assets()
        keys={self.assets[s]["key"]:s for s in symbols if s in self.assets}
        if not keys: return {}
        result=self.get("Ticker",{"pair":",".join(keys)})
        out={}
        for key,t in result.items():
            if key not in keys: continue
            out[keys[key]]=validate_quote(dict(bid=float(t["b"][0]),ask=float(t["a"][0]),
                at=now,volume_usd=float(t["v"][1])*float(t["p"][1]),source="Kraken response observation"),now)
        return out
    def bars(self,symbol,now,timeframe="1h"):
        minutes={"15m":15,"1h":60,"4h":240,"1d":1440}[timeframe]
        result=self.get("OHLC",{"pair":self.assets[symbol]["key"],"interval":minutes})
        raw=next(v for k,v in result.items() if k!="last")
        return [dict(time=float(r[0]),open=float(r[1]),high=float(r[2]),low=float(r[3]),
                     close=float(r[4]),volume=float(r[6])) for r in raw if float(r[0])+minutes*60<=now]
    def size(self,symbol,quantity,price):
        a=self.assets[symbol]; qty=rounded(quantity,int(a["lot_decimals"]))
        if qty<float(a.get("ordermin",0)) or qty*price<float(a.get("costmin",0)):
            raise ProviderError("Below venue minimum order")
        return qty
    def liquidity(self,symbol,quantity,price,action):
        book=next(iter(self.get("Depth",{"pair":self.assets[symbol]["key"],"count":25}).values()))
        levels=book["asks" if action=="buy" else "bids"]
        available=sum(float(r[1]) for r in levels if (float(r[0])<=price if action=="buy" else float(r[0])>=price))
        if available<quantity: raise ProviderError("Insufficient displayed depth at limit")


class Alpaca:
    mode="ALPACA BROKER PAPER"
    def __init__(self, transport=request_json, environ=None):
        e=os.environ if environ is None else environ
        self.http=transport; self.key=e.get("ALPACA_PAPER_KEY_ID",""); self.secret=e.get("ALPACA_PAPER_SECRET","")
        self.configured=bool(self.key and self.secret); self.assets={}; self.clock={}; self.account={}
    def get(self,path,params=None,host=ALPACA,method="GET",body=None):
        if not self.configured: raise ProviderError("Set ALPACA_PAPER_KEY_ID and ALPACA_PAPER_SECRET")
        return self.http(host,path,method=method,params=params,body=body,
            headers={"APCA-API-KEY-ID":self.key,"APCA-API-SECRET-KEY":self.secret})
    def refresh(self):
        self.account=self.get("/v2/account"); self.clock=self.get("/v2/clock")
        if self.account.get("status")!="ACTIVE" or self.account.get("trading_blocked") or self.account.get("account_blocked"):
            raise ProviderError("Alpaca paper account blocked")
        if not self.assets:
            self.assets={a["symbol"]:a for a in self.get("/v2/assets",{"status":"active","asset_class":"us_equity"}) if a.get("tradable")}
        return self.account,self.clock
    def calendar(self,day): return self.get("/v2/calendar",{"start":day,"end":day})
    def quotes(self,symbols,now):
        data=self.get("/v2/stocks/quotes/latest",{"symbols":",".join(symbols),"feed":"iex"},host=DATA)
        out={}
        for s,q in data.get("quotes",{}).items():
            try: out[s]=validate_quote(dict(bid=float(q["bp"]),ask=float(q["ap"]),at=timestamp(q["t"]),
                           bid_size=float(q["bs"])*100,ask_size=float(q["as"])*100,source="Alpaca IEX",volume_usd=None),now)
            except (ValueError,KeyError,ProviderError): pass
        return out
    def bars(self,symbol,now,timeframe="1h"):
        data=self.get("/v2/stocks/"+quote(symbol,safe="")+"/bars",dict(timeframe="1Hour",start=iso(now-45*86400),
            end=iso(now),limit=10000,adjustment="all",feed="iex",sort="asc"),host=DATA)
        if data.get("next_page_token"): raise ProviderError("History pagination exceeds bounded warmup")
        return [dict(time=timestamp(b["t"]),open=float(b["o"]),high=float(b["h"]),low=float(b["l"]),close=float(b["c"]),volume=float(b["v"]))
                for b in data.get("bars",[]) if timestamp(b["t"])+3600<=now]
    def size(self,symbol,quantity,price):
        a=self.assets.get(symbol)
        if not a: raise ProviderError("Asset unsupported or not tradable")
        return rounded(quantity,6 if a.get("fractionable") else 0)
    def positions(self): return self.get("/v2/positions")
    def open_orders(self): return self.get("/v2/orders",{"status":"open","limit":500})
    def parse(self,raw,order):
        if raw.get("client_order_id")!=order["id"] or raw.get("symbol")!=order["symbol"] or raw.get("side")!=order["action"]:
            raise ProviderError("Alpaca order identity mismatch")
        fq=number(raw.get("filled_qty",0)); price=number(raw.get("filled_avg_price") or 0)
        status=raw["status"]
        status={"new":"accepted","pending_new":"accepted","accepted_for_bidding":"accepted",
                "partially_filled":"partial","done_for_day":"accepted","stopped":"unknown","suspended":"unknown","replaced":"unknown"}.get(status,status)
        if status not in {"filled","accepted","partial","canceled","rejected","expired","pending_cancel"}: status="unknown"
        value=fq*price
        return dict(client_id=order["id"],provider_id=raw["id"],status=status,filled_qty=fq,filled_value=value,
                    fee=value*order["fee_rate"],filled_at=timestamp(raw["filled_at"]) if raw.get("filled_at") else None)
    def submit(self,o):
        if not self.clock.get("is_open"): raise ProviderError("Market closed",422)
        if o["action"]=="buy" and number(self.account.get("buying_power",0))<o["reserve"]:
            raise ProviderError("Insufficient paper buying power",422)
        raw=self.get("/v2/orders",method="POST",body=dict(symbol=o["symbol"],qty=format(o["quantity"],".6f"),
            side=o["action"],type="limit",limit_price=format(o["limit_price"],".2f"),time_in_force="day",
            extended_hours=False,client_order_id=o["id"]))
        return self.parse(raw,o)
    def lookup(self,o):
        try: return self.parse(self.get("/v2/orders:by_client_order_id",{"client_order_id":o["id"]}),o)
        except ProviderError as e:
            if e.status==404: return None
            raise
    def cancel(self,o):
        if o.get("provider_id"): self.get("/v2/orders/"+quote(o["provider_id"],safe=""),method="DELETE")


class Kalshi:
    """Long YES binary contracts only. Demo writes cannot reach production."""
    def __init__(self,transport=request_json,environ=None):
        e=os.environ if environ is None else environ
        self.http=transport; self.key_id=e.get("KALSHI_DEMO_KEY_ID",""); self.pem=e.get("KALSHI_DEMO_PRIVATE_KEY_PEM","")
        self.configured=bool(self.key_id and self.pem)
        self.host=KALSHI_DEMO if self.configured else KALSHI_PUBLIC
        self.mode="KALSHI DEMO" if self.configured else "PUBLIC DATA / EXECUTION BLOCKED"
    def call(self,path,params=None,method="GET",body=None,auth=False):
        full="/trade-api/v2"+path; headers={}
        if auth or method!="GET":
            if not self.configured or self.host!=KALSHI_DEMO: raise PermissionError("Demo credentials required")
            from cryptography.hazmat.primitives import serialization, hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa, ed25519
            key=serialization.load_pem_private_key(self.pem.encode(),password=None)
            stamp=str(int(time.time()*1000)); message=(stamp+method+full).encode()
            if isinstance(key,rsa.RSAPrivateKey):
                signed=key.sign(message,padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32),hashes.SHA256())
            elif isinstance(key,ed25519.Ed25519PrivateKey): signed=key.sign(message)
            else: raise ProviderError("Unsupported Kalshi demo signing key")
            headers={"KALSHI-ACCESS-KEY":self.key_id,"KALSHI-ACCESS-TIMESTAMP":stamp,"KALSHI-ACCESS-SIGNATURE":base64.b64encode(signed).decode()}
        return self.http(self.host,full,method=method,params=params,body=body,headers=headers)
    def discover(self):
        # Ordinary events only; explicitly bounded discovery, never claims exhaustive coverage.
        rows=self.call("/markets",{"status":"open","limit":30,"mve_filter":"exclude"})
        return rows.get("markets",[])
    def market(self,ticker): return self.call("/markets/"+quote(ticker,safe=""))["market"]
    def quote(self,ticker,now):
        data=self.call("/markets/"+quote(ticker,safe="")+"/orderbook",{"depth":20})
        book=data.get("orderbook_fp",{})
        yes=book.get("yes_dollars",[]); no=book.get("no_dollars",[])
        if not yes or not no: raise ProviderError("No two-sided contract liquidity")
        y=max(yes,key=lambda v:float(v[0])); n=max(no,key=lambda v:float(v[0]))
        return validate_quote(dict(bid=float(y[0]),ask=1-float(n[0]),bid_size=float(y[1]),ask_size=float(n[1]),at=now,source=self.mode),now)
    def account(self): return self.call("/portfolio/balance",auth=True)
    def positions(self):
        d=self.call("/portfolio/positions",{"limit":1000},auth=True)
        if d.get("cursor"): raise ProviderError("Position pagination requires review")
        return d.get("market_positions",[])
    def open_orders(self):
        d=self.call("/portfolio/orders",{"status":"resting","limit":1000},auth=True)
        if d.get("cursor"): raise ProviderError("Order pagination requires review")
        return d.get("orders",[])
    def submit(self,o):
        raw=self.call("/portfolio/events/orders",method="POST",auth=True,body=dict(ticker=o["symbol"],
            client_order_id=o["id"],side="bid" if o["action"]=="buy" else "ask",count=format(o["quantity"],".2f"),
            price=format(o["limit_price"],".4f"),time_in_force="immediate_or_cancel",
            self_trade_prevention_type="taker_at_cross",cancel_order_on_pause=True,reduce_only=o["action"]=="sell"))
        if raw.get("client_order_id")!=o["id"]: raise ProviderError("Kalshi create identity mismatch")
        # Create receipt lacks fill cost. Only GET reconciliation can book an execution.
        return dict(client_id=o["id"],provider_id=raw["order_id"],status="unknown",filled_qty=0,filled_value=0,fee=0)
    def parse(self,raw,o):
        if raw.get("client_order_id")!=o["id"] or raw.get("ticker")!=o["symbol"]:
            raise ProviderError("Kalshi order identity mismatch")
        expected_outcome="yes" if o["action"]=="buy" else "no"
        if raw.get("outcome_side")!=expected_outcome: raise ProviderError("Contract exposure direction mismatch")
        book=raw.get("book_side")
        if book is not None and book!=("bid" if o["action"]=="buy" else "ask"): raise ProviderError("Contract direction mismatch")
        qty=number(raw["fill_count_fp"])
        value=number(raw["taker_fill_cost_dollars"])+number(raw["maker_fill_cost_dollars"])
        fee=number(raw["taker_fees_dollars"])+number(raw["maker_fees_dollars"])
        status={"executed":"filled","resting":"partial" if qty else "accepted","canceled":"canceled"}[raw["status"]]
        return dict(client_id=o["id"],provider_id=raw["order_id"],status=status,filled_qty=qty,filled_value=value,fee=fee)
    def lookup(self,o):
        if o.get("provider_id"):
            raw=self.call("/portfolio/orders/"+quote(o["provider_id"],safe=""),{"market_ticker":o["symbol"]},auth=True)["order"]
            return self.parse(raw,o)
        cursor=None
        for _ in range(5):
            params={"ticker":o["symbol"],"limit":200}
            if cursor: params["cursor"]=cursor
            d=self.call("/portfolio/orders",params,auth=True)
            for r in d.get("orders",[]):
                if r.get("client_order_id")==o["id"]: return self.parse(r,o)
            cursor=d.get("cursor")
            if not cursor: return None
        raise ProviderError("Order discovery bound reached; uncertain order remains blocked")
    def cancel(self,o):
        if o.get("provider_id"):
            self.call("/portfolio/events/orders/"+quote(o["provider_id"],safe=""),
                      {"market_ticker":o["symbol"]},method="DELETE",auth=True)
    def settlement(self,ticker):
        d=self.call("/portfolio/settlements",{"ticker":ticker,"limit":100},auth=True)
        if d.get("cursor"): raise ProviderError("Settlement pagination requires review")
        return [r for r in d.get("settlements",[]) if r.get("ticker")==ticker]
