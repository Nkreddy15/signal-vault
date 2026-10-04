"""Two fixed alternatives, reused-data screening, no parameter search or activation."""
import argparse
import hashlib
import json
from pathlib import Path
from .engine import load_config
from .research import load_archive,precompute,replay
from .store import digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--archive',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    candidate=load_config(Path(__file__).with_name('campaign.regime-v2.json'))
    baseline=load_config();baseline.update(crypto_fee_fraction=.008,risk_per_trade=.005,daily_loss_fraction=.02)
    data,manifest=load_archive(args.archive,candidate['crypto_symbols'])
    if set(data)!=set(candidate['crypto_symbols']):raise ValueError('Missing configured archive assets')
    first=max(rows[0]['time'] for rows in data.values());last=min(rows[-1]['time']+3600 for rows in data.values())
    hours=(last-first)//3600;cuts=[first,first+int(hours*.6)*3600,first+int(hours*.8)*3600,last]
    results={}
    for name,cfg in [('existing_rules_realistic_costs',baseline),('regime_v2_predeclared',candidate)]:
        print('Computing '+name,flush=True)
        signals,blocks=precompute(data,cfg)
        results[name]=dict(config=cfg,config_hash=digest(cfg),signal_blockers=dict(blocks),
            periods={label:replay(data,signals,cfg,cuts[i],cuts[i+1]) for i,label in enumerate(('reused_development','reused_validation','reused_test_not_holdout'))})
        print(json.dumps({k:{m:v[m] for m in ('net_return','maximum_drawdown','closed_trades','profit_factor','final_equity')} for k,v in results[name]['periods'].items()}),flush=True)
    result=dict(kind='EXPERIMENTAL_REUSED_DATA_COMPARISON',archive_sha256=hashlib.sha256(Path(args.archive).read_bytes()).hexdigest(),
        dataset=manifest,candidates_evaluated=2,results=results,
        limitations=['Q1/Q2 already inspected; no untouched holdout, no parameters selected from this run',
            '15 crypto assets; stocks and Kalshi results unavailable',
            'Each partition resets an isolated $500 historical account; no prospective campaign reset',
            'Fixed 0.8% taker fee per side; conservative Tier 1, no volume-tier discounts or maker fills assumed',
            '0.15% half spread plus 0.1% slippage per side; hourly adverse stop ordering and next-hour entry',
            'Historical lot eligibility and depth unavailable; 1% prior hourly volume cap, $5 assumed minimum',
            'Hourly risk controls, missing position marks and OHLC execution uncertainty; stops may overshoot',
            'No operational costs deducted; no automatic promotion, deployment or live trading'],
        conclusion='Experimental only; positive historical results, if any, do not establish an edge.')
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
