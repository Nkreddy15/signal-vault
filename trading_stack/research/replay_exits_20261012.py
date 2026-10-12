"""Reproduce a fixed negative historical comparison; never writes an account."""
import gzip
import json
from pathlib import Path

from trading_stack.cloud_paper.engine import load_config
from trading_stack.cloud_paper.research import datetime_from_iso, precompute, replay


def main():
    root=Path(__file__).resolve().parent
    data=json.loads(gzip.decompress((root/'native15m-exits-20261012.json.gz').read_bytes()))['data']
    evidence=json.loads((root/'bounded_exit_comparison_20261012.json').read_text())
    start=int(datetime_from_iso(evidence['start']));end=int(datetime_from_iso(evidence['end']))
    output={}
    for name,filename in [('prior_15m_long_hold','campaign.intraday.json'),('bounded_intraday_exits','campaign.intraday-exits.json')]:
        cfg=load_config(root.parent/'cloud_paper'/filename)
        candidates,_=precompute(data,cfg)
        result=replay(data,candidates,cfg,start,end)
        expected=evidence['results'][name]
        if abs(result['final_equity']-expected['final_equity'])>1e-7 or result['closed_trades']!=expected['closed_trades']:
            raise ValueError(f'Fixed comparison differs for {name}')
        output[name]={k:result[k] for k in ('final_equity','net_return','closed_trades','fees_usd')}
    print(json.dumps({'kind':'RETROSPECTIVE REPLAY ONLY; NO CLOUD FILLS','results':output},indent=2))


if __name__=='__main__':main()
