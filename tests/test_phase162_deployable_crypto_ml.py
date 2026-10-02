from __future__ import annotations

import unittest

from signal_vault.crypto_universe_forward import BOOTSTRAP_HOURS
from signal_vault.deployable_crypto_ml_tournament import (
    DEPLOYABLE_FEATURES,
    HORIZON,
    MAX_FEATURE_LOOKBACK_HOURS,
)


class Phase162DeployableCryptoMlTests(unittest.TestCase):
    def test_feature_profile_fits_existing_forward_bootstrap(self):
        self.assertEqual(BOOTSTRAP_HOURS, 72)
        self.assertEqual(MAX_FEATURE_LOOKBACK_HOURS, BOOTSTRAP_HOURS)
        self.assertNotIn("ret_168h", DEPLOYABLE_FEATURES)
        self.assertIn("vol_72h", DEPLOYABLE_FEATURES)
        self.assertEqual(HORIZON, 48)

    def test_deployable_features_have_no_lookback_over_72h(self):
        forbidden = ("168", "200", "240", "336", "720")
        for feature in DEPLOYABLE_FEATURES:
            self.assertFalse(
                any(token in feature for token in forbidden),
                msg=f"feature exceeds prospective bootstrap: {feature}",
            )


if __name__ == "__main__":
    unittest.main()
