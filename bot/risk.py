from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP

from .models import SymbolRules


class RiskManager:
    def __init__(
        self,
        risk_per_trade: float,
        daily_loss_limit: float,
        max_margin_fraction: float,
        leverage: int,
    ) -> None:
        self.risk_per_trade = risk_per_trade
        self.daily_loss_limit = daily_loss_limit
        self.max_margin_fraction = max_margin_fraction
        self.leverage = leverage

    def daily_limit_hit(self, start_equity: float, current_equity: float) -> bool:
        if start_equity <= 0:
            return True
        return current_equity <= start_equity * (1.0 - self.daily_loss_limit)

    @staticmethod
    def margin_for_score(
        score: int,
        minimum_score: int,
        minimum_margin_usdt: float,
        maximum_margin_usdt: float,
    ) -> float:
        if maximum_margin_usdt <= minimum_margin_usdt or minimum_score >= 100:
            return minimum_margin_usdt
        quality = min(1.0, max(0.0, (score - minimum_score) / (100 - minimum_score)))
        return minimum_margin_usdt + quality * (maximum_margin_usdt - minimum_margin_usdt)

    def position_quantity(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        rules: SymbolRules,
        target_margin_usdt: float | None = None,
        minimum_margin_usdt: float = 0.0,
    ) -> Decimal:
        if equity <= 0 or entry_price <= 0:
            return Decimal("0")
        stop_distance = abs(entry_price - stop_price)
        if stop_distance <= 0:
            return Decimal("0")
        risk_quantity = Decimal(str(equity * self.risk_per_trade / stop_distance))
        max_notional = equity * self.max_margin_fraction * self.leverage
        margin_quantity = Decimal(str(max_notional / entry_price))
        quality_quantity = (
            Decimal(str(target_margin_usdt * self.leverage / entry_price))
            if target_margin_usdt is not None
            else rules.max_quantity
        )
        raw_quantity = min(risk_quantity, margin_quantity, quality_quantity, rules.max_quantity)
        quantity = quantize_down(raw_quantity, rules.step_size)
        minimum_notional = max(
            rules.min_notional,
            Decimal(str(minimum_margin_usdt * self.leverage)),
        )
        if quantity * Decimal(str(entry_price)) < minimum_notional:
            rounded_up = quantize_up(minimum_notional / Decimal(str(entry_price)), rules.step_size)
            if rounded_up <= min(risk_quantity, margin_quantity, rules.max_quantity):
                quantity = rounded_up
        if quantity < rules.min_quantity:
            return Decimal("0")
        if quantity * Decimal(str(entry_price)) < minimum_notional:
            return Decimal("0")
        return quantity


def quantize_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def quantize_up(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def quantize_price(value: float, tick: Decimal) -> Decimal:
    decimal_value = Decimal(str(value))
    if tick <= 0:
        return decimal_value
    return (decimal_value / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick
