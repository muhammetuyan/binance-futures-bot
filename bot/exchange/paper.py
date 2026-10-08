from __future__ import annotations

import json
import logging
import math
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..config import Settings
from ..models import Candle, Position, SymbolRules
from ..persistence import atomic_json_write
from .binance_futures import BinanceFuturesClient


class PaperBroker:
    """Binance piyasa verisiyle çalışan, emirleri yerelde simüle eden aracı."""

    def __init__(self, settings: Settings, market: BinanceFuturesClient | None = None) -> None:
        self.settings = settings
        self.market = market or BinanceFuturesClient(settings)
        self.state_path = settings.runtime_dir / "paper_account.json"
        self._lock = threading.RLock()
        self._last_prices: dict[str, float] = {}
        self.monitoring_errors: dict[str, str] = {}
        self._state = self._load_state()

    def discover_symbols(self, limit: int, minimum_quote_volume: float) -> list[str]:
        return self.market.discover_symbols(limit, minimum_quote_volume)

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[Candle]:
        candles = self.market.get_candles(symbol, interval, limit)
        if candles:
            self._last_prices[symbol] = candles[-1].close
            # Analysis candles must never settle trades (their wick can predate entry).
        return candles

    def get_order_book(self, symbol: str) -> dict[str, Any]:
        return self.market.get_order_book(symbol)

    def get_symbol_rules(self, symbol: str) -> SymbolRules:
        return self.market.get_symbol_rules(symbol)

    def get_positions(self) -> list[Position]:
        for symbol in list(self._state["positions"]):
            try:
                item = self._state["positions"][symbol]
                start = int(item.get("monitor_since", (int(item["entry_time"]) // 60_000 + 1) * 60_000))
                if start > int(time.time() * 1000) or not hasattr(self.market, "get_monitoring_candles"):
                    # In the entry minute use the current quote, never old wicks.
                    candles = self.market.get_candles(symbol, "1m", 3)
                else:
                    candles = self.market.get_monitoring_candles(symbol, start)
                if candles:
                    self._last_prices[symbol] = candles[-1].close
                    self._settle_if_triggered(symbol, candles)
                if not candles or candles[-1].close_time < int(time.time() * 1000) - 60_000:
                    self.monitoring_errors[symbol] = "Eksik 1 dk mumları tamamlanıyor; yeni girişler bekliyor"
                    continue
                self.monitoring_errors.pop(symbol, None)
            except Exception as exc:
                self.monitoring_errors[symbol] = str(exc)
                logging.getLogger("atlas.paper").warning("%s pozisyon takibi başarısız: %s", symbol, exc)
        return self.get_cached_positions()

    def get_cached_positions(self) -> list[Position]:
        output: list[Position] = []
        with self._lock:
            for symbol, item in self._state["positions"].items():
                mark = self._last_prices.get(symbol, float(item["entry_price"]))
                amount = float(item["amount"])
                pnl = (mark - float(item["entry_price"])) * amount
                output.append(Position(symbol, amount, float(item["entry_price"]), mark, pnl))
        return output

    def get_account_snapshot(self) -> dict[str, float]:
        with self._lock:
            unrealized = 0.0
            notional = 0.0
            for symbol, item in self._state["positions"].items():
                mark = self._last_prices.get(symbol, float(item["entry_price"]))
                amount = float(item["amount"])
                unrealized += (mark - float(item["entry_price"])) * amount
                notional += abs(mark * amount)
            wallet = float(self._state["balance"])
            initial_margin = notional / max(self.settings.leverage, 1)
            equity = wallet + unrealized
            return {
                "wallet_balance": wallet,
                "unrealized_pnl": unrealized,
                "equity": equity,
                "available_balance": max(0.0, wallet - initial_margin),
                "margin_balance": equity,
                "initial_margin": initial_margin,
            }

    def get_trade_history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            trades = self._state.setdefault("trades", [])
            return [dict(item) for item in reversed(trades[-max(1, limit):])]

    def prepare_symbol(self, symbol: str, leverage: int) -> None:
        if not 1 <= leverage <= 20:
            raise ValueError("Paper kaldıraç güvenlik sınırı dışında")

    def place_market_order(self, symbol: str, side: str, quantity: Decimal, client_id: str) -> dict[str, Any]:
        with self._lock:
            if symbol in self._state["positions"]:
                raise RuntimeError(f"{symbol} için zaten açık paper pozisyonu var")
            candles = self.market.get_candles(symbol, "1m", 2)
            if not candles or int(time.time() * 1000) - candles[-1].open_time > 120_000:
                raise RuntimeError("Paper giriş için güncel fiyat alınamadı")
            price = candles[-1].close
            self._last_prices[symbol] = price
            signed_quantity = float(quantity) if side == "BUY" else -float(quantity)
            if side not in {"BUY", "SELL"} or not math.isfinite(float(quantity)) or quantity <= 0 or not math.isfinite(price) or price <= 0:
                raise ValueError("Paper emir fiyatı, yönü veya miktarı geçersiz")
            fee = abs(price * signed_quantity) * 0.0005
            required_margin = abs(price * signed_quantity) / self.settings.leverage
            if required_margin + fee > self.get_account_snapshot()["available_balance"]:
                raise ValueError("Paper hesapta teminat ve komisyon için yeterli bakiye yok")
            self._state["balance"] = float(self._state["balance"]) - fee
            self._state["positions"][symbol] = {
                "amount": signed_quantity,
                "entry_price": price,
                "entry_time": int(time.time() * 1000),
                "monitor_since": (int(time.time() * 1000) // 60_000 + 1) * 60_000,
                "last_checked": int(time.time() * 1000),
                "stop": None,
                "take_profit": None,
                "entry_fee": fee,
                "client_id": client_id,
            }
            self._save_state()
            return {
                "symbol": symbol,
                "status": "FILLED",
                "avgPrice": str(price),
                "executedQty": format(quantity, "f"),
                "clientOrderId": client_id,
                "paper": True,
            }

    def place_protection_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: Decimal,
        client_id: str,
    ) -> dict[str, Any]:
        with self._lock:
            position = self._state["positions"].get(symbol)
            if not position:
                raise RuntimeError(f"{symbol} paper pozisyonu bulunamadı")
            if order_type == "STOP_MARKET":
                position["stop"] = float(trigger_price)
            elif order_type == "TAKE_PROFIT_MARKET":
                position["take_profit"] = float(trigger_price)
            else:
                raise ValueError(f"Paper modunda desteklenmeyen emir türü: {order_type}")
            self._save_state()
            return {
                "symbol": symbol,
                "algoStatus": "NEW",
                "orderType": order_type,
                "triggerPrice": format(trigger_price, "f"),
                "clientAlgoId": client_id,
                "paper": True,
            }

    def close_position(self, symbol: str, side: str, quantity: Decimal, client_id: str) -> dict[str, Any]:
        price = self._last_prices.get(symbol)
        if not price:
            candles = self.market.get_candles(symbol, "1m", 2)
            price = candles[-1].close
        self._close(symbol, price, "SAFE_CLOSE")
        return {"symbol": symbol, "status": "FILLED", "avgPrice": str(price), "clientOrderId": client_id, "paper": True}

    def reset(self, balance: float | None = None) -> None:
        with self._lock:
            self._state = {"balance": float(balance or self.settings.paper_balance), "positions": {}, "trades": []}
            self._save_state()

    def _settle_if_triggered(self, symbol: str, candles: list[Candle]) -> None:
        with self._lock:
            position = self._state["positions"].get(symbol)
            if not position:
                return
            now = int(time.time() * 1000)
            # Only completed, one-minute bars fully after entry may use high/low.
            start = int(position.get("monitor_since", (int(position["entry_time"]) // 60_000 + 1) * 60_000))
            relevant = sorted([c for c in candles if c.open_time >= start and c.close_time < now and c.close_time - c.open_time < 60_000], key=lambda c: c.open_time)
            amount = float(position["amount"])
            stop = position.get("stop")
            take_profit = position.get("take_profit")
            for candle in relevant:
                stop_hit = stop is not None and (candle.low <= stop if amount > 0 else candle.high >= stop)
                take_hit = take_profit is not None and (candle.high >= take_profit if amount > 0 else candle.low <= take_profit)
                if stop_hit:
                    fill = min(float(stop), candle.open) if amount > 0 else max(float(stop), candle.open)
                    self._close(symbol, fill, "STOP", candle.close_time, ambiguous=take_hit)
                    return
                if take_hit:
                    self._close(symbol, float(take_profit), "TAKE_PROFIT", candle.close_time)
                    return
            if relevant:
                position["monitor_since"] = relevant[-1].close_time + 1
            # A forming bar's range contains pre-entry movement. Its current quote
            # is safe to use only when all preceding monitoring bars are caught up.
            if candles:
                latest = max(candles, key=lambda c: c.open_time)
                caught_up = int(position.get("monitor_since", start)) >= now // 60_000 * 60_000
                if latest.close_time >= now and caught_up:
                    stop_hit = stop is not None and (latest.close <= stop if amount > 0 else latest.close >= stop)
                    take_hit = take_profit is not None and (latest.close >= take_profit if amount > 0 else latest.close <= take_profit)
                    if stop_hit or take_hit:
                        self._close(symbol, latest.close if stop_hit else float(take_profit), "STOP" if stop_hit else "TAKE_PROFIT", now)
                        return
            self._save_state()

    def _close(self, symbol: str, exit_price: float, reason: str, closed_at: int | None = None, ambiguous: bool = False) -> None:
        with self._lock:
            item = self._state["positions"].pop(symbol, None)
            if not item:
                return
            amount = float(item["amount"])
            pnl = (exit_price - float(item["entry_price"])) * amount
            fee = abs(exit_price * amount) * 0.0005
            self._state["balance"] = float(self._state["balance"]) + pnl - fee
            self._state["trades"].append({
                "symbol": symbol,
                "side": "LONG" if amount > 0 else "SHORT",
                "entry": item["entry_price"],
                "exit": exit_price,
                "pnl": pnl - fee - float(item.get("entry_fee", 0.0)),
                "reason": reason,
                "closed_at": closed_at or int(time.time() * 1000),
                "processed_at": int(time.time() * 1000),
                "entry_time": item.get("entry_time"),
                "entry_context": item.get("entry_context", {}),
                "ambiguous_bar": ambiguous,
                "execution_version": "PAPER_1M_V2",
            })
            self._state["trades"] = self._state["trades"][-200:]
            self._save_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                state = json.load(handle)
            if (isinstance(state, dict) and "balance" in state and
                    isinstance(state.get("positions"), dict) and
                    isinstance(state.get("trades", []), list) and
                    math.isfinite(float(state["balance"]))):
                state.setdefault("trades", [])
                return state
            raise ValueError("Paper hesap dosyasının yapısı geçersiz")
        except FileNotFoundError:
            return {"balance": self.settings.paper_balance, "positions": {}, "trades": []}
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as exc:
            raise RuntimeError("Paper hesap dosyası okunamadı; bakiye sıfırlanmadı ve işlem açılmadı") from exc
        return {"balance": self.settings.paper_balance, "positions": {}, "trades": []}

    def _save_state(self) -> None:
        atomic_json_write(self.state_path, self._state)

    def record_entry_context(self, symbol: str, context: dict[str, Any]) -> None:
        with self._lock:
            if symbol in self._state["positions"]:
                self._state["positions"][symbol]["entry_context"] = context
                self._save_state()
