import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from signal_vault.offline_kalshi_strategy_simulation import (
    simulate_resolved_market_references,
)


def write(path,obj):
    raw=(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n").encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


class KalshiReferenceStrategySimulationTests(unittest.TestCase):
    def make_bundle(self, *, result="yes", expensive=False, crossed=False):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)/"evidence"
        root.mkdir(mode=0o700)
        settlement="2026-01-02T00:00:00Z"
        settled=int(datetime(2026,1,2,tzinfo=timezone.utc).timestamp())
        metadata={"market":{
            "ticker":"TEST-MARKET","status":"settled","result":result,
            "settlement_ts":settlement,
            "settlement_value_dollars":"1.0000" if result=="yes" else "0.0000",
        }}
        metadata_sha=write(root/"market.json",metadata)

        rows=[]
        specs=[
            (settled-30*3600,"0.4000","0.3800","0.4200"),
            (settled-7*3600,"0.5500","0.5300","0.5700"),
            (settled-2*3600,"0.7000","0.6800","0.7200"),
        ]
        if expensive:
            specs[1]=(settled-7*3600,"0.7000","0.9800","0.9900")
        if crossed:
            specs[1]=(settled-7*3600,"0.5500","0.6000","0.5900")
        for at,price,bid,ask in specs:
            rows.append({
                "end_period_ts":at,
                "price":{
                    "open":price,"low":price,"high":price,"close":price,
                    "mean":price,"previous":price,
                },
                "yes_bid":{
                    "open":bid,"low":bid,"high":bid,"close":bid,
                },
                "yes_ask":{
                    "open":ask,"low":ask,"high":ask,"close":ask,
                },
                "volume":"10","open_interest":"20",
            })
        candles={"ticker":"TEST-MARKET","candlesticks":rows}
        candle_sha=write(root/"candlesticks.json",candles)
        trade_sha=write(root/"trades-page-001.json",{
            "trades":[{"trade_id":"t1","ticker":"TEST-MARKET"}],
            "cursor":"",
        })
        manifest={
            "kind":"IMMUTABLE_KALSHI_RESOLVED_MARKET_PUBLIC_EVIDENCE",
            "ticker":"TEST-MARKET",
            "start_ts":settled-40*3600,
            "end_ts":settled,
            "candlestick_interval":60,
            "market_metadata_sha256":metadata_sha,
            "resolved_result":result,
            "settlement_ts":settlement,
            "candlesticks_sha256":candle_sha,
            "trade_pages":[{"page":1,"sha256":trade_sha}],
            "credentials_accessed":"NONE",
            "authenticated_portfolio_access":"DISABLED",
            "demo_order_submission":"DISABLED",
            "live_order_submission":"DISABLED",
        }
        write(root/"manifest.json",manifest)
        return root

    def test_yes_settlement_scores_favorite_and_contrarian_after_decision(self):
        result=simulate_resolved_market_references(self.make_bundle(result="yes"))
        base=result["friction_scenarios"][
            "illustrative_base_extra_entry_friction"
        ]["hypotheses"]
        fav6=base["market-favorite-6h-hold-v1-predeclared"]
        self.assertEqual(fav6["decision"]["action"],"buy_yes")
        self.assertEqual(fav6["entry_reference"],"YES_ASK_CLOSE")
        self.assertEqual(fav6["quoted_entry_cost_dollars"],"0.5700")
        self.assertEqual(fav6["total_hypothetical_entry_cost_dollars"],"0.5800")
        self.assertEqual(fav6["settlement_payout_dollars"],"1")
        self.assertEqual(fav6["hypothetical_pnl_dollars"],"0.4200")

        contra=base["market-contrarian-6h-hold-v1-predeclared"]
        self.assertEqual(contra["decision"]["action"],"buy_no")
        self.assertEqual(contra["entry_reference"],"ONE_MINUS_YES_BID_CLOSE")
        self.assertEqual(contra["quoted_entry_cost_dollars"],"0.4700")
        self.assertEqual(contra["hypothetical_pnl_dollars"],"-0.4800")

        fav24=base["market-favorite-24h-hold-v1-predeclared"]
        self.assertEqual(fav24["decision"]["action"],"buy_no")
        self.assertEqual(fav24["quoted_entry_cost_dollars"],"0.6200")
        self.assertEqual(fav24["hypothetical_pnl_dollars"],"-0.6300")

        cash=base["cash-v1-predeclared"]
        self.assertEqual(cash["hypothetical_contract_count"],0)
        self.assertEqual(cash["hypothetical_pnl_dollars"],"0")
        self.assertTrue(result["decision_made_before_outcome_scoring"])
        self.assertTrue(result["historical_quote_close_is_not_guaranteed_fill"])
        self.assertFalse(result["provider_fee_schedule_modeled"])
        self.assertFalse(result["strategy_selection_performed"])
        self.assertEqual(result["demo_order_submission"],"DISABLED")

    def test_no_settlement_changes_payout_not_predeclared_decision(self):
        yes=simulate_resolved_market_references(self.make_bundle(result="yes"))
        no=simulate_resolved_market_references(self.make_bundle(result="no"))
        yes_decision=yes["friction_scenarios"][
            "illustrative_base_extra_entry_friction"
        ]["hypotheses"]["market-favorite-6h-hold-v1-predeclared"]["decision"]
        no_decision=no["friction_scenarios"][
            "illustrative_base_extra_entry_friction"
        ]["hypotheses"]["market-favorite-6h-hold-v1-predeclared"]["decision"]
        self.assertEqual(yes_decision["action"],no_decision["action"])
        self.assertEqual(yes_decision["yes_trade_probability"],
                         no_decision["yes_trade_probability"])

    def test_crossed_quote_fails_and_excessive_cost_blocks_entry(self):
        with self.assertRaises(ValueError):
            simulate_resolved_market_references(self.make_bundle(crossed=True))

        result=simulate_resolved_market_references(self.make_bundle(expensive=True))
        high=result["friction_scenarios"][
            "illustrative_high_extra_entry_friction"
        ]["hypotheses"]["market-favorite-6h-hold-v1-predeclared"]
        self.assertTrue(high["entry_blocked"])
        self.assertEqual(high["hypothetical_contract_count"],0)
        self.assertEqual(
            high["entry_block_reason"],
            "CONSERVATIVE_TOTAL_COST_NOT_INSIDE_0_1",
        )


if __name__=="__main__":
    unittest.main()
