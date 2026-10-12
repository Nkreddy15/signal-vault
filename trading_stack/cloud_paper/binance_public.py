"""Bounded public data and internal sweep estimates. No authenticated/order endpoints."""
import json
import math
import time
from decimal import Decimal,ROUND_DOWN
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request,build_opener
from .providers import NoRedirect,ProviderError,validate_quote

HOST='https://api.binance.us'
PATHS={'exchangeInfo','time','ticker/24hr','klines','depth'}


def public_json(path,params=None):
    if path not in PATHS:raise PermissionError('Public data endpoints only')
    url=HOST+'/api/v3/'+path+('?' + urlencode(params) if params else '')
    req=Request(url,headers={'Accept':'application/json','User-Agent':'SignalVault-Paper-Research/1'},method='GET')
    try:
        with build_opener(NoRedirect).open(req,timeout=8) as r:
            raw=r.read(2000001)
        if len(raw)>2000000:raise ProviderError('Native public feed response exceeds bound')
        data=json.loads(raw)
    except HTTPError as e:raise ProviderError(f'Native public feed {path} HTTP {e.code}') from None
    except (ValueError,UnicodeError):raise ProviderError('Native public feed returned non-JSON data') from None
    except ProviderError:raise
    except Exception:raise ProviderError('Native public feed is unavailable') from None
    if isinstance(data,dict) and isinstance(data.get('code'),int) and data['code']<0:raise ProviderError('Native public feed rejected request')
    return data


class BinancePublic:
    mode='INTERNAL SIMULATION / BINANCE.US PUBLIC DATA'
    def __init__(self,transport=public_json,clock=time.time):self.http=transport;self.clock=clock;self.assets={}
    def load_assets(self):
        data=self.http('exchangeInfo')
        if not isinstance(data,dict) or not isinstance(data.get('symbols'),list):raise ProviderError('Invalid native asset metadata')
        assets={}
        for a in data['symbols']:
            if a.get('quoteAsset')!='USD' or a.get('status')!='TRADING' or not a.get('isSpotTradingAllowed',True):continue
            base=a.get('baseAsset','')
            if not base.isalnum() or not 2<=len(base)<=12 or a.get('symbol')!=base+'USD':continue
            filters={f.get('filterType'):f for f in a.get('filters',[])};lot=filters.get('LOT_SIZE',{})
            minimum=filters.get('NOTIONAL',filters.get('MIN_NOTIONAL',{})).get('minNotional')
            try:
                step=Decimal(lot['stepSize']);qty=Decimal(lot['minQty']);cost=Decimal(minimum)
                if not all(v.is_finite() and v>0 for v in (step,qty,cost)):continue
            except Exception:continue
            assets[base+'/USD']=dict(key=a['symbol'],step=str(step),minimum_quantity=str(qty),minimum_cost=str(cost))
        self.assets=assets;return assets
    def quotes(self,symbols,now):
        if not self.assets:self.load_assets()
        selected={self.assets[s]['key']:s for s in symbols if s in self.assets}
        if not selected:return {}
        # The documented all-market form avoids array-query parser differences.
        # This bounded read costs 40 request-weight units and is cached by the probe.
        raw=self.http('ticker/24hr')
        if isinstance(raw,dict):raw=[raw]
        if not isinstance(raw,list):raise ProviderError('Invalid native ticker response')
        out={}
        for r in raw:
            if r.get('symbol') not in selected:continue
            try:
                q=dict(bid=float(r['bidPrice']),ask=float(r['askPrice']),at=float(r['closeTime'])/1000,
                    volume_usd=float(r['quoteVolume']),source='Binance.US timestamped native public ticker')
                if not math.isfinite(q['volume_usd']) or q['volume_usd']<0:raise ValueError()
                out[selected[r['symbol']]]=validate_quote(q,now,90)
            except (KeyError,ValueError,TypeError,ProviderError):continue
        return out
    def bars(self,symbol,now,timeframe='5m'):
        if symbol not in self.assets:raise ProviderError('Unsupported native asset')
        if timeframe not in ('5m','15m'):raise ProviderError('Unsupported native study timeframe')
        step=300 if timeframe=='5m' else 900
        raw=self.http('klines',{'symbol':self.assets[symbol]['key'],'interval':timeframe,'limit':1000})
        if not isinstance(raw,list) or len(raw)>1000:raise ProviderError('Invalid native candle response')
        rows=[]
        for r in raw:
            if not isinstance(r,list) or len(r)<11:raise ProviderError('Invalid native candle row')
            b=dict(time=float(r[0])/1000,open=float(r[1]),high=float(r[2]),low=float(r[3]),close=float(r[4]),
                volume=float(r[5]),quote_volume=float(r[7]),taker_buy_base_volume=float(r[9]))
            if b['time']+step<=now:rows.append(b)
        return rows
    def size(self,symbol,quantity,price):
        a=self.assets[symbol];step=Decimal(a['step']);qty=(Decimal(str(quantity))/step).to_integral_value(rounding=ROUND_DOWN)*step
        if qty<Decimal(a['minimum_quantity']) or qty*Decimal(str(price))<Decimal(a['minimum_cost']):raise ProviderError('Native venue minimum order not met')
        return float(qty)
    def sweep(self,symbol,quantity,limit,side):
        if symbol not in self.assets or side not in ('buy','sell') or not math.isfinite(quantity) or quantity<=0 or not math.isfinite(limit) or limit<=0:raise ProviderError('Invalid native sweep request')
        raw=self.http('depth',{'symbol':self.assets[symbol]['key'],'limit':100});levels=raw.get('asks' if side=='buy' else 'bids')
        if not isinstance(levels,list):raise ProviderError('Invalid native depth')
        remaining=quantity;value=0.;used=[];last=None
        for r in levels:
            price=float(r[0]);size=float(r[1])
            if not math.isfinite(price) or not math.isfinite(size) or price<=0 or size<0:raise ProviderError('Invalid native depth level')
            if last is not None and ((side=='buy' and price<last) or (side=='sell' and price>last)):raise ProviderError('Nonchronological native depth prices')
            last=price
            if price>limit if side=='buy' else price<limit:break
            take=min(remaining,size);value+=take*price;remaining-=take
            if take:used.append(dict(price=price,quantity=take))
            if remaining<=1e-12:break
        if remaining>1e-12:raise ProviderError('Insufficient observed depth within limit')
        return dict(estimated_price=value/quantity,quantity=quantity,levels=used,observed_at=self.clock(),mode='INTERNAL ESTIMATE; NOT AN EXCHANGE FILL')
    def preflight(self):
        from .entry_model import check_history
        now=self.clock();self.load_assets();pairs=['BTC/USD','ETH/USD','SOL/USD','XRP/USD','DOGE/USD','ADA/USD']
        quotes=self.quotes(pairs,now)
        if 'BTC/USD' not in quotes:raise ProviderError('Fresh native BTC quote unavailable')
        bars=self.bars('BTC/USD',self.clock())
        if not check_history(bars,self.clock()):raise ProviderError('Complete fresh native 5m history unavailable')
        q=quotes['BTC/USD'];qty=self.size('BTC/USD',50/q['ask'],q['ask']);sweep=self.sweep('BTC/USD',qty,q['ask']*1.001,'buy')
        return dict(venue='Binance.US',mode='READ_ONLY_PUBLIC_PREFLIGHT',checked_at=self.clock(),assets=len(self.assets),fresh_pairs=sorted(quotes),
            native_bars=len(bars),bid=q['bid'],ask=q['ask'],estimated_50_usd_sweep=sweep,orders_submitted=0)
