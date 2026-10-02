"""Closed-candle heuristics, not observations of hidden stops or liquidations."""
from __future__ import annotations

from .models import Candle


def pivots(candles: list[Candle], end: int) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Two candles on each side; all confirmation candles precede `end`."""
    highs, lows = [], []
    for i in range(max(2, end - 80), end - 2):
        neighbors = candles[i - 2:i] + candles[i + 1:i + 3]
        if all(candles[i].high > c.high for c in neighbors):
            highs.append((i, candles[i].high))
        if all(candles[i].low < c.low for c in neighbors):
            lows.append((i, candles[i].low))
    return highs, lows


def analyze_structure(candles: list[Candle], volatility: float) -> dict:
    """Sweep -> MSS, or a recent MSS plus rejection of an unfilled FVG."""
    last = len(candles) - 1
    result = {}
    for side in ("LONG", "SHORT"):
        bullish = side == "LONG"
        sweeps, shifts = [], []
        for i in range(max(5, last - 9), last + 1):
            c = candles[i]
            highs, lows = pivots(candles, i)
            levels = lows if bullish else highs
            if levels:
                level = levels[-1][1]
                swept = (c.low < level - volatility * .05 and c.close > level and c.close > c.open) if bullish else (c.high > level + volatility * .05 and c.close < level and c.close < c.open)
                if swept:
                    sweeps.append(i)
            # MSS requires a prior lower-high (bullish) / higher-low (bearish),
            # a CLOSE through it, and a displacement body, not just a wick.
            opposing = highs if bullish else lows
            if len(opposing) >= 2 and i >= last - 3:
                old, level = opposing[-2][1], opposing[-1][1]
                prior_structure = level < old if bullish else level > old
                crossed = (candles[i - 1].close <= level < c.close) if bullish else (candles[i - 1].close >= level > c.close)
                displacement = (c.close - c.open if bullish else c.open - c.close) >= volatility * .5
                if prior_structure and crossed and displacement:
                    shifts.append((i, level))
        shift = shifts[-1] if shifts else None
        mss = bool(shift and (candles[-1].close > shift[1] if bullish else candles[-1].close < shift[1]))
        eligible_sweeps = [i for i in sweeps if shift and shift[0] - 6 <= i <= shift[0]]
        sweep_index = eligible_sweeps[-1] if eligible_sweeps else None
        sweep_extreme = (min(c.low for c in candles[sweep_index:]) if bullish else max(c.high for c in candles[sweep_index:])) if sweep_index is not None else None
        zone = None
        retest = False
        rejection = False
        for i in range(max(2, last - 40), last):
            a, middle, b = candles[i - 2:i + 1]
            lower, upper = (a.high, b.low) if bullish else (b.high, a.low)
            body = middle.close - middle.open if bullish else middle.open - middle.close
            if upper - lower < volatility * .1 or body < volatility * .5:
                continue
            # A fully filled zone is not reused, including wick fills.
            invalidated = any(c.low <= lower if bullish else c.high >= upper for c in candles[i + 1:last])
            current = candles[-1]
            invalidated = invalidated or (current.low <= lower if bullish else current.high >= upper)
            if invalidated:
                continue
            zone = {"lower": lower, "upper": upper, "formed_at": b.close_time}
            rejection = (current.low <= upper and current.close > upper and current.close > current.open) if bullish else (current.high >= lower and current.close < lower and current.close < current.open)
            retest = bool(rejection and shift and i >= shift[0] - 2)
            if rejection:
                break
        setup = "SWEEP_MSS" if mss and sweep_index is not None else "FVG_MSS" if mss and retest else "WAIT"
        invalidation = sweep_extreme if setup == "SWEEP_MSS" else (zone["lower"] if bullish else zone["upper"]) if setup == "FVG_MSS" else None
        result[side] = {
            "sweep": sweep_index is not None or bool(sweeps and sweeps[-1] >= last - 6),
            "mss": mss,
            "mss_level": shift[1] if shift else None,
            "fvg": zone,
            "fvg_retest": retest,
            "fvg_rejection": bool(zone and rejection),
            "setup": setup,
            "invalidation": invalidation,
        }
    return result
