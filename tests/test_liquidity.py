import time
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

from bot.config import Settings
from bot.engine import TradingEngine
from bot.liquidity import assess_order_book
from bot.models import Signal, SymbolRules


def book():
    return {'T': int(time.time() * 1000), 'bids': [['99.99', '200']], 'asks': [['100.01', '200']]}


class LiquidityTests(unittest.TestCase):
    def test_good_book_both_directions(self):
        for side in ('LONG', 'SHORT'):
            self.assertTrue(assess_order_book(book(), side, 400, 100, 2)['ok'])

    def test_wide_spread_thin_stale_and_invalid_book_rejected(self):
        for data in (
            {**book(), 'asks': [['101', '200']]},
            {**book(), 'bids': [['99.99', '1']]},
            {**book(), 'T': int(time.time() * 1000) - 20000},
            {**book(), 'T': int(time.time() * 1000) + 20000},
            {**book(), 'bids': []},
            {**book(), 'bids': [['nan', '200']]},
            {**book(), 'bids': [['102', '200']]},
            {},
        ):
            self.assertFalse(assess_order_book(data, 'LONG', 400, 100, 2)['ok'])

    def test_price_drift_and_excessive_slippage_rejected(self):
        self.assertFalse(assess_order_book(book(), 'LONG', 400, 97, 2)['ok'])
        data = {**book(), 'asks': [['100.01', '0.001'], ['100.19', '200']]}
        self.assertFalse(assess_order_book(data, 'LONG', 400, 100, 2)['ok'])

    def test_missing_book_fails_closed_and_execution_rechecks(self):
        broker, store = Mock(), Mock()
        broker.get_account_snapshot.return_value = {"equity": 100, "available_balance": 100}
        store.read_risk_state.return_value = {}
        engine = TradingEngine(Settings.load(), broker, store)
        signal = Signal('TESTUSDT', 'LONG', 90, 100, 2, 'test', 1000)
        broker.get_order_book.side_effect = RuntimeError('offline')
        checked = engine._with_liquidity(signal, 100)
        self.assertEqual(checked.side, 'WAIT')
        self.assertFalse(checked.checks['emir defteri likiditesi'])
        broker.get_symbol_rules.return_value = SymbolRules('TESTUSDT', Decimal('.01'), Decimal('.001'), Decimal('.001'), Decimal('10000'), Decimal('5'))
        engine.risk.position_quantity = Mock(return_value=Decimal('1'))
        self.assertFalse(engine._execute_signal(signal, 100))
        broker.place_market_order.assert_not_called()
        broker.prepare_symbol.assert_not_called()

    def test_fill_keeps_structural_stop_and_two_r_target(self):
        broker, store = Mock(), Mock()
        broker.get_account_snapshot.return_value = {"equity": 100, "available_balance": 100}
        store.read_risk_state.return_value = {}
        engine = TradingEngine(Settings.load(), broker, store)
        broker.get_symbol_rules.return_value = SymbolRules('TESTUSDT', Decimal('.01'), Decimal('.001'), Decimal('.001'), Decimal('10000'), Decimal('5'))
        broker.get_order_book.return_value = book()
        broker.place_market_order.return_value = {'avgPrice': '100.5'}
        engine.risk.position_quantity = Mock(return_value=Decimal('1'))
        signal = Signal('TESTUSDT', 'LONG', 90, 100, 2, 'test', 1000, {'risk_distance': 10.3, 'invalidation': 90})
        self.assertTrue(engine._execute_signal(signal, 100))
        protections = broker.place_protection_order.call_args_list
        stop, target = protections[0].args[3], protections[1].args[3]
        self.assertEqual(stop, Decimal('89.70'))
        self.assertEqual(target, Decimal('122.10'))
        self.assertAlmostEqual(float(target) - 100.5, (100.5 - float(stop)) * 2)
        self.assertLess(engine.risk.position_quantity.call_args.args[2], float(stop))

    def test_good_liquidity_does_not_bypass_insufficient_balance(self):
        broker, store = Mock(), Mock()
        store.read_risk_state.return_value = {}
        broker.get_account_snapshot.return_value = {"equity": 100, "available_balance": 1}
        engine = TradingEngine(Settings.load(), broker, store)
        broker.get_symbol_rules.return_value = SymbolRules('TEST', Decimal('.01'), Decimal('.001'), Decimal('.001'), Decimal('10000'), Decimal('5'))
        broker.get_order_book.return_value = book()
        engine.risk.position_quantity = Mock(return_value=Decimal('1'))
        signal = Signal('TEST', 'LONG', 100, 100, 2, '', 1000, {"confirmation": {"long": 9}})
        self.assertFalse(engine._execute_signal(signal, 100))
        broker.place_market_order.assert_not_called()
