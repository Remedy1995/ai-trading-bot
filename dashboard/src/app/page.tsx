"use client";

import { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { TrendingUp, TrendingDown, Activity, DollarSign, Brain, BarChart3, AlertCircle } from 'lucide-react';

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/data')
      .then(res => res.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to load data", err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
      </div>
    );
  }

  const { botResults = [], backtestResults = [], sentimentResults = [] } = data || {};

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-sans">
      <header className="max-w-7xl mx-auto mb-10 border-b border-slate-800 pb-6">
        <h1 className="text-4xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-cyan-400 flex items-center gap-3">
          <Activity className="w-8 h-8 text-indigo-400" />
          AI Trading Terminal
        </h1>
        <p className="text-slate-400 mt-2">Live signals, backtest history, and Perplexity AI sentiment</p>
      </header>

      <main className="max-w-7xl mx-auto space-y-12">
        {/* Live Signals Section */}
        <section>
          <div className="flex items-center gap-2 mb-6">
            <BarChart3 className="w-6 h-6 text-emerald-400" />
            <h2 className="text-2xl font-semibold">Live Market Signals (Layer 1)</h2>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {botResults.map((coin: any) => {
              const isBullish = coin.signal === 'BULLISH';
              const isBearish = coin.signal === 'BEARISH';
              const isNeutral = !isBullish && !isBearish;

              return (
                <div key={coin.crypto_id} className={`rounded-xl p-6 border ${
                  isBullish ? 'bg-emerald-950/20 border-emerald-900/50' : 
                  isBearish ? 'bg-rose-950/20 border-rose-900/50' : 
                  'bg-slate-900/50 border-slate-800'
                } backdrop-blur-sm transition-all hover:scale-[1.02]`}>
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="text-xl font-bold uppercase">{coin.crypto_id}</h3>
                      <p className="text-slate-400 text-sm">{coin.type || "No Crossover"}</p>
                    </div>
                    <span className="text-2xl">{coin.emoji}</span>
                  </div>

                  <div className="text-3xl font-bold mb-2 flex items-center gap-2">
                    ${coin.current_price?.toLocaleString() || 'N/A'}
                    {coin.change_24h && (
                      <span className={`text-sm flex items-center ${coin.change_24h > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {coin.change_24h > 0 ? <TrendingUp className="w-4 h-4 mr-1" /> : <TrendingDown className="w-4 h-4 mr-1" />}
                        {Math.abs(coin.change_24h)}%
                      </span>
                    )}
                  </div>

                  <div className="mt-6 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-400">Verdict</span>
                      <span className={`font-semibold ${isBullish ? 'text-emerald-400' : isBearish ? 'text-rose-400' : 'text-amber-400'}`}>
                        {coin.action}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-400">50-Day MA</span>
                      <span>${coin.short_ma?.toLocaleString() || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-slate-400">200-Day MA</span>
                      <span>${coin.long_ma?.toLocaleString() || 'N/A'}</span>
                    </div>
                    <div className="flex justify-between text-sm border-t border-slate-800 pt-2 mt-2">
                      <span className="text-slate-400">RSI (14)</span>
                      <span className={coin.rsi > 70 ? 'text-rose-400' : coin.rsi < 30 ? 'text-emerald-400' : 'text-slate-300'}>
                        {coin.rsi}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
            {botResults.length === 0 && (
              <div className="col-span-3 text-center py-10 text-slate-500 bg-slate-900/40 rounded-xl border border-dashed border-slate-700">
                <AlertCircle className="w-10 h-10 mx-auto mb-3 opacity-50" />
                <p>No live signal data found. Run the bot script first.</p>
              </div>
            )}
          </div>
        </section>

        {/* AI Sentiment Layer */}
        {sentimentResults.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-6">
              <Brain className="w-6 h-6 text-purple-400" />
              <h2 className="text-2xl font-semibold">Dual Confirmation (MA + AI Sentiment)</h2>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-xl overflow-hidden backdrop-blur-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-900 text-slate-400 text-sm border-b border-slate-800">
                      <th className="p-4 font-medium uppercase tracking-wider">Asset</th>
                      <th className="p-4 font-medium uppercase tracking-wider">Chart Signal</th>
                      <th className="p-4 font-medium uppercase tracking-wider text-purple-400">AI Sentiment</th>
                      <th className="p-4 font-medium uppercase tracking-wider">Decision</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {sentimentResults.map((row: any) => (
                      <tr key={row.coin} className="hover:bg-slate-800/30 transition-colors">
                        <td className="p-4 font-semibold uppercase">{row.ticker}</td>
                        <td className="p-4">
                           <span className={`px-2 py-1 rounded-md text-xs font-semibold ${
                             row.chart.verdict === 'BULLISH' ? 'bg-emerald-500/10 text-emerald-400' :
                             row.chart.verdict === 'BEARISH' ? 'bg-rose-500/10 text-rose-400' : 'bg-slate-700 text-slate-300'
                           }`}>
                             {row.chart.verdict}
                           </span>
                        </td>
                        <td className="p-4">
                           <span className={`px-2 py-1 rounded-md text-xs font-semibold ${
                             row.sentiment.verdict === 'BULLISH' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-900/50' :
                             row.sentiment.verdict === 'BEARISH' ? 'bg-rose-500/10 text-rose-400 border border-rose-900/50' : 'bg-purple-900/30 text-purple-300 border border-purple-900/50'
                           }`}>
                             {row.sentiment.verdict}
                           </span>
                           <div className="text-xs text-slate-500 mt-2 max-w-xs">{row.sentiment.reason}</div>
                        </td>
                        <td className="p-4">
                          <div className="flex items-center gap-2">
                            <span>{row.decision.emoji}</span>
                            <span className="font-bold">{row.decision.final_signal}</span>
                          </div>
                          <div className="text-xs text-slate-400 mt-1">{row.decision.action}</div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        )}

        {/* Backtest Section */}
        {backtestResults.length > 0 && (
          <section>
            <div className="flex items-center gap-2 mb-6">
              <DollarSign className="w-6 h-6 text-amber-400" />
              <h2 className="text-2xl font-semibold">Backtest Performance (2 Years)</h2>
            </div>
            
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {backtestResults.map((res: any) => (
                <div key={res.coin} className="bg-slate-900/40 border border-slate-800 rounded-xl p-6">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-xl font-bold uppercase">{res.coin} Strategy</h3>
                    <div className={`px-3 py-1 rounded-full text-sm font-semibold ${res.metrics.profit_usd > 0 ? 'bg-emerald-950 text-emerald-400' : 'bg-rose-950 text-rose-400'}`}>
                      {res.metrics.total_return_pct >= 0 ? '+' : ''}{res.metrics.total_return_pct}%
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                     <div className="bg-slate-950 rounded-lg p-3">
                        <div className="text-xs text-slate-500 mb-1">Win Rate</div>
                        <div className="font-semibold">{res.metrics.win_rate_pct}%</div>
                     </div>
                     <div className="bg-slate-950 rounded-lg p-3">
                        <div className="text-xs text-slate-500 mb-1">Net Profit</div>
                        <div className={`font-semibold ${res.metrics.profit_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                          ${res.metrics.profit_usd?.toLocaleString()}
                        </div>
                     </div>
                     <div className="bg-slate-950 rounded-lg p-3">
                        <div className="text-xs text-slate-500 mb-1">Sharpe</div>
                        <div className="font-semibold">{res.metrics.sharpe_ratio}</div>
                     </div>
                     <div className="bg-slate-950 rounded-lg p-3">
                        <div className="text-xs text-slate-500 mb-1">Max DD</div>
                        <div className="font-semibold text-rose-400">-{res.metrics.max_drawdown_pct}%</div>
                     </div>
                  </div>

                  {res.equity_curve && res.equity_curve.length > 0 && (
                    <div className="h-64 min-h-[250px] w-full mt-4 pt-4 border-t border-slate-800/60">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={res.equity_curve}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                          <XAxis 
                            dataKey="date" 
                            stroke="#475569" 
                            fontSize={10}
                            tickFormatter={(val) => val.substring(5)} 
                            minTickGap={30}
                          />
                          <YAxis 
                            domain={['auto', 'auto']} 
                            stroke="#475569" 
                            fontSize={10} 
                            tickFormatter={(val) => `$${val/1000}k`}
                          />
                          <Tooltip 
                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                            itemStyle={{ color: '#818cf8', fontWeight: 'bold' }}
                            formatter={(value: any) => [`$${Number(value).toLocaleString()}`, 'Portfolio']}
                          />
                          <Line 
                            type="stepAfter" 
                            dataKey="equity" 
                            stroke="#818cf8" 
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
