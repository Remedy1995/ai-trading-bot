import os
import json
import time
import requests
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import ccxt
except ImportError:
    ccxt = None

import pandas as pd
import numpy as np

# Reuse the powerful mathematics already built in your enhanced_bot
from enhanced_bot import build_all_indicators, score_confluence, trade_levels
from notifier import send_discord_alert

# ─────────────────────────────────────────────────────────────────
#  1. BOT CONFIGURATION (24/7 DAEMON MODE)
# ─────────────────────────────────────────────────────────────────
STATE_FILE = "open_trades.json"          # Bot's Memory (so it doesn't double-buy)
STATS_FILE = "trade_stats.json"          # Bot's Aggregated Stats
POLL_INTERVAL_SEC = 60 * 5               # Check the market every 5 minutes
TRADE_AMOUNT_USD = 100.0                 # Dollar amount to spend per trade

# Timeframe: Changed to 5-minute candles to find trades rapidly.
TIMEFRAME = '5m'                         

# Groq AI Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL   = "llama-3.1-70b-versatile"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

# Your Exchange configuration
EXCHANGE_ID = os.environ.get("EXCHANGE_NAME", "binance") # binance, coinbase, kraken
API_KEY = os.environ.get("EXCHANGE_API_KEY", "")
API_SECRET = os.environ.get("EXCHANGE_API_SECRET", "")
SIMULATION_MODE = True                   # Keep True until you are trading real money.

# Standardized trading pairs for the Exchange
COINS = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
    "SOL/USDT": "solana",
    "WIF/USDT": "dogwifhat",
    "DOGE/USDT": "dogecoin"
}

# ─────────────────────────────────────────────────────────────────
#  2. EXCHANGE AND MEMORY SETUP
# ─────────────────────────────────────────────────────────────────
def get_exchange():
    """Connects to the real crypto exchange."""
    if ccxt is None:
        print("  ⚠️ ccxt library not installed. Simulation only.")
        return None
        
    try:
        exchange_class = getattr(ccxt, EXCHANGE_ID)
        exchange = exchange_class({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
        })
        return exchange
    except Exception as e:
        print(f"  ❌ Failed to connect to exchange: {e}")
        return None

def load_state():
    """Loads the bot's memory of open trades."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_state(state):
    """Saves the bot's memory to disk."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def load_stats():
    """Loads the bot's aggregate stats."""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    return {"total_trades": 0, "wins": 0, "losses": 0, "total_pnl_usd": 0.0}

def save_stats(stats):
    """Saves the bot's aggregate stats to disk."""
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=4)

def log_trade_history(message):
    """Appends all permanent trade executions to a simple text file for easy reading."""
    from datetime import datetime
    with open("trade_history.txt", "a") as f:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"[{now_str}] {message}\n")


# ─────────────────────────────────────────────────────────────────
#  3. FAST DATA FETCHING (No Rate Limits)
# ─────────────────────────────────────────────────────────────────
def fetch_ohlcv(exchange, symbol, timeframe=TIMEFRAME, limit=250):
    """
    Downloads historical data from the Exchange directly.
    Much faster and more reliable than CoinGecko for a 24/7 bot.
    """
    if exchange is None and SIMULATION_MODE:
        # Mock data for demonstration if ccxt is totally unavailable
        # But generally we need CCXT to get true live data
        pass

    try:
        # Returns: [Timestamp, Open, High, Low, Close, Volume]
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['ts', 'open', 'high', 'low', 'close', 'vol_proxy'])
        df['date'] = pd.to_datetime(df['ts'], unit='ms')
        return df
    except Exception as e:
        print(f"  [Error] Failed to fetch data for {symbol}: {str(e)}")
        return pd.DataFrame()

def get_current_price(exchange, symbol):
    """Fetches the immediate live price."""
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except:
        return None

def get_ai_sentiment(coin_name: str, ticker: str) -> dict:
    """Asks Groq AI (Llama 3.1) for the current market sentiment to act as a safety veto."""
    if not GROQ_API_KEY:
        return {"verdict": "NEUTRAL", "reason": "No API Key"}

    prompt = f"""You are a professional crypto market analyst. 
Based on technical factors, recent historical behavior, and typical market sentiment, analyze {coin_name} ({ticker}).

Respond with EXACTLY this JSON format — no extra text:
{{
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "key_reason": "One sentence summary"
}}"""

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": "You are a concise, data-driven crypto analyst. Valid JSON only."},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": 150,
        "temperature": 0.2,
    }

    try:
        r = requests.post(GROQ_URL, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()
        parsed = json.loads(content)
        return {"verdict": parsed.get("sentiment", "NEUTRAL").upper(), "reason": parsed.get("key_reason", "")}
    except Exception as e:
        return {"verdict": "NEUTRAL", "reason": f"API Error: {e}"}

# ─────────────────────────────────────────────────────────────────
#  4. ADVANCED ORDER EXECUTION & MANAGEMENT
# ─────────────────────────────────────────────────────────────────
def manage_open_trade(exchange, symbol, trade_info, current_price):
    """
    Software Bracket Order (OCO Handler).
    The bot monitors the live price itself and acts as the trigger.
    """
    tp_price = trade_info["take_profit"]
    sl_price = trade_info["stop_loss"]
    buy_price = trade_info["buy_price"]
    amount = trade_info["amount"]

    # 1. Take Profit Hit?
    if current_price >= tp_price:
        print(f"  🟢 [TAKE PROFIT TRIGGERED] {symbol} hit {current_price}! Selling.")
        if not SIMULATION_MODE and exchange:
            exchange.create_market_order(symbol, 'sell', amount)
            
        return "CLOSED_TAKE_PROFIT"

    # 2. Stop Loss Hit?
    elif current_price <= sl_price:
        print(f"  🔴 [STOP LOSS TRIGGERED] {symbol} dropped to {current_price}! Selling to protect capital.")
        if not SIMULATION_MODE and exchange:
            exchange.create_market_order(symbol, 'sell', amount)
            
        return "CLOSED_STOP_LOSS"

    # Wait
    pnl = ((current_price - buy_price) / buy_price) * 100
    print(f"  ⏳ [IN TRADE] {symbol}: P&L {pnl:+.2f}% | Live: ${current_price:.2f} | Wait for TP: ${tp_price:.2f} or SL: ${sl_price:.2f}")
    return "OPEN"


def execute_market_buy(exchange, symbol, action, current_price, sl_price, tp_price):
    """Enters the market when all conditions are met."""
    amount = TRADE_AMOUNT_USD / current_price
    
    if SIMULATION_MODE:
        print(f"  [SIMULATION] ✅ BOUGHT {amount:.4f} {symbol} @ ${current_price:.2f}")
        return amount

    try:
        print(f"  ⚡ Executing LIVE Market BUY for {symbol}...")
        order = exchange.create_market_order(symbol, 'buy', amount)
        # Use exact filled amount if available
        actual_amount = order.get('filled', amount)
        print(f"  ✅ SUCCESS! Buy order complete.")
        return actual_amount
    except Exception as e:
        print(f"  ❌ FAILED to execute buy: {e}")
        return None

# ─────────────────────────────────────────────────────────────────
#  5. THE 24/7 CONTINUOUS LOOP (DAEMON)
# ─────────────────────────────────────────────────────────────────
def run_continuous_daemon():
    print("\n" + "═" * 60)
    print("  🚀 STARTING 24/7 CONTINUOUS TRADING DAEMON")
    print("  Monitoring real-time prices & checking Indicators.")
    print(f"  Interval: Every {int(POLL_INTERVAL_SEC/60)} minutes.")
    print("═" * 60)

    exchange = get_exchange()
    if not exchange and not SIMULATION_MODE:
        print("CRITICAL: Cannot start without Exchange API keys in live mode.")
        return

    while True:
        state = load_state()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{now_str}] 🔍 Scanning markets...")
        
        cycle_results = []
        for symbol, coin_name in COINS.items():

            
            current_price = get_current_price(exchange, symbol)
            if not current_price: continue

            # --- A. Check if we are already in a trade ---
            trade_active = False
            if symbol in state and state[symbol]['status'] == 'OPEN':
                trade_active = True
                new_status = manage_open_trade(exchange, symbol, state[symbol], current_price)
                
                if new_status != "OPEN":
                    # Trade closed. Calculate PNL and Win/Loss
                    buy_price = state[symbol]['buy_price']
                    amount = state[symbol].get('amount', TRADE_AMOUNT_USD / buy_price)
                    
                    trade_pnl_usd = (current_price - buy_price) * amount
                    is_win = trade_pnl_usd > 0
                    result_str = "🟢 WON" if is_win else "🔴 LOST"
                    
                    stats = load_stats()
                    stats["total_trades"] += 1
                    if is_win:
                        stats["wins"] += 1
                    else:
                        stats["losses"] += 1
                    stats["total_pnl_usd"] += trade_pnl_usd
                    save_stats(stats)
                    
                    # Update memory and alert.
                    if symbol in state:
                        del state[symbol]
                    save_state(state)
                    send_discord_alert(symbol, coin_name, f"EXIT: {new_status} | {result_str} | PNL: ${trade_pnl_usd:.2f}", current_price)
                    log_trade_history(f"{result_str} ({new_status}): {symbol} @ ${current_price:.6f}. (Bought at ${buy_price:.6f}) - PNL: ${trade_pnl_usd:.2f}")

            # --- B. Fetch Chart Data & Analyze ---
            df = fetch_ohlcv(exchange, symbol, timeframe=TIMEFRAME, limit=250)
            if df.empty or len(df) < 200:
                print(f"  ⚠️ Not enough data for {symbol}, skipping.")
                continue

            # Calculate the 7 custom indicators from your enhanced bot
            df = build_all_indicators(df)
            conf = score_confluence(df)
            verdict = conf["verdict"]

            row = df.iloc[-1]
            indicators = {
                "close":       round(float(row.close), 4),
                "ema9":        round(float(row.ema9),   4),
                "ema21":       round(float(row.ema21),  4),
                "ema50":       round(float(row.ema50),  4),
                "ema200":      round(float(row.ema200), 4),
                "macd":        round(float(row.macd),   6),
                "macd_sig":    round(float(row.macd_sig),  6),
                "macd_hist":   round(float(row.macd_hist), 6),
                "rsi":         round(float(row.rsi),   2),
                "bb_upper":    round(float(row.bb_upper), 4),
                "bb_mid":      round(float(row.bb_mid),   4),
                "bb_lower":    round(float(row.bb_lower), 4),
                "bb_pct_b":    round(float(row.bb_pct_b), 4),
                "atr":         round(float(row.atr),   4),
                "adx":         round(float(row.adx),   2),
                "plus_di":     round(float(row.plus_di), 2),
                "minus_di":    round(float(row.minus_di), 2),
            }

            history = [
                {
                    "date":      r["date"].strftime("%Y-%m-%d %H:%M"),
                    "price":     round(float(r["close"]),  4),
                    "ema21":     round(float(r["ema21"]),  4),
                    "ema50":     round(float(r["ema50"]),  4),
                    "ema200":    round(float(r["ema200"]), 4),
                    "rsi":       round(float(r["rsi"]),    2),
                    "macd_hist": round(float(r["macd_hist"]), 6),
                }
                for _, r in df.tail(90).iterrows()
            ]

            cycle_results.append({
                "coin":          coin_name.lower(),
                "ticker":        coin_name.upper(),
                "current_price": current_price,
                "change_24h":    0, # Simplified for continuous
                "market_cap":    0,
                "confluence":    conf,
                "action":        "HOLD" if trade_active else ("BUY" if verdict == "STRONG_BUY" else "HOLD"),
                "levels":        trade_levels(df, "BUY") if (verdict == "STRONG_BUY" or trade_active) else None,
                "indicators":    indicators,
                "history":       history,
                "timestamp":     now_str
            })

            # If we are already in an active trade, skip new buy logic and move to next coin.
            if trade_active:
                continue

            if verdict == "STRONG_BUY":
                print(f"\n  🎯 [SIGNAL TRIGGERED] {symbol} hit STRONG BUY requirements!")
                
                # --- NEW: AI SAFETY VETO ---
                ticker = symbol.split('/')[0]
                print(f"  🧠 Querying AI Sentiment safety check for {coin_name} ({ticker})...")
                ai_sentiment = get_ai_sentiment(coin_name, ticker)
                ai_verdict = ai_sentiment.get('verdict', 'NEUTRAL')
                
                if ai_verdict == "BEARISH":
                    print(f"  ❌ [SAFETY VETO] AI detected BEARISH sentiment! Cancelling technical buy sequence.")
                    print(f"     Reason: {ai_sentiment.get('reason')}")
                    continue
                else:
                    print(f"  ✅ [AI CLEARED] AI permits trade (Sentiment: {ai_verdict})")
                
                for signal in conf["signals"]:
                    if signal["bias"] == "BULL":
                        print(f"     + {signal['note']}")

                levels = trade_levels(df, "BUY")
                sl_price = levels["stop_loss"]
                tp_price = levels["take_profit"]

                # --- C. Execute Trade ---
                amount_filled = execute_market_buy(exchange, symbol, "BUY", current_price, sl_price, tp_price)
                
                if amount_filled:
                    # Save to Memory!
                    state[symbol] = {
                        "status": "OPEN",
                        "buy_price": current_price,
                        "amount": amount_filled,
                        "stop_loss": sl_price,
                        "take_profit": tp_price,
                        "timestamp": now_str
                    }
                    save_state(state)
                    
                    send_discord_alert(
                        symbol, coin_name, "🟢 ENTER LONG", current_price, 
                        reason=f"TP: ${tp_price:.2f} | SL: ${sl_price:.2f} | Score: {conf['score']}/7"
                    )
                    log_trade_history(f"🟡 OPENED LONG: {symbol} @ ${current_price:.6f} (TP: ${tp_price:.6f} | SL: ${sl_price:.6f})")

            
            else:
                # Still waiting for the perfect setup
                print(f"  [{symbol}] Status: Waiting. Score: {conf['score']}/7 (Needs 4/7). Current: ${current_price:.2f}")

        # --- D. Save to Dashboard & Sleep until next cycle ---
        stats = load_stats()
        stats["open_trades"] = len([x for x in state.values() if x.get("status") == "OPEN"])

        output = {
            "strategy": "Continuous 24/7 Multi-Confluence",
            "min_signals": 4,
            "results":  cycle_results,
            "aggregate_stats": stats,
            "generated": now_str,
        }
        with open("/Users/asoribabackend/Desktop/ai-trading-bot/enhanced_results.json", "w") as f:
            json.dump(output, f, indent=2, default=str)
            
        print(f"\n[DASHBOARD UI UPDATED] The NextJS web interface charts have been seeded!")
        print(f"💤 Cycle complete. Sleeping for {int(POLL_INTERVAL_SEC/60)} minutes...")
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    run_continuous_daemon()
