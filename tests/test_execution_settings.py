import unittest
from unittest.mock import patch

from bot.config import Settings
from bot.exchange.binance_futures import BinanceFuturesClient


class ExecutionSettingsTests(unittest.TestCase):
    def test_requested_defaults_are_locked_in(self):
        settings = Settings.load()
        self.assertEqual(settings.leverage, 10)
        self.assertEqual(settings.reward_risk_ratio, 2.0)
        self.assertEqual(settings.interval, "15m")
        self.assertEqual(settings.confirmation_interval, "1h")
        self.assertEqual(settings.scan_interval_minutes, 15)
        self.assertEqual(settings.minimum_margin_usdt, 5.0)
        self.assertEqual(settings.maximum_margin_usdt, 40.0)
        self.assertEqual(settings.max_margin_fraction, 0.40)
        self.assertEqual(settings.risk_per_trade, 0.02)
        self.assertEqual(settings.daily_loss_limit, 0.10)
        self.assertEqual(settings.minimum_signal_score, 85)
        self.assertEqual(settings.minimum_confirmations, 4)
        self.assertEqual(settings.max_open_positions, 4)
        self.assertEqual(settings.position_limit_override_confirmations, 7)
        self.assertEqual(settings.atr_stop_multiple, 2.2)
        self.assertEqual(settings.minimum_adx, 20.0)
        self.assertEqual(settings.minimum_volume_ratio, 0.8)
        self.assertEqual(settings.mode, "paper")

    def test_exchange_is_prepared_as_ten_x_isolated(self):
        client = BinanceFuturesClient(Settings.load())
        with patch.object(
            client,
            "_signed",
            side_effect=[{"dualSidePosition": False}, {}, {}],
        ) as signed:
            client.prepare_symbol("BTCUSDT", 10)

        signed.assert_any_call(
            "POST",
            "/fapi/v1/leverage",
            {"symbol": "BTCUSDT", "leverage": 10},
        )
        signed.assert_any_call(
            "POST",
            "/fapi/v1/marginType",
            {"symbol": "BTCUSDT", "marginType": "ISOLATED"},
        )


if __name__ == "__main__":
    unittest.main()
