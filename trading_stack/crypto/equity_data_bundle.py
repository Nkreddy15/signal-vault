"""GET-only stock research export. Only calendar and historical bars endpoints."""
import argparse
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo
import zipfile

import pandas as pd
import multi_strategy_lab as m

SYMBOLS=('SPY','QQQ','AAPL','MSFT','NVDA','AMZN','META','GOOGL','JPM','V','AMD','TSLA')
BARS_URL='https://data.alpaca.markets/v2/stocks/bars'
CALENDAR_URL='https://paper-api.alpaca.markets/v2/calendar'
VERSION='EQUITY-RESEARCH-DATA-1'
START='2026-01-01T00:00:00Z'
END='2026-10-01T00:00:00Z'
NY=ZoneInfo('America/New_York')
MAX_ZIP=30*1024*1024
MAX_RAW=128*1024*1024


class ReadError(RuntimeError):
    def __init__(self,status=None):
        self.status=status
        super().__init__('Alpaca read failed'+(f' (HTTP {status})' if status else ' (connection/JSON error)'))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def credentials(env_path=None):
    values={k:os.environ.get(k,'').strip() for k in ('ALPACA_API_KEY','ALPACA_API_SECRET')}
    if env_path:
        for line in Path(env_path).read_text().splitlines():
            key,sep,value=line.partition('=')
            key=key.strip()
            if sep and key in values and not values[key]:
                value=value.strip()
                if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):
                    value=value[1:-1]
                values[key]=value
    if not all(values.values()):
        raise RuntimeError('Existing Alpaca paper key and secret are required in trading_stack/.env')
    return {'APCA-API-KEY-ID':values['ALPACA_API_KEY'],'APCA-API-SECRET-KEY':values['ALPACA_API_SECRET']}


def reader(headers):
    opener=build_opener(NoRedirect())
    def get(url,params):
        if url not in (BARS_URL,CALENDAR_URL):
            raise ValueError('Endpoint outside the GET-only research allowlist')
        req=Request(url+'?'+urlencode(params),headers=headers,method='GET')
        for attempt in range(3):
            try:
                with opener.open(req,timeout=30) as response:
                    return json.load(response)
            except HTTPError as exc:
                if exc.code in (429,500,502,503,504) and attempt<2:
                    time.sleep(1+attempt)
                    continue
                raise ReadError(exc.code) from None
            except (URLError,ValueError):
                raise ReadError() from None
        raise ReadError()
    return get


def sessions(calendar):
    result=[]
    for item in calendar:
        date=item['date']
        opening=datetime.fromisoformat(date+'T'+item['open']).replace(tzinfo=NY)
        closing=datetime.fromisoformat(date+'T'+item['close']).replace(tzinfo=NY)
        lo,hi=int(opening.timestamp()*1000),int(closing.timestamp()*1000)
        if hi<=lo or (hi-lo)%m.BAR:
            raise ValueError('Invalid market calendar session')
        result.append(dict(date=date,open_ms=lo,close_ms=hi,expected_bars=(hi-lo)//m.BAR))
    if not result or len({v['date'] for v in result})!=len(result):
        raise ValueError('Empty or duplicate market calendar')
    return sorted(result,key=lambda v:v['open_ms'])


def fetch_bars(get,feed,adjustment,symbols):
    found={symbol:[] for symbol in symbols}
    params=dict(symbols=','.join(symbols),timeframe='15Min',start=START,end=END,
        limit=10000,adjustment=adjustment,feed=feed,sort='asc',asof='2026-10-01')
    seen=set()
    for page in range(100):
        response=get(BARS_URL,params)
        for symbol,rows in (response.get('bars') or {}).items():
            if symbol not in found:
                raise ValueError('Unexpected symbol in historical response')
            found[symbol].extend(rows)
        token=response.get('next_page_token')
        if not token:
            return found
        if token in seen:
            raise ValueError('Repeated history pagination token')
        seen.add(token);params['page_token']=token
    raise ValueError('Historical pagination exceeded 100 pages')


def regular_frame(rows,calendar):
    if not rows:
        raise ValueError('No historical bars returned for a required symbol')
    frame=pd.DataFrame(rows).rename(columns=dict(o='open',h='high',l='low',c='close',v='volume'))
    frame['ts']=pd.to_datetime(frame['t'],utc=True).astype('datetime64[ns, UTC]').astype('int64')//1_000_000
    frame=m.normalized(frame)
    kept=pd.Series(False,index=frame.index)
    for session in calendar:
        kept|=(frame.ts>=session['open_ms'])&(frame.ts+m.BAR<=session['close_ms'])
    return m.normalized(frame[kept])


def collect(get,feed='sip',symbols=SYMBOLS):
    calendar=sessions(get(CALENDAR_URL,dict(start='2026-01-01',end='2026-09-30',date_type='TRADING')))
    if feed not in ('sip','iex'):
        raise ValueError('Only SIP and IEX research feeds are supported')
    # If SIP access is denied, restart both adjustments on IEX. Never mix feeds
    # within a series or silently label IEX as consolidated market coverage.
    try:
        bars={adjustment:fetch_bars(get,feed,adjustment,symbols) for adjustment in ('raw','all')}
    except ReadError as exc:
        if feed!='sip' or exc.status!=403:
            raise
        feed='iex'
        print('SIP access unavailable; exporting IEX-only bars, explicitly labeled.',file=sys.stderr)
        bars={adjustment:fetch_bars(get,feed,adjustment,symbols) for adjustment in ('raw','all')}
    files={'calendar.json':(json.dumps(calendar,indent=2)+'\n').encode()}
    records=[]
    for adjustment in ('raw','all'):
        for symbol in symbols:
            frame=regular_frame(bars[adjustment][symbol],calendar)
            name=adjustment+'/'+symbol+'-15m.csv'
            files[name]=frame.to_csv(index=False).encode()
            coverage=[]
            for session in calendar:
                count=int(((frame.ts>=session['open_ms'])&(frame.ts<session['close_ms'])).sum())
                coverage.append(dict(date=session['date'],observed=count,expected=session['expected_bars']))
            records.append(dict(symbol=symbol,adjustment=adjustment,path=name,bars=len(frame),coverage=coverage))
    manifest=dict(version=VERSION,feed=feed,symbols=list(symbols),start=START,end_exclusive=END,
        timeframe='15Min',adjustments=['raw','all'],records=records,
        query_scope='GET calendar and public historical stock bars only; no account/order endpoints',
        limitations=['Chosen symbol universe is not a historical constituent database.',
            'IEX, when selected, is a single-venue feed; no omitted execution bars are fabricated.',
            'All-adjusted prices are separate total-return research inputs, not actual historical execution prices.',
            'Calendar and bars establish data coverage only, not profitability, quotes or fills.'],
        files={name:dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()) for name,raw in files.items()})
    files['manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    if sum(map(len,files.values()))>MAX_RAW:
        raise ValueError('Stock archive exceeds uncompressed limit')
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,raw in files.items():
            z.writestr(name,raw)
    if buffer.tell()>MAX_ZIP:
        raise ValueError('Stock archive exceeds 30 MiB upload limit')
    return buffer.getvalue(),manifest


def verify(data):
    if len(data)>MAX_ZIP:
        raise ValueError('Oversized stock archive')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=z.namelist()
        if len(set(names))!=len(names) or sum(v.file_size for v in z.infolist())>MAX_RAW:
            raise ValueError('Duplicate or oversized stock archive members')
        manifest=json.loads(z.read('manifest.json'))
        if manifest['version']!=VERSION or set(names)!=set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Stock archive manifest mismatch')
        for name,meta in manifest['files'].items():
            raw=z.read(name)
            if len(raw)!=meta['bytes'] or hashlib.sha256(raw).hexdigest()!=meta['sha256']:
                raise ValueError('Stock archive checksum mismatch')
        for record in manifest['records']:
            raw=m.normalized(pd.read_csv(io.BytesIO(z.read(record['path'])),float_precision='round_trip'))
            if len(raw)!=record['bars']:
                raise ValueError('Stock candle count mismatch')
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--env-file');p.add_argument('--feed',choices=['sip','iex'],default='sip')
    target=p.add_mutually_exclusive_group(required=True)
    target.add_argument('--stdout',action='store_true');target.add_argument('--output')
    a=p.parse_args()
    try:
        data,manifest=collect(reader(credentials(a.env_file)),a.feed)
        verify(data)
    except (ReadError,ValueError,RuntimeError,OSError) as exc:
        print(str(exc),file=sys.stderr)
        raise SystemExit(2) from None
    print(f"Verified {len(manifest['symbols'])} symbols, raw and adjusted; feed={manifest['feed']}; {len(data)/1024/1024:.2f} MiB.",file=sys.stderr)
    if a.stdout:
        sys.stdout.buffer.write(data)
    else:
        Path(a.output).write_bytes(data)


if __name__=='__main__':
    main()
