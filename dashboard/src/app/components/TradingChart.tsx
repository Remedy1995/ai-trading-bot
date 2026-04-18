'use client';

import { useEffect, useRef } from 'react';

interface CandleData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  ema9: number; ema21: number; ema50: number; ema200: number;
  bb_upper: number; bb_mid: number; bb_lower: number;
  rsi: number; macd: number; macd_sig: number; macd_hist: number;
  adx: number; plus_di: number; minus_di: number;
  obv: number; obv_ema: number; volume: number;
}

interface TradingLevels {
  entry?: number;
  take_profit?: number;
  stop_loss?: number;
  trail_stop?: number;
}

interface Props {
  history: CandleData[];
  levels?: TradingLevels | null;
  symbol: string;
  signals?: { id: string; bias: string; note: string }[];
  score?: number;
}

// ── Indicator Scorecard ───────────────────────────────────────────
function IndicatorCard({ id, bias, note }: { id: string; bias: string; note: string }) {
  const isBull = bias === 'BULL';
  const isBear = bias === 'BEAR';

  const label: Record<string, string> = {
    EMA_STACK:  'Trend Structure',
    EMA_MOM:    'Price Momentum',
    MACD:       'MACD Momentum',
    RSI:        'RSI Strength',
    BB:         'Bollinger Bands',
    ADX:        'Trend Strength',
    OBV:        'Volume Flow',
  };

  return (
    <div className={`flex items-start gap-2 rounded-lg p-2.5 border ${
      isBull ? 'bg-emerald-950/30 border-emerald-800/40' :
      isBear ? 'bg-red-950/30 border-red-800/40' :
               'bg-slate-900/50 border-slate-800'
    }`}>
      <div className={`mt-0.5 w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-black shrink-0 ${
        isBull ? 'bg-emerald-500 text-white' :
        isBear ? 'bg-red-500 text-white' :
                 'bg-slate-700 text-slate-400'
      }`}>
        {isBull ? '↑' : isBear ? '↓' : '–'}
      </div>
      <div className="min-w-0">
        <div className={`text-[10px] font-black uppercase tracking-wider ${
          isBull ? 'text-emerald-400' : isBear ? 'text-red-400' : 'text-slate-500'
        }`}>{label[id] ?? id}</div>
        <div className="text-[10px] text-slate-400 leading-tight mt-0.5 truncate">{note}</div>
      </div>
    </div>
  );
}

// ── Main Chart (candlesticks + key levels only) ───────────────────
function PriceChart({ history, levels }: { history: CandleData[]; levels?: TradingLevels | null }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!history?.length || !ref.current) return;
    let chart: any;

    import('lightweight-charts').then((lc) => {
      const { createChart, CrosshairMode, LineStyle, CandlestickSeries, LineSeries } = lc as any;

      chart = createChart(ref.current!, {
        width:  ref.current!.clientWidth,
        height: 280,
        layout:          { background: { color: '#0f172a' }, textColor: '#94a3b8' },
        grid:            { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair:       { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#334155' },
        timeScale:       { borderColor: '#334155', timeVisible: true, secondsVisible: false },
      });

      const toTs = (d: string) => Math.floor(new Date(d).getTime() / 1000);

      // Candlesticks
      const candles = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });
      candles.setData(history.map(c => ({
        time: toTs(c.date), open: c.open, high: c.high, low: c.low, close: c.close,
      })));

      // EMA21 and EMA50 only — clean, minimal
      chart.addSeries(LineSeries, { color: '#818cf8', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: 'EMA21' })
           .setData(history.map(c => ({ time: toTs(c.date), value: c.ema21 })));
      chart.addSeries(LineSeries, { color: '#38bdf8', lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: 'EMA50' })
           .setData(history.map(c => ({ time: toTs(c.date), value: c.ema50 })));

      // Entry / TP / SL / Trail as horizontal lines
      if (levels) {
        const pl = (price: number, color: string, title: string) => ({
          price, color, lineWidth: 2, lineStyle: LineStyle.Solid, axisLabelVisible: true, title,
        });
        if (levels.entry)       candles.createPriceLine(pl(levels.entry,       '#facc15', `📍 Entry`));
        if (levels.take_profit) candles.createPriceLine(pl(levels.take_profit, '#22c55e', `🎯 Take Profit`));
        if (levels.stop_loss)   candles.createPriceLine(pl(levels.stop_loss,   '#ef4444', `🛑 Stop Loss`));
        if (levels.trail_stop && levels.trail_stop !== levels.stop_loss)
          candles.createPriceLine(pl(levels.trail_stop, '#f97316', `📈 Trail Stop`));
      }

      chart.timeScale().fitContent();

      const ro = new ResizeObserver(() => {
        if (ref.current) chart.resize(ref.current.clientWidth, 280);
      });
      if (ref.current) ro.observe(ref.current);
      return () => ro.disconnect();
    });

    return () => { try { chart?.remove(); } catch {} };
  }, [history, levels]);

  return <div ref={ref} className="w-full" style={{ height: 280 }} />;
}

// ── Exported Component ────────────────────────────────────────────
export default function TradingChart({ history, levels, symbol, signals = [], score }: Props) {
  const bullCount = signals.filter(s => s.bias === 'BULL').length;
  const bearCount = signals.filter(s => s.bias === 'BEAR').length;

  return (
    <div className="w-full space-y-3 mt-3">

      {/* ── Price Chart ── */}
      <div className="rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
        {/* Chart header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800">
          <span className="text-[11px] font-black text-slate-300 uppercase tracking-wider">{symbol} — Price Chart</span>
          <div className="flex items-center gap-2 text-[10px]">
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-indigo-400 inline-block rounded"/> EMA21</span>
            <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-sky-400 inline-block rounded"/> EMA50</span>
            {levels?.entry       && <span className="text-yellow-400 font-bold">── Entry</span>}
            {levels?.take_profit && <span className="text-green-400 font-bold">── TP</span>}
            {levels?.stop_loss   && <span className="text-red-400 font-bold">── SL</span>}
          </div>
        </div>
        <PriceChart history={history} levels={levels} />
      </div>

      {/* ── Indicator Scorecard ── */}
      <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
        {/* Scorecard header */}
        <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800">
          <span className="text-[11px] font-black text-slate-300 uppercase tracking-wider">Signal Scorecard</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-emerald-400">{bullCount} Bullish</span>
            <span className="text-slate-600">·</span>
            <span className="text-[10px] font-bold text-red-400">{bearCount} Bearish</span>
            <span className="text-slate-600">·</span>
            <span className={`text-[10px] font-black px-2 py-0.5 rounded-full ${
              (score ?? 0) >= 4 ? 'bg-emerald-500/20 text-emerald-300' :
              (score ?? 0) <= -4 ? 'bg-red-500/20 text-red-300' :
              'bg-slate-700 text-slate-400'
            }`}>{score ?? 0}/7</span>
          </div>
        </div>

        {/* Signal grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 p-3">
          {signals.length > 0 ? signals.map(s => (
            <IndicatorCard key={s.id} id={s.id} bias={s.bias} note={s.note} />
          )) : (
            <div className="col-span-2 text-center text-slate-600 text-xs py-4">No signal data yet</div>
          )}
        </div>

        {/* Score bar */}
        <div className="px-3 pb-3">
          <div className="flex items-center gap-2">
            <span className="text-[9px] text-red-400 font-bold">BEAR</span>
            <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  (score ?? 0) >= 4 ? 'bg-emerald-500' :
                  (score ?? 0) <= -4 ? 'bg-red-500' : 'bg-amber-500'
                }`}
                style={{ width: `${((score ?? 0) + 7) / 14 * 100}%` }}
              />
            </div>
            <span className="text-[9px] text-emerald-400 font-bold">BULL</span>
          </div>
          <div className="text-center text-[9px] text-slate-500 mt-1">
            Score bar: left = bearish · center = neutral · right = bullish
          </div>
        </div>
      </div>

    </div>
  );
}
