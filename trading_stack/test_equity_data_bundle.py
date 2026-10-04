"""Read-only stock data transport and session-calendar fixtures."""
import contextlib
import io
import json
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import equity_data_bundle as e


CALENDAR=[dict(date='2026-03-06',open='09:30',close='16:00'),
    dict(date='2026-03-09',open='09:30',close='16:00'),
    dict(date='2026-11-27',open='09:30',close='13:00')]


def bar(timestamp):
    return dict(t=timestamp,o=100.,h=101.,l=99.,c=100.5,v=10.)


class EquityDataTests(unittest.TestCase):
    def test_calendar_dst_and_early_close_are_preserved(self):
        days=e.sessions(CALENDAR)
        self.assertEqual(days[0]['open_ms']%86400000,14*3600000+30*60000)
        self.assertEqual(days[1]['open_ms']%86400000,13*3600000+30*60000)
        self.assertEqual(days[2]['expected_bars'],14)
        rows=[bar('2026-03-06T14:15:00Z'),bar('2026-03-06T14:30:00Z'),
            bar('2026-03-06T21:00:00Z'),bar('2026-11-27T17:45:00Z'),bar('2026-11-27T18:00:00Z')]
        frame=e.regular_frame(rows,days)
        self.assertEqual(len(frame),2)

    def test_pagination_both_adjustments_and_zip_validation(self):
        calls=[]
        def get(url,params):
            calls.append((url,params.copy()))
            if url==e.CALENDAR_URL:
                return CALENDAR[:2]
            if 'page_token' not in params:
                return dict(bars={'SPY':[bar('2026-03-06T14:30:00Z')]},next_page_token='NEXT')
            return dict(bars={'SPY':[bar('2026-03-09T13:30:00Z')]},next_page_token=None)
        data,manifest=e.collect(get,symbols=('SPY',))
        self.assertEqual(e.verify(data),manifest)
        self.assertEqual(len(calls),5)
        self.assertEqual([v['bars'] for v in manifest['records']],[2,2])
        self.assertEqual([v['adjustment'] for v in manifest['records']],['raw','all'])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertEqual(set(z.namelist()),{'calendar.json','manifest.json','raw/SPY-15m.csv','all/SPY-15m.csv'})
        corrupted=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as z,zipfile.ZipFile(corrupted,'w') as target:
            for name in z.namelist():
                target.writestr(name,b'changed' if name.endswith('.csv') else z.read(name))
        with self.assertRaisesRegex(ValueError,'checksum'):
            e.verify(corrupted.getvalue())

    def test_explicit_feed_fallback_and_repeated_page_detection(self):
        def get(url,params):
            if url==e.CALENDAR_URL:
                return CALENDAR[:1]
            if params['feed']=='sip':
                raise e.ReadError(403)
            return dict(bars={'SPY':[bar('2026-03-06T14:30:00Z')]})
        with contextlib.redirect_stderr(io.StringIO()):
            data,manifest=e.collect(get,symbols=('SPY',))
        self.assertEqual(manifest['feed'],'iex')
        self.assertEqual(e.verify(data)['feed'],'iex')
        with self.assertRaisesRegex(ValueError,'Repeated'):
            e.fetch_bars(lambda url,params:dict(bars={},next_page_token='SAME'),'iex','raw',('SPY',))

    def test_only_gets_to_the_two_fixed_endpoints_and_no_secret_export(self):
        class Opener:
            def open(self,req,timeout):
                self.req=req
                return io.BytesIO(b'{"fixture":true}')
        opener=Opener()
        with patch.object(e,'build_opener',return_value=opener):
            get=e.reader({'APCA-API-KEY-ID':'TEST_KEY','APCA-API-SECRET-KEY':'TEST_SECRET'})
            self.assertEqual(get(e.BARS_URL,{'limit':1}),{'fixture':True})
            self.assertEqual(opener.req.get_method(),'GET')
            with self.assertRaisesRegex(ValueError,'allowlist'):
                get('https://paper-api.alpaca.markets/v2/orders',{})
        with tempfile.NamedTemporaryFile(mode='w') as env:
            env.write('ALPACA_API_KEY="TEST_KEY"\nALPACA_API_SECRET=TEST_SECRET\nUNRELATED=OTHER\n');env.flush()
            with patch.dict(e.os.environ,{},clear=True):
                headers=e.credentials(env.name)
            self.assertEqual(set(headers),{'APCA-API-KEY-ID','APCA-API-SECRET-KEY'})
        self.assertNotIn('TEST_SECRET',str(e.ReadError(401)))


if __name__=='__main__':
    unittest.main()
