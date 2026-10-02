from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .config import Settings
from .chart import build_signal_chart
from .exchange.base import Broker
from .models import Position, Signal
from .liquidity import assess_order_book
from .risk import RiskManager, quantize_price
from .store import RuntimeStore
from .strategy import TrendMomentumStrategy


LOGGER = logging.getLogger("atlas.engine")


class TradingEngine:
    def __init__(self, settings: Settings, broker: Broker, store: RuntimeStore) -> None:
        self.settings = settings
        self.broker = broker
        self.store = store
        self.strategy = TrendMomentumStrategy(
            settings.minimum_signal_score,
            settings.minimum_adx,
            settings.minimum_volume_ratio,
            settings.minimum_stop_percent,
            settings.atr_stop_multiple,
            (settings.long_rsi_min, settings.long_rsi_max),
            (settings.short_rsi_min, settings.short_rsi_max),
            triple_rsi=True,
            minimum_confirmations=settings.minimum_confirmations,
        )
        self.risk = RiskManager(
            settings.risk_per_trade,
            settings.daily_loss_limit,
            settings.max_margin_fraction,
            settings.leverage,
        )
        self._last_candle: dict[str, int] = {}
        self._signals: deque[dict[str, Any]] = deque(maxlen=12)
        self._equity_curve: deque[dict[str, Any]] = deque(maxlen=96)
        self._day = datetime.now().astimezone().date()
        risk_state = self.store.read_risk_state()
        if risk_state.get("day") == self._day.isoformat():
            self._start_equity = float(risk_state.get("start_equity", 0.0))
        elif not risk_state.get("day") and self.settings.paper_mode:
            self._start_equity = self.settings.paper_balance
        else:
            self._start_equity = 0.0
        self._prepared_symbols: set[str] = set()
        self._symbols = list(settings.symbols)
        self._universe_updated_at = 0.0
        self._last_scan_bucket: int | None = None

    def run(self, stop_event: threading.Event) -> None:
        LOGGER.info("Atlas Trade motoru başladı")
        if self.settings.has_credentials and not self.settings.paper_mode:
            try:
                getattr(self.broker, "sync_time")()
            except Exception:
                LOGGER.exception("Saat eşitleme başarısız")
        while not stop_event.is_set():
            cycle_started = time.monotonic()
            try:
                self.tick()
            except Exception as exc:
                LOGGER.exception("İşlem döngüsü hatası")
                current = self.store.read_status()
                current.update({
                    "state": "error",
                    "message": str(exc),
                    "next_check_seconds": self.settings.poll_seconds,
                })
                self.store.write_status(current)
                self.store.append_event({"type": "error", "message": str(exc)})
            elapsed = time.monotonic() - cycle_started
            stop_event.wait(max(1.0, self.settings.poll_seconds - elapsed))
        current = self.store.read_status()
        current.update({"state": "stopped", "message": "Bot güvenli biçimde durduruldu", "next_check_seconds": 0})
        self.store.write_status(current)

    def tick(self) -> None:
        paused = bool(self.store.read_control().get("paused", False))
        now_ms = int(time.time() * 1000)
        scan_interval_ms = self.settings.scan_interval_minutes * 60_000
        next_scan_at = ((now_ms // scan_interval_ms) + 1) * scan_interval_ms
        symbols = self._active_symbols()
        latest_signals: list[Signal] = []
        last_candle_time: int | None = None

        positions: list[Position] = []
        trade_history: list[dict[str, Any]] = []
        account = {
            "wallet_balance": 0.0,
            "unrealized_pnl": 0.0,
            "equity": 0.0,
            "available_balance": 0.0,
            "margin_balance": 0.0,
            "initial_margin": 0.0,
        }
        account_available = self.settings.paper_mode or self.settings.has_credentials
        if account_available:
            positions = self.broker.get_positions()
            account = self.broker.get_account_snapshot()
            trade_history = self.broker.get_trade_history(100)

        scan_bucket = now_ms // (self.settings.scan_interval_minutes * 60_000)
        if self._last_scan_bucket != scan_bucket:
            scan_payloads: list[dict[str, Any]] = []
            for symbol in symbols:
                try:
                    candles = self.broker.get_candles(symbol, self.settings.interval, self.settings.candle_limit)
                    confirmation_candles = self.broker.get_candles(
                        symbol,
                        self.settings.confirmation_interval,
                        self.settings.candle_limit,
                    )
                    closed = [candle for candle in candles if candle.close_time < now_ms]
                    confirmation_closed = [
                        candle for candle in confirmation_candles if candle.close_time < now_ms
                    ]
                    if len(closed) < 220 or len(confirmation_closed) < 220:
                        continue
                    signal = self.strategy.analyze(symbol, closed, confirmation_closed)
                    signal = replace(signal, indicators={**signal.indicators, "chart": build_signal_chart(signal, closed, self.settings.interval, self.settings.reward_risk_ratio)})
                    if signal.side != "WAIT":
                        notional = self.risk.margin_for_score(signal.score, self.settings.minimum_signal_score, self.settings.minimum_margin_usdt, self.settings.maximum_margin_usdt) * self.settings.leverage
                        signal = self._with_liquidity(signal, notional)
                    latest_signals.append(signal)
                    last_candle_time = max(last_candle_time or 0, signal.candle_close_time)
                    if self._last_candle.get(symbol) != signal.candle_close_time:
                        self._last_candle[symbol] = signal.candle_close_time
                        scan_payloads.append(self._signal_payload(signal))
                except Exception as exc:
                    LOGGER.warning("%s taranamadı: %s", symbol, exc)
                    self.store.append_event({"type": "scan_error", "symbol": symbol, "message": str(exc)})
            if scan_payloads:
                ranked_payloads = sorted(
                    scan_payloads,
                    key=lambda item: (item["signal"] != "WAIT", item["score"]),
                    reverse=True,
                )
                self._signals = deque(ranked_payloads[:12], maxlen=12)
            self._last_scan_bucket = scan_bucket
        elif self._signals:
            last_candle_time = int(self._signals[0].get("timestamp", 0)) or None

        today = datetime.now().astimezone().date()
        if today != self._day:
            self._day = today
            self._start_equity = account["equity"]
        if self._start_equity <= 0 and account["equity"] > 0:
            self._start_equity = account["equity"]
        if self._start_equity > 0:
            self.store.write_risk_state(self._day.isoformat(), self._start_equity)

        daily_limit_hit = (
            self._start_equity > 0
            and self.risk.daily_limit_hit(self._start_equity, account["equity"])
        )
        if daily_limit_hit and not paused:
            self.store.write_control(paused=True)
            paused = True
            self.store.append_event({"type": "risk_lock", "message": "Günlük zarar limiti tetiklendi"})

        if not paused and not daily_limit_hit and self.settings.order_execution_enabled:
            self._open_candidates(latest_signals, positions, account["equity"])

        equity = account["equity"]
        daily_pnl = equity - self._start_equity if self._start_equity > 0 else 0.0
        daily_pnl_percent = (daily_pnl / self._start_equity * 100.0) if self._start_equity > 0 else 0.0
        loss_used = max(0.0, -daily_pnl_percent / (self.settings.daily_loss_limit * 100.0) * 100.0)
        margin_used = (
            account["initial_margin"] / account["margin_balance"] * 100.0
            if account["margin_balance"] > 0
            else 0.0
        )
        if equity > 0:
            self._equity_curve.append({
                "time": datetime.now(UTC).strftime("%H:%M"),
                "equity": round(equity, 2),
            })

        if self.settings.paper_mode and paused:
            state = "paused"
            message = "Paper işlemleri durduruldu; açık sanal pozisyonlar izleniyor"
        elif self.settings.paper_mode:
            state = "paper_running"
            message = (
                f"{self.settings.paper_balance:g} USDT paper hesapla {len(symbols)} likit parite "
                f"her {self.settings.scan_interval_minutes} dakikada 15dk+1s taranıyor"
            )
        elif not self.settings.has_credentials:
            state = "needs_credentials"
            message = "Piyasa analizi aktif; testnet API anahtarları bekleniyor"
        elif paused:
            state = "paused"
            message = "Yeni işlem açma durduruldu; koruma emirleri borsada aktif"
        elif self.settings.dry_run:
            state = "dry_run"
            message = "Analiz aktif; emir gönderimi kapalı"
        else:
            state = "running"
            message = "Testnet analizi ve otomatik emir akışı aktif"

        self.store.write_status({
            "state": state,
            "mode": "PAPER" if self.settings.paper_mode else ("TESTNET" if self.settings.testnet else "LIVE"),
            "message": message,
            "equity": round(equity, 2),
            "wallet_balance": round(account["wallet_balance"], 2),
            "available_balance": round(account["available_balance"], 2),
            "daily_pnl": round(daily_pnl, 2),
            "daily_pnl_percent": round(daily_pnl_percent, 2),
            "daily_loss_used_percent": round(min(loss_used, 100.0), 2),
            "open_risk_percent": round(len(positions) * self.settings.risk_per_trade * 100.0, 2),
            "margin_used_percent": round(margin_used, 2),
            "daily_loss_limit_percent": self.settings.daily_loss_limit * 100.0,
            "risk_per_trade_percent": self.settings.risk_per_trade * 100.0,
            "positions": [self._position_payload(position) for position in positions],
            "trade_history": trade_history,
            "signals": list(self._signals),
            "equity_curve": list(self._equity_curve),
            "last_candle_time": last_candle_time,
            "next_check_seconds": self.settings.poll_seconds,
            "next_scan_at": next_scan_at,
            "execution_enabled": self.settings.order_execution_enabled,
            "symbols": symbols,
            "interval": self.settings.interval,
            "confirmation_interval": self.settings.confirmation_interval,
            "scan_interval_minutes": self.settings.scan_interval_minutes,
            "leverage": self.settings.leverage,
            "margin_mode": "ISOLATED",
            "reward_risk_ratio": self.settings.reward_risk_ratio,
            "entry_model": "CONFIRMATION_VOTE",
            "minimum_confirmations": self.settings.minimum_confirmations,
            "max_open_positions": self.settings.max_open_positions,
            "position_limit_override_confirmations": self.settings.position_limit_override_confirmations,
            "minimum_margin_usdt": self.settings.minimum_margin_usdt,
            "maximum_margin_usdt": self.settings.maximum_margin_usdt,
            "paper_start_balance": self.settings.paper_balance if self.settings.paper_mode else None,
        })

    def _has_position_limit_override(self, signal: Signal) -> bool:
        if signal.side not in {"LONG", "SHORT"}:
            return False
        confirmation = signal.indicators.get("confirmation")
        if not isinstance(confirmation, dict):
            return False
        count = confirmation.get(signal.side.lower())
        return type(count) is int and self.settings.position_limit_override_confirmations <= count <= 9

    def _open_candidates(self, signals: list[Signal], positions: list[Position], equity: float) -> None:
        open_symbols = {position.symbol for position in positions}
        open_count = len(positions)
        for signal in sorted(signals, key=lambda item: item.score, reverse=True):
            if signal.side == "WAIT" or signal.symbol in open_symbols:
                continue
            if self._last_candle.get(f"executed:{signal.symbol}") == signal.candle_close_time:
                continue
            above_limit = open_count >= self.settings.max_open_positions
            if above_limit and not self._has_position_limit_override(signal):
                self.store.append_event({"type": "skipped", "symbol": signal.symbol, "message": f"{self.settings.max_open_positions} pozisyon sınırı dolu; seçilen yönde en az {self.settings.position_limit_override_confirmations} onay gerekli"})
                # Do not stop scanning: a later candidate may qualify for the exception.
                continue
            opened = self._execute_signal(signal, equity)
            self._last_candle[f"executed:{signal.symbol}"] = signal.candle_close_time
            if opened:
                open_symbols.add(signal.symbol)
                open_count += 1
                if above_limit:
                    self.store.append_event({"type": "position_limit_override", "symbol": signal.symbol, "side": signal.side, "confirmations": signal.indicators["confirmation"][signal.side.lower()], "open_positions": open_count})

    def _active_symbols(self) -> list[str]:
        if self.settings.symbols:
            return list(self.settings.symbols)
        if not self._symbols or time.monotonic() - self._universe_updated_at >= 3600:
            discovered = self.broker.discover_symbols(
                self.settings.universe_limit,
                self.settings.minimum_24h_quote_volume,
            )
            if not discovered:
                raise RuntimeError("Likidite filtresine uyan Binance Futures paritesi bulunamadı")
            self._symbols = discovered
            self._universe_updated_at = time.monotonic()
            self.store.append_event({"type": "universe", "symbols": discovered})
        return list(self._symbols)

    @staticmethod
    def _interval_ms(interval: str) -> int:
        unit = interval[-1]
        amount = int(interval[:-1])
        factors = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
        if unit not in factors:
            raise ValueError(f"Desteklenmeyen mum aralığı: {interval}")
        return amount * factors[unit]

    def _with_liquidity(self, signal: Signal, notional: float) -> Signal:
        try:
            result = assess_order_book(self.broker.get_order_book(signal.symbol), signal.side, notional, signal.price, signal.atr)
        except Exception:
            result = {"ok": False, "message": "Emir defteri alınamadı; giriş engellendi", "checked_at": int(time.time() * 1000)}
        return replace(
            signal,
            side=signal.side if result["ok"] else "WAIT",
            reason=signal.reason + " · " + result["message"],
            checks={**signal.checks, "emir defteri likiditesi": result["ok"]},
            indicators={**signal.indicators, "liquidity": result},
        )

    def _execute_signal(self, signal: Signal, equity: float) -> bool:
        snapshot = self.broker.get_account_snapshot()
        current_equity = float(snapshot["equity"])
        if not math.isfinite(current_equity) or current_equity <= 0:
            return False
        if self._start_equity > 0 and self.risk.daily_limit_hit(self._start_equity, current_equity):
            self.store.write_control(paused=True)
            self.store.append_event({"type": "risk_lock", "message": "Emir öncesinde günlük zarar limiti tetiklendi"})
            return False
        equity = min(equity, current_equity)
        rules = self.broker.get_symbol_rules(signal.symbol)
        stop_distance = float(signal.indicators.get("risk_distance", signal.atr * self.settings.atr_stop_multiple))
        invalidation = signal.indicators.get("invalidation")
        if invalidation is not None:
            # Size for the worst admitted 0.5 ATR entry drift.
            stop_distance += signal.atr * .5
        if signal.side == "LONG":
            stop_price = signal.price - stop_distance
            take_profit = signal.price + stop_distance * self.settings.reward_risk_ratio
            entry_side, exit_side = "BUY", "SELL"
        else:
            stop_price = signal.price + stop_distance
            take_profit = signal.price - stop_distance * self.settings.reward_risk_ratio
            entry_side, exit_side = "SELL", "BUY"

        requested_margin = self.risk.margin_for_score(
            signal.score,
            self.settings.minimum_signal_score,
            self.settings.minimum_margin_usdt,
            self.settings.maximum_margin_usdt,
        )
        quantity = self.risk.position_quantity(
            equity,
            signal.price,
            stop_price,
            rules,
            target_margin_usdt=requested_margin,
            minimum_margin_usdt=self.settings.minimum_margin_usdt,
        )
        if quantity <= 0:
            self.store.append_event({
                "type": "skipped",
                "symbol": signal.symbol,
                "message": f"En az {self.settings.minimum_margin_usdt:g} USDT teminat mevcut risk sınırına sığmadı",
            })
            return False

        # Recheck just before the order: a scan snapshot may already have changed.
        checked = self._with_liquidity(signal, float(quantity) * signal.price)
        self._signals = deque(
            [self._signal_payload(checked) if item["symbol"] == signal.symbol else item for item in self._signals],
            maxlen=12,
        )
        if checked.side == "WAIT":
            self.store.append_event({"type": "skipped", "symbol": signal.symbol, "message": checked.indicators["liquidity"]["message"]})
            return False
        available = float(self.broker.get_account_snapshot()["available_balance"])
        # Reserve margin and entry commission for admitted price drift.
        reserved_notional = float(quantity) * (signal.price + signal.atr * .5)
        required_balance = reserved_notional / self.settings.leverage + reserved_notional * .0005
        if not math.isfinite(available) or available < required_balance:
            self.store.append_event({"type": "skipped", "symbol": signal.symbol, "message": "Boş teminat ve giriş komisyonu için bakiye yetersiz"})
            return False
        self.broker.prepare_symbol(signal.symbol, self.settings.leverage)
        stamp = str(signal.candle_close_time // 1000)[-10:]
        readable = "".join(character.lower() for character in signal.symbol if character.isascii() and character.isalnum())[:10]
        digest = hashlib.sha1(signal.symbol.encode("utf-8"), usedforsecurity=False).hexdigest()[:4]
        prefix = f"atlas-{readable}{digest}-{stamp}"
        entry = self.broker.place_market_order(signal.symbol, entry_side, quantity, f"{prefix}-e")
        fill_price = float(entry.get("avgPrice") or signal.price)
        if invalidation is not None:
            structural_distance = fill_price - float(invalidation) if signal.side == "LONG" else float(invalidation) - fill_price
            stop_distance = max(signal.atr * self.settings.atr_stop_multiple, structural_distance + signal.atr * .15)
        actual_notional = float(quantity) * fill_price
        actual_margin = actual_notional / self.settings.leverage
        stop_price = fill_price - stop_distance if signal.side == "LONG" else fill_price + stop_distance
        take_profit = fill_price + stop_distance * self.settings.reward_risk_ratio if signal.side == "LONG" else fill_price - stop_distance * self.settings.reward_risk_ratio
        rounded_stop = quantize_price(stop_price, rules.tick_size)
        rounded_take_profit = quantize_price(take_profit, rules.tick_size)
        try:
            self.broker.place_protection_order(signal.symbol, exit_side, "STOP_MARKET", rounded_stop, f"{prefix}-sl")
            self.broker.place_protection_order(signal.symbol, exit_side, "TAKE_PROFIT_MARKET", rounded_take_profit, f"{prefix}-tp")
        except Exception:
            LOGGER.exception("%s koruma emirleri kurulamadı; pozisyon kapatılıyor", signal.symbol)
            self.broker.close_position(signal.symbol, exit_side, quantity, f"{prefix}-safe")
            raise
        self.store.append_event({
            "type": "entry",
            "symbol": signal.symbol,
            "side": signal.side,
            "quantity": format(quantity, "f"),
            "entry": fill_price,
            "stop": format(rounded_stop, "f"),
            "take_profit": format(rounded_take_profit, "f"),
            "score": signal.score,
            "margin_usdt": round(actual_margin, 2),
            "notional_usdt": round(actual_notional, 2),
        })
        return True

    def _signal_payload(self, signal: Signal) -> dict[str, Any]:
        return {
            "symbol": signal.symbol,
            "signal": signal.side,
            "score": signal.score,
            "price": round(signal.price, 6),
            "reason": signal.reason,
            "indicators": signal.indicators,
            "checks": signal.checks,
            "time": datetime.fromtimestamp(signal.candle_close_time / 1000, UTC).strftime("%H:%M"),
            "timestamp": signal.candle_close_time,
            "planned_margin_usdt": round(self.risk.margin_for_score(
                signal.score,
                self.settings.minimum_signal_score,
                self.settings.minimum_margin_usdt,
                self.settings.maximum_margin_usdt,
            ), 2) if signal.side != "WAIT" else None,
        }

    def _position_payload(self, position: Position) -> dict[str, Any]:
        notional = abs(position.amount * position.mark_price)
        return {
            "symbol": position.symbol,
            "side": position.side,
            "size": abs(position.amount),
            "entry": position.entry_price,
            "mark": position.mark_price,
            "pnl": position.unrealized_pnl,
            "notional_usdt": round(notional, 2),
            "margin_usdt": round(notional / self.settings.leverage, 2),
        }
