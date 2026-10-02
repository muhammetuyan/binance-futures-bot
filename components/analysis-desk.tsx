'use client';

import { useState } from 'react';
import { Activity, Check, Minus, Radar } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CandidateChart, type CandidateChartData } from '@/components/candidate-chart';

export type AnalysisSignal = {
  symbol: string;
  signal: string;
  score: number;
  reason: string;
  indicators?: {
    chart?: CandidateChartData;
    confirmation?: { minimum: number; total: number; long: number; short: number; inspected_side: string; eligible: boolean; reason: string };
    rsi?: Record<string, number>;
    higher_rsi?: Record<string, number>;
    rsi_bias?: string;
    adx?: number;
    volume_ratio?: number;
    stop_percent?: number;
    structure?: Record<string, {
      sweep: boolean; mss: boolean; mss_level?: number | null;
      fvg?: { lower: number; upper: number } | null;
      fvg_retest: boolean; fvg_rejection?: boolean; setup: string;
    }>;
    liquidity?: { ok: boolean; message: string; spread_percent?: number; bid_depth_usdt?: number; ask_depth_usdt?: number; checked_at?: number };
  };
  checks?: Record<string, boolean>;
};

const periods = [
  { period: '7', label: 'Hızlı momentum', color: '#f5be36' },
  { period: '14', label: 'Orta vade', color: '#60a5fa' },
  { period: '21', label: 'Yavaş teyit', color: '#a78bfa' },
];
const fmt = (value?: number) => value == null || !Number.isFinite(value) ? '—' : value.toLocaleString('tr-TR', { maximumFractionDigits: 1 });

export function AnalysisDesk({ signals, symbolsCount, fresh, normalLimit, overrideConfirmations }: { signals: AnalysisSignal[]; symbolsCount: number; fresh: boolean; normalLimit?: number; overrideConfirmations?: number }) {
  const [selectedSymbol, setSelectedSymbol] = useState('');
  const selected = signals.find(item => item.symbol === selectedSymbol) ?? signals[0];
  const indicators = selected?.indicators;
  const approval = indicators?.confirmation;
  const structure = indicators?.structure;
  const liquidity = indicators?.liquidity;
  const failed = Object.entries(selected?.checks ?? {}).filter(([, ok]) => !ok).map(([label]) => label);
  const candidates = signals.filter(item => item.signal !== 'WAIT').length;
  return (
    <Card className="overflow-hidden border-sky-300/15 bg-card/95" id="analiz">
      <CardHeader className="border-b border-white/6 pb-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3"><div className="grid size-10 place-items-center rounded-xl bg-sky-400/10 text-sky-300"><Radar className="size-5" /></div><div><CardTitle>Piyasa radarı</CardTitle><CardDescription className="mt-1">{symbolsCount} parite · kapanmış 15 dk ve 1 saat mumları</CardDescription></div></div>
          <Badge className="border border-amber-300/20 bg-amber-300/8 px-3 py-1.5 text-amber-200">{fresh ? `${candidates} işlem adayı` : 'Güncel veri bekleniyor'}</Badge>
        </div>
      </CardHeader>
      {normalLimit != null && overrideConfirmations != null && <p className="px-6 pb-4 text-sm text-muted-foreground">Normal açık pozisyon sınırı: {normalLimit} · Seçilen yönde {overrideConfirmations}+ onaylı adaylar sayı sınırından muaf; bakiye ve risk sınırları geçerli.</p>}
      <CardContent className="grid gap-6 pt-0 lg:grid-cols-[230px_minmax(0,1fr)]">
        <div className="flex gap-2 overflow-x-auto pb-2 lg:max-h-[430px] lg:flex-col lg:overflow-y-auto lg:pr-3" aria-label="Analiz edilecek parite">
          {signals.map(item => (
            <button type="button" key={item.symbol} aria-pressed={selected?.symbol === item.symbol} onClick={() => setSelectedSymbol(item.symbol)} className={`flex min-w-[170px] shrink-0 items-center justify-between gap-3 rounded-xl border p-3 text-left transition ${selected?.symbol === item.symbol ? 'border-sky-300/30 bg-sky-300/10' : 'border-transparent bg-white/[.02] hover:bg-white/5'}`}>
              <span><span className="block text-sm font-semibold">{item.symbol.replace(/USDT$/, '')}<span className="ml-1 text-xs font-normal text-muted-foreground">/ USDT</span></span><span className="mt-1 block text-xs text-muted-foreground">Kalite {item.score}/100</span></span>
              <span className={`text-xs font-medium ${item.signal === 'LONG' ? 'text-emerald-300' : item.signal === 'SHORT' ? 'text-red-300' : 'text-muted-foreground'}`}>{item.signal === 'WAIT' ? 'Bekle' : item.signal}</span>
            </button>
          ))}
          {!signals.length && <p className="p-3 text-sm text-muted-foreground">İlk tarama bekleniyor.</p>}
        </div>
        <div className="min-w-0 space-y-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-xl font-semibold tracking-tight">{selected?.symbol ?? 'RSI analizi'}</h2><p className="mt-1 text-sm text-muted-foreground">Üç dönem, ortak yön · RSI 7 / 14 / 21</p></div><div className="text-right"><p className="text-xs text-muted-foreground">15 dk RSI yön onayı</p><p className="mt-1 text-sm font-semibold text-sky-200">{indicators?.rsi_bias === 'LONG' ? 'Yukarı' : indicators?.rsi_bias === 'SHORT' ? 'Aşağı' : 'Uyum bekleniyor'}</p></div></div>
          {approval && <section className="rounded-xl border border-sky-300/20 bg-sky-300/5 p-4" aria-label="Analiz onay sayısı">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-sm font-semibold">Giriş eşiği: en az {approval.minimum} analiz</h3>
              <div className="flex gap-4 font-mono text-base"><span className="text-emerald-200">LONG {approval.long}/{approval.total}</span><span className="text-red-200">SHORT {approval.short}/{approval.total}</span></div>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{approval.reason}. Eşitlikte işlem açılmaz.</p>
            <p className="mt-1 text-xs text-muted-foreground">ADX, hacim ve oynaklık ortak piyasa koşullarıdır. RSI üçlüsü tek oy; 15 dk yön ve momentum tek oy sayılır. Bakiye ve emir güvenliği ayrıca kontrol edilir.</p>
          </section>}
          <CandidateChart data={indicators?.chart} symbol={selected?.symbol} fresh={fresh} />
          <div className="grid gap-3 sm:grid-cols-3">
            {periods.map(({ period, label, color }) => {
              const value = indicators?.rsi?.[period];
              return <div key={period} className="rounded-xl border border-white/8 bg-background/50 p-4">
                <div className="flex items-center justify-between"><span className="text-sm font-medium" style={{ color }}>RSI {period}</span><Activity className="size-4 text-muted-foreground" /></div>
                <p className="mt-3 font-mono text-3xl font-semibold tabular-nums">{fmt(value)}</p><p className="mt-1 text-xs text-muted-foreground">{label} · 15 dk</p>
                {value != null && <meter className="sr-only" min={0} max={100} value={value} aria-label={`RSI ${period}`} />}
                <div className="rsi-meter relative my-4 h-1.5 rounded-full" aria-hidden="true">
                  <span className="absolute left-1/2 -top-1 h-3.5 w-px bg-white/30" />
                  {value != null && <span className="absolute -top-1 size-3.5 -translate-x-1/2 rounded-full border-2 border-background" style={{ left: `${Math.max(0, Math.min(100, value))}%`, backgroundColor: color }} />}
                </div><p className="flex justify-between text-xs text-muted-foreground"><span>1 saat</span><span className="font-mono text-foreground">{fmt(indicators?.higher_rsi?.[period])}</span></p>
              </div>;
            })}
          </div>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground"><span>Trend gücü <strong className="ml-1 font-mono text-foreground">{fmt(indicators?.adx)}</strong></span><span>Hacim / ortalama <strong className="ml-1 font-mono text-foreground">{fmt(indicators?.volume_ratio)}×</strong></span><span>Planlanan stop <strong className="ml-1 font-mono text-foreground">%{fmt(indicators?.stop_percent)}</strong></span></div>
          <div className="grid gap-3 sm:grid-cols-2">
            {(['LONG', 'SHORT'] as const).map(side => {
              const info = structure?.[side];
              return <section key={side} className="rounded-xl border border-white/8 bg-background/50 p-4">
                <h3 className={`text-sm font-semibold ${side === 'LONG' ? 'text-emerald-200' : 'text-red-200'}`}>{side === 'LONG' ? 'Yukarı yönlü yapı' : 'Aşağı yönlü yapı'}</h3>
                <dl className="mt-3 space-y-2 text-sm">
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">Likidite süpürmesi</dt><dd>{!info ? '—' : info.sweep ? 'Görüldü' : 'Yok'}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">MSS · kapanış onayı</dt><dd>{!info ? '—' : info.mss ? 'Var' : 'Bekleniyor'}</dd></div>
                  <div className="flex justify-between gap-2"><dt className="text-muted-foreground">FVG dönüşü</dt><dd>{!info ? '—' : info.fvg_rejection ? 'Tepki onaylandı' : info.fvg ? 'Bölge izleniyor' : 'Aktif bölge yok'}</dd></div>
                  {info?.fvg && <div className="font-mono text-xs text-muted-foreground">FVG: {info.fvg.lower.toLocaleString('tr-TR', { maximumSignificantDigits: 7 })} – {info.fvg.upper.toLocaleString('tr-TR', { maximumSignificantDigits: 7 })}</div>}
                </dl>
                <p className="mt-3 text-sm">{info?.setup === 'SWEEP_MSS' ? 'Süpürme → MSS kurulumu' : info?.setup === 'FVG_MSS' ? 'MSS → FVG dönüşü kurulumu' : 'Birleşik kurulum yok; diğer onaylar sayılır'}</p>
              </section>;
            })}
          </div>
          <div className="rounded-xl border border-white/8 p-4 text-sm">
            <p className="font-medium">Emir defteri kontrolü</p>
            <p className="mt-1 text-muted-foreground">{liquidity?.message ?? 'İşlem adayı oluşunca ve emirden hemen önce kontrol edilir.'}</p>
            {liquidity?.spread_percent != null && <p className="mt-2 text-muted-foreground">Alış-satış farkı: %{liquidity.spread_percent.toLocaleString('tr-TR', { maximumFractionDigits: 4 })} · Alış derinliği: {fmt(liquidity.bid_depth_usdt)} USDT · Satış derinliği: {fmt(liquidity.ask_depth_usdt)} USDT</p>}
            {liquidity?.checked_at && <p className="mt-1 text-xs text-muted-foreground">Son anlık kontrol: {new Date(liquidity.checked_at).toLocaleTimeString('tr-TR')} · Derinlik: ±%0,2, en fazla 100 seviye</p>}
            <p className="mt-2 text-xs text-muted-foreground">Grafik seviyeleri olası likidite bölgeleridir; gizli stop veya tasfiye emirlerini göstermez.</p>
          </div>
          <div className="flex flex-wrap gap-2">{Object.entries(selected?.checks ?? {}).map(([label, ok]) => <span key={label} className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs ${ok ? 'border-emerald-300/15 bg-emerald-300/5 text-emerald-200' : 'border-white/8 bg-white/[.02] text-muted-foreground'}`}>{ok ? <Check className="size-3.5" /> : <Minus className="size-3.5" />}{label}</span>)}</div>
          <div className="rounded-xl border-l-2 border-amber-300/60 bg-amber-300/[.04] p-4 text-sm leading-6">
            <p className="font-medium">{!selected ? 'Analiz bekleniyor' : !fresh ? 'Son kaydedilen analiz' : selected.signal === 'WAIT' ? 'Neden bekliyor?' : 'İşlem adayı oluştu'}</p>
            <p className="text-muted-foreground">{!selected ? 'Analiz tamamlandığında karar ve göstergeler burada görünür.' : approval?.eligible && liquidity?.ok === false ? liquidity.message : approval?.reason ?? 'Güncel onay sayıları bekleniyor.'}</p>
            {selected?.signal !== 'WAIT' && selected && <p className="text-muted-foreground">Tüm analizlerin uyması gerekmez. Emir için bakiye, risk, açık pozisyon ve güncel emir defteri kontrolleri de geçmelidir.</p>}
            {failed.length > 0 && <p className="mt-2 text-xs text-muted-foreground">Onay vermeyen kontroller: {failed.join(', ')}. Analiz eksikleri tek başına veto değildir; güvenlik kontrolleri zorunludur.</p>}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
