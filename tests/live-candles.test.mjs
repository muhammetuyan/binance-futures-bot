import assert from 'node:assert/strict';
import test from 'node:test';
import { parseKline, parseHistory, mergeCandles, liveEventIsFresh } from '../lib/live-candles.ts';

const event = (changes = {}) => ({
  e: 'kline', E: 2000, s: 'BTCUSDT',
  k: { s: 'BTCUSDT', i: '15m', t: 0, T: 899999, o: '100', h: '105', l: '98', c: '102', x: false, ...changes },
});
test('accepts the current unfinished Binance candle', () => {
  const c = parseKline(event(), 'BTCUSDT', '15m');
  assert.equal(c.close, 102);
  assert.equal(c.closed, false);
});
test('rejects wrong symbols, intervals and malformed prices', () => {
  for (const raw of [null, {}, event({ s: 'ETHUSDT' }), event({ i: '1h' }), event({ c: 'NaN' }), event({ h: '99' }), event({ x: 'false' })]) {
    assert.equal(parseKline(raw, 'BTCUSDT', '15m'), null);
  }
});
test('updates the same candle without duplicates and ignores older events', () => {
  const first = parseKline(event(), 'BTCUSDT', '15m');
  const next = { ...first, close: 104, updatedAt: 3000 };
  let series = mergeCandles([first], [next]);
  assert.equal(series.length, 1);
  assert.equal(series[0].close, 104);
  series = mergeCandles(series, [first]);
  assert.equal(series[0].close, 104);
});
test('a closed candle cannot be reopened by delayed history', () => {
  const closed = { ...parseKline(event({ x: true }), 'BTCUSDT', '15m'), updatedAt: 900000 };
  const delayed = { ...closed, closed: false, updatedAt: 901000 };
  assert.equal(mergeCandles([closed], [delayed])[0].closed, true);
});
test('appends a new candle and bounds the window to sixty without mutating analysis', () => {
  const c = parseKline(event(), 'BTCUSDT', '15m');
  const baseline = Array.from({ length: 60 }, (_, i) => ({ ...c, time: i * 900000, close_time: (i + 1) * 900000 - 1 }));
  const original = JSON.stringify(baseline);
  const merged = mergeCandles(baseline, [{ ...c, time: 54000000, close_time: 54899999 }]);
  assert.equal(merged.length, 60);
  assert.equal(merged[0].time, 900000);
  assert.equal(merged.at(-1).time, 54000000);
  assert.equal(JSON.stringify(baseline), original);
});
test('REST fills missing bars but cannot overwrite a newer stream price', () => {
  const rows = [[0, '100', '105', '98', '101', '10', 899999], [900000, '102', '106', '101', '103', '10', 1799999]];
  const history = parseHistory(rows, 1000000);
  assert.equal(history[0].closed, true);
  assert.equal(history[1].closed, false);
  const stream = { ...history[1], close: 105, updatedAt: 1001000 };
  const merged = mergeCandles([stream], history);
  assert.equal(merged.length, 2);
  assert.equal(merged[1].close, 105);
});
test('stale or future-dated events do not qualify as live', () => {
  assert.equal(liveEventIsFresh(100000, 101000), true);
  assert.equal(liveEventIsFresh(100000, 116000), false);
  assert.equal(liveEventIsFresh(120000, 100000), false);
  assert.equal(liveEventIsFresh(NaN, 100000), false);
});
