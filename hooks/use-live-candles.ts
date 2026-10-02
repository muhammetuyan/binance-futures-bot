'use client';

import { useEffect, useState } from 'react';
import { liveEventIsFresh, mergeCandles, parseHistory, parseKline, type LiveCandle } from '@/lib/live-candles';

type Feed = { key: string; candles: LiveCandle[]; phase: 'connecting' | 'live' | 'reconnecting'; receivedAt: number; eventTime: number; historyOk: boolean };

export function useLiveCandles(symbol?: string, interval?: string) {
  const key = `${symbol ?? ''}:${interval ?? ''}`;
  const [feed, setFeed] = useState<Feed>({ key: '', candles: [], phase: 'connecting', receivedAt: 0, eventTime: 0, historyOk: false });
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!symbol || !interval || !['15m', '1h'].includes(interval)) return;
    let stopped = false, generation = 0, retries = 0, lastReceived = Date.now();
    let socket: WebSocket | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let request: AbortController | undefined;
    let requestTimeout: ReturnType<typeof setTimeout> | undefined;
    const state: Feed = { key, candles: [], phase: 'connecting', receivedAt: 0, eventTime: 0, historyOk: false };
    setFeed(state);
    setNow(Date.now());
    function publish() { if (!stopped) setFeed({ ...state, candles: [...state.candles] }); }
    function reconnect() {
      if (stopped || retry) return;
      generation++;
      request?.abort();
      clearTimeout(requestTimeout);
      if (socket) { socket.onclose = null; socket.onerror = null; socket.onmessage = null; socket.close(); }
      state.phase = 'reconnecting'; publish();
      retry = setTimeout(() => { retry = undefined; connect(); }, Math.min(15000, 1000 * 2 ** Math.min(retries++, 4)));
    }
    function connect() {
      if (stopped) return;
      const current = ++generation;
      lastReceived = Date.now();
      request = new AbortController();
      const requestedAt = Date.now();
      requestTimeout = setTimeout(() => request?.abort(), 10000);
      // Fill gaps on first connection and reconnect, without sending data to the bot.
      void fetch(`https://fapi.binance.com/fapi/v1/klines?symbol=${encodeURIComponent(symbol!)}&interval=${interval}&limit=60`, { signal: request.signal, credentials: 'omit', cache: 'no-store' })
        .then(response => { if (!response.ok) throw new Error('history unavailable'); return response.json(); })
        .then(raw => {
          if (stopped || current !== generation) return;
          const history = parseHistory(raw, requestedAt);
          state.candles = mergeCandles(state.candles, history);
          state.historyOk = history.length > 1;
          publish();
        })
        .catch(() => { if (!stopped && current === generation) { state.historyOk = false; publish(); } })
        .finally(() => { if (current === generation) clearTimeout(requestTimeout); });
      try {
        socket = new WebSocket(`wss://fstream.binance.com/market/ws/${encodeURIComponent(symbol!.toLowerCase())}@kline_${interval}`);
        socket.onmessage = message => {
          if (stopped || current !== generation) return;
          try {
            const candle = parseKline(JSON.parse(String(message.data)), symbol!, interval!);
            if (!candle || !liveEventIsFresh(candle.updatedAt, Date.now()) || candle.updatedAt < state.eventTime) return;
            state.candles = mergeCandles(state.candles, [candle]);
            state.eventTime = candle.updatedAt; state.receivedAt = Date.now();
            lastReceived = state.receivedAt; retries = 0;
            state.phase = 'live'; publish();
          } catch { /* Ignore malformed messages; watchdog detects a stalled feed. */ }
        };
        socket.onclose = reconnect;
        socket.onerror = reconnect;
      } catch { reconnect(); }
    }
    connect();
    const watchdog = setInterval(() => {
      setNow(Date.now());
      if (Date.now() - lastReceived > 15000) reconnect();
    }, 1000);
    return () => {
      stopped = true; generation++;
      clearInterval(watchdog); clearTimeout(retry); clearTimeout(requestTimeout);
      request?.abort();
      if (socket) { socket.onclose = null; socket.onerror = null; socket.onmessage = null; socket.close(); }
    };
  }, [key, symbol, interval]);
  const selected = feed.key === key ? feed : { key, candles: [], phase: 'connecting' as const, receivedAt: 0, eventTime: 0, historyOk: false };
  return { ...selected, live: selected.phase === 'live' && liveEventIsFresh(selected.eventTime, now || Date.now()) && (now || Date.now()) - selected.receivedAt < 15000 };
}
