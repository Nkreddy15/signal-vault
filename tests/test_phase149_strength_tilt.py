from decimal import Decimal
import unittest

from signal_vault.relative_strength_tilt_research import StrengthTiltConfig


class Phase149StrengthTiltTests(unittest.TestCase):
    def test_moderate_and_strong_configs_preserve_exact_30_gross(self):
        moderate=StrengthTiltConfig(
            top_target_usd=Decimal("7.5"),other_target_usd=Decimal("3.75")
        )
        strong=StrengthTiltConfig(
            top_target_usd=Decimal("10"),other_target_usd=Decimal("2.5")
        )
        for cfg in (moderate,strong):
            gross=cfg.top_target_usd*2+cfg.other_target_usd*4
            self.assertEqual(gross,Decimal("30"))

    def test_invalid_exposure_or_non_tilt_fails_closed(self):
        with self.assertRaises(ValueError):
            StrengthTiltConfig(
                top_target_usd=Decimal("9"),other_target_usd=Decimal("2")
            )
        with self.assertRaises(ValueError):
            StrengthTiltConfig(
                top_target_usd=Decimal("5"),other_target_usd=Decimal("5")
            )


if __name__=="__main__":
    unittest.main()
