export type LiveCandle = {
  time: number; close_time: number; open: number; high: number; low: number; close: number;
  closed: boolean; updatedAt: number;
};

function valid(c: LiveCandle) {
  return [c.time, c.close_time, c.updatedAt].every(Number.isFinite) && c.time >= 0 && c.close_time > c.time
    && [c.open, c.high, c.low, c.close].every(v => Number.isFinite(v) && v > 0)
    && c.high >= Math.max(c.open, c.close, c.low) && c.low <= Math.min(c.open, c.close);
}

export function parseKline(raw: unknown, symbol: string, interval: string): LiveCandle | null {
  if (!raw || typeof raw !== 'object') return null;
  const event = raw as Record<string, unknown>;
  if (event.e !== 'kline' || event.s !== symbol || !event.k || typeof event.k !== 'object') return null;
  const k = event.k as Record<string, unknown>;
  if (k.s !== symbol || k.i !== interval || typeof k.x !== 'boolean') return null;
  const candle = { time: Number(k.t), close_time: Number(k.T), open: Number(k.o), high: Number(k.h), low: Number(k.l), close: Number(k.c), closed: k.x, updatedAt: Number(event.E) };
  return valid(candle) ? candle : null;
}

export function parseHistory(raw: unknown, requestedAt: number): LiveCandle[] {
  if (!Array.isArray(raw)) return [];
  return raw.filter(Array.isArray).map(row => ({
    time: Number(row[0]), close_time: Number(row[6]), open: Number(row[1]),
    high: Number(row[2]), low: Number(row[3]), close: Number(row[4]),
    closed: Number(row[6]) < requestedAt, updatedAt: requestedAt,
  })).filter(valid);
}

export function mergeCandles(previous: LiveCandle[], updates: LiveCandle[], limit = 60): LiveCandle[] {
  const byTime = new Map(previous.map(c => [c.time, c]));
  for (const c of updates) {
    if (!valid(c)) continue;
    const old = byTime.get(c.time);
    if (old && ((old.closed && !c.closed) || old.updatedAt > c.updatedAt)) continue;
    byTime.set(c.time, c);
  }
  return [...byTime.values()].sort((a, b) => a.time - b.time).slice(-limit);
}

export function liveEventIsFresh(eventTime: number, now: number) {
  return Number.isFinite(eventTime) && now - eventTime <= 15000 && eventTime - now <= 5000;
}
