import asyncio, hashlib, json, time
from urllib.parse import urlencode, quote
from .models import Market, Book, Opportunity, D, decimal

class Scanner:
    def __init__(self,c,http):
        self.c=c; self.http=http; self.cycle=0; self.offset=0; self.next_offset=0
        self.metrics={"market_rows":0,"compatible_markets":0,"book_errors":0,"unsupported_markets":0}
    async def markets(self):
        if self.c.DATA_SOURCE=="DEMO":
            return [Market("demo-complete-set","demo-condition","demo-yes","demo-no","Synthetic binary event",D("0"))]
        result=[]
        for page in range(self.c.MARKET_PAGES):
            rows=await self.http.request(self.c.GAMMA_URL+"/markets?"+urlencode({"active":"true","closed":"false","limit":self.c.MARKET_LIMIT,"offset":self.offset+page*self.c.MARKET_LIMIT}))
            if not isinstance(rows,list): raise ValueError("Unexpected Gamma schema")
            self.metrics["market_rows"]+=len(rows)
            self.next_offset=self.offset+(page+1)*self.c.MARKET_LIMIT if len(rows)==self.c.MARKET_LIMIT else 0
            for m in rows:
                try:
                    if m.get("positionIds") or m.get("negRisk") or m.get("closed") or not m.get("acceptingOrders") or not m.get("enableOrderBook"):
                        self.metrics["unsupported_markets"]+=1;continue
                    labels=m["outcomes"]; tokens=m["clobTokenIds"]
                    if isinstance(labels,str): labels=json.loads(labels)
                    if isinstance(tokens,str): tokens=json.loads(tokens)
                    labels=[str(x).lower() for x in labels]
                    if len(labels)!=2 or set(labels)!={"yes","no"} or len(set(tokens))!=2: continue
                    condition=m["conditionId"]
                    info=await self.http.request(self.c.CLOB_URL+"/clob-markets/"+quote(condition,safe=""))
                    fd=info.get("fd")
                    # Unsupported fee curves are rejected instead of assumed fee-free.
                    if not isinstance(fd,dict) or "r" not in fd or decimal(fd.get("e",1))!=1 or decimal(info.get("tbf",0))!=0: continue
                    rate=decimal(fd["r"])
                    if not 0<=rate<=1: continue
                    mapping={t["o"].lower():t["t"] for t in info["t"]}
                    if mapping.get("yes")!=tokens[labels.index("yes")] or mapping.get("no")!=tokens[labels.index("no")]: continue
                    result.append(Market(m.get("events",[{}])[0].get("slug",m["slug"]) if m.get("events") else m["slug"],condition,mapping["yes"],mapping["no"],m.get("question",""),rate,decimal(info["mos"])))
                except (KeyError,ValueError,TypeError,IndexError): self.metrics["unsupported_markets"]+=1;continue
            if len(rows)<self.c.MARKET_LIMIT: break
        self.metrics["compatible_markets"]=len(result)
        return result

    async def book(self,market,token):
        if self.c.DATA_SOURCE=="DEMO":
            p=D("0.47") if token==market.yes else D("0.50")
            size=D("4") if self.c.DEMO_PARTIAL_LEG and token==market.no else D("100")
            now=time.time()
            return Book(token,market.condition,[(p,size),(p+D("0.01"),D("100"))],[(p-D("0.03"),D("100"))],now,now,str(self.cycle)+token)
        raw=await self.http.request(self.c.CLOB_URL+"/book?"+urlencode({"token_id":token})); received=time.time()
        if raw["asset_id"]!=token or raw["market"]!=market.condition or raw.get("neg_risk"): raise ValueError("Book identity mismatch")
        def levels(side):
            data=[(decimal(x["price"]),decimal(x["size"])) for x in raw[side]]
            if any(not 0<p<1 or s<=0 for p,s in data): raise ValueError("Invalid book levels")
            return data
        tick=decimal(raw["tick_size"])
        if tick<=0: raise ValueError("Invalid tick")
        return Book(token,market.condition,levels("asks"),levels("bids"),float(raw["timestamp"])/1000,received,raw.get("hash") or hashlib.sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest(),decimal(raw["min_order_size"]),tick)

    async def pair(self,m): return await asyncio.gather(self.book(m,m.yes),self.book(m,m.no))
    def price(self,m,y,n):
        q=self.c.PAIR_SHARES.quantize(D("0.01")); fy,cy,ly=y.sweep(q); fn,cn,ln=n.sweep(q)
        if q<max(m.min_size,y.min_size,n.min_size) or fy<q or fn<q: return None
        if not y.asks or not n.asks: return None
        # Fee upper bound at every occupied price; avoids applying curve to VWAP.
        def fee(book):
            remaining=q; total=D(0)
            for p,s in sorted(book.asks):
                take=min(s,remaining); total+=take*m.fee_rate*p*(1-p); remaining-=take
                if remaining<=0: break
            return total
        from decimal import ROUND_CEILING
        fees=sum((fee(b).quantize(D("0.00001"),rounding=ROUND_CEILING) for b in (y,n)),D(0))
        reserve=cy+cn+fees+q*self.c.MAX_SLIPPAGE*2+self.c.MERGE_COST
        key=hashlib.sha256((m.condition+y.fingerprint+n.fingerprint).encode()).hexdigest()
        ay=min(y.asks)[0]; an=min(n.asks)[0]
        return Opportunity(m,y,n,q,ay,an,1-ay-an,(q-reserve)/q,reserve,fees,ly,ln,key)

    def price_sale(self,m,y,n):
        # Requires splitting collateral first; research only, never an unowned short.
        from decimal import ROUND_CEILING
        q=self.c.PAIR_SHARES.quantize(D("0.01"))
        fy,cy,ly=y.sweep(q,"bids");fn,cn,ln=n.sweep(q,"bids")
        if q<max(m.min_size,y.min_size,n.min_size) or min(fy,fn)<q or not y.bids or not n.bids:return None
        fees=D(0)
        for book in (y,n):
            left=q;fee=D(0)
            for p,size in sorted(book.bids,reverse=True):
                take=min(left,size);fee+=take*m.fee_rate*p*(1-p);left-=take
                if left<=0:break
            fees+=fee.quantize(D("0.00001"),rounding=ROUND_CEILING)
        cost=q+fees+q*self.c.MAX_SLIPPAGE*2+self.c.MERGE_COST
        by,bn=max(y.bids)[0],max(n.bids)[0]
        key=hashlib.sha256(("split-sale"+m.condition+y.fingerprint+n.fingerprint).encode()).hexdigest()
        return Opportunity(m,y,n,q,by,bn,by+bn-1,(cy+cn-cost)/q,cost,fees,ly,ln,key,"split_then_sell")
    async def scan(self):
        self.cycle+=1
        opportunities=[]
        for m in await self.markets():
            try:
                y,n=await self.pair(m)
                for o in (self.price(m,y,n),self.price_sale(m,y,n)):
                    if o and o.gross_edge>0: opportunities.append(o)
            except Exception: self.metrics["book_errors"]+=1;continue
        return sorted(opportunities,key=lambda o:o.net_edge,reverse=True)
