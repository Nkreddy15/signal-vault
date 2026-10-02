import unittest
from unittest.mock import patch

from signal_vault import railway_all_markets_research_cron as cron


class Phase151BtcShadowExposureTests(unittest.TestCase):
    def test_output_marks_shadow_actions_as_non_authoritative(self):
        shadow={
            "kind":"OFFLINE_SIX_CRYPTO_SHA_CHAINED_SHADOW_ONLY",
            "latest_newly_observed_UTC_close":"2026-10-02T00:00:00+00:00",
            "shadow_payload_sha256":"a"*64,
            "predeclared_flat_and_held_hypothetical_decisions":{
                "BTC/USD":{
                    "generic-ema12x26-v1-predeclared":{
                        "flat":{"hypothetical_action":"buy"}
                    },
                    "generic-momentum24bar50bps-v1-predeclared":{
                        "flat":{"hypothetical_action":"hold"}
                    },
                }
            },
        }
        output={}
        with patch.object(cron,"inspect_six_crypto_shadow",return_value=shadow):
            got=cron.inspect_six_crypto_shadow(root=None)
            decisions=got["predeclared_flat_and_held_hypothetical_decisions"]["BTC/USD"]
            actions={k:v["flat"]["hypothetical_action"] for k,v in decisions.items()}
            output["current_btc_flat_actions"]=actions
            output["current_btc_actions_are_order_authority"]=False
        self.assertEqual(output["current_btc_flat_actions"]["generic-ema12x26-v1-predeclared"],"buy")
        self.assertFalse(output["current_btc_actions_are_order_authority"])


if __name__=="__main__":
    unittest.main()
