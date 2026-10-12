"""Restore pinned native archives without reading their outcome contents."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request,build_opener
from trading_stack.cloud_paper.providers import NoRedirect

ROOT=Path(__file__).resolve().parent/'entry_study_20261012'
PREFIX='https://data.binance.us/public_data/spot/monthly/klines/'


def restore(root=ROOT,include_reserved=False):
    manifest=json.loads((root/'manifest.json').read_text());restored=0
    for record in manifest['files']:
        if record['month']=='2026-09' and not include_reserved:continue
        expected=f"{record['symbol']}-5m-{record['month']}.zip"
        url=PREFIX+f"{record['symbol']}/5m/{expected}"
        if record['file']!=expected or record['source']!=url or len(record['sha256'])!=64:raise ValueError('Unexpected archive identity')
        dest=root/expected
        if dest.exists() and hashlib.sha256(dest.read_bytes()).hexdigest()==record['sha256']:continue
        with build_opener(NoRedirect).open(Request(url,headers={'User-Agent':'SignalVault-Paper-Research/1'}),timeout=30) as response:raw=response.read(2000001)
        if len(raw)>2000000 or len(raw)!=record['bytes'] or hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Pinned archive checksum mismatch')
        temporary=dest.with_suffix('.download');temporary.write_bytes(raw);temporary.replace(dest);restored+=1
        print('Verified',expected,flush=True)
    return restored


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--include-reserved',action='store_true',help='Restore reserved ZIP bytes without parsing candles; studies still require frozen qualification to validate.')
    args=parser.parse_args();print('Restored:',restore(include_reserved=args.include_reserved))
