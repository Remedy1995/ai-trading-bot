'use client';

import { useEffect, useRef } from 'react';

interface CandleData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema9: number;
  ema21: number;
  ema50: number;
  ema200: number;
  bb_upper: number;
  bb_mid: number;
  bb_lower: number;
  rsi: number;
  macd: number;
  macd_sig: number;
  macd_hist: number;
  adx: number;
  plus_di: number;
  minus_di: number;
  obv: number;
  obv_ema: number;
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
}

export default function TradingChart({ history, levels, symbol }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef  = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const adxRef  = useRef<HTMLDivElement>(null);
  const obvRef  = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!history?.length || !mainRef.current || !rsiRef.current || !macdRef.current || !adxRef.current || !obvRef.current) return;

    const charts: any[] = [];

    import('lightweight-charts').then((lc) => {
      const {
        createChart, CrosshairMode, LineStyle,
        CandlestickSeries, LineSeries, HistogramSeries,
      } = lc as any;

      const toTs = (d: string) => Math.floor(new Date(d).getTime() / 1000);

      const makeChart = (el: HTMLDivElement, height: number) => {
        const c = createChart(el, {
          width:  el.clientWidth,
          height,
          layout:          { background: { color: '#0f172a' }, textColor: '#94a3b8' },
          grid:            { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
          crosshair:       { mode: CrosshairMode.Normal },
          rightPriceScale: { borderColor: '#334155' },
          timeScale:       { borderColor: '#334155', timeVisible: true, secondsVisible: false },
        });
        charts.push(c);
        return c;
      };

      const addSeries = (chart: any, SeriesClass: any, opts: any) =>
        chart.addSeries(SeriesClass, opts);

      // ── 1. MAIN — Candlesticks + EMAs + Bollinger Bands ──────────
      const main = makeChart(mainRef.current!, 320);

      const candles = addSeries(main, CandlestickSeries, {
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });
      candles.setData(history.map(c => ({
        time: toTs(c.date), open: c.open, high: c.high, low: c.low, close: c.close,
      })));

      // EMA Stack (Indicators 1 & 2)
      const emaConfigs = [
        { key: 'ema9',   color: '#f59e0b', title: 'EMA9'   },
        { key: 'ema21',  color: '#818cf8', title: 'EMA21'  },
        { key: 'ema50',  color: '#38bdf8', title: 'EMA50'  },
        { key: 'ema200', color: '#f472b6', title: 'EMA200' },
      ];
      emaConfigs.forEach(({ key, color, title }) => {
        const s = addSeries(main, LineSeries, {
          color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title,
        });
        s.setData(history.map((c: any) => ({ time: toTs(c.date), value: c[key] })));
      });

      // Bollinger Bands (Indicator 5)
      const bbConfigs = [
        { key: 'bb_upper', title: 'BB Upper', style: LineStyle.Dashed },
        { key: 'bb_mid',   title: 'BB Mid',   style: LineStyle.Dotted },
        { key: 'bb_lower', title: 'BB Lower', style: LineStyle.Dashed },
      ];
      bbConfigs.forEach(({ key, title, style }) => {
        const s = addSeries(main, LineSeries, {
          color: '#475569', lineWidth: 1, lineStyle: style,
          priceLineVisible: false, lastValueVisible: false, title,
        });
        s.setData(history.map((c: any) => ({ time: toTs(c.date), value: c[key] })));
      });

      // Entry / TP / SL / Trail price lines on candles
      if (levels) {
        const pl = (price: number, color: string, title: string) => ({
          price, color, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: true, title,
        });
        if (levels.entry)       candles.createPriceLine(pl(levels.entry,       '#facc15', `Entry $${levels.entry}`));
        if (levels.take_profit) candles.createPriceLine(pl(levels.take_profit, '#22c55e', `TP $${levels.take_profit}`));
        if (levels.stop_loss)   candles.createPriceLine(pl(levels.stop_loss,   '#ef4444', `SL $${levels.stop_loss}`));
        if (levels.trail_stop)  candles.createPriceLine(pl(levels.trail_stop,  '#f97316', `Trail $${levels.trail_stop}`));
      }
      main.timeScale().fitContent();

      // ── 2. RSI (Indicator 4) ──────────────────────────────────────
      const rsiChart = makeChart(rsiRef.current!, 100);
      addSeries(rsiChart, LineSeries, { color: '#a78bfa', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'RSI' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.rsi })));
      addSeries(rsiChart, LineSeries, { color: '#ef444466', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: '70' })
        .setData(history.map(c => ({ time: toTs(c.date), value: 70 })));
      addSeries(rsiChart, LineSeries, { color: '#22c55e66', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: '30' })
        .setData(history.map(c => ({ time: toTs(c.date), value: 30 })));
      rsiChart.timeScale().fitContent();

      // ── 3. MACD (Indicator 3) ─────────────────────────────────────
      const macdChart = makeChart(macdRef.current!, 100);
      addSeries(macdChart, LineSeries, { color: '#38bdf8', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'MACD' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.macd })));
      addSeries(macdChart, LineSeries, { color: '#f97316', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'Signal' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.macd_sig })));
      addSeries(macdChart, HistogramSeries, { priceLineVisible: false, lastValueVisible: false })
        .setData(history.map(c => ({
          time: toTs(c.date), value: c.macd_hist,
          color: c.macd_hist >= 0 ? '#22c55e88' : '#ef444488',
        })));
      macdChart.timeScale().fitContent();

      // ── 4. ADX (Indicator 6) ──────────────────────────────────────
      const adxChart = makeChart(adxRef.current!, 100);
      addSeries(adxChart, LineSeries, { color: '#facc15', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'ADX' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.adx })));
      addSeries(adxChart, LineSeries, { color: '#22c55e', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: '+DI' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.plus_di })));
      addSeries(adxChart, LineSeries, { color: '#ef4444', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: '-DI' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.minus_di })));
      addSeries(adxChart, LineSeries, { color: '#47556966', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: '20' })
        .setData(history.map(c => ({ time: toTs(c.date), value: 20 })));
      adxChart.timeScale().fitContent();

      // ── 5. OBV (Indicator 7) ──────────────────────────────────────
      const obvChart = makeChart(obvRef.current!, 100);
      addSeries(obvChart, LineSeries, { color: '#34d399', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'OBV' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.obv })));
      addSeries(obvChart, LineSeries, { color: '#f472b6', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true, title: 'OBV EMA' })
        .setData(history.map(c => ({ time: toTs(c.date), value: c.obv_ema })));
      obvChart.timeScale().fitContent();

      // ── Sync time scale across all panels ────────────────────────
      const allCharts = [main, rsiChart, macdChart, adxChart, obvChart];
      allCharts.forEach(src => {
        src.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
          allCharts.filter(t => t !== src).forEach(t => {
            t.timeScale().setVisibleLogicalRange(range);
          });
        });
      });

      // ── Resize observer ───────────────────────────────────────────
      const refs = [mainRef, rsiRef, macdRef, adxRef, obvRef];
      const heights = [320, 100, 100, 100, 100];
      const ro = new ResizeObserver(() => {
        allCharts.forEach((ch, i) => {
          const el = refs[i].current;
          if (el) ch.resize(el.clientWidth, heights[i]);
        });
      });
      if (mainRef.current) ro.observe(mainRef.current);

      return () => { ro.disconnect(); };
    });

    return () => { charts.forEach(c => { try { c.remove(); } catch {} }); };
  }, [history, levels]);

  return (
    <div className="w-full rounded-xl overflow-hidden border border-slate-800 bg-slate-950 mt-3">

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 pt-2 pb-2 border-b border-slate-800 text-[10px] font-bold">
        <span className="text-slate-300 font-black uppercase tracking-wider mr-1">{symbol}</span>
        <span className="flex items-center gap-1 text-amber-400"><span className="w-4 h-0.5 bg-amber-400 inline-block rounded"/> EMA9</span>
        <span className="flex items-center gap-1 text-indigo-400"><span className="w-4 h-0.5 bg-indigo-400 inline-block rounded"/> EMA21</span>
        <span className="flex items-center gap-1 text-sky-400"><span className="w-4 h-0.5 bg-sky-400 inline-block rounded"/> EMA50</span>
        <span className="flex items-center gap-1 text-pink-400"><span className="w-4 h-0.5 bg-pink-400 inline-block rounded"/> EMA200</span>
        <span className="flex items-center gap-1 text-slate-500"><span className="w-4 h-0.5 bg-slate-500 inline-block rounded border-dashed"/> BB</span>
        {levels?.entry       && <span className="text-yellow-400">── Entry</span>}
        {levels?.take_profit && <span className="text-green-400">── TP</span>}
        {levels?.stop_loss   && <span className="text-red-400">── SL</span>}
        {levels?.trail_stop  && <span className="text-orange-400">── Trail</span>}
      </div>

      {/* Candlestick + EMA + BB */}
      <div ref={mainRef} className="w-full" style={{ height: 320 }} />

      {/* RSI */}
      <div className="px-3 py-1 flex items-center gap-2 border-t border-slate-800 bg-slate-900/50">
        <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">RSI</span>
        <span className="text-[9px] text-violet-400">● Purple line</span>
        <span className="text-[9px] text-red-400">── 70 Overbought</span>
        <span className="text-[9px] text-green-400">── 30 Oversold</span>
      </div>
      <div ref={rsiRef} className="w-full" style={{ height: 100 }} />

      {/* MACD */}
      <div className="px-3 py-1 flex items-center gap-2 border-t border-slate-800 bg-slate-900/50">
        <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">MACD</span>
        <span className="text-[9px] text-sky-400">── MACD</span>
        <span className="text-[9px] text-orange-400">── Signal</span>
        <span className="text-[9px] text-green-400">▌ Green = momentum up</span>
        <span className="text-[9px] text-red-400">▌ Red = momentum down</span>
      </div>
      <div ref={macdRef} className="w-full" style={{ height: 100 }} />

      {/* ADX */}
      <div className="px-3 py-1 flex items-center gap-2 border-t border-slate-800 bg-slate-900/50">
        <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">ADX</span>
        <span className="text-[9px] text-yellow-400">── Trend strength</span>
        <span className="text-[9px] text-green-400">── +DI Bull</span>
        <span className="text-[9px] text-red-400">── -DI Bear</span>
        <span className="text-[9px] text-slate-500">── 20 threshold</span>
      </div>
      <div ref={adxRef} className="w-full" style={{ height: 100 }} />

      {/* OBV */}
      <div className="px-3 py-1 flex items-center gap-2 border-t border-slate-800 bg-slate-900/50">
        <span className="text-[9px] font-black uppercase tracking-widest text-slate-500">OBV</span>
        <span className="text-[9px] text-emerald-400">── OBV above EMA = big players buying</span>
        <span className="text-[9px] text-pink-400">── OBV EMA</span>
      </div>
      <div ref={obvRef} className="w-full" style={{ height: 100 }} />

    </div>
  );
}
