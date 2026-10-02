from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


Side = Literal["LONG", "SHORT", "WAIT"]


@dataclass(frozen=True, slots=True)
class Candle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int


@dataclass(frozen=True, slots=True)
class Signal:
    symbol: str
    side: Side
    score: int
    price: float
    atr: float
    reason: str
    candle_close_time: int
    indicators: dict[str, object] = field(default_factory=dict)
    checks: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SymbolRules:
    symbol: str
    tick_size: Decimal
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    amount: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float

    @property
    def side(self) -> str:
        return "LONG" if self.amount > 0 else "SHORT"
