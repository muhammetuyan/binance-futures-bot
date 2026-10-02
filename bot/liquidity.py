from __future__ import annotations

import math
import time


def assess_order_book(book: dict, side: str, notional: float, reference: float, atr: float) -> dict:
    """Conservative snapshot gate; never interprets resting orders as a forecast."""
    def rejected(message: str) -> dict:
        return {"ok": False, "message": message, "checked_at": int(time.time() * 1000)}
    try:
        if not all(math.isfinite(value) and value > 0 for value in (notional, reference, atr)):
            return rejected("İşlem fiyatı veya büyüklüğü geçersiz")
        now = int(time.time() * 1000)
        age = now - int(book["T"])
        if age > 10_000 or age < -5_000:
            return rejected("Emir defteri güncel değil")
        bids = [(float(p), float(q)) for p, q in book["bids"]]
        asks = [(float(p), float(q)) for p, q in book["asks"]]
        if not bids or not asks or not all(math.isfinite(p) and math.isfinite(q) and p > 0 and q > 0 for p, q in bids + asks):
            return rejected("Emir defteri boş veya geçersiz")
        if bids != sorted(bids, reverse=True) or asks != sorted(asks):
            return rejected("Emir defteri sıralaması geçersiz")
        bid, ask = bids[0][0], asks[0][0]
        if bid >= ask or side not in {"LONG", "SHORT"} or notional <= 0:
            return rejected("Emir defteri veya işlem yönü geçersiz")
        mid = (bid + ask) / 2
        spread = (ask - bid) / mid * 100
        bid_depth = sum(p * q for p, q in bids if p >= mid * .998)
        ask_depth = sum(p * q for p, q in asks if p <= mid * 1.002)
        remaining, units = notional, 0.0
        for p, q in asks if side == "LONG" else bids:
            used = min(remaining, p * q)
            units += used / p
            remaining -= used
            if remaining <= 1e-8:
                break
        average = notional / units if units else mid
        slippage = abs(average - (ask if side == "LONG" else bid)) / mid * 100
        reasons = []
        if spread > .08:
            reasons.append("alış-satış farkı %0,08 üzerinde")
        if min(bid_depth, ask_depth) < max(10_000, notional * 20):
            reasons.append("±%0,2 bandındaki görünür derinlik yetersiz")
        if remaining > 1e-8 or slippage > .05:
            reasons.append("tahmini fiyat kayması fazla veya defter yetersiz")
        if atr <= 0 or abs(average - reference) > atr * .5:
            reasons.append("fiyat sinyal kapanışından fazla uzaklaşmış")
        return {
            "ok": not reasons, "message": "; ".join(reasons) if reasons else "Emir defteri uygun",
            "spread_percent": round(spread, 4), "slippage_percent": round(slippage, 4),
            "bid_depth_usdt": round(bid_depth, 2), "ask_depth_usdt": round(ask_depth, 2),
            "checked_at": now, "book_time": int(book["T"]),
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return rejected("Emir defteri verisi doğrulanamadı")
