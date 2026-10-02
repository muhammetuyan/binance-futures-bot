'use client';

import { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  CirclePlay,
  CircleStop,
  Clock3,
  History,
  RefreshCw,
  ShieldCheck,
  WalletCards,
} from 'lucide-react';
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from 'recharts';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { Progress } from '@/components/ui/progress';
import { AnalysisDesk, type AnalysisSignal } from '@/components/analysis-desk';

type AtlasPosition = {
  symbol: string;
  side: string;
  size: number;
  entry: number;
  mark: number;
  pnl: number;
  notional_usdt: number;
  margin_usdt: number;
};

type AtlasSignal = AnalysisSignal & {
  symbol: string;
  signal: string;
  score: number;
  reason: string;
  time: string;
  timestamp?: number;
  planned_margin_usdt?: number | null;
};

type AtlasTrade = {
  symbol: string;
  side: string;
  entry: number | null;
  exit: number | null;
  pnl: number;
  reason: string;
  closed_at: number;
};

type EquityPoint = { time: string; equity: number };

type AtlasStatus = {
  state: string;
  mode: string;
  message: string;
  equity: number;
  wallet_balance: number;
  available_balance: number;
  daily_pnl: number;
  daily_pnl_percent: number;
  daily_loss_used_percent: number;
  open_risk_percent: number;
  margin_used_percent: number;
  daily_loss_limit_percent: number;
  risk_per_trade_percent: number;
  positions: AtlasPosition[];
  trade_history: AtlasTrade[];
  signals: AtlasSignal[];
  equity_curve: EquityPoint[];
  last_candle_time: number | null;
  next_check_seconds: number;
  next_scan_at: number | null;
  execution_enabled: boolean;
  symbols: string[];
  interval: string;
  confirmation_interval: string;
  scan_interval_minutes: number;
  leverage: number;
  margin_mode: string;
  reward_risk_ratio: number;
  entry_model: string;
  max_open_positions?: number;
  position_limit_override_confirmations?: number;
  minimum_margin_usdt: number;
  maximum_margin_usdt: number;
  updated_at: string | null;
};

type WebMcpContext = {
  registerTool: (
    tool: {
      name: string;
      title: string;
      description: string;
      inputSchema: object;
      annotations?: { readOnlyHint?: boolean; untrustedContentHint?: boolean };
      execute: (input: unknown) => unknown;
    },
    options?: { signal?: AbortSignal },
  ) => void | Promise<void>;
};

declare global {
  interface Document {
    readonly modelContext?: WebMcpContext;
  }
}

const API_URL = 'http://127.0.0.1:8788';
const emptyStatus: AtlasStatus = {
  state: 'connecting',
  mode: 'TESTNET',
  message: 'Yerel bot hizmetine bağlanılıyor',
  equity: 0,
  wallet_balance: 0,
  available_balance: 0,
  daily_pnl: 0,
  daily_pnl_percent: 0,
  daily_loss_used_percent: 0,
  open_risk_percent: 0,
  margin_used_percent: 0,
  daily_loss_limit_percent: 10,
  risk_per_trade_percent: 0.5,
  positions: [],
  trade_history: [],
  signals: [],
  equity_curve: [],
  last_candle_time: null,
  next_check_seconds: 0,
  next_scan_at: null,
  execution_enabled: false,
  symbols: ['BTCUSDT', 'ETHUSDT'],
  interval: '15m',
  confirmation_interval: '1h',
  scan_interval_minutes: 15,
  leverage: 10,
  margin_mode: 'ISOLATED',
  reward_risk_ratio: 2,
  entry_model: "CONFIRMATION_VOTE",
  minimum_margin_usdt: 5,
  maximum_margin_usdt: 40,
  updated_at: null,
};
const chartConfig = {
  equity: { label: 'Equity', color: 'var(--accent-gold)' },
} satisfies ChartConfig;

async function loadStatus(): Promise<AtlasStatus> {
  const response = await fetch(`${API_URL}/api/status`, { cache: 'no-store' });
  if (!response.ok) throw new Error('Durum alınamadı');
  const payload = await response.json() as Partial<AtlasStatus>;
  return {
    ...emptyStatus,
    ...payload,
    positions: payload.positions ?? [],
    trade_history: payload.trade_history ?? [],
    signals: payload.signals ?? [],
    equity_curve: payload.equity_curve ?? [],
    symbols: payload.symbols ?? emptyStatus.symbols,
  };
}

export default function Home() {
  const [status, setStatus] = useState<AtlasStatus>(emptyStatus);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [controlError, setControlError] = useState('');
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [activeTradeTab, setActiveTradeTab] = useState<'open' | 'history'>('open');

  async function setPaused(paused: boolean) {
    setBusy(true);
    setControlError('');
    try {
      const response = await fetch(`${API_URL}/api/control/${paused ? 'pause' : 'resume'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!response.ok) throw new Error('Kontrol isteği başarısız');
      window.dispatchEvent(new Event('atlas-status-refresh'));
    } catch {
      setControlError('Komut uygulanamadı. Bağlantıyı kontrol edip tekrar deneyin.');
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let active = true;
    const update = async () => {
      try {
        const nextStatus = await loadStatus();
        if (active) {
          setStatus(nextStatus);
          setConnected(true);
        }
      } catch {
        if (active) setConnected(false);
      }
    };
    const requestUpdate = () => void update();
    const initialId = window.setTimeout(requestUpdate, 0);
    const intervalId = window.setInterval(requestUpdate, 4000);
    window.addEventListener('atlas-status-refresh', requestUpdate);
    return () => {
      active = false;
      window.clearTimeout(initialId);
      window.clearInterval(intervalId);
      window.removeEventListener('atlas-status-refresh', requestUpdate);
    };
  }, []);

  useEffect(() => {
    const clockId = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(clockId);
  }, []);

  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    void Promise.resolve(context.registerTool({
      name: 'read_atlas_status',
      title: 'Atlas Trade durumunu oku',
      description: 'Botun bağlantı, risk, pozisyon ve son sinyal durumunu okur.',
      inputSchema: { type: 'object', properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true, untrustedContentHint: false },
      execute: async () => {
        const response = await fetch(`${API_URL}/api/status`, { cache: 'no-store' });
        if (!response.ok) throw new Error('Atlas Trade durumuna ulaşılamadı');
        return response.json();
      },
    }, { signal: lifecycle.signal })).catch(() => undefined);
    void Promise.resolve(context.registerTool({
      name: 'set_atlas_paused',
      title: 'Atlas Trade yeni işlemlerini aç veya durdur',
      description: 'Yeni işlem açmayı durdurur veya yeniden başlatır; mevcut pozisyonları zorla kapatmaz.',
      inputSchema: {
        type: 'object',
        properties: { paused: { type: 'boolean' } },
        required: ['paused'],
        additionalProperties: false,
      },
      annotations: { readOnlyHint: false, untrustedContentHint: false },
      execute: async (input) => {
        const paused = (input as { paused?: unknown }).paused;
        if (typeof paused !== 'boolean') throw new Error('paused boolean olmalı');
        const response = await fetch(`${API_URL}/api/control/${paused ? 'pause' : 'resume'}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!response.ok) throw new Error('Atlas Trade kontrol isteği başarısız');
        window.dispatchEvent(new Event('atlas-status-refresh'));
        return { ok: true, paused };
      },
    }, { signal: lifecycle.signal })).catch(() => undefined);
    return () => lifecycle.abort();
  }, []);

  const isPaused = status.state === 'paused';
  const dataAge = status.updated_at ? Math.max(0, nowMs - Date.parse(status.updated_at)) : Infinity;
  const fresh = connected && dataAge < 180_000;
  const isActive = fresh && ['paper_running', 'running', 'dry_run'].includes(status.state);
  const equityData = status.equity_curve;
  const lastData = status.last_candle_time
    ? new Date(status.last_candle_time).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })
    : '—';
  const scanRemainingSeconds = status.next_scan_at
    ? Math.max(0, Math.ceil((status.next_scan_at - nowMs) / 1000))
    : 0;
  const scanCountdown = status.next_scan_at && scanRemainingSeconds > 0
    ? `${String(Math.floor(scanRemainingSeconds / 60)).padStart(2, '0')}:${String(scanRemainingSeconds % 60).padStart(2, '0')}`
    : status.next_scan_at
      ? 'Taranıyor'
      : '—';
  const modeLabel =
    status.mode === 'PAPER'
      ? 'SANAL İŞLEM'
      : status.execution_enabled
        ? 'TESTNET EMİR'
        : 'GÜVENLİ İZLEME';
  const universeLabel = status.symbols.length > 4
    ? `${status.symbols.slice(0, 3).join(' / ')} +${status.symbols.length - 3} coin`
    : status.symbols.join(' / ');

  return (
    <main className="atlas-dashboard relative min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none fixed inset-0 z-0" aria-hidden="true">
        <div className="absolute -left-40 -top-44 size-[520px] rounded-full bg-amber-400/[.055] blur-[110px]" />
        <div className="absolute -right-52 top-48 size-[560px] rounded-full bg-sky-400/[.045] blur-[120px]" />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/40 to-transparent" />
      </div>
      <header className="sticky top-0 z-20 border-b border-white/8 bg-background/85 backdrop-blur-2xl">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-[var(--accent-gold)] text-[#17130a] shadow-[0_8px_30px_rgba(245,190,54,.18)]">
              <Bot className="size-5" aria-hidden="true" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-semibold tracking-tight sm:text-lg">Atlas Trade</h1>
                <Badge className="bg-amber-400/12 text-amber-300 ring-1 ring-amber-300/20">{status.mode}</Badge>
              </div>
              <p className="text-xs text-muted-foreground">Binance USDⓈ-M Futures · {universeLabel}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className={`hidden items-center gap-2 rounded-lg border px-3 py-2 text-xs sm:flex ${isActive ? 'border-emerald-400/15 bg-emerald-400/8 text-emerald-300' : 'border-white/10 bg-white/4 text-muted-foreground'}`}>
              <span className={`size-1.5 rounded-full ${isActive ? 'animate-pulse bg-emerald-300' : 'bg-zinc-500'}`} />
              {!fresh ? 'Veri bekleniyor' : isPaused ? 'İşlemler duraklatıldı' : isActive ? 'Bot çalışıyor' : 'Bot hazırlanıyor'}
            </div>
            <Button variant="outline" className="border-white/10 bg-white/4" onClick={() => window.dispatchEvent(new Event('atlas-status-refresh'))} aria-label="Durumu yenile">
              <RefreshCw data-icon="inline-start" />
              <span className="hidden sm:inline">Yenile</span>
            </Button>
            <Button
              variant={isPaused ? 'default' : 'destructive'}
              className={isPaused ? '' : 'border border-red-400/15'}
              disabled={!fresh || busy}
              onClick={() => void setPaused(!isPaused)}
            >
              {isPaused ? <CirclePlay data-icon="inline-start" /> : <CircleStop data-icon="inline-start" />}
              {isPaused ? 'Botu başlat' : 'Botu durdur'}
            </Button>
          </div>
        </div>
      </header>

      <div className="relative z-10 mx-auto max-w-[1480px] space-y-5 px-4 py-5 sm:px-6 lg:px-8">
        {controlError && <p role="alert" className="rounded-xl border border-red-300/20 bg-red-300/5 p-4 text-sm text-red-200">{controlError}</p>}
        {connected && !fresh && <output className="block rounded-xl border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-200">Veriler güncel değil. Son görülen değerler gösteriliyor; botun çalışma durumu doğrulanamıyor.</output>}
        {status.state === 'needs_credentials' && (
          <div className="flex items-start gap-3 rounded-xl border border-amber-300/15 bg-amber-300/6 px-4 py-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-300" />
            <div><span className="font-medium text-amber-200">Analiz aktif, emirler kapalı.</span> <span className="text-muted-foreground">Testnet API anahtarlarını .env dosyasına eklediğinizde hesap verileri görünür.</span></div>
          </div>
        )}

        <section className="flex flex-col gap-3 rounded-2xl border border-amber-300/10 bg-gradient-to-r from-amber-300/[.07] via-white/[.025] to-sky-300/[.045] px-4 py-3.5 shadow-[0_18px_70px_rgba(0,0,0,.18)] sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-xl border border-amber-300/15 bg-amber-300/10 text-amber-200"><ShieldCheck className="size-4" /></div>
            <div><p className="text-sm font-medium">Üç RSI ile momentum takibi</p><p className="text-xs text-muted-foreground">RSI 7 · 14 · 21 / 15 dk giriş · 1 saat trend onayı</p></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">15 dk tarama</Badge>
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">10x isolated</Badge>
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">1:2 RR</Badge>
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">5–40 USDT</Badge>
          </div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Hesap özeti">
          <MetricCard icon={WalletCards} label="Toplam hesap değeri" value={money(status.equity)} detail={`Kullanılabilir ${money(status.available_balance)}`} />
          <MetricCard icon={Activity} label="Günlük sonuç" value={percent(status.daily_pnl_percent)} detail={money(status.daily_pnl, true)} positive={status.daily_pnl > 0} negative={status.daily_pnl < 0} />
          <MetricCard icon={ShieldCheck} label="Açık risk bütçesi" value={percent(status.open_risk_percent)} detail={`İşlem başına %${status.risk_per_trade_percent.toFixed(2)}`} />
          <MetricCard icon={Clock3} label="Sonraki taramaya" value={fresh ? scanCountdown : '—'} detail={`Son mum ${lastData} · ${status.interval} + ${status.confirmation_interval}`} />
        </section>

        <AnalysisDesk signals={status.signals} symbolsCount={status.symbols.length} fresh={fresh} normalLimit={status.max_open_positions} overrideConfirmations={status.position_limit_override_confirmations} />

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,.7fr)]">
          <Card className="border-white/8 bg-card/85 shadow-[0_18px_70px_rgba(0,0,0,.22)]">
            <CardHeader>
              <CardTitle>Hesap performansı</CardTitle>
              <CardDescription>{status.equity_curve.length > 1 ? (status.mode === 'PAPER' ? 'Gerçek piyasa verisiyle sanal hesap performansı' : 'Bugünkü Binance hesap performansı') : 'İşlemler başladığında hesap eğrisi burada oluşur'}</CardDescription>
              <CardAction><Badge variant="outline" className="border-white/10 bg-white/4 text-muted-foreground">UTC</Badge></CardAction>
            </CardHeader>
            <CardContent>
              {equityData.length > 1 ? <ChartContainer config={chartConfig} className="h-[280px] w-full aspect-auto">
                <AreaChart data={equityData} margin={{ left: 4, right: 8, top: 10 }}>
                  <defs>
                    <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--color-equity)" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="var(--color-equity)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} strokeDasharray="3 6" />
                  <XAxis dataKey="time" tickLine={false} axisLine={false} tickMargin={12} />
                  <YAxis domain={['dataMin - 0.25', 'dataMax + 0.25']} tickLine={false} axisLine={false} tickMargin={8} width={58} />
                  <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line" />} />
                  <Area dataKey="equity" type="monotone" fill="url(#equityFill)" stroke="var(--color-equity)" strokeWidth={2.2} />
                </AreaChart>
              </ChartContainer> : <EmptyState title="Performans verisi birikiyor" detail="Hesap ölçümleri geldikçe eğri burada oluşacak." />}
            </CardContent>
          </Card>

          <Card className="border-white/8 bg-card/85">
            <CardHeader><CardTitle>Risk merkezi</CardTitle><CardDescription>{status.leverage}x · {status.margin_mode} · 1:{status.reward_risk_ratio} RR · {status.minimum_margin_usdt}–{status.maximum_margin_usdt} USDT teminat</CardDescription></CardHeader>
            <CardContent className="space-y-5">
              <RiskRow label={`Günlük zarar limiti: %${status.daily_loss_limit_percent}`} value={`Bütçenin %${status.daily_loss_used_percent.toFixed(1)} kadarı`} percent={status.daily_loss_used_percent} tone="gold" />
              <RiskRow label="Açık pozisyon riski" value={percent(status.open_risk_percent)} percent={Math.min(status.open_risk_percent / Math.max(status.daily_loss_limit_percent, 0.01) * 100, 100)} tone="green" />
              <RiskRow label="Marjin kullanımı" value={percent(status.margin_used_percent)} percent={status.margin_used_percent} tone="blue" />
              <div className="rounded-xl border border-emerald-300/10 bg-emerald-300/6 p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-emerald-300"><ShieldCheck className="size-4" />Koruma katmanı aktif</div>
                <p className="mt-1.5 text-xs leading-5 text-muted-foreground">Sinyal kalitesi yükseldikçe ana teminat 5 USDT’den 40 USDT’ye çıkar. Risk sınırına sığmayan işlem açılmaz.</p>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4">
          <Card className="border-white/8 bg-card/85 shadow-[0_18px_70px_rgba(0,0,0,.2)]">
            <CardHeader><CardTitle>İşlem merkezi</CardTitle><CardDescription>Açık pozisyonlar ve kapanmış işlem geçmişi</CardDescription></CardHeader>
            <CardContent>
              <div>
                <div role="tablist" aria-label="İşlem görünümü" className="mb-4 grid w-full max-w-sm grid-cols-2 rounded-xl border border-white/6 bg-white/[.035] p-1">
                  <button type="button" role="tab" aria-selected={activeTradeTab === 'open'} onClick={() => setActiveTradeTab('open')} className={`flex h-8 items-center justify-center rounded-lg px-3 text-xs font-medium transition ${activeTradeTab === 'open' ? 'bg-white/9 text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Açık pozisyonlar <span className="ml-1 text-[10px] text-muted-foreground">({status.positions.length})</span></button>
                  <button type="button" role="tab" aria-selected={activeTradeTab === 'history'} onClick={() => setActiveTradeTab('history')} className={`flex h-8 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-medium transition ${activeTradeTab === 'history' ? 'bg-white/9 text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}><History className="size-3.5" /> Geçmiş <span className="text-[10px] text-muted-foreground">({status.trade_history.length})</span></button>
                </div>
                {activeTradeTab === 'open' ? <div role="tabpanel" className="overflow-x-auto">
                  {status.positions.length ? (
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead className="text-[11px] uppercase tracking-[.08em] text-muted-foreground"><tr className="border-b border-white/8"><th className="pb-3 font-medium">Parite</th><th className="pb-3 font-medium">Yön</th><th className="pb-3 font-medium">Teminat</th><th className="pb-3 font-medium">Pozisyon</th><th className="pb-3 font-medium">Giriş</th><th className="pb-3 font-medium">Mark fiyatı</th><th className="pb-3 text-right font-medium">Gerçekleşmemiş K/Z</th></tr></thead>
                      <tbody>{status.positions.map((position) => (
                        <tr key={position.symbol} className="border-b border-white/6 last:border-0">
                          <td className="py-4 font-semibold">{position.symbol}</td><td className="py-4"><SideBadge side={position.side} /></td><td className="py-4 font-mono text-xs text-amber-200">{money(position.margin_usdt)}</td><td className="py-4 font-mono text-xs text-muted-foreground">{money(position.notional_usdt)}</td><td className="py-4 font-mono text-xs">{price(position.entry)}</td><td className="py-4 font-mono text-xs">{price(position.mark)}</td><td className={`py-4 text-right font-mono text-sm font-semibold ${position.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{money(position.pnl, true)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  ) : <EmptyState title="Açık pozisyon yok" detail="Yeni işlem yalnızca tüm analiz ve risk filtreleri geçtiğinde açılır." />}
                </div> : <div role="tabpanel" className="overflow-x-auto">
                  {status.trade_history.length ? (
                    <table className="w-full min-w-[820px] text-left text-sm">
                      <thead className="text-[11px] uppercase tracking-[.08em] text-muted-foreground"><tr className="border-b border-white/8"><th className="pb-3 font-medium">Parite</th><th className="pb-3 font-medium">Yön</th><th className="pb-3 font-medium">Giriş</th><th className="pb-3 font-medium">Kapanış</th><th className="pb-3 font-medium">Sonuç</th><th className="pb-3 font-medium">Neden</th><th className="pb-3 text-right font-medium">Zaman</th></tr></thead>
                      <tbody>{status.trade_history.map((trade, index) => (
                        <tr key={`${trade.symbol}-${trade.closed_at}-${index}`} className="border-b border-white/6 last:border-0">
                          <td className="py-4 font-semibold">{trade.symbol}</td>
                          <td className="py-4"><SideBadge side={trade.side} /></td>
                          <td className="py-4 font-mono text-xs">{trade.entry == null ? '—' : price(trade.entry)}</td>
                          <td className="py-4 font-mono text-xs">{trade.exit == null ? '—' : price(trade.exit)}</td>
                          <td className={`py-4 font-mono text-sm font-semibold ${trade.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{money(trade.pnl, true)}</td>
                          <td className="py-4 text-xs text-muted-foreground">{closeReason(trade.reason)}</td>
                          <td className="py-4 text-right font-mono text-xs text-muted-foreground">{formatTradeTime(trade.closed_at)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  ) : <EmptyState title="Henüz kapanmış işlem yok" detail="Stop, kâr al veya güvenli kapamayla tamamlanan işlemler burada kalıcı olarak listelenecek." />}
                </div>}
              </div>
            </CardContent>
          </Card>


        </section>

        <footer className="flex flex-col gap-1 border-t border-white/6 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>Atlas Trade v0.1 · {modeLabel}</span>
          <span>{connected ? status.message : 'Yerel bot hizmetine ulaşılamıyor'}</span>
        </footer>
      </div>
    </main>
  );
}

function MetricCard({ icon: Icon, label, value, detail, positive = false, negative = false }: { icon: typeof Activity; label: string; value: string; detail: string; positive?: boolean; negative?: boolean }) {
  return <Card className="group relative overflow-hidden border-white/8 bg-gradient-to-br from-card via-card to-white/[.025] shadow-[0_14px_50px_rgba(0,0,0,.16)] transition duration-300 hover:-translate-y-0.5 hover:border-amber-300/15"><div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/25 to-transparent opacity-0 transition group-hover:opacity-100" /><CardContent className="flex items-start justify-between gap-4"><div><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 font-mono text-2xl font-semibold tracking-tight">{value}</p><p className={`mt-1.5 text-xs ${positive ? 'text-emerald-300' : negative ? 'text-red-300' : 'text-muted-foreground'}`}>{detail}</p></div><div className="grid size-9 place-items-center rounded-xl border border-white/8 bg-white/4 text-muted-foreground transition group-hover:border-amber-300/15 group-hover:text-amber-200"><Icon className="size-4" /></div></CardContent></Card>;
}

function RiskRow({ label, value, percent: valuePercent, tone }: { label: string; value: string; percent: number; tone: 'gold' | 'green' | 'blue' }) {
  const toneClass = tone === 'green' ? '[&_[data-slot=progress-indicator]]:bg-emerald-400' : tone === 'blue' ? '[&_[data-slot=progress-indicator]]:bg-sky-400' : '[&_[data-slot=progress-indicator]]:bg-amber-400';
  return <div className="space-y-2.5"><div className="flex items-center justify-between gap-3 text-xs"><span className="text-muted-foreground">{label}</span><span className="font-mono">{value}</span></div><Progress value={Math.max(0, Math.min(valuePercent, 100))} className={toneClass} aria-label={`${label} yüzde ${valuePercent}`} /></div>;
}

function SideBadge({ side }: { side: string }) {
  const classes = side === 'LONG' ? 'bg-emerald-400/10 text-emerald-300 ring-emerald-300/15' : side === 'SHORT' ? 'bg-red-400/10 text-red-300 ring-red-300/15' : 'bg-white/5 text-muted-foreground ring-white/8';
  return <Badge className={`${classes} ring-1`}>{side === 'WAIT' ? 'Bekle' : side}</Badge>;
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="grid min-h-36 place-items-center rounded-xl border border-dashed border-white/10 bg-white/[.02] p-6 text-center"><div><Activity className="mx-auto mb-2 size-5 text-muted-foreground" /><p className="text-sm font-medium">{title}</p><p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">{detail}</p></div></div>;
}

function closeReason(reason: string): string {
  const labels: Record<string, string> = {
    STOP: 'Stop loss',
    TAKE_PROFIT: 'Kâr al',
    SAFE_CLOSE: 'Güvenli kapama',
    REALIZED_PNL: 'Gerçekleşen K/Z',
  };
  return labels[reason] ?? reason;
}

function formatTradeTime(timestamp: number): string {
  if (!timestamp) return '—';
  return new Date(timestamp).toLocaleString('tr-TR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function money(value: number, signed = false): string {
  const prefix = signed && value > 0 ? '+' : '';
  return `${prefix}${new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} USDT`;
}

function price(value: number): string {
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(value);
}

function percent(value: number): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}%${value.toFixed(2)}`;
}
