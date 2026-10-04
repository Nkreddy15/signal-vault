"""Loopback-only browser fixture, isolated temporary ledger; NEVER a campaign server."""
import base64
import json
import tempfile
import time
from pathlib import Path
from trading_stack.cloud_paper.engine import load_config
from trading_stack.cloud_paper.store import Store
from trading_stack.cloud_paper.web import create_app
from trading_stack.test_cloud_paper import bars,order,obs


def main():
    now=time.time();directory=tempfile.mkdtemp(prefix="sv-ui-fixture-")
    cfg=load_config();cfg["evidence"]="ISOLATED EXECUTION FIXTURE — NOT CAMPAIGN PERFORMANCE"
    store=Store(directory,cfg,now-7200)
    for i,market,symbol in ((1,"crypto","BTC/USD"),(2,"crypto","ETH/USD"),(3,"stocks","SPY"),(4,"kalshi","DEMO-CONTRACT")):
        o=order("fixture-"+str(i),market=market,symbol=symbol,quantity=1 if market=="kalshi" else .5,price=.4 if market=="kalshi" else 100)
        o.update(signal_at=now-3600,mode="ISOLATED EXECUTION FIXTURE")
        if market=="kalshi":o.update(stop=None,target=None,stop_distance=.4,contract=dict(market=dict(title="Isolated binary contract fixture",close_time="2026-10-05T20:00:00Z")))
        store.prepare(o,now-3500);ob=obs(o);ob["filled_at"]=now-3500;store.observe(o["id"],ob,now-3500)
        store.put_candles(market,symbol,"1h",bars(now+3600,93))
    sell=order("fixture-exit",action="sell",tid="fixture-1",price=103)
    store.prepare(sell,now-100);ob=obs(sell);ob["filled_at"]=now-100;store.observe(sell["id"],ob,now-100)
    s=store.read();s.update(heartbeat=now,last_cycle=now,cycles=2)
    s["providers"]={m:dict(status="FIXTURE",mode="ISOLATED EXECUTION FIXTURE",reason="Browser verification only") for m in ("crypto","stocks","kalshi")}
    s["diagnostics"]=[dict(market="crypto",pair="BTC/USD",reason="ISOLATED EXECUTION FIXTURE — NOT CAMPAIGN PERFORMANCE",execution="TESTED")]
    s["marks"]={m+":"+sym:dict(bid=.45 if m=="kalshi" else 102,ask=.46 if m=="kalshi" else 102.01,at=now) for m,sym in (("crypto","BTC/USD"),("crypto","ETH/USD"),("stocks","SPY"),("kalshi","DEMO-CONTRACT"))}
    store.save(s)
    for i in range(15):store.db.execute("INSERT INTO equity VALUES(?,?,?,?,?)",(now-7200+i*400,500+i*.05,350,150,0))
    store.db.close()
    password="isolated-browser-fixture-only-"+"x"*20
    app=create_app(directory,password)
    auth="Basic "+base64.b64encode(("nikhil:"+password).encode()).decode()
    original=app.wsgi_app
    def fixture_auth(environ,start_response):
        environ["HTTP_AUTHORIZATION"]=auth
        return original(environ,start_response)
    app.wsgi_app=fixture_auth
    print(json.dumps(dict(mode="ISOLATED FIXTURE",directory=directory)),flush=True)
    app.run(host="127.0.0.1",port=8090,debug=False)


if __name__=="__main__":main()
