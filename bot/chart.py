from __future__ import annotations

from .models import Candle, Signal


def build_signal_chart(signal: Signal, candles: list[Candle], interval: str, reward_risk: float) -> dict:
    """Chart and annotations share the exact closed-candle analysis snapshot."""
    closed = [c for c in candles if c.close_time <= signal.candle_close_time][-60:]
    structure = signal.indicators.get("structure", {})
    zones, levels = [], []
    for side in ("LONG", "SHORT"):
        info = structure.get(side, {})
        color = "#34d399" if side == "LONG" else "#fb7185"
        zone = info.get("fvg")
        if zone:
            zones.append({**zone, "label": f"{side} FVG", "color": color})
        if info.get("mss_level") is not None:
            levels.append({"label": f"{side} MSS" + ("" if info.get("mss") else " (izlenen)"), "price": info["mss_level"], "color": "#a78bfa", "kind": "structure"})
    confirmation = signal.indicators.get("confirmation", {})
    planned_side = signal.side if signal.side in {"LONG", "SHORT"} else confirmation.get("inspected_side") if confirmation.get("eligible") else None
    levels.append({"label": "Taslak giriş" if planned_side else "Analiz fiyatı", "price": signal.price, "color": "#fbbf24", "kind": "entry"})
    distance = float(signal.indicators.get("risk_distance", 0))
    if planned_side and distance > 0:
        direction = 1 if planned_side == "LONG" else -1
        levels.extend([
            {"label": "Taslak stop", "price": signal.price - direction * distance, "color": "#fb7185", "kind": "stop"},
            {"label": "Taslak hedef", "price": signal.price + direction * distance * reward_risk, "color": "#34d399", "kind": "target"},
        ])
    return {
        "interval": interval, "as_of": signal.candle_close_time, "planned_side": planned_side,
        "candles": [{"time": c.open_time, "close_time": c.close_time, "open": c.open, "high": c.high, "low": c.low, "close": c.close} for c in closed],
        "zones": zones, "levels": levels,
    }
