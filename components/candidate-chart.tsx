'use client';

import { useLiveCandles } from '@/hooks/use-live-candles';
import { mergeCandles } from '@/lib/live-candles';
import { locale, translate, type Language } from '@/lib/i18n';

export type CandidateChartData = {
  interval: string;
  as_of: number;
  planned_side: string | null;
  candles: { time: number; close_time: number; open: number; high: number; low: number; close: number }[];
  zones: { lower: number; upper: number; formed_at?: number; label: string; color: string }[];
  levels: { label: string; price: number; color: string; kind: string }[];
};

const price = (value: number, language: Language) => value.toLocaleString(locale(language), { maximumSignificantDigits: 7 });
const time = (value: number, language: Language) => new Date(value).toLocaleTimeString(locale(language), { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });

export function CandidateChart({ data, symbol, fresh, language }: { data?: CandidateChartData; symbol?: string; fresh: boolean; language: Language }) {
  const tx = (value: string) => translate(value, language);
  const feed = useLiveCandles(symbol, data?.interval);
  const baseline = data?.candles.map(c => ({ ...c, closed: true, updatedAt: data.as_of })) ?? [];
  const candles = mergeCandles(baseline, feed.candles);
  if (!data || candles.length < 2) {
    return <section className="rounded-xl border border-white/10 bg-background/60 p-5 text-sm text-muted-foreground">{tx('Mum grafiği ilk tamamlanan analizle gelecek. Örnek fiyat çizilmez.')}</section>;
  }
  const latest = feed.candles[feed.candles.length - 1];
  const levels = [...data.levels, ...(latest ? [{ label: feed.live ? tx('Canlı fiyat') : tx('Son alınan fiyat'), price: latest.close, color: '#38bdf8', kind: 'live' }] : [])].filter(l => Number.isFinite(l.price) && l.price > 0);
  const zones = data.zones.filter(z => Number.isFinite(z.lower) && Number.isFinite(z.upper) && z.upper > z.lower);
  const values = [...candles.flatMap(c => [c.high, c.low]), ...levels.map(l => l.price), ...zones.flatMap(z => [z.lower, z.upper])];
  const minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * .1, Math.abs(maximum) * .0001, .00000001);
  const bottom = minimum - padding, top = maximum + padding;
  const left = 12, right = 608, plotTop = 18, plotBottom = 224, width = 720;
  const step = (right - left) / candles.length;
  const x = (index: number) => left + step * (index + .5);
  const y = (value: number) => plotBottom - (value - bottom) / (top - bottom) * (plotBottom - plotTop);
  return <figure className="overflow-hidden rounded-xl border border-sky-300/15 bg-[#0a1320]">
    <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b border-white/8 px-4 py-3 text-sm">
      <span className="font-semibold">{symbol} · {data.interval} {tx('mum grafiği')}</span>
      <span className={`text-sm ${feed.live ? 'text-sky-300' : 'text-amber-200'}`}>{feed.live ? `● ${tx('Canlı')} · Binance` : feed.phase === 'reconnecting' ? tx('Bağlantı kesildi · yeniden bağlanıyor') : tx('Canlı bağlantı kuruluyor')}</span>
    </figcaption>
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${width} 258`} className="block min-w-[620px] w-full" aria-label={`${symbol} ${tx('canlı mumları; son analizin FVG bölgeleri ve taslak işlem seviyeleri')}`}>
        <title>{symbol} {tx('fiyat ve işlem planı')}</title>
        <desc>{tx('Yeşil yükselen, kırmızı düşen mum. Son mum henüz kapanmamış olabilir. Mavi çizgi son alınan fiyatı, diğer çizgiler ve FVG bölgeleri son kapanış analizini gösterir. Plan gerçekleşmiş emir değildir.')}</desc>
        {[0, 1, 2, 3, 4].map(i => {
          const value = bottom + (top - bottom) * i / 4;
          return <g key={i}><line x1={left} x2={right} y1={y(value)} y2={y(value)} stroke="#ffffff" strokeOpacity=".07" /><text x={right + 10} y={y(value) + 4} fill="#9bacbf" fontSize="12" fontFamily="Consolas,monospace">{price(value, language)}</text></g>;
        })}
        {zones.map((zone, i) => {
          const found = candles.findIndex(c => c.close_time >= (zone.formed_at ?? candles[0].time));
          const start = found < 0 ? candles.length - 1 : found;
          return <g key={`${zone.label}-${i}`}><rect x={x(start) - step / 2} y={y(zone.upper)} width={right - x(start) + step / 2} height={Math.max(1, y(zone.lower) - y(zone.upper))} fill={zone.color} fillOpacity=".13" stroke={zone.color} strokeOpacity=".5" strokeDasharray="3 3" /><title>{tx(zone.label)}: {price(zone.lower, language)} – {price(zone.upper, language)}</title></g>;
        })}
        {candles.map((candle, i) => {
          const color = candle.close >= candle.open ? '#34d399' : '#fb7185';
          return <g key={candle.time}><title>{time(candle.time, language)} · {tx(candle.closed ? 'Kapanmış' : 'Oluşan mum')} · {tx('Açılış')} {price(candle.open, language)} · {tx('Yüksek')} {price(candle.high, language)} · {tx('Düşük')} {price(candle.low, language)} · {tx('Son fiyat')} {price(candle.close, language)}</title><line x1={x(i)} x2={x(i)} y1={y(candle.high)} y2={y(candle.low)} stroke={color} /><rect x={x(i) - step * .3} y={Math.min(y(candle.open), y(candle.close))} width={Math.max(1, step * .6)} height={Math.max(1, Math.abs(y(candle.open) - y(candle.close)))} fill={color} fillOpacity={candle.closed ? 1 : .65} stroke={candle.closed ? 'none' : '#38bdf8'} /></g>;
        })}
        {levels.map((level, i) => <g key={`${level.label}-${i}`}><line x1={left} x2={right} y1={y(level.price)} y2={y(level.price)} stroke={level.color} strokeWidth={level.kind === 'entry' ? 1.5 : 1} strokeDasharray={level.kind === 'entry' ? '6 3' : '3 4'} /><circle cx={right} cy={y(level.price)} r={7} fill="#0a1320" stroke={level.color} /><text x={right} y={y(level.price) + 3} textAnchor="middle" fill={level.color} fontSize="9">{i + 1}</text><title>{tx(level.label)}: {price(level.price, language)}</title></g>)}
        {[0, Math.floor(candles.length / 2), candles.length - 1].map(i => <text key={i} x={x(i)} y="247" textAnchor={i === 0 ? 'start' : i === candles.length - 1 ? 'end' : 'middle'} fill="#9bacbf" fontSize="12">{time(candles[i].time, language)}</text>)}
      </svg>
    </div>
    <div className="flex flex-wrap gap-x-4 gap-y-2 px-4 pb-3 text-sm">
      {levels.map((level, i) => <span key={level.label} style={{ color: level.color }}>{i + 1}. {tx(level.label)}: <span className="font-mono">{price(level.price, language)}</span></span>)}
      {zones.map(zone => <span key={zone.label} style={{ color: zone.color }}>{tx(zone.label)}: <span className="font-mono">{price(zone.lower, language)}–{price(zone.upper, language)}</span></span>)}
      {zones.length === 0 && <span className="text-muted-foreground">{tx('Aktif FVG yok')}</span>}
    </div>
    <div className="border-t border-white/8 px-4 py-2 text-xs leading-5 text-muted-foreground">
      <p>{language === 'en' ? `${candles.length} candles · ` : `Son ${candles.length} mum · `}{latest && !latest.closed ? tx('Son mum henüz kapanmadı.') : tx('Yeni mum güncellemesi bekleniyor.')} {tx('Mavi çizgi son alınan fiyattır; işlemlere esas alınan analiz yalnızca kapanmış mumları kullanır.')}</p>
      <p>{tx('FVG, MSS ve taslak giriş/stop/hedef:')} {new Date(data.as_of).toLocaleString(locale(language), { timeZone: 'Europe/Istanbul' })} {tx('kapanış analizinden.')} {fresh ? tx('Bot bağlantısı güncel.') : tx('Bot analiz bağlantısı eski; çizgiler güncel olmayabilir.')} {tx('Gerçekleşen emir seviyeleri farklı olabilir.')}</p>
      {!feed.historyOk && <p className="text-amber-200">{tx('Mum geçmişi tamamlanıyor; bağlantı kesintisinden kalan boşluklar olabilir.')}</p>}
    </div>
  </figure>;
}
