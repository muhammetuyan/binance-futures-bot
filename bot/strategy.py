from __future__ import annotations

from .indicators import adx, atr, ema, rolling_mean, rsi
from .models import Candle, Signal
from .structure import analyze_structure


class TrendMomentumStrategy:
    """Yön başına analiz oylaması; hesap ve emir güvenliği motor katmanındadır."""

    def __init__(
        self,
        minimum_score: int = 70,
        minimum_adx: float = 0.0,
        minimum_volume_ratio: float = 0.0,
        minimum_stop_percent: float = 0.0,
        atr_stop_multiple: float = 1.8,
        long_rsi_range: tuple[float, float] = (0.0, 100.0),
        short_rsi_range: tuple[float, float] = (0.0, 100.0),
        triple_rsi: bool = False,
        minimum_confirmations: int = 4,
        quality_guard: bool = True,
    ) -> None:
        self.minimum_score = minimum_score  # Teminat puanının tabanı; giriş vetosu değil.
        if not 1 <= minimum_confirmations <= 9:
            raise ValueError('Onay eşiği 1-9 arasında olmalı')
        self.minimum_confirmations = minimum_confirmations
        self.minimum_adx = minimum_adx
        self.minimum_volume_ratio = minimum_volume_ratio
        self.minimum_stop_percent = minimum_stop_percent
        self.atr_stop_multiple = atr_stop_multiple
        self.long_rsi_range = long_rsi_range
        self.short_rsi_range = short_rsi_range
        self.triple_rsi = triple_rsi
        self.quality_guard = quality_guard

    @staticmethod
    def choose_direction(checks: dict[str, dict[str, bool]], minimum: int = 4) -> tuple[str, dict[str, int]]:
        counts = {side: sum(bool(value) for value in items.values()) for side, items in checks.items()}
        if counts["LONG"] == counts["SHORT"] or max(counts.values()) < minimum:
            return "WAIT", counts
        return ("LONG" if counts["LONG"] > counts["SHORT"] else "SHORT"), counts

    @staticmethod
    def rsi_confirmation(values: tuple[float, float, float], previous_fast: float) -> tuple[bool, bool]:
        """Two periods agree; fast momentum must not reverse or be exhausted."""
        fast, medium, slow = values
        long_ok = sum(value > 50 for value in values) >= 2 and fast >= previous_fast and fast < 85
        short_ok = sum(value < 50 for value in values) >= 2 and fast <= previous_fast and fast > 15
        return long_ok, short_ok

    def analyze(
        self,
        symbol: str,
        candles: list[Candle],
        confirmation_candles: list[Candle] | None = None,
    ) -> Signal:
        if len(candles) < 220:
            raise ValueError("Strateji için en az 220 kapanmış mum gerekli")
        closes = [candle.close for candle in candles]
        volumes = [candle.volume for candle in candles]
        fast = ema(closes, 20)
        slow = ema(closes, 50)
        regime = ema(closes, 200)
        rsi_values = rsi(closes, 14)
        rsi_fast = rsi(closes, 7)
        rsi_slow = rsi(closes, 21)
        rsi_long, rsi_short = self.rsi_confirmation(
            (rsi_fast[-1], rsi_values[-1], rsi_slow[-1]), rsi_fast[-2]
        )
        atr_values = atr(candles, 14)
        adx_values = adx(candles, 14)
        volume_average = rolling_mean(volumes, 20)

        close = closes[-1]
        current_rsi = rsi_values[-1]
        current_adx = adx_values[-1]
        current_atr = atr_values[-1]
        volume_ratio = volumes[-1] / volume_average[-1] if volume_average[-1] > 0 else 0.0
        volume_ok = volume_ratio >= self.minimum_volume_ratio
        structure = analyze_structure(candles, current_atr)
        momentum_up = fast[-1] > fast[-2]
        momentum_down = fast[-1] < fast[-2]
        stop_percent = current_atr * self.atr_stop_multiple / close * 100.0 if close > 0 else 0.0

        higher_long = False
        higher_short = False
        higher_label = "kapalı"
        higher_rsi: dict[str, float] = {}
        if confirmation_candles is not None:
            if len(confirmation_candles) < 220:
                raise ValueError("Üst zaman onayı için en az 220 kapanmış mum gerekli")
            higher_closes = [candle.close for candle in confirmation_candles]
            higher_rsi = {str(period): round(rsi(higher_closes, period)[-1], 2) for period in (7, 14, 21)}
            higher_fast = ema(higher_closes, 20)[-1]
            higher_slow = ema(higher_closes, 50)[-1]
            higher_regime = ema(higher_closes, 200)[-1]
            higher_long = higher_fast > higher_slow > higher_regime
            higher_short = higher_fast < higher_slow < higher_regime
            higher_label = "yukarı" if higher_long else "aşağı" if higher_short else "karışık"

        directional_checks = {}
        for side in ("LONG", "SHORT"):
            bullish = side == "LONG"
            info = structure[side]
            rsi_band = self.long_rsi_range if bullish else self.short_rsi_range
            rsi_ok = rsi_band[0] <= current_rsi <= rsi_band[1]
            rsi_ok = rsi_ok and (not self.triple_rsi or (rsi_long if bullish else rsi_short))
            directional_checks[side] = {
                "15 dk yön ve momentum": close > fast[-1] and momentum_up if bullish else close < fast[-1] and momentum_down,
                "1 saat trend": higher_long if bullish else higher_short,
                "RSI 7 / 14 / 21 onayı": rsi_ok,
                "MSS kapanış onayı": bool(info["mss"]),
                "likidite süpürmesi": bool(info.get("sweep", False)),
                "FVG dönüş tepkisi": bool(info.get("fvg_rejection", False)),
                "trend gücü (ADX)": current_adx >= self.minimum_adx,
                "hacim": volume_ok,
                "oynaklık": stop_percent >= self.minimum_stop_percent,
            }
        best_side, counts = self.choose_direction(directional_checks, self.minimum_confirmations)
        quality_reason = ""
        direction_counts = {side: sum(value for name, value in items.items() if name not in {"trend gücü (ADX)", "hacim", "oynaklık"}) for side, items in directional_checks.items()}
        if self.quality_guard and best_side != "WAIT":
            opposite = "SHORT" if best_side == "LONG" else "LONG"
            if direction_counts[best_side] < 2:
                quality_reason = "Yön desteği zayıf: en az iki yönlü analiz gerekli"
            elif counts[best_side] - counts[opposite] < 2:
                quality_reason = "LONG/SHORT çelişkisi: en az iki onay farkı gerekli"
            # Countertrend entries remain possible, but require a genuine reversal.
            elif directional_checks[opposite]["1 saat trend"] and not directional_checks[best_side]["MSS kapanış onayı"]:
                quality_reason = "1 saat trendine karşı giriş için MSS dönüş kapanışı gerekli"
            if quality_reason:
                best_side = "WAIT"
        inspecting_side = best_side if best_side != "WAIT" else ("LONG" if counts["LONG"] >= counts["SHORT"] else "SHORT")
        checks = directional_checks[inspecting_side]
        confirmed = counts[inspecting_side]
        total = len(checks)
        # Four approvals start at the sizing baseline; further approvals increase margin.
        if confirmed >= self.minimum_confirmations:
            best_score = round(self.minimum_score + (100 - self.minimum_score) * (confirmed - self.minimum_confirmations) / max(1, total - self.minimum_confirmations))
        else:
            best_score = round(self.minimum_score * confirmed / self.minimum_confirmations)
        if quality_reason:
            decision_reason = quality_reason
        elif current_atr <= 0 or close <= 0:
            best_side = "WAIT"
            decision_reason = "Geçerli fiyat ve stop mesafesi yok"
        elif counts["LONG"] == counts["SHORT"]:
            decision_reason = f"Yönler eşit: LONG {counts['LONG']}/{total}, SHORT {counts['SHORT']}/{total}"
        elif confirmed < self.minimum_confirmations:
            decision_reason = f"{inspecting_side} {confirmed}/{total} onay; en az {self.minimum_confirmations} gerekli"
        else:
            decision_reason = f"{best_side} {confirmed}/{total} onay; analiz eşiği sağlandı"
        directional = structure[inspecting_side]
        invalidation = directional["invalidation"]
        risk_distance = max(current_atr * self.atr_stop_multiple, abs(close - invalidation) + current_atr * .15) if invalidation is not None else current_atr * self.atr_stop_multiple

        reason = (
            f"{decision_reason} · "
            f"EMA20/50/200 {'yukarı' if fast[-1] > slow[-1] > regime[-1] else 'aşağı' if fast[-1] < slow[-1] < regime[-1] else 'karışık'} · "
            f"ADX {current_adx:.1f} · RSI 7/14/21 {rsi_fast[-1]:.1f}/{current_rsi:.1f}/{rsi_slow[-1]:.1f} · "
            f"1s trend {higher_label} · "
            f"yapı {directional['setup']} · MSS {'var' if directional['mss'] else 'yok'} · "
            f"hacim {'uygun' if volume_ok else 'zayıf'}"
        )
        return Signal(
            symbol=symbol,
            side=best_side,
            score=best_score,
            price=close,
            atr=current_atr,
            reason=reason,
            candle_close_time=candles[-1].close_time,
            indicators={
                "confirmation": {"minimum": self.minimum_confirmations, "total": total, "long": counts["LONG"], "short": counts["SHORT"], "inspected_side": inspecting_side, "eligible": best_side != "WAIT", "reason": decision_reason},
                "directional_checks": directional_checks,
                "directional_counts": direction_counts,
                "strategy_version": "DIRECTION_QUALITY_V2",
                "structure": structure,
                "invalidation": invalidation,
                "risk_distance": risk_distance,
                "rsi": {"7": round(rsi_fast[-1], 2), "14": round(current_rsi, 2), "21": round(rsi_slow[-1], 2)},
                "higher_rsi": higher_rsi,
                "rsi_bias": "LONG" if rsi_long else "SHORT" if rsi_short else "WAIT",
                "adx": round(current_adx, 2),
                "volume_ratio": round(volume_ratio, 2),
                "stop_percent": round(risk_distance / close * 100, 2) if close > 0 else 0,
                "triple_rsi_enabled": self.triple_rsi,
            },
            checks=checks,
        )
