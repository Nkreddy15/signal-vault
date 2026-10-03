"""Portable cached-candle and replay export. No network, orders or paper writes."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import pandas as pd
import multi_strategy_lab as m

VERSION = 'SIGNAL-VAULT-RESEARCH-BUNDLE-1'
MAX_ZIP = 30 * 1024 * 1024
MAX_RAW = 256 * 1024 * 1024
PAIR = re.compile(r'[A-Z0-9]+/USD')
NAME = re.compile(r'[a-z0-9_-]+-15bps-(trigger|extrema)')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False)+'\n').encode()


def selected_pairs(receipt):
    pairs = [item['pair'] for item in receipt['selected']]
    if not pairs or len(pairs)>64 or len(pairs)!=len(set(pairs)) or any(not PAIR.fullmatch(p) for p in pairs):
        raise ValueError('Invalid frozen-universe pairs')
    return pairs


def export_bundle(data_dir, evidence_dir):
    data_dir, evidence_dir = Path(data_dir), Path(evidence_dir)
    receipt = json.loads((data_dir/'universe.json').read_text())
    pairs = selected_pairs(receipt)
    summary_raw = (evidence_dir/'regime-summary.json').read_bytes()
    summary = json.loads(summary_raw)
    if summary.get('version') not in ('REGIME-SWING-LAB-1','REGIME-SWING-LAB-2','DURABLE-TREND-LAB-1') or summary.get('universe')!=receipt:
        raise ValueError('Replay does not match this frozen universe')
    expected = {item['pair']:item for item in summary['input_manifest']}
    if set(expected)!=set(pairs) or len(expected)!=len(summary['input_manifest']):
        raise ValueError('Replay input manifest does not match the universe')
    files = {'universe.json':encoded(receipt), 'evidence/regime-summary.json':summary_raw}
    candles = []
    for pair in pairs:
        source = data_dir/(pair.replace('/','_')+'-15m.feather')
        source_hash = digest(source.read_bytes())
        if source_hash!=expected[pair]['sha256']:
            raise ValueError('Cached candles changed since replay: '+pair)
        frame = m.normalized(pd.read_feather(source))
        if len(frame)!=expected[pair]['bars']:
            raise ValueError('Replay candle count mismatch: '+pair)
        name = 'candles/'+pair.replace('/','_')+'-15m.csv'
        files[name] = frame.to_csv(index=False).encode()
        candles.append(dict(pair=pair,path=name,bars=len(frame),source_feather_sha256=source_hash,
            gaps=int((frame.ts.diff().dropna()!=m.BAR).sum()),
            start_ms=int(frame.ts.iloc[0]),end_ms=int(frame.ts.iloc[-1])+m.BAR))
    names = [row['name'] for row in summary['reports']]
    if len(names)!=64 or len(names)!=len(set(names)) or any(not NAME.fullmatch(n) for n in names):
        raise ValueError('Expected the complete 64-scenario replay')
    for name in names:
        path = evidence_dir/(name+'.json')
        raw = path.read_bytes()
        result = json.loads(raw)
        if result['input_manifest']!=summary['input_manifest'] or result['universe']!=receipt:
            raise ValueError('Scenario provenance mismatch: '+name)
        files['evidence/'+path.name] = raw
        # Full scenario JSON includes its fills, equity curve and monthly accounts.
        # Do not duplicate those ledgers as CSV in this compact transport.
    strategy_name='durable_trend_lab.py' if summary['version']=='DURABLE-TREND-LAB-1' else 'regime_swing_lab.py'
    sources=[(strategy_name,'source_sha256','replay-strategy.py'),
        ('multi_strategy_lab.py','shared_engine_sha256','replay-accounting.py')]
    if 'runner_sha256' in summary:
        sources.append(('regime_swing_lab.py','runner_sha256','replay-runner.py'))
    for name,field,snapshot in sources:
        source=evidence_dir/snapshot
        raw = source.read_bytes() if source.exists() else Path(__file__).with_name(name).read_bytes()
        if digest(raw)!=summary[field]:
            raise ValueError('Replay engine changed; preserve the original source before export')
        files['source/'+name] = raw
    files['README.txt'] = (
        'Signal Vault cached research data and completed replay. No trading activation.\n'
        'candles/: normalized original 15m candles; no gap filling or resampling.\n'
        'evidence/: 64 account replays, including trade ledgers and monthly results.\n'
        'source/: exact replay engines, matched against the summary hashes.\n'
        'manifest.json: original archive hashes and hashes of each exported member.\n'
        'Hashes check internal consistency, not independent data authenticity.\n'
        'Q1/Q2 are reused development data, not untouched validation.\n'
    ).encode()
    manifest = dict(version=VERSION,candles=candles,runtime_versions=summary['runtime_versions'],
        files={name:dict(sha256=digest(raw),bytes=len(raw)) for name,raw in files.items()})
    files['manifest.json'] = encoded(manifest)
    if sum(map(len,files.values()))>MAX_RAW:
        raise ValueError('Export exceeds uncompressed size limit')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,raw in files.items():
            archive.writestr(name,raw)
    if buffer.tell()>MAX_ZIP:
        raise ValueError('Export exceeds the 30 MiB upload limit')
    return buffer.getvalue()


def load_bundle(data):
    """Verify and load directly from ZIP; never extract arbitrary filesystem paths."""
    if isinstance(data,(str,Path)):
        data = Path(data).read_bytes()
    if len(data)>MAX_ZIP:
        raise ValueError('Bundle exceeds upload size limit')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names)!=len(set(names)) or sum(item.file_size for item in infos)>MAX_RAW:
            raise ValueError('Duplicate members or oversized archive')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest['version']!=VERSION or set(names)!=set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Bundle members do not match manifest')
        files = {}
        for name,meta in manifest['files'].items():
            raw = archive.read(name)
            if len(raw)!=meta['bytes'] or digest(raw)!=meta['sha256']:
                raise ValueError('Bundle checksum mismatch: '+name)
            files[name] = raw
        receipt = json.loads(files['universe.json'])
        pairs = selected_pairs(receipt)
        candles = manifest['candles']
        if [c['pair'] for c in candles]!=pairs:
            raise ValueError('Bundle candle universe mismatch')
        frames = {}
        for item in candles:
            pair = item['pair']
            if item['path']!='candles/'+pair.replace('/','_')+'-15m.csv':
                raise ValueError('Unexpected candle member')
            frame = m.normalized(pd.read_csv(io.BytesIO(files[item['path']]),float_precision='round_trip'))
            if len(frame)!=item['bars'] or int(frame.ts.iloc[0])!=item['start_ms'] or int(frame.ts.iloc[-1])+m.BAR!=item['end_ms']:
                raise ValueError('Bundle candle metadata mismatch: '+pair)
            frames[pair] = frame
    return frames, receipt, manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-dir',required=True)
    p.add_argument('--evidence-dir',required=True)
    p.add_argument('--stdout',action='store_true')
    p.add_argument('--output')
    a = p.parse_args()
    if bool(a.stdout)==bool(a.output):
        p.error('Choose exactly one of --stdout or --output')
    data = export_bundle(a.data_dir,a.evidence_dir)
    frames,_,_ = load_bundle(data)
    print(f'Verified {len(frames)} assets, {sum(map(len,frames.values())):,} candles; {len(data)/1024/1024:.2f} MiB.',file=sys.stderr)
    if a.stdout:
        sys.stdout.buffer.write(data)
    else:
        Path(a.output).write_bytes(data)


if __name__=='__main__':
    main()
