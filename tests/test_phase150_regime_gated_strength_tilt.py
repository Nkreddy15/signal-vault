from decimal import Decimal
import unittest

from signal_vault.regime_gated_strength_tilt_research import RegimeTiltConfig


class Phase150RegimeTiltConfigTests(unittest.TestCase):
    def test_predeclared_config_preserves_exact_30_gross(self):
        cfg=RegimeTiltConfig()
        self.assertEqual(cfg.top_target_usd*2+cfg.other_target_usd*4,Decimal("30"))
        self.assertEqual(cfg.breadth_required,4)

    def test_invalid_breadth_or_exposure_fails_closed(self):
        with self.assertRaises(ValueError):
            RegimeTiltConfig(breadth_required=7)
        with self.assertRaises(ValueError):
            RegimeTiltConfig(top_target_usd=Decimal("9"),other_target_usd=Decimal("2"))


if __name__=="__main__":
    unittest.main()
