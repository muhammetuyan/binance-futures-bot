from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass

from .config import Settings
from .exchange.binance_futures import BinanceFuturesClient
from .models import Candle
from .strategy import TrendMomentumStrategy


@dataclass(slots=True)
class BacktestResult:
    symbol: str
    days: int
    trades: int
    wins: int
    losses: int
    win_rate: float
    net_r: float
    max_drawdown_r: float
    net_return_percent: float
    max_drawdown_percent: float
    profit_factor: float


def evaluate_candles(
    symbol: str,
    days: int,
    candles: list[Candle],
    settings: Settings,
    confirmation_candles: list[Candle] | None = None,
) -> BacktestResult:
    """Tek pozisyonlu, sonraki mumdan girişli ve maliyet dahil ihtiyatlı simülasyon."""
    strategy = TrendMomentumStrategy(
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
    trades: list[float] = []
    index = 220
    maximum_holding_candles = 96
    taker_fee_rate = 0.0005
    slippage_rate = 0.0002

    while index < len(candles) - 1:
        confirmation_window = None
        if confirmation_candles is not None:
            confirmation_window = [
                candle
                for candle in confirmation_candles
                if candle.close_time <= candles[index].close_time
            ]
            if len(confirmation_window) < 220:
                index += 1
                continue
        signal = strategy.analyze(symbol, candles[: index + 1], confirmation_window)
        if signal.side == "WAIT":
            index += 1
            continue

        entry_index = index + 1
        entry = candles[entry_index].open
        risk_distance = float(signal.indicators.get("risk_distance", signal.atr * settings.atr_stop_multiple))
        invalidation = signal.indicators.get("invalidation")
        if invalidation is not None:
            structural_distance = entry - float(invalidation) if signal.side == "LONG" else float(invalidation) - entry
            risk_distance = max(signal.atr * settings.atr_stop_multiple, structural_distance + signal.atr * .15)
        if entry <= 0 or risk_distance <= 0:
            index += 1
            continue
        stop = entry - risk_distance if signal.side == "LONG" else entry + risk_distance
        take = (
            entry + risk_distance * settings.reward_risk_ratio
            if signal.side == "LONG"
            else entry - risk_distance * settings.reward_risk_ratio
        )
        exit_index = min(entry_index + maximum_holding_candles, len(candles) - 1)
        gross_r: float | None = None
        for future_index in range(entry_index, exit_index + 1):
            future = candles[future_index]
            stop_hit = future.low <= stop if signal.side == "LONG" else future.high >= stop
            take_hit = future.high >= take if signal.side == "LONG" else future.low <= take
            if stop_hit:
                # Mum içinde ikisi de görülürse zaman sırası bilinemez; zarar varsayılır.
                gross_r = -1.0
                exit_index = future_index
                break
            if take_hit:
                gross_r = settings.reward_risk_ratio
                exit_index = future_index
                break

        if gross_r is None:
            exit_price = candles[exit_index].close
            gross_r = (
                (exit_price - entry) / risk_distance
                if signal.side == "LONG"
                else (entry - exit_price) / risk_distance
            )

        round_trip_cost = entry * (2 * taker_fee_rate + 2 * slippage_rate)
        trades.append(gross_r - round_trip_cost / risk_distance)
        index = exit_index + 1

    wins = sum(1 for value in trades if value > 0)
    equity_r = 0.0
    peak_r = 0.0
    max_drawdown_r = 0.0
    for value in trades:
        equity_r += value
        peak_r = max(peak_r, equity_r)
        max_drawdown_r = max(max_drawdown_r, peak_r - equity_r)
    equity = 1.0
    peak = 1.0
    maximum_drawdown = 0.0
    for value in trades:
        equity *= max(0.0, 1.0 + value * settings.risk_per_trade)
        peak = max(peak, equity)
        maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak if peak else 0.0)
    gross_profit = sum(value for value in trades if value > 0)
    gross_loss = abs(sum(value for value in trades if value < 0))
    return BacktestResult(
        symbol=symbol,
        days=days,
        trades=len(trades),
        wins=wins,
        losses=len(trades) - wins,
        win_rate=round((wins / len(trades) * 100.0) if trades else 0.0, 2),
        net_r=round(sum(trades), 2),
        max_drawdown_r=round(max_drawdown_r, 2),
        net_return_percent=round((equity - 1.0) * 100.0, 2),
        max_drawdown_percent=round(maximum_drawdown * 100.0, 2),
        profit_factor=round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
    )


def run_backtest(symbol: str, days: int, settings: Settings) -> BacktestResult:
    client = BinanceFuturesClient(settings)
    start = int((time.time() - days * 86400) * 1000)
    candles = client.get_historical_candles(symbol, settings.interval, start)
    confirmation_candles = client.get_historical_candles(
        symbol,
        settings.confirmation_interval,
        start,
    )
    return evaluate_candles(symbol, days, candles, settings, confirmation_candles)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atlas Trade geçmiş veri testi")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    result = run_backtest(args.symbol.upper(), args.days, Settings.load())
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
