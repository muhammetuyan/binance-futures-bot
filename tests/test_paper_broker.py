import tempfile
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from bot.config import Settings
from bot.exchange.paper import PaperBroker
from bot.models import Candle, SymbolRules


class FakeMarket:
    def __init__(self):
        self.price = 100.0
        self.candles = self._candles(100.0, 100.5, 99.5)

    @staticmethod
    def _candles(close, high, low):
        now = int(time.time() * 1000)
        return [Candle(now, close, high, low, close, 1000, now + 60_000)]

    def discover_symbols(self, limit, minimum_quote_volume):
        return ["TESTUSDT"]

    def get_candles(self, symbol, interval, limit):
        return self.candles

    def get_symbol_rules(self, symbol):
        return SymbolRules(symbol, Decimal("0.1"), Decimal("0.001"), Decimal("0.001"), Decimal("100"), Decimal("5"))


class PaperBrokerTests(unittest.TestCase):
    def test_margin_cannot_exceed_remaining_paper_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(Settings.load(), runtime_dir=Path(directory), paper_balance=100.0)
            broker = PaperBroker(settings, FakeMarket())
            broker.place_market_order("FIRST", "BUY", Decimal("6"), "first")
            before = broker.get_account_snapshot()
            with self.assertRaisesRegex(ValueError, "bakiye"):
                broker.place_market_order("SECOND", "BUY", Decimal("6"), "second")
            self.assertEqual(broker.get_account_snapshot(), before)
            self.assertNotIn("SECOND", broker._state["positions"])

    def test_take_profit_updates_virtual_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(Settings.load(), runtime_dir=Path(directory), paper_balance=100.0)
            market = FakeMarket()
            broker = PaperBroker(settings, market)
            broker.get_candles("TESTUSDT", "1m", 2)
            broker.place_market_order("TESTUSDT", "BUY", Decimal("0.1"), "entry")
            broker.place_protection_order("TESTUSDT", "SELL", "STOP_MARKET", Decimal("95"), "sl")
            broker.place_protection_order("TESTUSDT", "SELL", "TAKE_PROFIT_MARKET", Decimal("110"), "tp")
            market.candles = market._candles(110.0, 111.0, 100.0)
            broker.get_candles("TESTUSDT", "1m", 2)
            self.assertEqual(broker.get_positions(), [])
            self.assertGreater(broker.get_account_snapshot()["wallet_balance"], 100.9)
            history = broker.get_trade_history()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["symbol"], "TESTUSDT")
            self.assertEqual(history[0]["side"], "LONG")
            self.assertEqual(history[0]["reason"], "TAKE_PROFIT")
            self.assertGreater(history[0]["pnl"], 0)


if __name__ == "__main__":
    unittest.main()
