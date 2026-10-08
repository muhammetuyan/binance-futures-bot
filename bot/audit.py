"""Replay selected entries for diagnosis, not an out-of-sample profit claim.

Run: python -m bot.audit --limit 8
Only public Binance market data is read. No orders or account changes.
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .config import Settings
from .exchange.binance_futures import BinanceFuturesClient
from .models import Candle
from .review import review_trades
from .strategy import TrendMomentumStrategy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=8)
    args = parser.parse_args()
    settings = Settings.load()
    state = json.loads((settings.runtime_dir / 'paper_account.json').read_text(encoding='utf-8'))
    events = [json.loads(line) for line in (settings.runtime_dir / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    entries = [event for event in events if event.get('type') == 'entry']
    review = review_trades(state['trades'])
    samples = [trade for trade in review['trades'] if trade['review_included']][:max(1, min(args.limit, 30))]

    def inspect(trade):
        result = {'symbol': trade['symbol'], 'side': trade['side'], 'pnl': round(trade['pnl'], 2), 'closed_at': trade['closed_at']}
        matching = [event for event in entries if event['symbol'] == trade['symbol'] and event['side'] == trade['side'] and abs(float(event['entry']) - float(trade['entry'])) < max(1e-9, float(trade['entry']) * 1e-7) and datetime.fromisoformat(event['time']).timestamp() * 1000 < trade['closed_at']]
        if not matching:
            return {**result, 'error': 'Eşleşen giriş kaydı yok'}
        event = matching[-1]
        entry_time = int(datetime.fromisoformat(event['time']).timestamp() * 1000)
        close_time = int(event.get('analysis', {}).get('candle_close_time') or (entry_time // 900_000 * 900_000 - 1))
        result['entry_time'] = event['time']
        result['original_score'] = event['score']
        try:
            client = BinanceFuturesClient(settings)
            def candles(interval):
                rows = client._request('GET', '/fapi/v1/klines', {'symbol': trade['symbol'], 'interval': interval, 'endTime': close_time, 'limit': 500}, base_url=settings.market_base_url)
                return [Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]), int(r[6])) for r in rows if int(r[6]) <= close_time]
            strategy = TrendMomentumStrategy(settings.minimum_signal_score, settings.minimum_adx, settings.minimum_volume_ratio, settings.minimum_stop_percent, settings.atr_stop_multiple, (settings.long_rsi_min, settings.long_rsi_max), (settings.short_rsi_min, settings.short_rsi_max), triple_rsi=True)
            current = strategy.analyze(trade['symbol'], candles('15m'), candles('1h'))
            result.update({'new_side': current.side, 'confirmation': current.indicators['confirmation'], 'directional_counts': current.indicators['directional_counts'], 'new_reason': current.reason})
        except Exception as exc:
            result['error'] = str(exc)
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        inspected = list(pool.map(inspect, samples))
    print(json.dumps({'summary': {key: value for key, value in review.items() if key != 'trades'},
                      'samples': inspected, 'warning': 'Güncel kurallarla giriş anı yeniden analizi; eski stratejinin birebir yeniden üretimi veya bağımsız performans testi değildir.'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
