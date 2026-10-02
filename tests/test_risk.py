import unittest
from decimal import Decimal

from bot.models import SymbolRules
from bot.risk import RiskManager, quantize_down, quantize_price, quantize_up


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.rules = SymbolRules(
            symbol="BTCUSDT",
            tick_size=Decimal("0.10"),
            step_size=Decimal("0.001"),
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("100"),
            min_notional=Decimal("5"),
        )

    def test_position_size_respects_margin_cap(self):
        manager = RiskManager(0.005, 0.02, 0.25, 3)
        quantity = manager.position_quantity(1000, 50000, 49000, self.rules)
        self.assertLessEqual(quantity * Decimal("50000"), Decimal("750"))
        self.assertEqual(quantity, Decimal("0.005"))

    def test_daily_limit(self):
        manager = RiskManager(0.005, 0.02, 0.25, 3)
        self.assertTrue(manager.daily_limit_hit(1000, 980))
        self.assertFalse(manager.daily_limit_hit(1000, 981))

    def test_quantization(self):
        self.assertEqual(quantize_down(Decimal("1.2349"), Decimal("0.001")), Decimal("1.234"))
        self.assertEqual(quantize_up(Decimal("1.2341"), Decimal("0.001")), Decimal("1.235"))
        self.assertEqual(quantize_price(100.06, Decimal("0.1")), Decimal("100.1"))

    def test_margin_scales_with_signal_quality(self):
        self.assertEqual(RiskManager.margin_for_score(90, 90, 5, 40), 5)
        self.assertEqual(RiskManager.margin_for_score(95, 90, 5, 40), 22.5)
        self.assertEqual(RiskManager.margin_for_score(100, 90, 5, 40), 40)

    def test_minimum_margin_is_skipped_when_risk_budget_is_too_small(self):
        manager = RiskManager(0.005, 0.02, 0.40, 10)
        quantity = manager.position_quantity(
            100,
            100,
            98,
            self.rules,
            target_margin_usdt=5,
            minimum_margin_usdt=5,
        )
        self.assertEqual(quantity, Decimal("0"))

    def test_high_quality_can_reach_forty_usdt_margin(self):
        manager = RiskManager(0.005, 0.02, 0.40, 10)
        quantity = manager.position_quantity(
            100,
            100,
            99.99,
            self.rules,
            target_margin_usdt=40,
            minimum_margin_usdt=5,
        )
        self.assertEqual(quantity, Decimal("4.000"))

    def test_two_percent_risk_allows_minimum_margin_with_wider_stop(self):
        manager = RiskManager(0.02, 0.10, 0.40, 10)
        quantity = manager.position_quantity(
            100,
            100,
            97,
            self.rules,
            target_margin_usdt=5,
            minimum_margin_usdt=5,
        )
        self.assertEqual(quantity, Decimal("0.500"))


if __name__ == "__main__":
    unittest.main()
