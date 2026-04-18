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

    let mainChart: any, rsiChart: any, macdChart: any, adxChart: any, obvChart: any;

    import('lightweight-charts').then(({ createChart, CrosshairMode, LineStyle }) => {

      const makeChart = (el: HTMLDivElement, height: number) => createChart(el, {
        width:  el.clientWidth,
        height,
        layout:          { background: { color: '#0f172a' }, textColor: '#94a3b8' },
        grid:            { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
        crosshair:       { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#334155' },
        timeScale:       { borderColor: '#334155', timeVisible: true, secondsVisible: false },
      });

      const toTs = (d: string) => Math.floor(new Date(d).getTime() / 1000);

      // ── 1. MAIN — Candlesticks + EMA Stack + Bollinger Bands ─────
      mainChart = makeChart(mainRef.current!, 320);

      const candleSeries = mainChart.addCandlestickSeries({
        upColor: '#22c55e', downColor: '#ef4444',
        borderUpColor: '#22c55e', borderDownColor: '#ef4444',
        wickUpColor: '#22c55e', wickDownColor: '#ef4444',
      });
      candleSeries.setData(history.map(c => ({
        time: toTs(c.date), open: c.open, high: c.high, low: c.low, close: c.close,
      })));

      // EMA Stack (Indicator 1 & 2)
      const lineOpts = (color: string, title: string) => ({
        color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title,
      });
      mainChart.addLineSeries(lineOpts('#f59e0b', 'EMA9'))
               .setData(history.map(c => ({ time: toTs(c.date), value: c.ema9 })));
      mainChart.addLineSeries(lineOpts('#818cf8', 'EMA21'))
               .setData(history.map(c => ({ time: toTs(c.date), value: c.ema21 })));
      mainChart.addLineSeries(lineOpts('#38bdf8', 'EMA50'))
               .setData(history.map(c => ({ time: toTs(c.date), value: c.ema50 })));
      mainChart.addLineSeries(lineOpts('#f472b6', 'EMA200'))
               .setData(history.map(c => ({ time: toTs(c.date), value: c.ema200 })));

      // Bollinger Bands (Indicator 5)
      mainChart.addLineSeries({ color: '#475569', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: 'BB Upper' })
               .setData(history.map(c => ({ time: toTs(c.date), value: c.bb_upper })));
      mainChart.addLineSeries({ color: '#334155', lineWidth: 1, lineStyle: LineStyle.Dotted, priceLineVisible: false, lastValueVisible: false, title: 'BB Mid' })
               .setData(history.map(c => ({ time: toTs(c.date), value: c.bb_mid })));
      mainChart.addLineSeries({ color: '#475569', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: 'BB Lower' })
               .setData(history.map(c => ({ time: toTs(c.date), value: c.bb_lower })));

      // Entry / TP / SL / Trail price lines
      if (levels) {
        const pl = (price: number, color: string, title: string) => ({
          price, color, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: true, title,
        });
        if (levels.entry)       candleSeries.createPriceLine(pl(levels.entry,       '#facc15', `Entry $${levels.entry}`));
        if (levels.take_profit) candleSeries.createPriceLine(pl(levels.take_profit, '#22c55e', `TP $${levels.take_profit}`));
        if (levels.stop_loss)   candleSeries.createPriceLine(pl(levels.stop_loss,   '#ef4444', `SL $${levels.stop_loss}`));
        if (levels.trail_stop)  candleSeries.createPriceLine(pl(levels.trail_stop,  '#f97316', `Trail $${levels.trail_stop}`));
      }
      mainChart.timeScale().fitContent();

      // ── 2. RSI (Indicator 4) ──────────────────────────────────────
      rsiChart = makeChart(rsiRef.current!, 100);
      rsiChart.addLineSeries({ color: '#a78bfa', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'RSI' })
              .setData(history.map(c => ({ time: toTs(c.date), value: c.rsi })));
      // Overbought 70 line
      rsiChart.addLineSeries({ color: '#ef444466', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: 'Overbought 70' })
              .setData(history.map(c => ({ time: toTs(c.date), value: 70 })));
      // Oversold 30 line
      rsiChart.addLineSeries({ color: '#22c55e66', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: 'Oversold 30' })
              .setData(history.map(c => ({ time: toTs(c.date), value: 30 })));
      rsiChart.timeScale().fitContent();

      // ── 3. MACD (Indicator 3) ─────────────────────────────────────
      macdChart = makeChart(macdRef.current!, 100);
      macdChart.addLineSeries({ color: '#38bdf8', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'MACD' })
               .setData(history.map(c => ({ time: toTs(c.date), value: c.macd })));
      macdChart.addLineSeries({ color: '#f97316', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'Signal' })
               .setData(history.map(c => ({ time: toTs(c.date), value: c.macd_sig })));
      // Histogram — green when momentum up, red when down
      macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false, title: 'Histogram' })
               .setData(history.map(c => ({
                 time: toTs(c.date), value: c.macd_hist,
                 color: c.macd_hist >= 0 ? '#22c55e88' : '#ef444488',
               })));
      macdChart.timeScale().fitContent();

      // ── 4. ADX (Indicator 6) ──────────────────────────────────────
      // ADX = trend strength (>20 = trending, >40 = strong)
      // +DI = bullish pressure, -DI = bearish pressure
      adxChart = makeChart(adxRef.current!, 100);
      adxChart.addLineSeries({ color: '#facc15', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'ADX' })
              .setData(history.map(c => ({ time: toTs(c.date), value: c.adx })));
      adxChart.addLineSeries({ color: '#22c55e', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: '+DI (Bull)' })
              .setData(history.map(c => ({ time: toTs(c.date), value: c.plus_di })));
      adxChart.addLineSeries({ color: '#ef4444', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: '-DI (Bear)' })
              .setData(history.map(c => ({ time: toTs(c.date), value: c.minus_di })));
      // Trend threshold line at 20
      adxChart.addLineSeries({ color: '#47556966', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false, title: 'Trend Threshold 20' })
              .setData(history.map(c => ({ time: toTs(c.date), value: 20 })));
      adxChart.timeScale().fitContent();

      // ── 5. OBV (Indicator 7) ──────────────────────────────────────
      // OBV rising = volume confirming uptrend
      // OBV above OBV-EMA = bullish volume pressure
      obvChart = makeChart(obvRef.current!, 100);
      obvChart.addLineSeries({ color: '#34d399', lineWidth: 1, priceLineVisible: false, lastValueVisible: true, title: 'OBV' })
              .setData(history.map(c => ({ time: toTs(c.date), value: c.obv })));
      obvChart.addLineSeries({ color: '#f472b6', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true, title: 'OBV EMA20' })
              .setData(history.map(c => ({ time: toTs(c.date), value: c.obv_ema })));
      obvChart.timeScale().fitContent();

      // ── Sync crosshair across all 5 panels ───────────────────────
      const allCharts = [mainChart, rsiChart, macdChart, adxChart, obvChart];
      allCharts.forEach(src => {
        src.subscribeCrosshairMove((param: any) => {
          allCharts.filter(t => t !== src).forEach(t => {
            if (!param?.time) { t.clearCrosshairPosition?.(); return; }
            t.setCrosshairPosition(param.point?.x, param.point?.y, t.series?.[0]);
          });
        });
      });

      // ── Resize all panels together ────────────────────────────────
      const refs = [mainRef, rsiRef, macdRef, adxRef, obvRef];
      const ro = new ResizeObserver(() => {
        allCharts.forEach((ch, i) => {
          const el = refs[i].current;
          if (el) ch.resize(el.clientWidth, ch.options().height);
        });
      });
      if (mainRef.current) ro.observe(mainRef.current);

      return () => { ro.disconnect(); allCharts.forEach(c => c.remove()); };
    });

    return () => {
      [mainChart, rsiChart, macdChart, adxChart, obvChart].forEach(c => c?.remove());
    };
  }, [history, levels]);

  return (
    <div className="w-full rounded-lg overflow-hidden border border-slate-800 bg-slate-950">

      {/* ── Legend ── */}
      <div className="flex flex-wrap gap-3 px-3 pt-2 pb-1 text-[10px] font-bold border-b border-slate-800">
        <span className="text-slate-400 uppercase tracking-wider">{symbol}</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-amber-400 inline-block"/> EMA9</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-indigo-400 inline-block"/> EMA21</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-sky-400  inline-block"/> EMA50</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-pink-400 inline-block"/> EMA200</span>
        <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-slate-500 inline-block"/> BB</span>
        {levels?.entry       && <span className="text-yellow-400">── Entry</span>}
        {levels?.take_profit && <span className="text-green-400">── TP</span>}
        {levels?.stop_loss   && <span className="text-red-400">── SL</span>}
        {levels?.trail_stop  && <span className="text-orange-400">── Trail</span>}
      </div>

      {/* ── 1. Candlesticks + EMA Stack + BB ── */}
      <div ref={mainRef} className="w-full" style={{ height: 320 }} />

      {/* ── 2. RSI ── */}
      <div className="px-3 pt-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider border-t border-slate-800">
        RSI (Relative Strength Index) —
        <span className="text-violet-400"> Purple line</span> ·
        <span className="text-red-400"> 70 = Overbought (reversal risk)</span> ·
        <span className="text-green-400"> 30 = Oversold (bounce likely)</span>
      </div>
      <div ref={rsiRef} className="w-full" style={{ height: 100 }} />

      {/* ── 3. MACD ── */}
      <div className="px-3 pt-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider border-t border-slate-800">
        MACD (Momentum) —
        <span className="text-sky-400"> MACD line</span> ·
        <span className="text-orange-400"> Signal line</span> ·
        <span className="text-green-400"> Green bars = rising momentum</span> ·
        <span className="text-red-400"> Red bars = falling momentum</span>
      </div>
      <div ref={macdRef} className="w-full" style={{ height: 100 }} />

      {/* ── 4. ADX ── */}
      <div className="px-3 pt-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider border-t border-slate-800">
        ADX (Trend Strength) —
        <span className="text-yellow-400"> ADX above 20 = trending market</span> ·
        <span className="text-green-400"> +DI = bull pressure</span> ·
        <span className="text-red-400"> -DI = bear pressure</span>
      </div>
      <div ref={adxRef} className="w-full" style={{ height: 100 }} />

      {/* ── 5. OBV ── */}
      <div className="px-3 pt-1 text-[10px] font-bold text-slate-500 uppercase tracking-wider border-t border-slate-800">
        OBV (On Balance Volume) —
        <span className="text-emerald-400"> OBV above pink EMA = big players buying</span> ·
        <span className="text-pink-400"> OBV below EMA = selling pressure</span>
      </div>
      <div ref={obvRef} className="w-full" style={{ height: 100 }} />

    </div>
  );
}
