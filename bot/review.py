"""Conservative trade review: operational exits are not strategy evidence."""
from __future__ import annotations

from typing import Any


def review_trades(trades: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted((dict(t) for t in trades), key=lambda t: t["closed_at"])
    clusters: list[list[dict[str, Any]]] = []
    for trade in ordered:
        if not clusters or trade["closed_at"] - clusters[-1][0]["closed_at"] > 10_000:
            clusters.append([])
        clusters[-1].append(trade)
    for cluster in clusters:
        legacy_batch = len(cluster) >= 3 and all(not t.get("execution_version") for t in cluster)
        for trade in cluster:
            if trade["reason"] not in {"STOP", "TAKE_PROFIT"}:
                trade["review_note"] = "Operasyonel/güvenli kapama; strateji örneği değil"
            elif legacy_batch:
                trade["review_note"] = "Eski toplu kapanış; kapalı dönem veya veri sırası belirsiz"
            elif trade.get("ambiguous_bar"):
                trade["review_note"] = "Aynı mumda stop ve hedef; sıra belirsiz"
            else:
                trade["review_note"] = "Değerlendirmeye dahil"
            trade["review_included"] = trade["review_note"] == "Değerlendirmeye dahil"
    selected = [t for t in ordered if t["review_included"]]
    def stats(items):
        wins = sum(t["pnl"] > 0 for t in items)
        gain = sum(max(t["pnl"], 0) for t in items)
        loss = sum(max(-t["pnl"], 0) for t in items)
        return {"count": len(items), "wins": wins, "losses": len(items) - wins,
                "net_pnl": round(sum(t["pnl"] for t in items), 2),
                "win_rate": round(wins / len(items) * 100, 1) if items else 0,
                "profit_factor": round(gain / loss, 2) if loss else None}
    return {"all": stats(ordered), "strategy": stats(selected), "excluded_count": len(ordered) - len(selected),
            "trades": list(reversed(ordered)),
            "note": "Toplu kapanışlar kesin manuel kabul edilmez; belirsiz oldukları için ayrı tutulur. Eski girişlerde tam analiz kaydı yok; sonuçlar kâr garantisi değildir."}
