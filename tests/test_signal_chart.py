import unittest
from bot.chart import build_signal_chart
from bot.models import Candle, Signal


class SignalChartTests(unittest.TestCase):
    def test_chart_uses_only_analysis_snapshot_and_bounds_history(self):
        candles = [Candle(i * 900000, 100, 102, 98, 101, 10, (i + 1) * 900000 - 1) for i in range(100)]
        signal = Signal("TEST", "LONG", 90, 101, 2, "", candles[80].close_time, {"risk_distance": 4})
        chart = build_signal_chart(signal, candles, "15m", 2)
        self.assertEqual(len(chart["candles"]), 60)
        self.assertEqual(chart["candles"][-1]["close_time"], signal.candle_close_time)
        self.assertEqual([p["price"] for p in chart["levels"]], [101, 97, 109])

    def test_short_plan_fvg_and_mss_match_backend_values(self):
        info = {"SHORT": {"fvg": {"lower": 104, "upper": 105, "formed_at": 500}, "mss_level": 102, "mss": True}}
        signal = Signal("TEST", "SHORT", 90, 100, 2, "", 1000, {"risk_distance": 3, "structure": info})
        chart = build_signal_chart(signal, [], "15m", 2)
        self.assertEqual(chart["zones"][0]["lower"], 104)
        self.assertEqual(chart["zones"][0]["upper"], 105)
        self.assertEqual([p["price"] for p in chart["levels"]], [102, 100, 103, 94])

    def test_wait_without_candidate_has_reference_not_a_fake_trade(self):
        signal = Signal("TEST", "WAIT", 20, 100, 2, "", 1000, {"risk_distance": 3})
        chart = build_signal_chart(signal, [], "15m", 2)
        self.assertIsNone(chart["planned_side"])
        self.assertEqual(len(chart["levels"]), 1)
        self.assertEqual(chart["levels"][0]["label"], "Analiz fiyatı")
