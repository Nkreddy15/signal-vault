"""Read-only view of the isolated V11 $500 synthetic account."""
import json
import time
from pathlib import Path
ROOT=Path('/paper-data/paper-v11-500')


def active():return (ROOT/'activated').exists()


def summary():
    try:
        data=json.loads((ROOT/'summary.json').read_text())
        if data.get('version')!='V11-PAPER-500-1':raise ValueError('Wrong V11 version')
        if time.time()*1000-(data.get('last_success_ms') or 0)>120000 and (data['crypto']['open_trade_count'] or data['status'] not in ('SESSION_COMPLETE','SESSION_LOSS_LIMIT','USER_STOP','STOPPED')):
            data['status']='STALE';data['crypto']['bot_state']='STALE'
            data['crypto']['errors']=list(data['crypto'].get('errors',[]))+['V11 public-data cycle is stale.']
        return data
    except (OSError,ValueError,TypeError,KeyError):
        return dict(version='V11-PAPER-500-1',status='UNAVAILABLE',note='V11 $500 trial status unavailable.',
            safety={},crypto=dict(bot_state='UNAVAILABLE',config=dict(timeframe='1d'),open_trades=[],closed_trades=[],
                open_trade_count=0,closed_trade_count=0,open_pnl_usd=None,closed_pnl_usd=None,
                marked_equity=None,open_exposure_usd=None,profit={},errors=['V11 account projection unavailable.']))


def candles(pair,limit,trade_id=None):
    try:return json.loads((ROOT/'candles.json').read_text()).get('pairs',{}).get(pair,[])[-limit:],None
    except (OSError,ValueError):return [],'V11 closed daily candle cache unavailable.'
