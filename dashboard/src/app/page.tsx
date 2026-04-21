"use client";

import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, BarChart, Bar, Cell,
} from 'recharts';

const TradingChart = dynamic(() => import('./components/TradingChart'), { ssr: false });
import {
  TrendingUp, TrendingDown, Activity, DollarSign, Brain,
  BarChart3, AlertCircle, Shield, Zap, Target,
} from 'lucide-react';

// ─── helpers ──────────────────────────────────────────────────────

const clsx = (...cls: (string | false | undefined | null)[]) =>
  cls.filter(Boolean).join(' ');

function VerdictBadge({ v }: { v: string }) {
  const map: Record<string, string> = {
    STRONG_BUY:  'bg-emerald-500/20 text-emerald-300 border border-emerald-700',
    BUY_WATCH:   'bg-emerald-900/30 text-emerald-400 border border-emerald-900',
    STRONG_SELL: 'bg-rose-500/20 text-rose-300 border border-rose-700',
    SELL_WATCH:  'bg-rose-900/30 text-rose-400 border border-rose-900',
    NEUTRAL:     'bg-slate-800 text-slate-400 border border-slate-700',
  };
  return (
    <span className={clsx('px-2 py-0.5 rounded text-xs font-bold tracking-wide', map[v] ?? map.NEUTRAL)}>
      {v.replace('_', ' ')}
    </span>
  );
}

function SignalDot({ bias }: { bias: string }) {
  if (bias === 'BULL')    return <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 mr-1.5" />;
  if (bias === 'BEAR')    return <span className="inline-block w-2 h-2 rounded-full bg-rose-400 mr-1.5" />;
  return                         <span className="inline-block w-2 h-2 rounded-full bg-slate-600 mr-1.5" />;
}

// ─── main ─────────────────────────────────────────────────────────

export default function Dashboard() {
  const [data, setData]       = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab]         = useState<'enhanced' | 'history' | 'legacy' | 'backtest'>('enhanced');
  const [tradeAmountInput, setTradeAmountInput] = useState<number>(15);


  useEffect(() => {
    const load = () =>
      fetch('/api/data')
        .then(r => r.json())
        .then(d => {
          setData(d);
          setLoading(false);
          if (d?.settings?.trade_amount) setTradeAmountInput(Number(d.settings.trade_amount));
        })
        .catch(() => setLoading(false));

    load();
    const interval = setInterval(load, 30_000); // auto-refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const updateTimeframe = async (tf: string) => {
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timeframe: tf }),
      });
      if (res.ok) {
        const d = await fetch('/api/data').then(r => r.json());
        setData(d);
      }
    } catch (e) {
      console.error('Failed to update timeframe', e);
    }
  };

  const updateTradeAmount = async (amount: number) => {
    if (amount < 5) return;  // enforce $5 minimum to match exchange minimums
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_amount: amount }),
      });
      if (res.ok) {
        const d = await fetch('/api/data').then(r => r.json());
        setData(d);
      }
    } catch (e) {
      console.error('Failed to update trade amount', e);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500" />
      </div>
    );
  }

  const {
    botResults        = [],
    backtestResults   = [],
    sentimentResults  = [],
    enhancedResults   = {},
    enhancedBacktest  = [],
    tradeHistory      = [],
    settings          = { timeframe: '1h', trade_amount: 15 },
    tradeState        = {},
    balance           = { usdt_free: null, usdt_total: null },
    lastUpdated,
  } = data || {};

  const enhancedCoins: any[] = enhancedResults?.results ?? [];

  // Map coin ticker → trade status
  const openTradeCount = Object.values(tradeState as Record<string, any>).filter((t: any) => t.status === 'OPEN').length;
  const MAX_TRADES = 4;

  function getTradeStatus(coin: any): { label: string; style: string; emoji: string } {
    const ticker = coin.symbol ?? (coin.ticker + '/USDT');
    const inTrade = (tradeState as Record<string, any>)[ticker]?.status === 'OPEN';
    const verdict = coin.confluence?.verdict ?? 'NEUTRAL';

    if (inTrade) return { label: 'IN TRADE', style: 'bg-yellow-500/20 text-yellow-300 border border-yellow-600', emoji: '🟡' };
    if (verdict === 'STRONG_BUY' && openTradeCount < MAX_TRADES) return { label: 'READY', style: 'bg-emerald-500/20 text-emerald-300 border border-emerald-600', emoji: '🟢' };
    if (verdict === 'STRONG_BUY' && openTradeCount >= MAX_TRADES) return { label: 'QUEUED', style: 'bg-blue-500/20 text-blue-300 border border-blue-600', emoji: '⏳' };
    if (verdict === 'BUY_WATCH') return { label: 'WATCHING', style: 'bg-slate-700/40 text-slate-400 border border-slate-600', emoji: '👀' };
    return { label: 'WAITING', style: 'bg-slate-800/40 text-slate-500 border border-slate-700', emoji: '⏸️' };
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">

      {/* ── Header ── */}
      <header className="border-b border-slate-800 bg-slate-950/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Activity className="w-7 h-7 text-indigo-400" />
            <div>
              <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-cyan-400">
                AI Trading Terminal
              </h1>
              <p className="text-xs text-slate-500">
                Multi-Confluence Engine · EMA + MACD + RSI + BB + ATR/ADX + OBV
              </p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            {(() => {
              // Calculate Bot Status based on the last updated timestamp
              const now = new Date().getTime();
              const updatedTime = enhancedResults?.generated ? new Date(enhancedResults.generated).getTime() : 0;
              const diffMinutes = (now - updatedTime) / (1000 * 60);
              
              // 5 minute interval + 2 minute buffer
              const isLive = diffMinutes <= 7 && updatedTime > 0;
              
              return (
                <div className={clsx(
                  "flex items-center gap-2 px-3 py-1 rounded-full border text-xs font-bold uppercase tracking-wider",
                  isLive ? "bg-emerald-950/40 text-emerald-400 border-emerald-900/60" : "bg-rose-950/40 text-rose-400 border-rose-900/60"
                )}>
                  <span className={clsx("w-2 h-2 rounded-full", isLive ? "bg-emerald-500 animate-pulse" : "bg-rose-500")} />
                  {isLive ? "BOT: ACTIVE" : "BOT: OFFLINE"}
                </div>
              );
            })()}
            <div className="text-[10px] text-slate-500 tracking-wider">
              {lastUpdated ? `LAST SCAN: ${new Date(lastUpdated).toLocaleTimeString()}` : ''}
            </div>

            {/* Binance Balance */}
            <div className="flex items-center gap-3 mt-2 bg-slate-900 border border-slate-800 rounded-lg px-3 py-2">
              <DollarSign className="w-3.5 h-3.5 text-emerald-400" />
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Binance Balance</div>
              <div className="ml-auto flex items-center gap-3">
                <div className="text-center">
                  <div className="text-[9px] text-slate-500 uppercase">Available</div>
                  <div className="text-sm font-black text-emerald-400">
                    {(balance as any)?.usdt_free != null ? `$${Number((balance as any).usdt_free).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-[9px] text-slate-500 uppercase">Total</div>
                  <div className="text-sm font-black text-slate-200">
                    {(balance as any)?.usdt_total != null ? `$${Number((balance as any).usdt_total).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                  </div>
                </div>
              </div>
            </div>

            {/* Timeframe + Trade Amount row */}
            <div className="flex items-center gap-2 mt-2">
              {/* Timeframe Selector */}
              <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800">
                {['5m', '15m', '1h', '4h', '1d'].map((tf) => (
                  <button
                    key={tf}
                    onClick={() => updateTimeframe(tf)}
                    className={clsx(
                      "px-2 py-0.5 rounded text-[10px] font-bold transition-all",
                      settings.timeframe === tf
                        ? "bg-indigo-500 text-white shadow-lg shadow-indigo-500/20"
                        : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                    )}
                  >
                    {tf.toUpperCase()}
                  </button>
                ))}
              </div>

              {/* Trade Amount */}
              <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-800 rounded-lg px-2 py-1">
                <DollarSign className="w-3 h-3 text-emerald-400 shrink-0" />
                <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider whitespace-nowrap">Trade $</span>
                <input
                  type="number"
                  min={5}
                  step={1}
                  value={tradeAmountInput}
                  onChange={(e) => setTradeAmountInput(Number(e.target.value))}
                  onBlur={() => updateTradeAmount(tradeAmountInput)}
                  onKeyDown={(e) => { if (e.key === 'Enter') updateTradeAmount(tradeAmountInput); }}
                  className="w-14 bg-slate-800 text-emerald-300 font-black text-[11px] text-center rounded px-1 py-0.5 border border-slate-700 focus:outline-none focus:border-indigo-500"
                />
              </div>
            </div>
          </div>
        </div>

        <div className="max-w-7xl mx-auto px-6 flex gap-1 pb-0">
          {[
            { id: 'enhanced', label: 'Enhanced Signals', icon: <Zap className="w-3.5 h-3.5" /> },
            { id: 'history',  label: 'Live History',     icon: <Activity className="w-3.5 h-3.5" /> },
            { id: 'backtest', label: 'Backtest',         icon: <BarChart3 className="w-3.5 h-3.5" /> },
            { id: 'legacy',   label: 'Legacy',           icon: <Brain className="w-3.5 h-3.5" /> },
          ].map(t => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as any)}
              className={clsx(
                'flex items-center gap-1.5 px-4 py-2 text-sm rounded-t-lg transition-colors border-b-2',
                tab === t.id
                  ? 'text-indigo-300 border-indigo-400 bg-slate-900/60'
                  : 'text-slate-500 border-transparent hover:text-slate-300',
              )}
            >
              {t.icon}{t.label}
            </button>
          ))}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">

        {/* ══════════════════════════════════════════════════════
            ENHANCED SIGNALS TAB
        ══════════════════════════════════════════════════════ */}
        {tab === 'enhanced' && (
          <>
            {enhancedCoins.length === 0 ? (
              <EmptyState msg="Run python3 enhanced_bot.py to generate enhanced signals." />
            ) : (
              <>
                {/* Strategy legend */}
                <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 text-sm text-slate-400">
                  <p className="font-semibold text-slate-300 mb-1 flex items-center gap-2">
                    <Shield className="w-4 h-4 text-indigo-400" /> Multi-Confluence Strategy
                  </p>
                  <p>
                    Signals trade only when <span className="text-indigo-300 font-bold">4+ of 7 independent indicators agree</span>.
                    Stop-loss and take-profit are <span className="text-amber-400">ATR-based</span> (adapts to current volatility).
                    Minimum <span className="text-emerald-400">3:1 risk-reward</span> on every trade.
                  </p>
                  <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    {['EMA Stack', 'EMA Momentum', 'MACD', 'RSI(14)', 'Bollinger %B', 'ADX + DI', 'OBV'].map(ind => (
                      <span key={ind} className="bg-slate-800 rounded px-2 py-1">{ind}</span>
                    ))}
                  </div>
                </div>

                {/* Coin cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {enhancedCoins.map((coin: any) => {
                    if (coin.error) return null;
                    const conf    = coin.confluence ?? {};
                    const lvl     = coin.levels;
                    const verdict = conf.verdict ?? 'NEUTRAL';
                    const isBuy   = verdict === 'STRONG_BUY';
                    const isSell  = verdict === 'STRONG_SELL';
                    const ind     = coin.indicators ?? {};
                    const ts      = getTradeStatus(coin);
                    const isInTrade = ts.label === 'IN TRADE';
                    const openTrade = (tradeState as Record<string, any>)[coin.symbol ?? (coin.ticker + '/USDT')];

                    return (
                      <div
                        key={coin.coin}
                        className={clsx(
                          'rounded-xl border p-6 space-y-4',
                          isInTrade ? 'bg-yellow-950/20 border-yellow-700/60' :
                          isBuy     ? 'bg-emerald-950/25 border-emerald-800/60' :
                          isSell    ? 'bg-rose-950/25 border-rose-800/60' :
                                      'bg-slate-900/40 border-slate-800',
                        )}
                      >
                        {/* Header */}
                        <div className="flex justify-between items-start">
                          <div>
                            <div className="text-2xl font-extrabold">{coin.ticker}</div>
                            <div className="text-xs text-slate-500 uppercase">{coin.coin}</div>
                          </div>
                          <div className="flex flex-col items-end gap-1">
                            <VerdictBadge v={verdict} />
                            <span className={clsx('px-2 py-0.5 rounded text-xs font-bold tracking-wide', ts.style)}>
                              {ts.emoji} {ts.label}
                            </span>
                          </div>
                        </div>

                        {/* In-trade live stats */}
                        {isInTrade && openTrade && (
                          <div className="bg-yellow-950/30 border border-yellow-800/40 rounded-lg p-3 space-y-1 text-xs">
                            <div className="flex justify-between">
                              <span className="text-slate-400">Bought at</span>
                              <span className="font-bold text-yellow-300">${openTrade.buy_price?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Take Profit</span>
                              <span className="font-bold text-emerald-400">${openTrade.take_profit?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Stop Loss</span>
                              <span className="font-bold text-rose-400">${openTrade.stop_loss?.toLocaleString(undefined, { maximumFractionDigits: 4 })}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">P&L</span>
                              <span className={clsx('font-bold', openTrade.buy_price ? ((coin.current_price - openTrade.buy_price) / openTrade.buy_price * 100) >= 0 ? 'text-emerald-400' : 'text-rose-400' : 'text-slate-400')}>
                                {openTrade.buy_price ? ((coin.current_price - openTrade.buy_price) / openTrade.buy_price * 100).toFixed(2) : '0.00'}%
                              </span>
                            </div>
                          </div>
                        )}

                        {/* Price */}
                        <div className="flex items-end gap-2">
                          <span className="text-3xl font-bold">
                            ${coin.current_price?.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                          </span>
                          <span className={clsx(
                            'text-sm mb-0.5',
                            coin.change_24h >= 0 ? 'text-emerald-400' : 'text-rose-400',
                          )}>
                            {coin.change_24h >= 0 ? '+' : ''}{coin.change_24h?.toFixed(2)}%
                          </span>
                        </div>

                        {/* Score bar */}
                        <div>
                          <div className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>Confluence Score</span>
                            <span className="font-bold text-slate-300">
                              {conf.bull_votes} BULL · {conf.bear_votes} BEAR · score {conf.score}/7
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-2">
                            <div
                              className={clsx(
                                'h-2 rounded-full transition-all',
                                conf.score >= 4 ? 'bg-emerald-500' :
                                conf.score <= -4 ? 'bg-rose-500' : 'bg-slate-600',
                              )}
                              style={{ width: `${((conf.score + 7) / 14) * 100}%` }}
                            />
                          </div>
                        </div>

                        {/* Signal list */}
                        <div className="space-y-1">
                          {(conf.signals ?? []).map((s: any) => (
                            <div key={s.id} className="flex items-start text-xs text-slate-400">
                              <SignalDot bias={s.bias} />
                              <span className="font-mono text-slate-500 w-20 shrink-0">{s.id}</span>
                              <span className="truncate">{s.note}</span>
                            </div>
                          ))}
                        </div>

                        {/* Trade levels — hidden when IN TRADE to avoid duplicate info */}
                        {lvl && !isInTrade && (
                          <div className="border-t border-slate-800 pt-3 space-y-1 text-sm">
                            <div className="flex justify-between">
                              <span className="text-slate-500">Entry</span>
                              <span className="font-semibold">${lvl.entry?.toLocaleString()}</span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-rose-400">Stop</span>
                              <span className="text-rose-400 font-semibold">
                                ${lvl.stop_loss?.toLocaleString()} <span className="text-xs">(-{lvl.stop_pct}%)</span>
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-emerald-400">Target</span>
                              <span className="text-emerald-400 font-semibold">
                                ${lvl.take_profit?.toLocaleString()} <span className="text-xs">(+{lvl.target_pct}%)</span>
                              </span>
                            </div>
                            <div className="flex justify-between border-t border-slate-800 pt-1 mt-1">
                              <span className="text-slate-500">Risk:Reward</span>
                              <span className="font-bold text-amber-400">{lvl.risk_reward}:1</span>
                            </div>
                          </div>
                        )}

                        {/* Key indicators */}
                        <div className="grid grid-cols-3 gap-2 text-xs border-t border-slate-800 pt-3">
                          {[
                            ['RSI', `${ind.rsi}`],
                            ['ADX', `${ind.adx}`],
                            ['ATR', `$${ind.atr?.toLocaleString(undefined, { maximumFractionDigits: 0 })}`],
                          ].map(([k, v]) => (
                            <div key={k} className="bg-slate-950 rounded p-2 text-center">
                              <div className="text-slate-500">{k}</div>
                              <div className="font-bold text-slate-200">{v}</div>
                            </div>
                          ))}
                        </div>

                        {/* Full Trading Chart */}
                        {coin.history?.length > 0 && (() => {
                          const trade = tradeState?.[coin.symbol];
                          const chartLevels = trade ? {
                            entry:       trade.buy_price,
                            take_profit: trade.take_profit,
                            stop_loss:   trade.stop_loss,
                            trail_stop:  trade.highest_price && trade.trail_atr
                                           ? Math.max(trade.stop_loss, trade.highest_price - 2 * trade.trail_atr)
                                           : trade.stop_loss,
                          } : coin.levels ? {
                            entry:       coin.levels.entry,
                            take_profit: coin.levels.take_profit,
                            stop_loss:   coin.levels.stop_loss,
                          } : null;
                          return (
                            <TradingChart
                              history={coin.history}
                              levels={chartLevels}
                              symbol={coin.symbol ?? coin.ticker}
                              signals={coin.confluence?.signals ?? []}
                              score={coin.confluence?.score ?? 0}
                            />
                          );
                        })()}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════════
            LIVE HISTORY TAB
        ══════════════════════════════════════════════════════ */}
        {tab === 'history' && (
          <section>
            <SectionHeader icon={<Activity className="w-5 h-5 text-indigo-400" />}
                           title="Live Execution Trade History" />

            {enhancedResults?.aggregate_stats && (
               <div className="space-y-4 mb-8">
                 {/* Financial Metrics */}
                 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                   <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 text-center shadow-lg shadow-black/20">
                     <div className="text-slate-500 text-[10px] uppercase font-bold tracking-widest mb-1">Total Capital Invested</div>
                     <div className="text-2xl font-black text-slate-100 flex items-center justify-center gap-1">
                       <span className="text-slate-500 text-sm">$</span>
                       {(enhancedResults.aggregate_stats.total_invested_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                     </div>
                   </div>
                   <div className="bg-emerald-950/20 border border-emerald-900/50 rounded-xl p-4 text-center">
                     <div className="text-emerald-500/80 text-[10px] uppercase font-bold tracking-widest mb-1">Gross Gains (+)</div>
                     <div className="text-2xl font-black text-emerald-400 flex items-center justify-center gap-1">
                       <span className="text-emerald-600 text-sm">$</span>
                       {(enhancedResults.aggregate_stats.cumulative_gains_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                     </div>
                   </div>
                   <div className="bg-rose-950/20 border border-rose-900/50 rounded-xl p-4 text-center">
                     <div className="text-rose-500/80 text-[10px] uppercase font-bold tracking-widest mb-1">Gross Losses (-)</div>
                     <div className="text-2xl font-black text-rose-400 flex items-center justify-center gap-1">
                       <span className="text-rose-600 text-sm">$</span>
                       {(enhancedResults.aggregate_stats.cumulative_losses_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                     </div>
                   </div>
                   <div className={clsx(
                     "border rounded-xl p-4 text-center shadow-xl",
                     (enhancedResults.aggregate_stats.net_pnl_usd || 0) >= 0
                       ? "bg-indigo-900/30 border-indigo-500/50 shadow-indigo-500/10"
                       : "bg-rose-900/30 border-rose-500/50 shadow-rose-500/10"
                   )}>
                     <div className="text-indigo-400/80 text-[10px] uppercase font-bold tracking-widest mb-1">Net PnL (after fees)</div>
                     <div className={clsx(
                       "text-2xl font-black flex items-center justify-center gap-1",
                       (enhancedResults.aggregate_stats.net_pnl_usd || 0) >= 0 ? "text-indigo-300" : "text-rose-300"
                     )}>
                       <span className="opacity-60 text-sm">$</span>
                       {(enhancedResults.aggregate_stats.net_pnl_usd || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                     </div>
                     <div className="text-slate-500 text-[9px] mt-1">
                       fees paid: ${(enhancedResults.aggregate_stats.total_fees_usd || 0).toFixed(3)}
                     </div>
                   </div>
                 </div>

                 {/* Trading Counts */}
                 <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                   <div className="bg-slate-900/30 border border-slate-800/50 rounded-xl p-3 text-center">
                     <div className="text-slate-500 text-[10px] uppercase font-bold tracking-tight mb-0.5">Total Closed</div>
                     <div className="text-lg font-bold text-slate-300">{enhancedResults.aggregate_stats.total_trades || 0}</div>
                   </div>
                   <div className="bg-amber-950/20 border border-amber-900/30 rounded-xl p-3 text-center">
                     <div className="text-amber-500/60 text-[10px] uppercase font-bold tracking-tight mb-0.5">Active Trades</div>
                     <div className="text-lg font-bold text-amber-400">{openTradeCount} / {MAX_TRADES}</div>
                   </div>
                   <div className="bg-emerald-950/10 border border-emerald-900/20 rounded-xl p-3 text-center">
                     <div className="text-emerald-500/60 text-[10px] uppercase font-bold tracking-tight mb-0.5">Win Rate</div>
                     <div className="text-lg font-bold text-emerald-400">
                       {enhancedResults.aggregate_stats.total_trades > 0 
                         ? ((enhancedResults.aggregate_stats.wins / enhancedResults.aggregate_stats.total_trades) * 100).toFixed(1) 
                         : '0.0'}%
                     </div>
                   </div>
                   <div className="bg-rose-950/10 border border-rose-900/20 rounded-xl p-3 text-center">
                     <div className="text-rose-500/60 text-[10px] uppercase font-bold tracking-tight mb-0.5">Lose Rate</div>
                     <div className="text-lg font-bold text-rose-400">
                       {enhancedResults.aggregate_stats.total_trades > 0 
                         ? ((enhancedResults.aggregate_stats.losses / enhancedResults.aggregate_stats.total_trades) * 100).toFixed(1) 
                         : '0.0'}%
                     </div>
                   </div>
                 </div>
               </div>
            )}
             {tradeHistory.length === 0 ? (
              <EmptyState msg="No simulated trades have executed yet. Leave the bot running to populate this view!" />
            ) : (
              <div className="space-y-6">
                {(() => {
                  const groupedHistory: Record<string, string[]> = {};
                  [...tradeHistory].reverse().forEach((line: string) => {
                    const match = line.match(/^\[(.*?)\s\d{2}:\d{2}:\d{2}\]/);
                    const date = match ? match[1] : 'Unknown Date';
                    if (!groupedHistory[date]) groupedHistory[date] = [];
                    groupedHistory[date].push(line);
                  });

                  return Object.keys(groupedHistory).sort((a, b) => b.localeCompare(a)).map((date) => (
                    <div key={date} className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden">
                      <div className="bg-slate-800/50 px-4 py-2 border-b border-slate-800 text-sm font-bold text-slate-300 tracking-widest uppercase">
                        📅 {date}
                      </div>
                      <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
                        {groupedHistory[date].map((line: string, i: number) => {
                          const isWin = line.includes('TAKE_PROFIT') || line.includes('WON');
                          const isLoss = line.includes('STOP_LOSS') || line.includes('LOST');
                          const cleanLine = line.replace(/^\[.*?\]\s*/, ''); // hide the full timestamp since date is broken out, or keep time? Let's keep it but just time.
                          const timeMatch = line.match(/^\[.*?\s(\d{2}:\d{2}:\d{2})\]/);
                          const timeOnly = timeMatch ? timeMatch[1] : '';

                          return (
                            <div key={i} className={clsx(
                              "p-3 border rounded-lg text-sm font-mono flex items-start gap-3",
                              isWin ? "bg-emerald-950/30 border-emerald-900/50 text-emerald-300" :
                              isLoss ? "bg-rose-950/30 border-rose-900/50 text-rose-300" :
                              "bg-amber-950/20 border-amber-900/40 text-amber-300"
                            )}>
                               <div className="flex flex-col items-center">
                                 <span className="text-lg leading-none mb-1">{isWin ? '🟢' : isLoss ? '🔴' : '🟡'}</span>
                                 {timeOnly && <span className="text-[10px] opacity-60 font-sans tracking-tighter">{timeOnly}</span>}
                               </div>
                               <span className="mt-0.5">{cleanLine}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ));
                })()}
              </div>
            )}
          </section>
        )}

        {/* ══════════════════════════════════════════════════════
            BACKTEST TAB
        ══════════════════════════════════════════════════════ */}
        {tab === 'backtest' && (
          <>
            {/* Enhanced backtest */}
            {enhancedBacktest.length > 0 && (
              <section>
                <SectionHeader icon={<Target className="w-5 h-5 text-indigo-400" />}
                               title="Enhanced Backtest (Multi-Confluence + ATR Trailing Stops)" />
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  {enhancedBacktest.map((res: any) => <BacktestCard key={res.coin} res={res} />)}
                </div>
              </section>
            )}

            {/* Legacy backtest */}
            {backtestResults.length > 0 && (
              <section>
                <SectionHeader icon={<DollarSign className="w-5 h-5 text-amber-400" />}
                               title="Legacy Backtest (MA Crossover + Fixed Stops)" />
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                  {backtestResults.map((res: any) => <BacktestCard key={res.coin} res={res} />)}
                </div>
              </section>
            )}

            {enhancedBacktest.length === 0 && backtestResults.length === 0 && (
              <EmptyState msg="Run python3 enhanced_backtest.py to generate backtest results." />
            )}
          </>
        )}

        {/* ══════════════════════════════════════════════════════
            LEGACY TAB
        ══════════════════════════════════════════════════════ */}
        {tab === 'legacy' && (
          <>
            <section>
              <SectionHeader icon={<BarChart3 className="w-5 h-5 text-slate-400" />}
                             title="Legacy Signals (50/200-day MA Crossover)" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {botResults.map((coin: any) => {
                  const bull = coin.signal === 'BULLISH';
                  const bear = coin.signal === 'BEARISH';
                  return (
                    <div key={coin.crypto_id} className={clsx(
                      'rounded-xl p-5 border',
                      bull ? 'bg-emerald-950/20 border-emerald-900/50' :
                      bear ? 'bg-rose-950/20 border-rose-900/50' : 'bg-slate-900/50 border-slate-800',
                    )}>
                      <div className="flex justify-between mb-3">
                        <div>
                          <div className="font-bold uppercase">{coin.crypto_id}</div>
                          <div className="text-xs text-slate-500">{coin.type ?? 'No Crossover'}</div>
                        </div>
                        <span className="text-2xl">{coin.emoji}</span>
                      </div>
                      <div className="text-2xl font-bold mb-3">
                        ${coin.current_price?.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                        <span className={clsx('text-sm ml-2', coin.change_24h >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                          {coin.change_24h >= 0 ? '+' : ''}{coin.change_24h?.toFixed(2)}%
                        </span>
                      </div>
                      <div className="space-y-1 text-sm">
                        <Row label="Action"   val={coin.action}   accent={bull ? 'emerald' : bear ? 'rose' : 'amber'} />
                        <Row label="50-day MA" val={`$${coin.short_ma?.toLocaleString()}`} />
                        <Row label="200-day MA" val={`$${coin.long_ma?.toLocaleString()}`} />
                        <Row label="RSI"       val={String(coin.rsi)}
                             accent={coin.rsi > 70 ? 'rose' : coin.rsi < 30 ? 'emerald' : undefined} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {sentimentResults.length > 0 && (
              <section>
                <SectionHeader icon={<Brain className="w-5 h-5 text-purple-400" />}
                               title="Dual Confirmation (MA + AI Sentiment)" />
                <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden">
                  <table className="w-full text-sm text-left">
                    <thead>
                      <tr className="bg-slate-900 text-slate-400 text-xs uppercase border-b border-slate-800">
                        <th className="p-4">Asset</th>
                        <th className="p-4">Chart</th>
                        <th className="p-4 text-purple-400">AI Sentiment</th>
                        <th className="p-4">Decision</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {sentimentResults.map((row: any) => (
                        <tr key={row.coin} className="hover:bg-slate-800/20">
                          <td className="p-4 font-bold uppercase">{row.ticker}</td>
                          <td className="p-4"><VerdictBadge v={row.chart?.verdict ?? 'NEUTRAL'} /></td>
                          <td className="p-4">
                            <VerdictBadge v={row.sentiment?.verdict ?? 'NEUTRAL'} />
                            <div className="text-xs text-slate-500 mt-1 max-w-xs truncate">{row.sentiment?.reason}</div>
                          </td>
                          <td className="p-4 font-bold">{row.decision?.final_signal}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {botResults.length === 0 && (
              <EmptyState msg="Run python3 trading_bot.py to generate legacy signals." />
            )}
          </>
        )}

      </main>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      {icon}
      <h2 className="text-lg font-semibold">{title}</h2>
    </div>
  );
}

function Row({ label, val, accent }: { label: string; val: string; accent?: string }) {
  const color =
    accent === 'emerald' ? 'text-emerald-400' :
    accent === 'rose'    ? 'text-rose-400' :
    accent === 'amber'   ? 'text-amber-400' : 'text-slate-300';
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={clsx('font-medium', color)}>{val ?? '—'}</span>
    </div>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return (
    <div className="col-span-3 text-center py-16 text-slate-500 bg-slate-900/30 rounded-xl border border-dashed border-slate-700">
      <AlertCircle className="w-10 h-10 mx-auto mb-3 opacity-40" />
      <p>{msg}</p>
    </div>
  );
}

function BacktestCard({ res }: { res: any }) {
  const m = res.metrics ?? {};
  const profitable = (m.profit_usd ?? 0) >= 0;

  // Compact trade list for bar chart
  const tradeChart = (res.trades ?? []).map((t: any, i: number) => ({
    n: i + 1,
    pnl: t.pnl_pct ?? 0,
  }));

  return (
    <div className="bg-slate-900/40 border border-slate-800 rounded-xl p-6">
      <div className="flex justify-between items-center mb-5">
        <h3 className="text-lg font-bold">{res.coin} / {res.ticker}</h3>
        <div className={clsx(
          'px-3 py-1 rounded-full text-sm font-bold',
          profitable ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400',
        )}>
          {m.total_return_pct >= 0 ? '+' : ''}{m.total_return_pct}%
          <span className="ml-2 text-xs opacity-60">Grade: {m.grade}</span>
        </div>
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {[
          { label: 'Win Rate',      val: `${m.win_rate_pct}%`,      color: m.win_rate_pct >= 55 ? 'text-emerald-400' : 'text-rose-400' },
          { label: 'Net Profit',    val: `$${m.profit_usd?.toLocaleString()}`, color: profitable ? 'text-emerald-400' : 'text-rose-400' },
          { label: 'Profit Factor', val: String(m.profit_factor),   color: m.profit_factor >= 1.5 ? 'text-emerald-400' : 'text-amber-400' },
          { label: 'Sharpe',        val: String(m.sharpe_ratio),    color: m.sharpe_ratio >= 1 ? 'text-emerald-400' : 'text-slate-300' },
          { label: 'Trades',        val: String(m.total_trades),    color: 'text-slate-300' },
          { label: 'Avg Win',       val: `${m.avg_win_pct}%`,       color: 'text-emerald-400' },
          { label: 'Avg Loss',      val: `${m.avg_loss_pct}%`,      color: 'text-rose-400' },
          { label: 'Max DD',        val: `-${m.max_drawdown_pct}%`, color: 'text-rose-400' },
        ].map(({ label, val, color }) => (
          <div key={label} className="bg-slate-950 rounded-lg p-3">
            <div className="text-xs text-slate-500 mb-1">{label}</div>
            <div className={clsx('font-semibold text-sm', color)}>{val}</div>
          </div>
        ))}
      </div>

      {/* Trade P&L bar chart */}
      {tradeChart.length > 0 && (
        <div className="h-24 mb-4">
          <p className="text-xs text-slate-500 mb-1">Trade-by-trade P&L (%)</p>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={tradeChart} barCategoryGap="20%">
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="n" hide />
              <YAxis stroke="#475569" fontSize={9} tickFormatter={v => `${v}%`} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }}
                formatter={(v: any) => [`${v}%`, 'P&L']}
              />
              <ReferenceLine y={0} stroke="#475569" />
              <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                {tradeChart.map((t: any, i: number) => (
                  <Cell key={i} fill={t.pnl >= 0 ? '#34d399' : '#f87171'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Equity curve */}
      {res.equity_curve?.length > 0 && (
        <div className="h-52 border-t border-slate-800 pt-4">
          <p className="text-xs text-slate-500 mb-1">Portfolio equity curve</p>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={res.equity_curve}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis dataKey="date" stroke="#475569" fontSize={9} tickFormatter={v => v.substring(5)} minTickGap={30} />
              <YAxis domain={['auto', 'auto']} stroke="#475569" fontSize={9} tickFormatter={v => `$${(v / 1000).toFixed(1)}k`} />
              <Tooltip
                contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 6, fontSize: 11 }}
                formatter={(v: any) => [`$${Number(v).toLocaleString()}`, 'Portfolio']}
              />
              <ReferenceLine y={10000} stroke="#475569" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="equity" stroke="#818cf8" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
