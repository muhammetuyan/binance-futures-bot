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
  X,
  Languages,
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
import { locale, translate, type Language } from '@/lib/i18n';

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
  review_included?: boolean;
  review_note?: string;
};

type TradeStats = { count: number; wins: number; losses: number; net_pnl: number; win_rate: number; profit_factor: number | null };

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
  trade_review?: { all: TradeStats; strategy: TradeStats; excluded_count: number; trades: AtlasTrade[]; note: string };
  remote_access?: { url?: string; state?: string };
  monitoring_errors?: Record<string, string>;
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
  live_access?: { active: boolean; credentials_configured: boolean; platform: string };
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

const API_URL = ''; // Same-origin proxy also works over the private phone connection.
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
  const [language, setLanguage] = useState<Language>('tr');
  const [status, setStatus] = useState<AtlasStatus>(emptyStatus);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const [controlError, setControlError] = useState('');
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [activeTradeTab, setActiveTradeTab] = useState<'open' | 'history'>('open');
  const [showExcluded, setShowExcluded] = useState(false);
  const [liveOpen, setLiveOpen] = useState(false);
  const [liveKey, setLiveKey] = useState('');
  const [liveSecret, setLiveSecret] = useState('');
  const [liveToken, setLiveToken] = useState('');
  const [liveEquity, setLiveEquity] = useState<number | null>(null);
  const [liveAcknowledged, setLiveAcknowledged] = useState(false);
  const [liveBusy, setLiveBusy] = useState(false);
  const [liveError, setLiveError] = useState('');
  const reviewedTrades = status.trade_review?.trades ?? status.trade_history;
  const visibleTrades = reviewedTrades.filter(trade => showExcluded || trade.review_included !== false);
  const tx = (value: string) => translate(value, language);
  const chartConfig = {
    equity: { label: language === 'en' ? 'Equity' : 'Hesap değeri', color: 'var(--accent-gold)' },
  } satisfies ChartConfig;

  useEffect(() => {
    const saved = window.localStorage.getItem('atlas-language');
    if (saved === 'tr' || saved === 'en') setLanguage(saved);
  }, []);

  useEffect(() => {
    window.localStorage.setItem('atlas-language', language);
    document.documentElement.lang = language;
    document.title = language === 'en' ? 'Atlas Trade | Binance Futures Bot' : 'Atlas Trade | Binance Futures Bot';
    const description = document.querySelector('meta[name="description"]');
    description?.setAttribute('content', language === 'en' ? 'Binance Futures trading bot and risk dashboard.' : 'Binance Futures işlem botu ve risk kontrol paneli.');
  }, [language]);

  async function setPaused(paused: boolean) {
    setBusy(true);
    setControlError('');
    try {
      const response = await fetch(`${API_URL}/api/control/${paused ? 'pause' : 'resume'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atlas-Control': '1' },
      });
      if (!response.ok) throw new Error(tx('Kontrol isteği başarısız'));
      window.dispatchEvent(new Event('atlas-status-refresh'));
    } catch {
      setControlError(tx('Komut uygulanamadı. Bağlantıyı kontrol edip tekrar deneyin.'));
    } finally {
      setBusy(false);
    }
  }

  async function checkLiveConnection() {
    setLiveBusy(true);
    setLiveError('');
    try {
      const response = await fetch(`${API_URL}/api/live/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atlas-Control': '1' },
        body: JSON.stringify({ api_key: liveKey, api_secret: liveSecret }),
      });
      const result = await response.json() as { detail?: string; token: string; equity: number };
      if (!response.ok) throw new Error(tx(result.detail ?? 'Binance bağlantısı doğrulanamadı.'));
      setLiveToken(result.token);
      setLiveEquity(result.equity);
      setLiveKey('');
      setLiveSecret('');
    } catch (error) {
      setLiveError(error instanceof Error ? tx(error.message) : tx('Bağlantı doğrulanamadı.'));
    } finally {
      setLiveBusy(false);
    }
  }

  async function activateLive() {
    if (!liveAcknowledged || !liveToken) return;
    setLiveBusy(true);
    setLiveError('');
    try {
      const response = await fetch(`${API_URL}/api/live/activate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Atlas-Control': '1' },
        body: JSON.stringify({ token: liveToken, acknowledged: true }),
      });
      const result = await response.json() as { detail?: string; mode: string; message: string };
      if (!response.ok) throw new Error(tx(result.detail ?? 'Live modu etkinleştirilemedi.'));
      setLiveOpen(false);
      setLiveToken('');
      setLiveAcknowledged(false);
      window.dispatchEvent(new Event('atlas-status-refresh'));
    } catch (error) {
      setLiveError(error instanceof Error ? tx(error.message) : tx('Live modu etkinleştirilemedi.'));
    } finally {
      setLiveBusy(false);
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
          headers: { 'Content-Type': 'application/json', 'X-Atlas-Control': '1' },
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
    ? new Date(status.last_candle_time).toLocaleTimeString(locale(language), { hour: '2-digit', minute: '2-digit' })
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
      ? tx('Sanal işlem').toUpperCase()
      : status.execution_enabled
        ? tx('TESTNET EMİR')
        : tx('Güvenli izleme').toUpperCase();
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
                <Badge className="bg-amber-400/12 text-amber-300 ring-1 ring-amber-300/20">{status.mode === 'PAPER' ? 'PAPER' : status.mode}</Badge>
              </div>
              <p className="text-xs text-muted-foreground">Binance USDⓈ-M Futures · {universeLabel}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div role="group" aria-label={language === 'en' ? 'Choose language' : 'Dil seçin'} className="flex rounded-lg border border-white/10 bg-white/4 p-0.5">
              {(['tr', 'en'] as const).map(code => <button key={code} type="button" aria-pressed={language === code} onClick={() => setLanguage(code)} className={`rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${language === code ? 'bg-amber-300 text-black' : 'text-muted-foreground hover:text-foreground'}`}><Languages className="mr-1 inline size-3.5" />{code.toUpperCase()}</button>)}
            </div>
            <div className={`hidden items-center gap-2 rounded-lg border px-3 py-2 text-xs sm:flex ${isActive ? 'border-emerald-400/15 bg-emerald-400/8 text-emerald-300' : 'border-white/10 bg-white/4 text-muted-foreground'}`}>
              <span className={`size-1.5 rounded-full ${isActive ? 'animate-pulse bg-emerald-300' : 'bg-zinc-500'}`} />
              {!fresh ? tx('Veri bekleniyor') : isPaused ? tx('İşlemler duraklatıldı') : isActive ? tx('Bot çalışıyor') : tx('Bot hazırlanıyor')}
            </div>
            <Button variant="outline" className="border-white/10 bg-white/4" onClick={() => window.dispatchEvent(new Event('atlas-status-refresh'))} aria-label={tx('Durumu yenile')}>
              <RefreshCw data-icon="inline-start" />
              <span className="hidden sm:inline">{tx('Yenile')}</span>
            </Button>
            <Button
              variant={isPaused ? 'default' : 'destructive'}
              className={isPaused ? '' : 'border border-red-400/15'}
              disabled={!fresh || busy}
              onClick={() => void setPaused(!isPaused)}
            >
              {isPaused ? <CirclePlay data-icon="inline-start" /> : <CircleStop data-icon="inline-start" />}
              {isPaused ? tx('Botu başlat') : tx('Botu durdur')}
            </Button>
            {status.mode === 'PAPER' ? <Button disabled={!fresh || liveBusy} onClick={() => { setLiveOpen(true); setLiveError(''); }} className="bg-amber-300 text-black hover:bg-amber-200">{tx('Gerçek işleme geç')}</Button> : <Badge className="bg-red-400/10 text-red-200 ring-1 ring-red-400/20">{tx('Gerçek hesap')}</Badge>}
          </div>
        </div>
      </header>

      <div className="relative z-10 mx-auto max-w-[1480px] space-y-5 px-4 py-5 sm:px-6 lg:px-8">
        {controlError && <p role="alert" className="rounded-xl border border-red-300/20 bg-red-300/5 p-4 text-sm text-red-200">{controlError}</p>}
        {connected && !fresh && <output className="block rounded-xl border border-amber-300/20 bg-amber-300/5 p-4 text-sm text-amber-200">{tx('Veriler güncel değil. Son görülen değerler gösteriliyor; botun çalışma durumu doğrulanamıyor.')}</output>}
        {status.state === 'needs_credentials' && (
          <div className="flex items-start gap-3 rounded-xl border border-amber-300/15 bg-amber-300/6 px-4 py-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-300" />
            <div><span className="font-medium text-amber-200">{tx('Analiz aktif, emirler kapalı.')}</span> <span className="text-muted-foreground">{tx('Testnet API anahtarlarını .env dosyasına eklediğinizde hesap verileri görünür.')}</span></div>
          </div>
        )}

        <section className="flex flex-col gap-3 rounded-2xl border border-amber-300/10 bg-gradient-to-r from-amber-300/[.07] via-white/[.025] to-sky-300/[.045] px-4 py-3.5 shadow-[0_18px_70px_rgba(0,0,0,.18)] sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-xl border border-amber-300/15 bg-amber-300/10 text-amber-200"><ShieldCheck className="size-4" /></div>
            <div><p className="text-sm font-medium">{tx('Üç RSI ile momentum takibi')}</p><p className="text-xs text-muted-foreground">{tx('RSI 7 · 14 · 21 / 15 dk giriş · 1 saat trend onayı')}</p></div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">{tx('15 dk tarama')}</Badge>
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">10x isolated</Badge>
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">1:2 RR</Badge>
            <Badge variant="outline" className="border-white/10 bg-black/15 text-muted-foreground">5–40 USDT</Badge>
          </div>
        </section>

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label={language === 'en' ? 'Account summary' : 'Hesap özeti'}>
          <MetricCard icon={WalletCards} label={tx('Toplam hesap değeri')} value={money(status.equity, false, language)} detail={`${tx('Kullanılabilir')} ${money(status.available_balance, false, language)}`} positive={false} negative={false} />
          <MetricCard icon={Activity} label={tx('Günlük sonuç')} value={percent(status.daily_pnl_percent, language)} detail={money(status.daily_pnl, true, language)} positive={status.daily_pnl > 0} negative={status.daily_pnl < 0} />
          <MetricCard icon={ShieldCheck} label={tx('Açık risk bütçesi')} value={percent(status.open_risk_percent, language)} detail={`${tx('İşlem başına')} %${status.risk_per_trade_percent.toLocaleString(locale(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} positive={false} negative={false} />
          <MetricCard icon={Clock3} label={tx('Sonraki taramaya')} value={fresh ? scanCountdown : '—'} detail={`${tx('Son mum')} ${lastData} · ${status.interval} + ${status.confirmation_interval}`} positive={false} negative={false} />
        </section>

        <AnalysisDesk signals={status.signals} symbolsCount={status.symbols.length} fresh={fresh} normalLimit={status.max_open_positions} overrideConfirmations={status.position_limit_override_confirmations} language={language} />

        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,.7fr)]">
          <Card className="border-white/8 bg-card/85 shadow-[0_18px_70px_rgba(0,0,0,.22)]">
            <CardHeader>
              <CardTitle>{tx('Hesap performansı')}</CardTitle>
              <CardDescription>{tx(status.equity_curve.length > 1 ? (status.mode === 'PAPER' ? 'Gerçek piyasa verisiyle sanal hesap performansı' : 'Bugünkü Binance hesap performansı') : 'İşlemler başladığında hesap eğrisi burada oluşur')}</CardDescription>
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
              </ChartContainer> : <EmptyState title={tx('Performans verisi birikiyor')} detail={tx('Hesap ölçümleri geldikçe eğri burada oluşacak.')} />}
            </CardContent>
          </Card>

          <Card className="border-white/8 bg-card/85">
            <CardHeader><CardTitle>{tx('Risk merkezi')}</CardTitle><CardDescription>{status.leverage}x · {status.margin_mode} · 1:{status.reward_risk_ratio} RR · {status.minimum_margin_usdt}–{status.maximum_margin_usdt} USDT {language === 'en' ? 'margin' : 'teminat'}</CardDescription></CardHeader>
            <CardContent className="space-y-5">
              <RiskRow language={language} label={`${tx('Günlük zarar limiti:')} %${status.daily_loss_limit_percent}`} value={language === 'en' ? `${status.daily_loss_used_percent.toLocaleString(locale(language), { maximumFractionDigits: 1 })}% of daily loss budget used` : `Bütçenin %${status.daily_loss_used_percent.toLocaleString(locale(language), { minimumFractionDigits: 1, maximumFractionDigits: 1 })} kadarı`} percent={status.daily_loss_used_percent} tone="gold" />
              <RiskRow language={language} label={tx('Açık pozisyon riski')} value={percent(status.open_risk_percent, language)} percent={Math.min(status.open_risk_percent / Math.max(status.daily_loss_limit_percent, 0.01) * 100, 100)} tone="green" />
              <RiskRow language={language} label={tx('Marjin kullanımı')} value={percent(status.margin_used_percent, language)} percent={status.margin_used_percent} tone="blue" />
              <div className="rounded-xl border border-emerald-300/10 bg-emerald-300/6 p-4">
                <div className="flex items-center gap-2 text-sm font-medium text-emerald-300"><ShieldCheck className="size-4" />{tx('Koruma katmanı aktif')}</div>
                <p className="mt-1.5 text-xs leading-5 text-muted-foreground">{tx('Sinyal kalitesi yükseldikçe ana teminat 5 USDT’den 40 USDT’ye çıkar. Risk sınırına sığmayan işlem açılmaz.')}</p>
              </div>
            </CardContent>
          </Card>
        </section>

        <section className="grid gap-4">
          <Card className="border-white/8 bg-card/85 shadow-[0_18px_70px_rgba(0,0,0,.2)]">
            <CardHeader><CardTitle>{tx('İşlem merkezi')}</CardTitle><CardDescription>{tx('Açık pozisyonlar ve kapanmış işlem geçmişi')}</CardDescription></CardHeader>
            <CardContent>
              <div>
                <div role="tablist" aria-label={tx('İşlem görünümü')} className="mb-4 grid w-full max-w-sm grid-cols-2 rounded-xl border border-white/6 bg-white/[.035] p-1">
                  <button type="button" role="tab" aria-selected={activeTradeTab === 'open'} onClick={() => setActiveTradeTab('open')} className={`flex h-8 items-center justify-center rounded-lg px-3 text-xs font-medium transition ${activeTradeTab === 'open' ? 'bg-white/9 text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>{tx('Açık pozisyonlar')} <span className="ml-1 text-[10px] text-muted-foreground">({status.positions.length})</span></button>
                  <button type="button" role="tab" aria-selected={activeTradeTab === 'history'} onClick={() => setActiveTradeTab('history')} className={`flex h-8 items-center justify-center gap-1.5 rounded-lg px-3 text-xs font-medium transition ${activeTradeTab === 'history' ? 'bg-white/9 text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}><History className="size-3.5" /> {tx('Geçmiş')} <span className="text-[10px] text-muted-foreground">({status.trade_history.length})</span></button>
                </div>
                {activeTradeTab === 'open' ? <div role="tabpanel" className="overflow-x-auto">
                  {status.positions.length ? (
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead className="text-[11px] uppercase tracking-[.08em] text-muted-foreground"><tr className="border-b border-white/8"><th className="pb-3 font-medium">{tx('Parite')}</th><th className="pb-3 font-medium">{tx('Yön')}</th><th className="pb-3 font-medium">{tx('Teminat')}</th><th className="pb-3 font-medium">{tx('Pozisyon')}</th><th className="pb-3 font-medium">{tx('Giriş')}</th><th className="pb-3 font-medium">{tx('Mark fiyatı')}</th><th className="pb-3 text-right font-medium">{tx('Gerçekleşmemiş K/Z')}</th></tr></thead>
                      <tbody>{status.positions.map((position) => (
                        <tr key={position.symbol} className="border-b border-white/6 last:border-0">
                          <td className="py-4 font-semibold">{position.symbol}</td><td className="py-4"><SideBadge side={position.side} language={language} /></td><td className="py-4 font-mono text-xs text-amber-200">{money(position.margin_usdt, false, language)}</td><td className="py-4 font-mono text-xs text-muted-foreground">{money(position.notional_usdt, false, language)}</td><td className="py-4 font-mono text-xs">{price(position.entry, language)}</td><td className="py-4 font-mono text-xs">{price(position.mark, language)}</td><td className={`py-4 text-right font-mono text-sm font-semibold ${position.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{money(position.pnl, true, language)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  ) : <EmptyState title={tx('Açık pozisyon yok')} detail={tx('Yeni işlem yalnızca tüm analiz ve risk filtreleri geçtiğinde açılır.')} />}
                </div> : <div role="tabpanel" className="overflow-x-auto">
                  {status.trade_review && <div className="mb-5 space-y-3 rounded-xl border border-white/10 bg-white/[.025] p-4">
                    <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                      <span>{tx('Analize dahil:')} <strong>{status.trade_review.strategy.count}</strong></span>
                      <span>{tx('Kazanma')} <strong>%{status.trade_review.strategy.win_rate}</strong></span>
                      <span>{tx('Net')} <strong>{money(status.trade_review.strategy.net_pnl, true, language)}</strong></span>
                      <span>{tx('Tüm işlemler net:')} <strong>{money(status.trade_review.all.net_pnl, true, language)}</strong></span>
                      <span>{tx('Ayrı tutulan:')} <strong>{status.trade_review.excluded_count}</strong></span>
                    </div>
                    <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">{tx(status.trade_review.note)}</p>
                    <label className="flex cursor-pointer items-center gap-2 text-xs"><input type="checkbox" checked={showExcluded} onChange={event => setShowExcluded(event.target.checked)} /> {tx('Operasyonel ve belirsiz toplu kapanışları da göster')}</label>
                  </div>}
                  {visibleTrades.length ? (
                    <table className="w-full min-w-[820px] text-left text-sm">
                      <thead className="text-[11px] uppercase tracking-[.08em] text-muted-foreground"><tr className="border-b border-white/8"><th className="pb-3 font-medium">{tx('Parite')}</th><th className="pb-3 font-medium">{tx('Yön')}</th><th className="pb-3 font-medium">{tx('Giriş')}</th><th className="pb-3 font-medium">{tx('Kapanış')}</th><th className="pb-3 font-medium">{tx('Sonuç')}</th><th className="pb-3 font-medium">{tx('Neden')}</th><th className="pb-3 text-right font-medium">{tx('Zaman')}</th></tr></thead>
                      <tbody>{visibleTrades.map((trade, index) => (
                        <tr key={`${trade.symbol}-${trade.closed_at}-${index}`} className="border-b border-white/6 last:border-0">
                          <td className="py-4 font-semibold">{trade.symbol}</td>
                          <td className="py-4"><SideBadge side={trade.side} language={language} /></td>
                          <td className="py-4 font-mono text-xs">{trade.entry == null ? '—' : price(trade.entry, language)}</td>
                          <td className="py-4 font-mono text-xs">{trade.exit == null ? '—' : price(trade.exit, language)}</td>
                          <td className={`py-4 font-mono text-sm font-semibold ${trade.pnl >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>{money(trade.pnl, true, language)}</td>
                          <td className="max-w-[240px] py-4 text-xs text-muted-foreground">{tx(closeReason(trade.reason))}{trade.review_note && <div className={`mt-1 text-[11px] ${trade.review_included === false ? 'text-amber-200' : ''}`}>{tx(trade.review_note)}</div>}</td>
                          <td className="py-4 text-right font-mono text-xs text-muted-foreground">{formatTradeTime(trade.closed_at, language)}</td>
                        </tr>
                      ))}</tbody>
                    </table>
                  ) : <EmptyState title={tx('Bu filtrede kapanmış işlem yok')} detail={tx('Ayrı tutulan kapanışları görmek için yukarıdaki seçeneği açabilirsin.')} />}
                </div>}
              </div>
            </CardContent>
          </Card>


        </section>

        <footer className="flex flex-col gap-1 border-t border-white/6 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <span>Atlas Trade v0.1 · {modeLabel}</span>
          <span>{connected ? tx(status.message) : tx('Yerel bot hizmetine ulaşılamıyor')}</span>
        </footer>
        {status.remote_access?.url && <div className="mb-5 rounded-xl border border-white/10 p-4 text-sm"><div className="font-semibold">{tx('Telefon erişimi · Özel ağ')}</div><a href={status.remote_access.url} className="mt-2 block break-all text-amber-200">{status.remote_access.url}</a><p className="mt-2 text-xs leading-relaxed text-muted-foreground">{tx('Telefonda Tailscale açık olmalı ve bu cihaza erişim izni olan aynı tailnet’te bulunmalı. Bilgisayar ve Atlas Trade açık kalmalı. Yetkili tailnet kullanıcıları botu kontrol edebilir; yalnızca güvendiğin kişileri ekle.')}</p></div>}
        {Object.keys(status.monitoring_errors ?? {}).length > 0 && <p role="alert" className="mb-5 rounded-xl border border-red-400/30 p-4 text-sm text-red-200">{tx('Bazı açık pozisyonlarda piyasa verisi güncel değil. Yeni girişler engellendi; bağlantı veya eksik mumlar bekleniyor.')}</p>}
      </div>
      {liveOpen && <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/75 p-4 backdrop-blur-sm" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget && !liveBusy) setLiveOpen(false); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="live-title" className="my-6 w-full max-w-lg rounded-2xl border border-red-300/25 bg-[#111318] p-5 shadow-2xl sm:p-6">
          <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[.15em] text-red-300">{tx('Yüksek risk · USDT-M Futures')}</p><h2 id="live-title" className="mt-2 text-xl font-semibold">{tx('Gerçek işlem modunu aç')}</h2></div><button type="button" aria-label={tx('Pencereyi kapat')} onClick={() => setLiveOpen(false)} className="rounded-lg p-2 text-muted-foreground hover:bg-white/10"><X className="size-4" /></button></div>
          <div className="mt-4 rounded-xl border border-red-300/20 bg-red-400/[.07] p-4 text-sm leading-relaxed text-red-100">{tx('Live mod gerçek Binance Futures hesabında, 10x isolated kaldıraçla emir gönderir. Ana paranı ve yatırdığın paranın tamamını kaybedebilirsin; kâr garantisi yoktur. Bağlantı başarılı olunca bot otomatik işlem aramaya devam eder.')}</div>
          <p className="mt-4 text-sm text-muted-foreground">{tx('Binance’te yalnızca Futures işlem izni olan bir API anahtarı oluştur. Para çekme iznini kapalı tut; mümkünse IP erişimini bu bilgisayarla sınırla. Anahtarlar bu bilgisayarda Windows tarafından şifrelenerek saklanır; sayfaya tekrar gönderilmez.')}</p>
          {!liveToken ? <div className="mt-5 space-y-3">
            {status.live_access?.credentials_configured && <p className="rounded-lg border border-emerald-300/15 bg-emerald-300/5 p-3 text-xs text-emerald-200">{tx('Bu bilgisayarda şifreli API bağlantısı bulundu. Alanları boş bırakıp doğrulayabilirsin.')}</p>}
            <label className="block space-y-1.5 text-sm"><span>Binance API Key</span><input autoComplete="off" value={liveKey} onChange={event => setLiveKey(event.target.value)} className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 font-mono text-sm outline-none focus:border-amber-300/50" placeholder="API key" /></label>
            <label className="block space-y-1.5 text-sm"><span>Binance API Secret</span><input autoComplete="new-password" type="password" value={liveSecret} onChange={event => setLiveSecret(event.target.value)} className="w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2.5 font-mono text-sm outline-none focus:border-amber-300/50" placeholder="API secret" /></label>
            <p className="text-xs leading-relaxed text-muted-foreground">{tx('API anahtarını yalnızca bu özel tailnet’teki güvendiğin kişiler kullanabilsin. Tailscale ağına erişimi olan herkes bu paneli kontrol edebilir.')}</p>
          </div> : <div className="mt-5 rounded-xl border border-emerald-300/20 bg-emerald-300/[.06] p-4 text-sm text-emerald-100">{tx('Binance Futures bağlantısı doğrulandı · Kullanılabilir hesap değeri yaklaşık')} {money(liveEquity ?? 0, false, language)}. {tx('Henüz emir gönderilmedi.')}</div>}
          {liveToken && <label className="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-white/10 p-3 text-sm"><input type="checkbox" checked={liveAcknowledged} onChange={event => setLiveAcknowledged(event.target.checked)} className="mt-1 accent-red-400" /><span>{tx('Gerçek para riski olduğunu anlıyorum. Binance hesabında otomatik Futures emirlerinin başlamasını onaylıyorum.')}</span></label>}
          {liveError && <p role="alert" className="mt-3 rounded-lg border border-red-300/20 bg-red-300/5 p-3 text-sm text-red-200">{liveError}</p>}
          <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><Button variant="outline" disabled={liveBusy} onClick={() => setLiveOpen(false)}>{tx('Vazgeç')}</Button>{!liveToken ? <Button disabled={liveBusy || (!status.live_access?.credentials_configured && (!liveKey || !liveSecret))} onClick={() => void checkLiveConnection()}>{liveBusy ? tx('Binance doğrulanıyor…') : tx('Bağlantıyı güvenli biçimde doğrula')}</Button> : <Button disabled={liveBusy || !liveAcknowledged} className="bg-red-500 text-white hover:bg-red-400" onClick={() => void activateLive()}>{liveBusy ? tx('Live modu açılıyor…') : tx('Onaylıyorum · Live modu aç')}</Button>}</div>
        </section>
      </div>}
    </main>
  );
}

function MetricCard({ icon: Icon, label, value, detail, positive = false, negative = false }: { icon: typeof Activity; label: string; value: string; detail: string; positive?: boolean; negative?: boolean }) {
  return <Card className="group relative overflow-hidden border-white/8 bg-gradient-to-br from-card via-card to-white/[.025] shadow-[0_14px_50px_rgba(0,0,0,.16)] transition duration-300 hover:-translate-y-0.5 hover:border-amber-300/15"><div className="absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-amber-300/25 to-transparent opacity-0 transition group-hover:opacity-100" /><CardContent className="flex items-start justify-between gap-4"><div><p className="text-xs font-medium text-muted-foreground">{label}</p><p className="mt-2 font-mono text-2xl font-semibold tracking-tight">{value}</p><p className={`mt-1.5 text-xs ${positive ? 'text-emerald-300' : negative ? 'text-red-300' : 'text-muted-foreground'}`}>{detail}</p></div><div className="grid size-9 place-items-center rounded-xl border border-white/8 bg-white/4 text-muted-foreground transition group-hover:border-amber-300/15 group-hover:text-amber-200"><Icon className="size-4" /></div></CardContent></Card>;
}

function RiskRow({ label, value, percent: valuePercent, tone, language }: { label: string; value: string; percent: number; tone: 'gold' | 'green' | 'blue'; language: Language }) {
  const toneClass = tone === 'green' ? '[&_[data-slot=progress-indicator]]:bg-emerald-400' : tone === 'blue' ? '[&_[data-slot=progress-indicator]]:bg-sky-400' : '[&_[data-slot=progress-indicator]]:bg-amber-400';
  return <div className="space-y-2.5"><div className="flex items-center justify-between gap-3 text-xs"><span className="text-muted-foreground">{label}</span><span className="font-mono">{value}</span></div><Progress value={Math.max(0, Math.min(valuePercent, 100))} className={toneClass} aria-label={`${label} ${language === 'en' ? 'percent' : 'yüzde'} ${valuePercent}`} /></div>;
}

function SideBadge({ side, language }: { side: string; language: Language }) {
  const classes = side === 'LONG' ? 'bg-emerald-400/10 text-emerald-300 ring-emerald-300/15' : side === 'SHORT' ? 'bg-red-400/10 text-red-300 ring-red-300/15' : 'bg-white/5 text-muted-foreground ring-white/8';
  return <Badge className={`${classes} ring-1`}>{side === 'WAIT' ? translate('Bekle', language) : side}</Badge>;
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

function formatTradeTime(timestamp: number, language: Language): string {
  if (!timestamp) return '—';
  return new Date(timestamp).toLocaleString(locale(language), {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function money(value: number, signed = false, language: Language = 'tr'): string {
  const prefix = signed && value > 0 ? '+' : '';
  return `${prefix}${new Intl.NumberFormat(locale(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)} USDT`;
}

function price(value: number, language: Language = 'tr'): string {
  return new Intl.NumberFormat(locale(language), { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(value);
}

function percent(value: number, language: Language = 'tr'): string {
  const prefix = value > 0 ? '+' : '';
  return `${prefix}%${value.toLocaleString(locale(language), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
