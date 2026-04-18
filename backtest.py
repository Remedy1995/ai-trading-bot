"""
Backtester — Moving Average Crossover Strategy
════════════════════════════════════════════════
Simulates trades on 2 years of real historical data.
Applies stop-loss, take-profit, and position sizing.
Reports: Win rate, Total return, Max drawdown, Sharpe ratio,
         and comparison against simple Buy & Hold.
"""

import requests
import pandas as pd
import numpy as np
import json
import time
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "backtest_results.json")


# ─────────────────────────────────────────────
#  CONFIG — tweak these to experiment
# ─────────────────────────────────────────────
STARTING_CAPITAL   = 10_000   # USD — simulated starting balance
POSITION_SIZE_PCT  = 0.20     # Use 20% of portfolio per trade
STOP_LOSS_PCT      = 0.03     # Exit trade if price drops 3% below entry
TAKE_PROFIT_PCT    = 0.06     # Exit trade if price rises 6% above entry
SHORT_WINDOW       = 20       # Short moving average (days)
LONG_WINDOW        = 50       # Long moving average (days)
RSI_PERIOD         = 14
COINS              = ['bitcoin', 'ethereum', 'solana']
LOOKBACK_DAYS      = 365      # 1 year (CoinGecko free tier max)


# ─────────────────────────────────────────────
#  DATA FETCHING
# ─────────────────────────────────────────────
def fetch_historical_data(coin_id: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Fetch daily OHLC price data from CoinGecko (free, no key needed)."""
    url = (
        f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        f"?vs_currency=usd&days={days}"
        # Note: interval=daily is automatic for days > 90 on the free tier
    )
    headers = {"accept": "application/json", "User-Agent": "AI-Trading-Bot/1.0"}

    for attempt in range(3):
        try:
            print(f"  Fetching {days} days of data for {coin_id.upper()}...")
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            raw = r.json()
            prices = raw.get('prices', [])
            volumes = raw.get('total_volumes', [])

            df = pd.DataFrame(prices, columns=['ts', 'price'])
            df['date'] = pd.to_datetime(df['ts'], unit='ms').dt.normalize()
            df.set_index('date', inplace=True)
            df.drop(columns=['ts'], inplace=True)

            if volumes:
                vol_df = pd.DataFrame(volumes, columns=['ts', 'volume'])
                vol_df['date'] = pd.to_datetime(vol_df['ts'], unit='ms').dt.normalize()
                vol_df.set_index('date', inplace=True)
                df['volume'] = vol_df['volume']

            df = df[~df.index.duplicated(keep='last')]
            print(f"  ✓ {len(df)} daily candles retrieved.")
            return df

        except Exception as e:
            print(f"  ✗ Attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                wait = 15 * (attempt + 1)  # 15s, then 30s
                print(f"  ⏸️  Waiting {wait}s before retry...")
                time.sleep(wait)

    return pd.DataFrame()


# ─────────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────────
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Moving averages
    df['short_ma'] = df['price'].rolling(SHORT_WINDOW, min_periods=SHORT_WINDOW).mean()
    df['long_ma']  = df['price'].rolling(LONG_WINDOW,  min_periods=LONG_WINDOW).mean()

    # RSI
    delta    = df['price'].diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Signal column: 1=Golden Cross, -1=Death Cross, 0=nothing
    df['above'] = (df['short_ma'] > df['long_ma']).astype(int)
    df['signal'] = df['above'].diff()  # +1 = just crossed up, -1 = just crossed down

    return df.dropna(subset=['short_ma', 'long_ma'])


# ─────────────────────────────────────────────
#  BACKTESTING ENGINE
# ─────────────────────────────────────────────
def run_backtest(coin_id: str, df: pd.DataFrame) -> dict:
    """
    Simulate trades on historical data.
    Rules:
      - BUY  when Golden Cross (short_ma crosses above long_ma), RSI < 75
      - SELL when Death Cross  (short_ma crosses below long_ma)
      - Also SELL if stop-loss or take-profit is hit during a trade
    """
    capital      = STARTING_CAPITAL
    position     = 0.0      # units of crypto held
    entry_price  = 0.0
    stop_loss    = 0.0
    take_profit  = 0.0
    in_trade     = False

    trades       = []
    equity_curve = []

    for date, row in df.iterrows():
        price = row['price']
        rsi   = row.get('rsi', 50)
        sig   = row['signal']

        # ── If in a trade, check stop-loss / take-profit ──
        if in_trade:
            hit_sl = price <= stop_loss
            hit_tp = price >= take_profit
            death_cross = sig < 0

            if hit_sl or hit_tp or death_cross:
                # Close the trade
                sell_value  = position * price
                pnl         = sell_value - (position * entry_price)
                pnl_pct     = (price - entry_price) / entry_price * 100
                capital    += sell_value

                reason = "Stop-Loss" if hit_sl else ("Take-Profit" if hit_tp else "Death Cross")
                trades.append({
                    "coin":        coin_id.upper(),
                    "entry_date":  entry_date.strftime('%Y-%m-%d'),
                    "exit_date":   date.strftime('%Y-%m-%d'),
                    "entry_price": round(entry_price, 4),
                    "exit_price":  round(price, 4),
                    "pnl_usd":     round(pnl, 2),
                    "pnl_pct":     round(pnl_pct, 2),
                    "result":      "WIN" if pnl > 0 else "LOSS",
                    "exit_reason": reason,
                })
                in_trade = False
                position = 0.0

        # ── Golden Cross → BUY (if not already in trade) ──
        if not in_trade and sig > 0 and rsi < 75:
            invest      = capital * POSITION_SIZE_PCT
            position    = invest / price
            entry_price = price
            entry_date  = date
            stop_loss   = entry_price * (1 - STOP_LOSS_PCT)
            take_profit = entry_price * (1 + TAKE_PROFIT_PCT)
            capital    -= invest
            in_trade    = True

        # Track equity (cash + open position value)
        open_value = position * price if position > 0 else 0
        equity_curve.append({
            "date":   date.strftime('%Y-%m-%d'),
            "equity": round(capital + open_value, 2)
        })

    # Close any open trade at end of period
    if in_trade:
        final_price = df.iloc[-1]['price']
        sell_value  = position * final_price
        pnl         = sell_value - (position * entry_price)
        pnl_pct     = (final_price - entry_price) / entry_price * 100
        capital    += sell_value
        trades.append({
            "coin":        coin_id.upper(),
            "entry_date":  entry_date.strftime('%Y-%m-%d'),
            "exit_date":   df.index[-1].strftime('%Y-%m-%d'),
            "entry_price": round(entry_price, 4),
            "exit_price":  round(final_price, 4),
            "pnl_usd":     round(pnl, 2),
            "pnl_pct":     round(pnl_pct, 2),
            "result":      "WIN" if pnl > 0 else "LOSS",
            "exit_reason": "End of Period",
        })

    return {
        "coin":         coin_id.upper(),
        "trades":       trades,
        "final_capital": round(capital, 2),
        "equity_curve": equity_curve,
    }


# ─────────────────────────────────────────────
#  PERFORMANCE METRICS
# ─────────────────────────────────────────────
def compute_metrics(result: dict, df: pd.DataFrame) -> dict:
    trades         = result['trades']
    final_capital  = result['final_capital']
    equity_curve   = result['equity_curve']

    total_return   = (final_capital - STARTING_CAPITAL) / STARTING_CAPITAL * 100
    wins           = [t for t in trades if t['result'] == 'WIN']
    losses         = [t for t in trades if t['result'] == 'LOSS']
    win_rate       = len(wins) / len(trades) * 100 if trades else 0

    avg_win        = np.mean([t['pnl_pct'] for t in wins])   if wins   else 0
    avg_loss       = np.mean([t['pnl_pct'] for t in losses]) if losses else 0

    # Max Drawdown
    equities = [e['equity'] for e in equity_curve]
    peak     = STARTING_CAPITAL
    max_dd   = 0.0
    for e in equities:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Buy & Hold comparison
    start_price = df.iloc[0]['price']
    end_price   = df.iloc[-1]['price']
    bah_units   = (STARTING_CAPITAL * POSITION_SIZE_PCT) / start_price
    bah_value   = STARTING_CAPITAL * (1 - POSITION_SIZE_PCT) + bah_units * end_price
    bah_return  = (bah_value - STARTING_CAPITAL) / STARTING_CAPITAL * 100

    # Sharpe Ratio (simplified, daily returns, risk-free = 0)
    if len(equities) > 1:
        eq_series    = pd.Series(equities)
        daily_returns = eq_series.pct_change().dropna()
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365) if daily_returns.std() > 0 else 0
    else:
        sharpe = 0

    return {
        "total_return_pct":   round(total_return, 2),
        "bah_return_pct":     round(bah_return, 2),
        "total_trades":       len(trades),
        "wins":               len(wins),
        "losses":             len(losses),
        "win_rate_pct":       round(win_rate, 2),
        "avg_win_pct":        round(avg_win, 2),
        "avg_loss_pct":       round(avg_loss, 2),
        "max_drawdown_pct":   round(max_dd, 2),
        "sharpe_ratio":       round(sharpe, 3),
        "final_capital_usd":  round(final_capital, 2),
        "profit_usd":         round(final_capital - STARTING_CAPITAL, 2),
    }


# ─────────────────────────────────────────────
#  PRETTY PRINT
# ─────────────────────────────────────────────
def print_report(coin_id: str, metrics: dict, trades: list):
    m = metrics
    separator = "─" * 54

    print(f"\n{'═'*54}")
    print(f"  📊  BACKTEST RESULTS — {coin_id.upper()}")
    print(f"{'═'*54}")
    print(f"  Strategy   : {SHORT_WINDOW}-day MA vs {LONG_WINDOW}-day MA crossover")
    print(f"  Period     : Last {LOOKBACK_DAYS} days (~2 years)")
    print(f"  Capital    : ${STARTING_CAPITAL:,}  |  Position size: {int(POSITION_SIZE_PCT*100)}%")
    print(f"  Stop-Loss  : -{int(STOP_LOSS_PCT*100)}%   |  Take-Profit: +{int(TAKE_PROFIT_PCT*100)}%")
    print(f"{separator}")

    # Returns
    beat = "✅ Beat" if m['total_return_pct'] > m['bah_return_pct'] else "❌ Underperformed"
    print(f"  💰 Final Capital   : ${m['final_capital_usd']:,.2f}")
    print(f"  📈 Strategy Return : {m['total_return_pct']:+.2f}%")
    print(f"  🏦 Buy & Hold      : {m['bah_return_pct']:+.2f}%  ({beat} Buy & Hold)")
    print(f"  💵 Net Profit/Loss : ${m['profit_usd']:+,.2f}")
    print(f"{separator}")

    # Trade stats
    print(f"  🎯 Total Trades    : {m['total_trades']}")
    print(f"  ✅ Wins            : {m['wins']}  ({m['win_rate_pct']}% win rate)")
    print(f"  ❌ Losses          : {m['losses']}")
    print(f"  📊 Avg Win         : +{m['avg_win_pct']:.2f}%")
    print(f"  📉 Avg Loss        : {m['avg_loss_pct']:.2f}%")
    print(f"{separator}")

    # Risk metrics
    dd_color = "⚠️ " if m['max_drawdown_pct'] > 15 else "✅"
    sharpe_color = "✅" if m['sharpe_ratio'] > 1 else ("⚠️ " if m['sharpe_ratio'] > 0 else "❌")
    print(f"  {dd_color} Max Drawdown    : -{m['max_drawdown_pct']:.2f}%")
    print(f"  {sharpe_color} Sharpe Ratio   : {m['sharpe_ratio']:.3f}  (>1.0 is good)")
    print(f"{separator}")

    # Individual trades
    if trades:
        print(f"\n  📋  Individual Trades:")
        print(f"  {'Date In':<12} {'Date Out':<12} {'Entry':>10} {'Exit':>10} {'P&L %':>8}  {'Result':<6}  Reason")
        print(f"  {'-'*90}")
        for t in trades[-15:]:   # show last 15 trades
            icon = "✅" if t['result'] == "WIN" else "❌"
            pnl_str = f"{t['pnl_pct']:+.2f}%"
            print(f"  {t['entry_date']:<12} {t['exit_date']:<12} "
                  f"${t['entry_price']:>9,.2f} ${t['exit_price']:>9,.2f} "
                  f"{pnl_str:>8}  {icon}      {t['exit_reason']}")


# ─────────────────────────────────────────────
#  VERDICT
# ─────────────────────────────────────────────
def print_overall_verdict(all_metrics: list):
    print(f"\n{'═'*54}")
    print(f"  🏆  OVERALL VERDICT")
    print(f"{'═'*54}")

    total_profit = sum(m['profit_usd'] for m in all_metrics)
    avg_win_rate = np.mean([m['win_rate_pct'] for m in all_metrics])
    avg_drawdown = np.mean([m['max_drawdown_pct'] for m in all_metrics])
    avg_sharpe   = np.mean([m['sharpe_ratio'] for m in all_metrics])

    print(f"  Combined Profit/Loss : ${total_profit:+,.2f}")
    print(f"  Average Win Rate     : {avg_win_rate:.1f}%")
    print(f"  Average Max Drawdown : -{avg_drawdown:.1f}%")
    print(f"  Average Sharpe Ratio : {avg_sharpe:.3f}")
    print()

    # Grade the strategy
    if avg_win_rate >= 55 and total_profit > 0 and avg_sharpe > 0.5:
        grade = "B+ — Strategy shows positive edge. Promising with improvements."
        icon  = "🟢"
    elif total_profit > 0:
        grade = "C+ — Profitable but inconsistent. Needs more filters."
        icon  = "🟡"
    else:
        grade = "D  — Strategy lost money in this period. Do NOT use live yet."
        icon  = "🔴"

    print(f"  {icon}  Strategy Grade: {grade}")
    print()
    print(f"  Next Steps:")
    print(f"  1. Add Perplexity AI sentiment layer → improves entry quality")
    print(f"  2. Add volume confirmation           → reduces false signals")
    print(f"  3. Run on shorter timeframes (4h)    → more trade opportunities")
    print(f"{'═'*54}\n")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────
def main():
    print("\n" + "═"*54)
    print("  🤖  BACKTEST ENGINE — MA Crossover Strategy")
    print("═"*54)
    print(f"  Capital    : ${STARTING_CAPITAL:,}")
    print(f"  Stop-Loss  : -{int(STOP_LOSS_PCT*100)}%  |  Take-Profit: +{int(TAKE_PROFIT_PCT*100)}%")
    print(f"  Period     : Last {LOOKBACK_DAYS} days (~2 years)")
    print(f"  Assets     : {', '.join(c.upper() for c in COINS)}")
    print("═"*54)

    all_results = []
    all_metrics = []

    for coin in COINS:
        print(f"\n⏳ Running backtest for {coin.upper()}...")

        df = fetch_historical_data(coin, days=LOOKBACK_DAYS)
        if df.empty:
            print(f"  ⚠️  Skipping {coin} — no data.")
            continue

        df     = add_indicators(df)
        result = run_backtest(coin, df)
        metrics = compute_metrics(result, df)

        print_report(coin, metrics, result['trades'])

        all_results.append({**result, "metrics": metrics})
        all_metrics.append(metrics)

        # Be polite to the free API
        if coin != COINS[-1]:
            print(f"\n  ⏸️  Pausing 20s to respect CoinGecko rate limits...")
            time.sleep(20)

    print_overall_verdict(all_metrics)

    # Save full results
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  📁 Full results saved to {OUTPUT_FILE}\n")


if __name__ == "__main__":
    main()
