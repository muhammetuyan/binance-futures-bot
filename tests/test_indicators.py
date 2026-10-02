import unittest

from bot.indicators import atr, ema, rsi
from bot.models import Candle


class IndicatorTests(unittest.TestCase):
    def test_ema_tracks_series_length_and_direction(self):
        values = [1.0, 2.0, 3.0, 4.0]
        result = ema(values, 3)
        self.assertEqual(len(result), len(values))
        self.assertGreater(result[-1], result[0])

    def test_rsi_is_bounded(self):
        result = rsi([100, 101, 100, 103, 102, 104, 106], 3)
        self.assertTrue(all(0 <= value <= 100 for value in result))

    def test_atr_is_positive(self):
        candles = [
            Candle(index, 100 + index, 102 + index, 99 + index, 101 + index, 10, index + 1)
            for index in range(20)
        ]
        self.assertGreater(atr(candles, 14)[-1], 0)


if __name__ == "__main__":
    unittest.main()
