"""Fixed scalping screen. Never submits orders or edits an execution ledger."""
import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

from trading_stack.cloud_paper.engine import load_config
from trading_stack.cloud_paper.providers import iso
from trading_stack.cloud_paper.research import replay
from trading_stack.cloud_paper.strategies_scalp import FAMILIES,signals
from trading_stack.cloud_paper.store import digest


def candidate_config():
    root=Path(__file__).resolve().parents[1]
    cfg=load_config(root/'cloud_paper/campaign.intraday-exits.json')
    cfg.update(version='SV-SCALP-5M-RESEARCH-20261012',evidence='Fixed experimental scalping hypotheses; performance unknown',
        strategy_pack='scalp-v1',crypto_timeframe='5m',bar_seconds=300,
        crypto_max_hold_hours=1,crypto_reentry_cooldown_bars=2,
        strategies=list(FAMILIES),crypto_symbols=['BTC/USD','ETH/USD','SOL/USD','XRP/USD','DOGE/USD','ADA/USD','LTC/USD','BCH/USD','LINK/USD','AVAX/USD','DOT/USD','UNI/USD','SUI/USD','NEAR/USD','ATOM/USD','HBAR/USD','XLM/USD','AAVE/USD','OP/USD','ARB/USD'])
    cfg['strategy_pack_source_sha256']=hashlib.sha256((root/'cloud_paper/strategies_scalp.py').read_bytes()).hexdigest()
    return cfg


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cost-sensitivity',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parent
    raw=gzip.decompress((root/'scalp5m-capture-20261012.json.gz').read_bytes());capture=json.loads(raw);data=capture['data'];cfg=candidate_config()
    if args.cost_sensitivity:cfg['crypto_fee_fraction']=.0025
    candidates={};blocks=Counter()
    for symbol,rows in data.items():
        for i,row in enumerate(rows):
            if i<288:continue  # Full lagged 24h liquidity; no partial-day extrapolation.
            history=rows[:i];found,why=signals(history,'crypto',symbol,row['time'],cfg)
            if not found:blocks[why]+=1;continue
            recent=history[-288:]
            if any(b['time']-a['time']!=300 for a,b in zip(recent,recent[1:])) or sum(b['close']*b['volume'] for b in recent)<cfg['minimum_daily_volume_usd']:
                blocks['Incomplete or insufficient lagged 24h liquidity']+=1;continue
            found[0]['lagged_volume_cap']=.01*recent[-1]['volume'];candidates.setdefault(int(row['time']),[]).append(found[0])
    start=int(max(rows[288]['time'] for rows in data.values()));end=int(min(rows[-1]['time']+300 for rows in data.values()))
    midpoint=start+((end-start)//600)*300
    results={name:replay(data,candidates,cfg,a,b) for name,a,b in [('all',start,end),('first_half',start,midpoint),('later_half',midpoint,end)]}
    report=dict(kind='HYPOTHETICAL 0.25% COST SENSITIVITY ON KRAKEN DATA; NOT ALPACA EXECUTION EVIDENCE' if args.cost_sensitivity else 'FIXED RETROSPECTIVE NATIVE 5M SCALP SCREEN; NO ACCOUNT WRITES',capture_sha256=hashlib.sha256(raw).hexdigest(),
        configuration=cfg,configuration_hash=digest(cfg),parameters_fixed_before_results=True,observed_start=iso(start),observed_end=iso(end),
        signal_blocks=dict(blocks),results=results,limits=['Approximately 36 hours after 24h liquidity warmup; insufficient to establish a durable edge.',
        'Chronological halves are descriptive; recent market data was previously observed in this conversation. Neither is an untouched holdout.',
        f'Same $500 independent portfolio, {cfg["crypto_fee_fraction"]*100}% fee per side, 0.1% slippage and 0.15% half-spread, current risk guards.',
        'Next-open entries, stop before target on an ambiguous bar, conservative liquidation marks and lagged volume caps.',
        'Venue minimum sizes, historical spreads and queue positions are not verified; these are simulated taker fills.',
        'New scalp hypotheses have stop/net-profit/time exits in this screen; the legacy trend-exit helper ignores their new strategy names.',
        'Research profile is not connected to the active worker and cannot be selected by its current config loader.',
        'No parameter search, candidate selection by historical winners or automatic promotion.'])
    if args.cost_sensitivity:
        report['sources']=['https://docs.alpaca.markets/us/docs/crypto-fees']
        report['limits']+=['Lower fee is conditional on a verified account/venue; active campaign fees remain 0.8%.',
            'Kraken prices and liquidity are reused; no historical Alpaca quotes, routing eligibility or order books are verified.']
    output='scalp5m-cost-sensitivity-20261012.json' if args.cost_sensitivity else 'scalp5m-screen-20261012.json'
    (root/output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({name:{key:r[key] for key in ('final_equity','net_return','closed_trades','fees_usd','maximum_drawdown','profit_factor')} for name,r in results.items()},indent=2))


if __name__=='__main__':main()
