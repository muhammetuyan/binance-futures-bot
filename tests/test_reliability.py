import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from bot.config import Settings
from bot.exchange.paper import PaperBroker
from bot.models import Candle
from bot.persistence import atomic_json_write
from bot.review import review_trades
from bot.store import RuntimeStore
from test_paper_broker import FakeMarket


class ReliabilityTests(unittest.TestCase):
    def broker(self, directory):
        broker = PaperBroker(replace(Settings.load(), runtime_dir=Path(directory)), FakeMarket())
        with patch('bot.exchange.paper.time.time', return_value=100):
            broker.place_market_order('TEST', 'BUY', Decimal('.1'), 'entry')
        broker.place_protection_order('TEST', 'SELL', 'STOP_MARKET', Decimal('95'), 'sl')
        broker.place_protection_order('TEST', 'SELL', 'TAKE_PROFIT_MARKET', Decimal('110'), 'tp')
        return broker

    def test_pre_entry_wicks_and_analysis_bars_cannot_close_a_trade(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker(directory)
            broker.market.candles = [Candle(60_000, 100, 120, 80, 100, 100, 119_999)]
            with patch('bot.exchange.paper.time.time', return_value=110):
                broker.get_candles('TEST', '1h', 500)
                broker._settle_if_triggered('TEST', broker.market.candles)
            self.assertIn('TEST', broker._state['positions'])
            self.assertEqual(broker._state['positions']['TEST']['monitor_since'], 120_000)

    def test_forming_bar_is_revisited_not_marked_as_future_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker(directory)
            bar = Candle(120_000, 100, 111, 99, 100, 100, 179_999)
            with patch('bot.exchange.paper.time.time', return_value=130):
                broker._settle_if_triggered('TEST', [bar])
            self.assertEqual(broker._state['positions']['TEST']['monitor_since'], 120_000)
            with patch('bot.exchange.paper.time.time', return_value=180):
                broker._settle_if_triggered('TEST', [bar])
            self.assertEqual(broker.get_trade_history()[0]['reason'], 'TAKE_PROFIT')
            self.assertEqual(broker.get_trade_history()[0]['closed_at'], 179_999)

    def test_gap_stop_uses_worse_open_and_keeps_processing_time_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker(directory)
            with patch('bot.exchange.paper.time.time', return_value=1000):
                broker._settle_if_triggered('TEST', [Candle(120_000, 93, 96, 92, 94, 100, 179_999)])
            trade = broker.get_trade_history()[0]
            self.assertEqual(trade['exit'], 93)
            self.assertEqual(trade['closed_at'], 179_999)
            self.assertEqual(trade['processed_at'], 1_000_000)

    def test_same_bar_stop_and_target_are_flagged_as_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker(directory)
            with patch('bot.exchange.paper.time.time', return_value=180):
                broker._settle_if_triggered('TEST', [Candle(120_000, 100, 111, 94, 100, 100, 179_999)])
            self.assertTrue(broker.get_trade_history()[0]['ambiguous_bar'])
            self.assertEqual(review_trades(broker.get_trade_history())['excluded_count'], 1)

    def test_monitor_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker(directory)
            with patch.object(broker.market, 'get_candles', side_effect=RuntimeError('offline')):
                positions = broker.get_positions()
            self.assertEqual(len(positions), 1)
            self.assertIn('offline', broker.monitoring_errors['TEST'])

    def test_windows_transient_lock_retries_without_losing_json(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'state.json'
            atomic_json_write(target, {'balance': 100})
            import os
            original = os.replace
            attempts = []
            def locked_once(source, destination):
                attempts.append(1)
                if len(attempts) == 1:
                    raise PermissionError('reader lock')
                original(source, destination)
            with patch('bot.persistence.os.replace', side_effect=locked_once), patch('bot.persistence.time.sleep'):
                atomic_json_write(target, {'balance': 99})
            self.assertEqual(json.loads(target.read_text())['balance'], 99)
            self.assertEqual(len(attempts), 2)

    def test_persistent_lock_preserves_previous_state_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'state.json'
            atomic_json_write(target, {'balance': 100})
            with patch('bot.persistence.os.replace', side_effect=PermissionError('locked')), patch('bot.persistence.time.sleep'):
                with self.assertRaises(PermissionError):
                    atomic_json_write(target, {'balance': 99})
            self.assertEqual(json.loads(target.read_text())['balance'], 100)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_execution_stamp_survives_store_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            RuntimeStore(Path(directory)).record_execution('BTCUSDT', 123)
            self.assertEqual(RuntimeStore(Path(directory)).read_execution_state(), {'BTCUSDT': 123})

    def test_corrupt_account_fails_closed_instead_of_resetting_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            broker = self.broker(directory)
            with patch('bot.exchange.paper.json.load', side_effect=json.JSONDecodeError('bad', '', 0)):
                with self.assertRaisesRegex(RuntimeError, 'sıfırlanmadı'):
                    PaperBroker(broker.settings, FakeMarket())
            self.assertEqual(len(json.loads(broker.state_path.read_text())['positions']), 1)

    def test_unreadable_control_defaults_to_paused(self):
        with tempfile.TemporaryDirectory() as directory:
            store = RuntimeStore(Path(directory))
            with patch('bot.store.json.load', side_effect=OSError('locked')):
                self.assertTrue(store.read_control()['paused'])

    def test_legacy_batch_and_safe_close_are_separate_not_deleted(self):
        trades = [{'symbol': str(i), 'closed_at': i * 1000, 'pnl': -1, 'reason': 'STOP'} for i in range(3)]
        trades += [{'symbol': 'SAFE', 'closed_at': 20000, 'pnl': -.1, 'reason': 'SAFE_CLOSE'},
                   {'symbol': 'WIN', 'closed_at': 40000, 'pnl': 2, 'reason': 'TAKE_PROFIT'}]
        result = review_trades(trades)
        self.assertEqual(result['all']['count'], 5)
        self.assertEqual(result['strategy']['count'], 1)
        self.assertEqual(result['excluded_count'], 4)
        self.assertNotIn('review_note', trades[0])

    def test_new_simultaneous_exits_are_not_automatically_excluded(self):
        trades = [{'closed_at': i * 1000, 'pnl': -1, 'reason': 'STOP', 'execution_version': 'PAPER_1M_V2'} for i in range(3)]
        self.assertEqual(review_trades(trades)['strategy']['count'], 3)
