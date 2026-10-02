from __future__ import annotations

from collections.abc import Sequence

from .models import Candle


def ema(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or not values:
        raise ValueError("EMA periyodu pozitif ve veri boş olmamalı")
    alpha = 2.0 / (period + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def rsi(values: Sequence[float], period: int = 14) -> list[float]:
    if len(values) < 2:
        return [50.0] * len(values)
    gains = [0.0]
    losses = [0.0]
    for previous, current in zip(values, values[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = ema(gains, period)
    avg_loss = ema(losses, period)
    output: list[float] = []
    for gain, loss in zip(avg_gain, avg_loss):
        if loss == 0:
            output.append(100.0 if gain > 0 else 50.0)
        else:
            relative_strength = gain / loss
            output.append(100.0 - (100.0 / (1.0 + relative_strength)))
    return output


def true_ranges(candles: Sequence[Candle]) -> list[float]:
    if not candles:
        return []
    ranges = [candles[0].high - candles[0].low]
    for previous, current in zip(candles, candles[1:]):
        ranges.append(max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        ))
    return ranges


def atr(candles: Sequence[Candle], period: int = 14) -> list[float]:
    return ema(true_ranges(candles), period) if candles else []


def adx(candles: Sequence[Candle], period: int = 14) -> list[float]:
    if len(candles) < 2:
        return [0.0] * len(candles)
    plus_dm = [0.0]
    minus_dm = [0.0]
    for previous, current in zip(candles, candles[1:]):
        up = current.high - previous.high
        down = previous.low - current.low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr_values = atr(candles, period)
    plus_smoothed = ema(plus_dm, period)
    minus_smoothed = ema(minus_dm, period)
    dx: list[float] = []
    for plus, minus, range_value in zip(plus_smoothed, minus_smoothed, atr_values):
        if range_value <= 0:
            dx.append(0.0)
            continue
        plus_di = 100.0 * plus / range_value
        minus_di = 100.0 * minus / range_value
        total = plus_di + minus_di
        dx.append(0.0 if total == 0 else 100.0 * abs(plus_di - minus_di) / total)
    return ema(dx, period)


def rolling_mean(values: Sequence[float], period: int) -> list[float]:
    result: list[float] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        divisor = min(index + 1, period)
        result.append(running / divisor)
    return result
