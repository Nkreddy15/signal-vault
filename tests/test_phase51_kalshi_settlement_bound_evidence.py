import json
import unittest
from urllib.parse import urlparse

from signal_vault.kalshi_public_research import KalshiPublicResearchClient


class KalshiHistoricalMarketMetadataTests(unittest.TestCase):
    def test_exact_historical_market_metadata_is_public_get_only(self):
        seen=[]
        def transport(request,timeout):
            seen.append(request)
            path=urlparse(request.full_url).path
            if path.endswith("/historical/markets/TEST-MARKET"):
                return json.dumps({"market":{
                    "ticker":"TEST-MARKET",
                    "status":"settled",
                    "result":"yes",
                    "settlement_ts":"2026-01-02T00:00:00Z",
                }}).encode()
            raise AssertionError(path)

        client=KalshiPublicResearchClient(transport=transport)
        result=client.historical_market("TEST-MARKET")
        self.assertEqual(result["market"]["result"],"yes")
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0].get_method(),"GET")
        self.assertNotIn("KALSHI-ACCESS-KEY",seen[0].headers)
        self.assertNotIn("KALSHI-ACCESS-SIGNATURE",seen[0].headers)

    def test_historical_market_ticker_path_is_strictly_allowlisted(self):
        client=KalshiPublicResearchClient(
            transport=lambda request,timeout:b'{"market":{}}'
        )
        for ticker in ("../BAD","bad ticker","", "A"*129):
            with self.subTest(ticker=ticker), self.assertRaises(ValueError):
                client.historical_market(ticker)


if __name__=="__main__":
    unittest.main()
