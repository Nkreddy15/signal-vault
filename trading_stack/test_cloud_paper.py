"""Isolated execution/accounting fixtures. Never writes a campaign or contacts a broker."""
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from trading_stack.cloud_paper.engine import Engine,load_config
from trading_stack.cloud_paper.store import Store,portfolio
from trading_stack.cloud_paper.providers import Alpaca,Kalshi,Kraken,ProviderError,validate_quote,ALPACA,KALSHI_DEMO,request_json
from trading_stack.cloud_paper.strategies import signals,probability_signal
from trading_stack.cloud_paper.web import create_app,snapshot
from trading_stack.cloud_paper.supervisor import settings

NOW=1780002000//3600*3600+600


def bars(now=NOW,base=100):
    boundary=int(now//3600)*3600
    return [dict(time=boundary-(90-i)*3600,open=base+i*.08,high=base+i*.08+.2,
                 low=base+i*.08-.2,close=base+i*.08+.1,volume=100000) for i in range(90)]


class FakeKraken:
    mode="ISOLATED FIXTURE INTERNAL SIMULATION"
    def __init__(self):self.price=bars()[-1]["close"];self.failed=False;self.depth=True
    def quotes(self,symbols,now):
        if self.failed:raise ProviderError("fixture unavailable")
        return {s:dict(bid=self.price,ask=self.price*1.0001,at=now,volume_usd=10000000) for s in symbols}
    def bars(self,symbol,now,timeframe="1h"):return bars(now)
    def size(self,symbol,quantity,price):return round(quantity,6)
    def liquidity(self,*args):
        if not self.depth:raise ProviderError("depth unavailable")


class NoKalshi:
    mode="PUBLIC DATA / EXECUTION BLOCKED";configured=False
    def discover(self):return []


def order(oid="one",market="crypto",symbol="BTC/USD",action="buy",tid=None,quantity=.5,price=100,fee=.004):
    return dict(id=oid,trade_id=tid or oid,market=market,symbol=symbol,action=action,mode="ISOLATED FIXTURE",
        signal=oid,strategy="trend",signal_at=NOW,reason="isolated execution test",quantity=quantity,
        limit_price=price,reserve=quantity*price*(1+fee) if action=="buy" else 0,fee_rate=fee,stop=98,target=105,stop_distance=2)


def obs(o,quantity=None,price=None,fee=None,status="filled"):
    qty=o["quantity"] if quantity is None else quantity;price=o["limit_price"] if price is None else price
    return dict(client_id=o["id"],provider_id="fixture-"+o["id"],status=status,filled_qty=qty,filled_value=qty*price,
                fee=qty*price*o["fee_rate"] if fee is None else fee,filled_at=NOW)


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.cfg=load_config();self.cfg["crypto_symbols"]=["BTC/USD","ETH/USD"]
        self.cfg["stock_symbols"]=["SPY"];self.store=Store(self.tmp.name,self.cfg,NOW)
        self.feed=FakeKraken();self.clock=NOW
        self.engine=Engine(self.store,self.feed,Alpaca(environ={}),NoKalshi(),clock=lambda:self.clock)
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def fill(self,o=None):
        o=o or order();self.assertTrue(self.store.prepare(o,self.clock));self.store.observe(o["id"],obs(o),self.clock);return o
    def test_first_cycle_evaluates_history_and_enters_without_delay(self):
        result=self.engine.cycle();self.assertGreater(result["open"],0)
        self.assertEqual(result["cycles"],1);self.assertEqual(self.store.read()["config"]["capital"],500)
    def test_restart_preserves_deadline_losses_and_duplicate_signals(self):
        self.engine.cycle();s=self.store.read();count=len(s["orders"])
        self.store.db.close();self.store=Store(self.tmp.name,self.cfg,NOW+1000)
        self.engine=Engine(self.store,self.feed,Alpaca(environ={}),NoKalshi(),clock=lambda:self.clock)
        self.engine.cycle();after=self.store.read()
        self.assertEqual(after["deadline"],s["deadline"]);self.assertEqual(after["cash"],s["cash"]);self.assertEqual(len(after["orders"]),count)
    def test_changed_frozen_config_refused(self):
        cfg=dict(self.cfg,capital=501)
        with self.assertRaises(ValueError):Store(self.tmp.name,cfg,NOW)
    def test_partial_fill_idempotence_and_cancel_release(self):
        o=order();self.store.prepare(o,NOW);p=obs(o,.2,status="partial")
        self.store.observe("one",p,NOW);self.store.observe("one",p,NOW)
        self.assertAlmostEqual(self.store.read()["cash"],479.92)
        self.store.observe("one",dict(p,status="canceled"),NOW+1)
        self.assertEqual(portfolio(self.store.read(),NOW)["reserved"],0)
        self.assertAlmostEqual(self.store.read()["positions"]["one"]["quantity"],.2)
    def test_buy_sell_exact_accounting_and_fees(self):
        self.fill();sell=order("sell",action="sell",tid="one",price=110)
        self.store.prepare(sell,NOW);self.store.observe("sell",obs(sell),NOW)
        s=self.store.read();self.assertAlmostEqual(s["cash"],504.58);self.assertAlmostEqual(s["realized"],4.58)
        self.assertEqual(s["positions"],{});self.assertAlmostEqual(s["fees"],.42)
    def test_nonmonotonic_and_overfill_rejected_atomically(self):
        o=order();self.store.prepare(o,NOW);self.store.observe("one",obs(o,.3,status="partial"),NOW)
        before=self.store.read()
        for bad in (obs(o,.2,status="partial"),obs(o,.6)):
            with self.assertRaises(ValueError):self.store.observe("one",bad,NOW)
            self.assertEqual(self.store.read(),before)
    def test_identity_mismatch_rejected(self):
        o=order();self.store.prepare(o,NOW)
        with self.assertRaises(ValueError):self.store.observe("one",dict(obs(o),client_id="other"),NOW)
    def test_no_sell_more_than_owned(self):
        self.fill();self.assertFalse(self.store.prepare(order("sell",action="sell",tid="one",quantity=.6),NOW))
    def test_shared_capital_across_markets_and_pending_reservations(self):
        for i,m in enumerate(["crypto","stocks","kalshi","crypto"]):
            self.assertTrue(self.store.prepare(order(str(i),market=m,symbol=str(i),quantity=.9),NOW))
        self.assertFalse(self.store.prepare(order("extra",market="stocks",symbol="other",quantity=.9),NOW))
        self.assertLessEqual(portfolio(self.store.read(),NOW)["reserved"],400)
    def test_position_size_limit(self):self.assertFalse(self.store.prepare(order(quantity=2),NOW))
    def test_pause_does_not_disable_protective_exit(self):
        self.fill();self.store.command("pause","pause-test");self.store.apply_commands(NOW)
        self.feed.price=90;self.engine.quotes={"crypto:BTC/USD":self.feed.quotes(["BTC/USD"],NOW)["BTC/USD"]}
        self.engine.exits();s=self.store.read();self.assertFalse(s["positions"]);self.assertTrue(s["paused"])
        self.assertEqual(s["closed"][0]["exit_reason"],"PROTECTIVE_STOP")
    def test_emergency_is_durable_and_resume_does_not_clear_it(self):
        self.fill();self.store.command("flatten","emergency-test");self.store.command("resume","resume-test")
        self.store.apply_commands(NOW);self.assertTrue(self.store.read()["emergency"])
        self.assertTrue(self.store.read()["paused"])
    def test_commands_idempotent(self):
        a=self.store.command("pause","duplicate-command");b=self.store.command("pause","duplicate-command")
        self.assertEqual(a,b)
    def test_stale_prices_never_close(self):
        self.fill();self.engine.quotes={"crypto:BTC/USD":dict(bid=90,ask=91,at=NOW-1000)}
        self.engine.exits();self.assertTrue(self.store.read()["positions"])
    def test_drawdown_halt_persists_on_restart(self):
        self.fill();s=self.store.read();s["cash"]-=60;s["marks"]["crypto:BTC/USD"]={"bid":100,"ask":100.01,"at":NOW};self.store.save(s);self.engine.risk()
        self.assertEqual(self.store.read()["halt"],"DRAWDOWN_LIMIT")
        other=Store(self.tmp.name,self.cfg,NOW);self.assertEqual(other.read()["halt"],"DRAWDOWN_LIMIT");other.db.close()
    def test_campaign_deadline_does_not_reset(self):
        self.clock=self.store.read()["deadline"]+1;self.engine.risk()
        self.assertEqual(self.store.read()["halt"],"CAMPAIGN_COMPLETE")
        self.assertFalse(self.store.prepare(order(),self.clock))
    def test_backup_restore_has_positions_and_deadline(self):
        self.fill();backup=self.store.backup(NOW)
        target=Path(self.tmp.name)/"restore";target.mkdir();shutil.copyfile(backup,target/"campaign.sqlite3")
        other=Store(target,self.cfg,NOW+1000);self.assertEqual(other.read(),self.store.read());other.db.close()
    def test_rejected_fill_has_no_position(self):
        self.feed.depth=False;self.engine.cycle();self.assertFalse(self.store.read()["positions"])
        self.assertTrue(all(o["status"]=="rejected" for o in self.store.read()["orders"].values()))
    def test_uncertain_post_is_looked_up_never_resubmitted(self):
        o=order("ambiguous",market="stocks",symbol="SPY");self.store.prepare(o,NOW);self.store.order_status(o["id"],"submitting",NOW)
        class Broker:
            configured=True
            def lookup(self,o):return obs(o)
            def submit(self,o):raise AssertionError("Duplicate POST")
        self.engine.adapters["stocks"]=Broker();self.engine.recover()
        self.assertEqual(self.store.read()["orders"][o["id"]]["status"],"filled")
        self.engine.recover();self.assertEqual(len(self.store.read()["positions"]),1)
    def test_unresolved_post_blocks_market(self):
        o=order("ambiguous",market="stocks",symbol="SPY");self.store.prepare(o,NOW);self.store.order_status(o["id"],"unknown",NOW)
        class Broker:
            configured=True
            def lookup(self,o):return None
        self.engine.adapters["stocks"]=Broker();self.engine.recover();self.assertIn("stocks",self.engine.blocked)
    def test_external_position_is_not_adopted(self):
        class Broker:
            def positions(self):return [dict(symbol="SPY",qty="4")]
            def open_orders(self):return []
        self.engine.reconcile_positions("stocks",Broker());self.assertIn("stocks",self.engine.blocked)
        self.assertFalse(self.store.read()["positions"])
    def test_no_history_lookahead_or_missing_bar_warmup(self):
        rows=bars();rows[-1]["time"]=NOW
        self.assertFalse(signals(rows,"crypto","BTC/USD",NOW,self.cfg)[0])
        self.assertFalse(signals(bars()[:-2]+bars()[-1:],"crypto","BTC/USD",NOW,self.cfg)[0])
    def test_probabilities_require_provenance_and_cost_cleared_lower_bound(self):
        m=dict(market_type="binary",status="active",ticker="TEST");q=dict(ask=.4,ask_size=10)
        self.assertIsNone(probability_signal(m,q,None,NOW,self.cfg)[0])
        e=dict(probability=.7,lower_bound=.6,upper_bound=.8,as_of=NOW,expires_at=NOW+300,source="fixture",model_version="fixture",calibration_report_sha256="a"*64)
        self.assertIsNotNone(probability_signal(m,q,e,NOW,self.cfg)[0])
        self.assertIsNone(probability_signal(m,q,dict(e,lower_bound=.41),NOW,self.cfg)[0])
    def test_private_dashboard_csrf_health_and_candles(self):
        self.fill();s=self.store.read();s["heartbeat"]=time.time();self.store.save(s)
        self.store.put_candles("crypto","BTC/USD","1h",bars())
        app=create_app(self.tmp.name,"x"*40);client=app.test_client();auth={"Authorization":"Basic "+base64.b64encode(b"nikhil:"+b"x"*40).decode()}
        self.assertEqual(client.get("/").status_code,401)
        self.assertEqual(client.get("/healthz").status_code,200)
        data=client.get("/api/snapshot",headers=auth).get_json();self.assertEqual(len(data["cloud"]["open_trades"]),1)
        self.assertEqual(client.post("/api/control",headers=auth,json={"action":"pause"}).status_code,403)
        h=dict(auth,Origin="http://localhost",**{"X-CSRF-Token":data["cloud"]["csrf_token"],"Idempotency-Key":"test-command"})
        self.assertEqual(client.post("/api/control",headers=h,json={"action":"pause"}).status_code,202)
        self.assertEqual(client.get("/api/candles?market=crypto&pair=BTC/USD&timeframe=1h",headers=auth).status_code,200)
        page=client.get("/",headers=auth).data.decode();self.assertIn("/static/cloud.js",page);self.assertNotIn("127.0.0.1:8080",page)
    def test_stale_worker_is_not_healthy(self):
        app=create_app(self.tmp.name,"x"*40);self.assertEqual(app.test_client().get("/healthz").status_code,503)
        self.assertEqual(snapshot(self.store,time.time())["cloud"]["status"],"WORKER STALE")


class AdapterTests(unittest.TestCase):
    def test_live_host_and_public_writes_refused(self):
        with self.assertRaises(PermissionError):request_json("https://example.com","/orders",method="POST")
        with self.assertRaises(PermissionError):request_json("https://external-api.kalshi.com","/trade-api/v2/portfolio/events/orders",method="POST")
    def test_alpaca_fractional_day_order_and_paper_host(self):
        calls=[];o=order("alpaca-test",market="stocks",symbol="SPY")
        def http(host,path,**kw):
            calls.append((host,path,kw));return dict(id="broker-1",client_order_id=o["id"],symbol="SPY",side="buy",status="new",filled_qty="0",filled_avg_price=None)
        a=Alpaca(http,{"ALPACA_PAPER_KEY_ID":"fixture","ALPACA_PAPER_SECRET":"fixture"});a.clock={"is_open":True};a.account={"buying_power":"500"}
        result=a.submit(o);self.assertEqual(calls[0][0],ALPACA);self.assertEqual(calls[0][2]["body"]["time_in_force"],"day")
        self.assertEqual(result["status"],"accepted")
    def test_closed_stock_market_refuses_submit(self):
        a=Alpaca(environ={});a.clock={"is_open":False}
        with self.assertRaises(ProviderError):a.submit(order())
    def test_kalshi_v2_demo_signature_payload_and_sell_direction(self):
        from cryptography.hazmat.primitives.asymmetric import rsa,padding
        from cryptography.hazmat.primitives import serialization,hashes
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048);calls=[]
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
        def http(host,path,**kw):
            calls.append((host,path,kw));return {"order_id":"test","client_order_id":"kalshi-test","fill_count":"1.00","remaining_count":"0.00"}
        a=Kalshi(http,{"KALSHI_DEMO_KEY_ID":"fixture","KALSHI_DEMO_PRIVATE_KEY_PEM":pem});o=order("kalshi-test",market="kalshi",symbol="TEST",quantity=1,price=.4)
        result=a.submit(o);host,path,kwargs=calls[0];self.assertEqual(host,KALSHI_DEMO);self.assertEqual(result["status"],"unknown")
        headers=kwargs["headers"];key.public_key().verify(base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),(headers["KALSHI-ACCESS-TIMESTAMP"]+"POST"+path).encode(),padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32),hashes.SHA256())
        self.assertEqual(kwargs["body"]["side"],"bid");self.assertEqual(kwargs["body"]["count"],"1.00")
        raw=dict(order_id="test",client_order_id=o["id"],ticker="TEST",outcome_side="no",book_side="ask",fill_count_fp="1.00",taker_fill_cost_dollars="0.60",maker_fill_cost_dollars="0",taker_fees_dollars="0.02",maker_fees_dollars="0",status="executed")
        self.assertEqual(a.parse(raw,dict(o,action="sell"))["filled_qty"],1)
    def test_quote_validation_and_no_fractional_short(self):
        with self.assertRaises(ProviderError):validate_quote(dict(bid=101,ask=100,at=NOW),NOW)
        with self.assertRaises(ProviderError):validate_quote(dict(bid=100,ask=101,at=NOW-100),NOW)
    def test_hosting_refuses_ephemeral_state(self):
        with self.assertRaises(ValueError):settings({"SV_DASHBOARD_PASSWORD":"x"*40,"SV_STATE_DIR":"/tmp/cloud-paper","RAILWAY_VOLUME_MOUNT_PATH":"/not-a-mount","SV_ALLOW_NEW_CAMPAIGN":"1"})
    def test_live_config_refused(self):
        with tempfile.NamedTemporaryFile(mode="w") as f:
            cfg=load_config();cfg["crypto_mode"]="live";json.dump(cfg,f);f.flush()
            with self.assertRaises(ValueError):load_config(f.name)


if __name__=="__main__":unittest.main()
