"""
AI Trading Bot - Moving Average Crossover Strategy
Based on the article: "I Built an AI Trading Bot in 15 Minutes Using Perplexity & Python"
Strategy: Golden Cross / Death Cross using 50-day and 200-day Moving Averages
Data Source: CoinGecko API (free, no API key required)
"""

import requests
import pandas as pd
import json
import time
from datetime import datetime


def get_crypto_data(crypto_id='bitcoin', days=250):
    """
    Fetches historical market data for a given cryptocurrency from CoinGecko API.
    Returns a pandas DataFrame with date and price columns.
    """
    url = (
        f"https://api.coingecko.com/api/v3/coins/{crypto_id}/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily"
    )
    headers = {
        "accept": "application/json",
        "User-Agent": "AI-Trading-Bot/1.0"
    }
    try:
        print(f"  Fetching {days} days of price data for {crypto_id.upper()}...")
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        prices = data.get('prices', [])
        if not prices:
            print("  WARNING: No price data returned from API.")
            return pd.DataFrame()
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df[['date', 'price']].copy()
        df.set_index('date', inplace=True)
        print(f"  ✓ Retrieved {len(df)} data points.")
        return df
    except requests.exceptions.RequestException as e:
        print(f"  ✗ Error fetching data: {e}")
        return pd.DataFrame()


def get_current_price(crypto_id='bitcoin'):
    """Fetches the current spot price for a cryptocurrency."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto_id}&vs_currencies=usd&include_24hr_change=true"
    headers = {"accept": "application/json", "User-Agent": "AI-Trading-Bot/1.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = data[crypto_id]['usd']
        change_24h = data[crypto_id].get('usd_24h_change', 0)
        return price, change_24h
    except Exception as e:
        print(f"  ✗ Error fetching current price: {e}")
        return None, None


def calculate_moving_averages(df, short_window=50, long_window=200):
    """
    Calculates short-term and long-term simple moving averages.
    """
    df = df.copy()
    df['short_ma'] = df['price'].rolling(window=short_window, min_periods=short_window).mean()
    df['long_ma'] = df['price'].rolling(window=long_window, min_periods=long_window).mean()
    df['rsi'] = calculate_rsi(df['price'], period=14)
    return df


def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index (RSI) for additional signal confirmation."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, float('nan'))
    rsi = 100 - (100 / (1 + rs))
    return rsi


def generate_signal(df):
    """
    Generates a trading signal based on Moving Average crossovers.
    
    Golden Cross (Bullish): Short MA crosses ABOVE Long MA → Buy signal
    Death Cross  (Bearish): Short MA crosses BELOW Long MA → Sell signal
    Neutral:               No crossover detected → Hold
    """
    clean_df = df.dropna(subset=['short_ma', 'long_ma'])
    if len(clean_df) < 2:
        return {
            "signal": "INSUFFICIENT DATA",
            "description": "Not enough data to generate a signal.",
            "action": "WAIT",
            "confidence": "LOW",
            "emoji": "⚠️"
        }

    latest = clean_df.iloc[-1]
    previous = clean_df.iloc[-2]

    # Detect crossovers
    was_below = previous['short_ma'] < previous['long_ma']
    is_above = latest['short_ma'] > latest['long_ma']
    was_above = previous['short_ma'] > previous['long_ma']
    is_below = latest['short_ma'] < latest['long_ma']

    rsi = latest.get('rsi', None)
    gap_pct = abs(latest['short_ma'] - latest['long_ma']) / latest['long_ma'] * 100

    if was_below and is_above:
        # Golden Cross — Bullish signal
        confidence = "HIGH" if (rsi is not None and rsi < 70) else "MEDIUM"
        return {
            "signal": "BULLISH",
            "type": "Golden Cross",
            "description": "50-day MA crossed ABOVE 200-day MA — Upward momentum detected.",
            "action": "BUY / LONG",
            "confidence": confidence,
            "emoji": "🟢",
            "short_ma": round(latest['short_ma'], 2),
            "long_ma": round(latest['long_ma'], 2),
            "rsi": round(rsi, 2) if rsi is not None else "N/A",
            "gap_pct": round(gap_pct, 3),
        }
    elif was_above and is_below:
        # Death Cross — Bearish signal
        confidence = "HIGH" if (rsi is not None and rsi > 30) else "MEDIUM"
        return {
            "signal": "BEARISH",
            "type": "Death Cross",
            "description": "50-day MA crossed BELOW 200-day MA — Downward momentum detected.",
            "action": "SELL / SHORT (or take profit)",
            "confidence": confidence,
            "emoji": "🔴",
            "short_ma": round(latest['short_ma'], 2),
            "long_ma": round(latest['long_ma'], 2),
            "rsi": round(rsi, 2) if rsi is not None else "N/A",
            "gap_pct": round(gap_pct, 3),
        }
    else:
        # No crossover — check which MA is on top for trend direction
        if latest['short_ma'] > latest['long_ma']:
            trend = "Bullish trend continues (short MA above long MA — no new crossover)"
            action = "HOLD / LONG BIAS"
        else:
            trend = "Bearish trend continues (short MA below long MA — no new crossover)"
            action = "HOLD / CASH"

        return {
            "signal": "NEUTRAL",
            "type": "No Crossover",
            "description": trend,
            "action": action,
            "confidence": "MEDIUM",
            "emoji": "🟡",
            "short_ma": round(latest['short_ma'], 2),
            "long_ma": round(latest['long_ma'], 2),
            "rsi": round(rsi, 2) if rsi is not None else "N/A",
            "gap_pct": round(gap_pct, 3),
        }


def get_price_history_for_chart(df, points=60):
    """Returns recent price data formatted for charting."""
    recent = df.tail(points).copy()
    return {
        "dates": [str(d.date()) for d in recent.index],
        "prices": [round(p, 2) for p in recent['price'].tolist()],
        "short_ma": [round(v, 2) if not pd.isna(v) else None for v in recent['short_ma'].tolist()],
        "long_ma": [round(v, 2) if not pd.isna(v) else None for v in recent['long_ma'].tolist()],
    }


def run_bot(crypto_ids=None, short_window=50, long_window=200):
    """
    Main bot runner. Analyzes multiple cryptocurrencies and prints signals.
    """
    if crypto_ids is None:
        crypto_ids = ['bitcoin', 'ethereum', 'solana']

    print("\n" + "="*60)
    print("   🤖  AI TRADING BOT — Moving Average Crossover Strategy")
    print("="*60)
    print(f"   Strategy : {short_window}-day MA  vs  {long_window}-day MA")
    print(f"   Signals  : Golden Cross (BUY) / Death Cross (SELL)")
    print(f"   Data via : CoinGecko API (free)")
    print(f"   Run time : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    results = []

    for i, crypto_id in enumerate(crypto_ids):
        print(f"\n📊 Analyzing {crypto_id.upper()}...")

        # Fetch data
        df = get_crypto_data(crypto_id, days=long_window + 60)
        if df.empty:
            print(f"  Skipping {crypto_id} — no data available.")
            continue

        # Calculate indicators
        df = calculate_moving_averages(df, short_window=short_window, long_window=long_window)

        # Small pause before fetching current price to avoid rate-limit
        time.sleep(3)

        # Get current price
        current_price, change_24h = get_current_price(crypto_id)

        # Generate signal
        result = generate_signal(df)
        result['crypto_id'] = crypto_id
        result['current_price'] = current_price
        result['change_24h'] = round(change_24h, 2) if change_24h else "N/A"
        result['chart_data'] = get_price_history_for_chart(df)
        result['timestamp'] = datetime.now().isoformat()
        results.append(result)

        # Rate-limit pause between coins (CoinGecko free tier: ~10-30 req/min)
        if i < len(crypto_ids) - 1:
            print(f"  ⏸️  Pausing 12s to respect CoinGecko rate limits...")
            time.sleep(12)

        # Pretty print to terminal
        print(f"\n  {'─'*50}")
        print(f"  {result['emoji']}  Signal   : {result['signal']} — {result.get('type', '')}")
        print(f"  📝 Description: {result['description']}")
        print(f"  🎯 Action     : {result['action']}")
        print(f"  💪 Confidence : {result['confidence']}")
        if current_price:
            change_str = f"+{change_24h:.2f}%" if change_24h and change_24h > 0 else f"{change_24h:.2f}%"
            print(f"  💰 Price      : ${current_price:,.2f}  ({change_str} 24h)")
        print(f"  📈 50-day MA  : ${result.get('short_ma', 'N/A'):,}")
        print(f"  📉 200-day MA : ${result.get('long_ma', 'N/A'):,}")
        print(f"  📊 RSI (14)   : {result.get('rsi', 'N/A')}")
        print(f"  {'─'*50}")

    print(f"\n{'='*60}")
    print(f"  ✅ Analysis complete for {len(results)} asset(s).")
    print(f"  ⚠️  DISCLAIMER: This is for educational purposes only.")
    print(f"     Always use stop-losses. Never risk more than 1% per trade.")
    print(f"{'='*60}\n")

    # Save results to JSON for the dashboard
    with open('/Users/asoribabackend/.gemini/antigravity/scratch/ai-trading-bot/bot_results.json', 'w') as f:
        # Remove chart_data from terminal output but keep in file
        json.dump(results, f, indent=2, default=str)
    print("  📁 Results saved to bot_results.json")

    return results


if __name__ == "__main__":
    run_bot(
        crypto_ids=['bitcoin', 'ethereum', 'solana'],
        short_window=50,
        long_window=200
    )
