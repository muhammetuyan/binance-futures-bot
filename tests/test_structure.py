import unittest
from dataclasses import replace

from bot.models import Candle
from bot.structure import analyze_structure, pivots


def structure_candles(fvg=False):
    candles = [Candle(i * 900000, 100, 100.5, 99.5, 100, 1000, (i + 1) * 900000 - 1) for i in range(80)]
    def put(i, o, h, l, c):
        candles[i] = replace(candles[i], open=o, high=h, low=l, close=c)
    put(60, 100, 110, 99, 101)
    put(65, 100, 106, 99, 101)
    put(68, 100, 100.5, 98, 100)
    put(74, 100, 102, 99 if fvg else 97, 101)
    put(75, 102, 105.5, 101, 105)
    put(76, 106 if fvg else 103, 109, 106 if fvg else 102, 108)
    put(77, 108, 109, 107, 108)
    put(78, 108, 109, 107, 108)
    put(79, 105 if fvg else 107, 109, 104 if fvg else 107, 108)
    return candles


def mirror(candles):
    return [replace(c, open=200-c.open, high=200-c.low, low=200-c.high, close=200-c.close) for c in candles]


class StructureTests(unittest.TestCase):
    def test_sweep_then_mss_without_range_breakout(self):
        candles = structure_candles()
        result = analyze_structure(candles, 2)['LONG']
        self.assertEqual(result['setup'], 'SWEEP_MSS')
        self.assertTrue(result['mss'])
        self.assertEqual(result['invalidation'], 97)
        self.assertLess(candles[-1].close, candles[60].high)

    def test_sweep_and_mss_are_symmetric(self):
        self.assertEqual(analyze_structure(mirror(structure_candles()), 2)['SHORT']['setup'], 'SWEEP_MSS')

    def test_mss_then_fvg_rejection(self):
        result = analyze_structure(structure_candles(True), 2)['LONG']
        self.assertEqual(result['setup'], 'FVG_MSS')
        self.assertTrue(result['fvg_retest'])
        self.assertEqual(result['fvg']['lower'], 102)
        self.assertEqual(result['fvg']['upper'], 106)

    def test_bearish_fvg_rejection(self):
        self.assertEqual(analyze_structure(mirror(structure_candles(True)), 2)['SHORT']['setup'], 'FVG_MSS')

    def test_fvg_can_vote_without_mss(self):
        candles = structure_candles(True)
        # Remove the prior lower high, keeping the gap and rejection intact.
        candles[65] = replace(candles[65], high=111)
        result = analyze_structure(candles, 2)['LONG']
        self.assertFalse(result['mss'])
        self.assertTrue(result['fvg_rejection'])
        self.assertFalse(result['fvg_retest'])

    def test_fully_filled_fvg_is_not_reused(self):
        candles = structure_candles(True)
        candles[77] = replace(candles[77], low=101)
        self.assertEqual(analyze_structure(candles, 2)['LONG']['setup'], 'WAIT')

    def test_wick_break_is_not_mss(self):
        candles = structure_candles()
        for i in range(76, 80):
            candles[i] = replace(candles[i], open=104, close=105, low=103)
        self.assertFalse(analyze_structure(candles, 2)['LONG']['mss'])

    def test_mss_expires_and_must_hold_broken_level(self):
        candles = structure_candles()
        candles[-1] = replace(candles[-1], close=104, low=103)
        self.assertEqual(analyze_structure(candles, 2)['LONG']['setup'], 'WAIT')
        candles = structure_candles()
        candles.append(replace(candles[-1], open_time=72000000, close_time=72899999))
        self.assertFalse(analyze_structure(candles, 2)['LONG']['mss'])

    def test_pivot_requires_two_already_closed_confirmation_candles(self):
        candles = [Candle(i, 1, h, 0, 1, 1, i) for i, h in enumerate([1, 2, 5, 2, 1, 9])]
        self.assertEqual(pivots(candles, 4)[0], [])
        self.assertEqual(pivots(candles, 5)[0], [(2, 5)])
        # Data beyond the decision prefix cannot influence that decision.
        self.assertEqual(pivots(candles, 5), pivots(candles[:5], 5))
