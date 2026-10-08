import unittest
from unittest.mock import patch

def valid_structure():
    return {
        side: {'setup': 'SWEEP_MSS', 'mss': True, 'invalidation': None}
        for side in ('LONG', 'SHORT')
    }


from bot.models import Candle
from bot.strategy import TrendMomentumStrategy


def trending_candles(direction: int) -> list[Candle]:
    candles = []
    price = 300.0
    for index in range(260):
        price += direction * (0.4 + index * 0.004)
        candles.append(
            Candle(
                open_time=index * 60_000,
                open=price - direction * 0.2,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=100 + index,
                close_time=(index + 1) * 60_000 - 1,
            )
        )
    return candles


class StrategyTests(unittest.TestCase):
    def test_three_rsi_periods_are_exposed_and_affect_entry(self):
        candles = trending_candles(1)
        def readings(closes, period):
            value = {7: 60.0, 14: 58.0, 21: 55.0}[period]
            return [value - 1] * (len(closes) - 1) + [value]
        with patch('bot.strategy.rsi', side_effect=readings), patch('bot.strategy.analyze_structure', return_value=valid_structure()):
            signal = TrendMomentumStrategy(70, triple_rsi=True).analyze('TESTUSDT', candles, candles)
        self.assertEqual(signal.side, 'LONG')
        self.assertEqual(signal.indicators['rsi'], {'7': 60.0, '14': 58.0, '21': 55.0})
        self.assertEqual(signal.indicators['higher_rsi'], signal.indicators['rsi'])
        self.assertTrue(signal.checks['RSI 7 / 14 / 21 onayı'])

    def test_conflicting_structure_votes_wait_even_with_four_approvals(self):
        def readings(closes, period):
            value = {7: 60.0, 14: 58.0, 21: 55.0}[period]
            return [value + 1] * (len(closes) - 1) + [value]
        with patch('bot.strategy.rsi', side_effect=readings), patch('bot.strategy.analyze_structure', return_value=valid_structure()):
            signal = TrendMomentumStrategy(70, triple_rsi=True).analyze('TESTUSDT', trending_candles(1))
        self.assertEqual(signal.side, 'WAIT')
        self.assertFalse(signal.checks['RSI 7 / 14 / 21 onayı'])
        self.assertGreaterEqual(signal.indicators['confirmation']['long'], 4)

    def test_rsi_confirmation_is_symmetric_and_rejects_extremes(self):
        self.assertEqual(TrendMomentumStrategy.rsi_confirmation((60, 58, 49), 59), (True, False))
        self.assertEqual(TrendMomentumStrategy.rsi_confirmation((40, 42, 51), 41), (False, True))
        self.assertEqual(TrendMomentumStrategy.rsi_confirmation((90, 60, 60), 89), (False, False))
        self.assertEqual(TrendMomentumStrategy.rsi_confirmation((10, 40, 40), 11), (False, False))
        self.assertEqual(TrendMomentumStrategy.rsi_confirmation((50, 50, 50), 50), (False, False))

    def test_three_neutral_checks_and_one_direction_are_not_enough(self):
        signal = TrendMomentumStrategy(70, triple_rsi=True).analyze("BTCUSDT", trending_candles(1))
        self.assertEqual(signal.side, "WAIT")
        self.assertEqual(signal.indicators["confirmation"]["long"], 4)
        self.assertEqual(signal.score, 70)
        self.assertFalse(signal.checks["MSS kapanış onayı"])

    def test_weak_short_direction_is_also_rejected(self):
        signal = TrendMomentumStrategy(70, triple_rsi=True).analyze("BTCUSDT", trending_candles(-1))
        self.assertEqual(signal.side, "WAIT")
        self.assertEqual(signal.indicators["confirmation"]["short"], 4)
        self.assertFalse(signal.checks["MSS kapanış onayı"])

    def test_three_approvals_are_insufficient(self):
        signal = TrendMomentumStrategy(70, triple_rsi=True, minimum_adx=101).analyze("BTCUSDT", trending_candles(1))
        self.assertEqual(signal.side, "WAIT")
        self.assertEqual(signal.indicators["confirmation"]["long"], 3)

    def test_direction_votes_are_not_combined_and_ties_wait(self):
        def checks(long_count, short_count):
            return {side: {str(i): i < count for i in range(9)} for side, count in (("LONG", long_count), ("SHORT", short_count))}
        for long_count, short_count, expected in ((3, 3, "WAIT"), (4, 3, "LONG"), (3, 4, "SHORT"), (4, 4, "WAIT"), (5, 4, "LONG"), (5, 6, "SHORT")):
            side, counts = TrendMomentumStrategy.choose_direction(checks(long_count, short_count), 4)
            self.assertEqual(side, expected)
            self.assertEqual(counts, {"LONG": long_count, "SHORT": short_count})

    def test_missing_higher_timeframe_is_not_a_free_vote(self):
        signal = TrendMomentumStrategy(triple_rsi=True).analyze("BTCUSDT", trending_candles(1))
        self.assertFalse(signal.checks["1 saat trend"])
        self.assertEqual(len(signal.checks), 9)
        self.assertEqual(sum("RSI" in label for label in signal.checks), 1)

    def test_more_approvals_increase_margin_score(self):
        candles = trending_candles(1)
        strategy = TrendMomentumStrategy(85, triple_rsi=True)
        base = strategy.analyze("BTCUSDT", candles)
        more = strategy.analyze("BTCUSDT", candles, candles)
        self.assertEqual(base.score, 85)
        self.assertGreater(more.score, base.score)

    def test_rejects_short_history(self):
        with self.assertRaises(ValueError):
            TrendMomentumStrategy().analyze("BTCUSDT", trending_candles(1)[:20])

    def test_opposing_higher_timeframe_can_cause_a_vote_tie(self):
        signal = TrendMomentumStrategy(90, triple_rsi=True).analyze(
            "BTCUSDT",
            trending_candles(1),
            trending_candles(-1),
        )
        self.assertEqual(signal.side, "WAIT")

    def test_rsi_band_removes_only_its_vote(self):
        signal = TrendMomentumStrategy(
            70,
            long_rsi_range=(45.0, 72.0),
            triple_rsi=True,
        ).analyze("BTCUSDT", trending_candles(1), trending_candles(1))
        self.assertEqual(signal.side, "LONG")
        self.assertFalse(signal.checks["RSI 7 / 14 / 21 onayı"])

    def test_old_range_breakout_is_removed(self):
        signal = TrendMomentumStrategy(70).analyze(
            "BTCUSDT",
            trending_candles(1),
        )
        self.assertNotIn("son 12 mum", signal.reason)
        self.assertIn("MSS", signal.reason)

    def test_exactly_four_well_supported_approvals_can_enter(self):
        for direction, side in ((1, "LONG"), (-1, "SHORT")):
            def readings(closes, period):
                value = (60 if direction > 0 else 40)
                return [value - direction] * (len(closes) - 1) + [value]
            with patch('bot.strategy.rsi', side_effect=readings):
                signal = TrendMomentumStrategy(85, triple_rsi=True, minimum_volume_ratio=2).analyze("TEST", trending_candles(direction))
            self.assertEqual(signal.side, side)
            self.assertEqual(signal.indicators['confirmation'][side.lower()], 4)
            self.assertFalse(signal.checks['MSS kapanış onayı'])
            self.assertFalse(signal.checks['FVG dönüş tepkisi'])


if __name__ == "__main__":
    unittest.main()
