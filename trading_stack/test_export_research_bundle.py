"""Portable transport checks. Fixture prices are not profitability evidence."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import pandas as pd
import export_research_bundle as e
import multi_strategy_lab as m
from test_multi_strategy_lab import frame


class ExportTests(unittest.TestCase):
    def fixture(self, root):
        data, evidence = root/'data',root/'evidence'
        data.mkdir(); evidence.mkdir()
        raw = frame(300).drop(index=97).reset_index(drop=True)
        raw['volume']=raw.volume.astype(float)
        raw.loc[5,'volume']=1.2345678901234567
        receipt=dict(selected=[dict(pair='BTC/USD')],kind='FIXTURE')
        (data/'universe.json').write_text(json.dumps(receipt))
        (data/'BTC_USD-15m.feather').write_bytes(b'FIXTURE Feather placeholder; patched reader')
        inputs=[dict(pair='BTC/USD',bars=len(raw),sha256=e.digest((data/'BTC_USD-15m.feather').read_bytes()))]
        reports=[dict(name=f'fixture_{i}-15bps-trigger') for i in range(64)]
        summary=dict(version='REGIME-SWING-LAB-1',universe=receipt,input_manifest=inputs,
            reports=reports,runtime_versions=dict(pandas=pd.__version__),
            source_sha256=e.digest(Path(e.__file__).with_name('regime_swing_lab.py').read_bytes()),
            shared_engine_sha256=e.digest(Path(m.__file__).read_bytes()))
        (evidence/'regime-summary.json').write_text(json.dumps(summary))
        for row in reports:
            (evidence/(row['name']+'.json')).write_text(json.dumps(dict(input_manifest=inputs,
                universe=receipt,trades=[dict(pair='BTC/USD',kind='FIXTURE')],equity_curve=[],monthly_independent_100=[])))
        (data/'.env').write_text('EXCLUDED_TEST_SECRET')
        (evidence/'unrelated-private.txt').write_text('EXCLUDED_TEST_SECRET')
        return data,evidence,raw,summary

    def test_round_trip_keeps_prices_gaps_and_ledgers_without_unrelated_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,evidence,raw,_=self.fixture(Path(tmp))
            with patch.object(e.pd,'read_feather',return_value=raw):
                bundle=e.export_bundle(data,evidence)
            frames,receipt,manifest=e.load_bundle(bundle)
            pd.testing.assert_frame_equal(frames['BTC/USD'],m.normalized(raw))
            self.assertEqual(manifest['candles'][0]['gaps'],1)
            self.assertEqual(manifest['candles'][0]['bars'],299)
            with zipfile.ZipFile(io.BytesIO(bundle)) as z:
                self.assertEqual(len([n for n in z.namelist() if n.startswith('evidence/')]),65)
                self.assertNotIn('EXCLUDED_TEST_SECRET',''.join(z.read(n).decode() for n in z.namelist()))
                self.assertEqual(json.loads(z.read('evidence/fixture_0-15bps-trigger.json'))['trades'][0]['kind'],'FIXTURE')

    def test_changed_cache_and_changed_engine_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,evidence,raw,summary=self.fixture(Path(tmp))
            source=data/'BTC_USD-15m.feather'
            old=source.read_bytes(); source.write_bytes(b'CHANGED')
            with self.assertRaisesRegex(ValueError,'changed since replay'):
                e.export_bundle(data,evidence)
            source.write_bytes(old)
            summary['source_sha256']='0'*64
            (evidence/'regime-summary.json').write_text(json.dumps(summary))
            with patch.object(e.pd,'read_feather',return_value=raw),self.assertRaisesRegex(ValueError,'engine changed'):
                e.export_bundle(data,evidence)

    def test_modified_member_fails_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,evidence,raw,_=self.fixture(Path(tmp))
            with patch.object(e.pd,'read_feather',return_value=raw):
                bundle=e.export_bundle(data,evidence)
            changed=io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(bundle)) as original,zipfile.ZipFile(changed,'w') as target:
                for name in original.namelist():
                    target.writestr(name,b'ALTERED' if name.endswith('-15m.csv') else original.read(name))
            with self.assertRaisesRegex(ValueError,'checksum mismatch'):
                e.load_bundle(changed.getvalue())

    def test_saved_replay_sources_allow_export_after_code_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            data,evidence,raw,summary=self.fixture(Path(tmp))
            archived=b'# archived fixture engine, not current code\n'
            summary['source_sha256']=e.digest(archived)
            summary['runner_sha256']=e.digest(archived)
            (evidence/'regime-summary.json').write_text(json.dumps(summary))
            (evidence/'replay-strategy.py').write_bytes(archived)
            (evidence/'replay-runner.py').write_bytes(archived)
            (evidence/'replay-accounting.py').write_bytes(Path(m.__file__).read_bytes())
            with patch.object(e.pd,'read_feather',return_value=raw):
                bundle=e.export_bundle(data,evidence)
            with zipfile.ZipFile(io.BytesIO(bundle)) as z:
                self.assertEqual(z.read('source/regime_swing_lab.py'),archived)
            frames,_,_=e.load_bundle(bundle)
            pd.testing.assert_frame_equal(frames['BTC/USD'],m.normalized(raw))

    def test_rejects_path_pairs_incomplete_ledgers_and_wrong_scenario_inputs(self):
        with self.assertRaisesRegex(ValueError,'Invalid frozen'):
            e.selected_pairs(dict(selected=[dict(pair='../BTC/USD')]))
        with tempfile.TemporaryDirectory() as tmp:
            data,evidence,raw,summary=self.fixture(Path(tmp))
            ledger=evidence/'fixture_0-15bps-trigger.json'
            ledger.write_text(json.dumps(dict(input_manifest=[],universe=summary['universe'])))
            with patch.object(e.pd,'read_feather',return_value=raw),self.assertRaisesRegex(ValueError,'Scenario provenance'):
                e.export_bundle(data,evidence)
            ledger.unlink()
            with patch.object(e.pd,'read_feather',return_value=raw),self.assertRaises(FileNotFoundError):
                e.export_bundle(data,evidence)


if __name__=='__main__':
    unittest.main()
