import unittest
from unittest.mock import Mock

from bot.config import Settings
from bot.engine import TradingEngine
from bot.models import Position, Signal


def candidate(symbol, count=4, side="LONG", score=85, other=0):
    return Signal(symbol, side, score, 100, 2, "test", 1000, {"confirmation": {side.lower(): count, ("short" if side == "LONG" else "long"): other}})


def positions(count):
    return [Position(f"OPEN{i}", 1, 100, 100, 0) for i in range(count)]


class PositionLimitTests(unittest.TestCase):
    def setUp(self):
        self.broker, self.store = Mock(), Mock()
        self.store.read_risk_state.return_value = {}
        self.engine = TradingEngine(Settings.load(), self.broker, self.store)
        self.engine._execute_signal = Mock(return_value=True)

    def test_normal_candidates_stop_at_four(self):
        self.engine._open_candidates([candidate(str(i)) for i in range(6)], [], 100)
        self.assertEqual(self.engine._execute_signal.call_count, 4)

    def test_existing_positions_reduce_normal_capacity(self):
        self.engine._open_candidates([candidate("A"), candidate("B")], positions(3), 100)
        self.assertEqual(self.engine._execute_signal.call_count, 1)

    def test_seven_and_above_can_exceed_four_for_both_sides(self):
        items = [candidate("A", 7), candidate("B", 7, "SHORT"), candidate("C", 9), candidate("D", 6)]
        self.engine._open_candidates(items, positions(4), 100)
        self.assertEqual([c.args[0].symbol for c in self.engine._execute_signal.call_args_list], ["A", "B", "C"])

    def test_blocked_candidate_does_not_hide_later_override(self):
        self.engine._open_candidates([candidate("LOW", 6, score=100), candidate("HIGH", 7, score=85)], positions(4), 100)
        self.engine._execute_signal.assert_called_once()
        self.assertEqual(self.engine._execute_signal.call_args.args[0].symbol, "HIGH")

    def test_opposite_direction_count_and_quality_score_do_not_bypass(self):
        self.engine._open_candidates([candidate("A", 6, score=100, other=9)], positions(4), 100)
        self.engine._execute_signal.assert_not_called()

    def test_duplicate_symbol_candle_and_wait_remain_blocked(self):
        self.engine._last_candle["executed:OLD"] = 1000
        self.engine._open_candidates([candidate("OPEN0", 9), candidate("OLD", 9), candidate("WAIT", 9, side="WAIT")], positions(4), 100)
        self.engine._execute_signal.assert_not_called()

    def test_failed_order_does_not_consume_slot(self):
        self.engine._execute_signal.side_effect = [False, True]
        self.engine._open_candidates([candidate("A"), candidate("B")], positions(3), 100)
        self.assertEqual(self.engine._execute_signal.call_count, 2)

    def test_advanced_counts_missing_or_malformed_do_not_bypass(self):
        for count in (None, "7", 7.0, True, 10):
            self.assertFalse(self.engine._has_position_limit_override(candidate("A", count)))

    def test_pause_and_daily_limit_block_all_candidates(self):
        for paused, equity in ((True, 100), (False, 89)):
            with self.subTest(paused=paused, equity=equity):
                self.engine._active_symbols = Mock(return_value=[])
                self.store.read_control.return_value = {"paused": paused}
                self.broker.get_positions.return_value = positions(4)
                self.broker.get_trade_history.return_value = []
                self.broker.get_account_snapshot.return_value = {"equity": equity, "wallet_balance": equity, "available_balance": equity, "initial_margin": 0, "margin_balance": equity}
                self.engine._start_equity = 100
                self.engine._open_candidates = Mock()
                self.engine.tick()
                self.engine._open_candidates.assert_not_called()
