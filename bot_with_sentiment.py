"""
AI Trading Bot — MA Crossover + Perplexity AI Sentiment
═══════════════════════════════════════════════════════
Two-layer confirmation strategy:
  Layer 1: 20-day vs 50-day Moving Average crossover (chart signal)
  Layer 2: Perplexity AI real-time sentiment analysis

Rule: Only act when BOTH layers agree.
  - MA Golden Cross  + AI says Bullish  →  BUY  ✅
  - MA Death Cross   + AI says Bearish  →  SELL ✅
  - Layers disagree                     →  WAIT ⛔

Data:   CoinGecko API (free)
AI:     Perplexity sonar-pro model
"""

import os
import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime

# Import our new exchange execution module
from exchange_execution import execute_trade
from notifier import send_discord_alert

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")   # set via env var
PERPLEXITY_MODEL   = "sonar"                  # free-tier model
PERPLEXITY_URL     = "https://api.perplexity.ai/chat/completions"

SHORT_WINDOW       = 20    # 20-day MA (faster signal)
LONG_WINDOW        = 50    # 50-day MA (trend baseline)
RSI_PERIOD         = 14
LOOKBACK_DAYS      = 120   # enough data to warm up both MAs + buffer

COINS = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
    "solana":   "SOL",
}


# ─────────────────────────────────────────────
#  LAYER 1 — CHART SIGNAL (MA Crossover + RSI)
# ─────────────────────────────────────────────
def fetch_price_data(coin_id: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Fetch daily price data from CoinGecko (free, no API key)."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days={days}"
    headers = {"accept": "application/json", "User-Agent": "AI-Trading-Bot/2.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        prices = r.json().get("prices", [])
        df = pd.DataFrame(prices, columns=["ts", "price"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms").dt.normalize()
        df.set_index("date", inplace=True)
        df.drop(columns=["ts"], inplace=True)
        df = df[~df.index.duplicated(keep="last")]
        return df
    except Exception as e:
        print(f"  ✗ Price fetch error: {e}")
        return pd.DataFrame()


def fetch_current_price(coin_id: str):
    """Get the live spot price and 24h change."""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true"
    try:
        r = requests.get(url, headers={"accept": "application/json"}, timeout=10)
        r.raise_for_status()
        data = r.json()[coin_id]
        return data["usd"], data.get("usd_24h_change", 0)
    except Exception:
        return None, None


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["sma20"] = df["price"].rolling(SHORT_WINDOW, min_periods=SHORT_WINDOW).mean()
    df["sma50"] = df["price"].rolling(LONG_WINDOW,  min_periods=LONG_WINDOW).mean()

    delta    = df["price"].diff()
    gain     = delta.where(delta > 0, 0.0)
    loss     = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.rolling(RSI_PERIOD, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))
    return df.dropna(subset=["sma20", "sma50"])


def get_chart_signal(df: pd.DataFrame) -> dict:
    """
    Returns the chart-based signal:
      BULLISH  = short MA just crossed above long MA (Golden Cross)
      BEARISH  = short MA just crossed below long MA (Death Cross)
      HOLD_UP  = short MA still above long MA (no fresh crossover)
      HOLD_DN  = short MA still below long MA (no fresh crossover)
    """
    if len(df) < 2:
        return {"verdict": "INSUFFICIENT_DATA", "confidence": "LOW"}

    prev = df.iloc[-2]
    curr = df.iloc[-1]
    rsi  = curr["rsi"]

    was_below = prev["sma20"] < prev["sma50"]
    is_above  = curr["sma20"] > curr["sma50"]
    was_above = prev["sma20"] > prev["sma50"]
    is_below  = curr["sma20"] < curr["sma50"]

    gap_pct = abs(curr["sma20"] - curr["sma50"]) / curr["sma50"] * 100

    if was_below and is_above:
        verdict    = "BULLISH"
        event      = "Golden Cross 🟢"
        confidence = "HIGH" if rsi < 70 else "MEDIUM"
    elif was_above and is_below:
        verdict    = "BEARISH"
        event      = "Death Cross 🔴"
        confidence = "HIGH" if rsi > 30 else "MEDIUM"
    elif is_above:
        verdict    = "HOLD_UP"
        event      = "Uptrend (no new cross)"
        confidence = "LOW"
    else:
        verdict    = "HOLD_DN"
        event      = "Downtrend (no new cross)"
        confidence = "LOW"

    return {
        "verdict":    verdict,
        "event":      event,
        "confidence": confidence,
        "sma20":      round(curr["sma20"], 2),
        "sma50":      round(curr["sma50"], 2),
        "rsi":        round(rsi, 2) if not np.isnan(rsi) else "N/A",
        "gap_pct":    round(gap_pct, 3),
    }


# ─────────────────────────────────────────────
#  LAYER 2 — PERPLEXITY AI SENTIMENT
# ─────────────────────────────────────────────
def get_ai_sentiment(coin_name: str, ticker: str) -> dict:
    """
    Asks Perplexity AI for the current market sentiment on a coin.
    Returns: BULLISH, BEARISH, or NEUTRAL with a short reasoning.
    """
    if not PERPLEXITY_API_KEY:
        return {
            "verdict":   "UNAVAILABLE",
            "reasoning": "No PERPLEXITY_API_KEY set. Export it as an env variable.",
            "confidence": "N/A",
        }

    prompt = f"""You are a professional crypto market analyst. 
Based on the latest news, on-chain data, macro events, and market sentiment 
as of today, analyze {coin_name} ({ticker}).

Respond with EXACTLY this JSON format — no extra text:
{{
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "key_reason": "One sentence summary of the main bullish or bearish driver",
  "risks": "One sentence on the main risk to this view"
}}"""

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {"role": "system", "content": "You are a concise, data-driven crypto market analyst. Always respond with valid JSON only."},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": 300,
        "temperature": 0.2,   # low temp = more consistent/factual
        "search_recency_filter": "day",   # Perplexity searches the web — restrict to today
    }

    try:
        r = requests.post(PERPLEXITY_URL, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        content = content.strip()

        parsed = json.loads(content)
        return {
            "verdict":    parsed.get("sentiment", "NEUTRAL").upper(),
            "confidence": parsed.get("confidence", "MEDIUM"),
            "reason":     parsed.get("key_reason", ""),
            "risks":      parsed.get("risks", ""),
        }

    except json.JSONDecodeError:
        # Perplexity returned something non-JSON — extract keyword
        verdict = "NEUTRAL"
        for kw in ["BULLISH", "BEARISH", "NEUTRAL"]:
            if kw in content.upper():
                verdict = kw
                break
        return {"verdict": verdict, "confidence": "LOW", "reason": content[:200], "risks": ""}

    except Exception as e:
        return {
            "verdict":    "ERROR",
            "confidence": "N/A",
            "reason":     str(e),
            "risks":      "",
        }


# ─────────────────────────────────────────────
#  SIGNAL FUSION — Both Layers Must Agree
# ─────────────────────────────────────────────
def fuse_signals(chart: dict, sentiment: dict) -> dict:
    """
    Combines chart signal + AI sentiment into a final trading decision.
    
    BUY  only if: chart=BULLISH  AND  AI=BULLISH
    SELL only if: chart=BEARISH  AND  AI=BEARISH
    HOLD in all other cases (disagreement = sit on hands)
    """
    cv = chart["verdict"]
    sv = sentiment["verdict"]

    if cv == "BULLISH" and sv == "BULLISH":
        action     = "BUY 🟢"
        final      = "STRONG BUY"
        emoji      = "🟢"
        both_agree = True
        confidence = "HIGH" if (chart["confidence"] == "HIGH" and sentiment["confidence"] in ["HIGH","MEDIUM"]) else "MEDIUM"
    elif cv == "BEARISH" and sv == "BEARISH":
        action     = "SELL / EXIT 🔴"
        final      = "STRONG SELL"
        emoji      = "🔴"
        both_agree = True
        confidence = "HIGH" if (chart["confidence"] == "HIGH" and sentiment["confidence"] in ["HIGH","MEDIUM"]) else "MEDIUM"
    elif cv == "BULLISH" and sv in ["BEARISH", "NEUTRAL"]:
        action     = "WAIT — Chart bullish but AI cautious ⚠️"
        final      = "NO TRADE"
        emoji      = "🟡"
        both_agree = False
        confidence = "LOW"
    elif cv == "BEARISH" and sv in ["BULLISH", "NEUTRAL"]:
        action     = "WAIT — Chart bearish but AI bullish ⚠️"
        final      = "NO TRADE"
        emoji      = "🟡"
        both_agree = False
        confidence = "LOW"
    else:
        action     = "HOLD — No clear directional signal"
        final      = "HOLD"
        emoji      = "⚪"
        both_agree = False
        confidence = "LOW"

    return {
        "final_signal": final,
        "action":       action,
        "emoji":        emoji,
        "both_agree":   both_agree,
        "confidence":   confidence,
    }


# ─────────────────────────────────────────────
#  PRINT REPORT
# ─────────────────────────────────────────────
def print_coin_report(coin_id: str, ticker: str, price: float, change_24h: float,
                       chart: dict, sentiment: dict, fused: dict):
    sep = "─" * 58
    print(f"\n{'═'*58}")
    print(f"  {fused['emoji']}  {coin_id.upper()} ({ticker})")
    print(f"{'═'*58}")

    # Price
    if price:
        sign = "+" if change_24h and change_24h > 0 else ""
        ch   = f"{sign}{change_24h:.2f}%" if change_24h else "N/A"
        print(f"  💰 Price       : ${price:,.4f}  ({ch} 24h)")
    print(sep)

    # Chart layer
    print(f"  📊 CHART SIGNAL — Layer 1")
    print(f"     Event      : {chart.get('event', 'N/A')}")
    print(f"     20-day MA  : ${chart.get('sma20', 'N/A'):,}")
    print(f"     50-day MA  : ${chart.get('sma50', 'N/A'):,}")
    print(f"     RSI (14)   : {chart.get('rsi', 'N/A')}")
    print(f"     Confidence : {chart.get('confidence', 'N/A')}")
    print(sep)

    # AI layer
    print(f"  🧠 AI SENTIMENT — Layer 2 (Perplexity)")
    print(f"     Verdict    : {sentiment.get('verdict', 'N/A')}")
    print(f"     Confidence : {sentiment.get('confidence', 'N/A')}")
    if sentiment.get("reason"):
        print(f"     Reason     : {sentiment['reason']}")
    if sentiment.get("risks"):
        print(f"     Risk       : {sentiment['risks']}")
    print(sep)

    # Final decision
    print(f"  🎯 FINAL DECISION")
    print(f"     Signal     : {fused['final_signal']}")
    print(f"     Action     : {fused['action']}")
    print(f"     Confidence : {fused['confidence']}")
    both_str = "✅ YES — Both signals aligned" if fused["both_agree"] else "❌ NO  — Signals conflict, staying out"
    print(f"     Both Agree : {both_str}")
    print(f"{'═'*58}")


# ─────────────────────────────────────────────
#  MAIN BOT RUNNER
# ─────────────────────────────────────────────
def run_bot():
    print("\n" + "═"*58)
    print("  🤖  AI TRADING BOT v2 — Dual Confirmation Strategy")
    print("═"*58)
    print(f"  Chart  : {SHORT_WINDOW}-day MA vs {LONG_WINDOW}-day MA crossover")
    print(f"  AI     : Perplexity real-time market sentiment")
    print(f"  Rule   : Trade ONLY when both layers agree")
    print(f"  Time   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═"*58)

    if not PERPLEXITY_API_KEY:
        print("\n  ⚠️  WARNING: PERPLEXITY_API_KEY not set!")
        print("  Export it first:  export PERPLEXITY_API_KEY='pplx-xxxx...'")
        print("  Get a free key at: https://www.perplexity.ai/settings/api")
        print("  Continuing with chart signals only...\n")

    all_results = []

    for coin_id, ticker in COINS.items():
        print(f"\n⏳ Analysing {coin_id.upper()} ({ticker})...")

        # ── Layer 1: Chart ──
        df = fetch_price_data(coin_id)
        if df.empty:
            print(f"  ⚠️  No data for {coin_id}, skipping.")
            continue
        df          = compute_indicators(df)
        chart_sig   = get_chart_signal(df)
        price, ch24 = fetch_current_price(coin_id)

        # ── Layer 2: AI Sentiment ──
        print(f"  🧠 Querying Perplexity AI for {coin_id.upper()} sentiment...")
        ai_sig = get_ai_sentiment(coin_id, ticker)

        # ── Fusion ──
        fused = fuse_signals(chart_sig, ai_sig)

        # ── Print ──
        print_coin_report(coin_id, ticker, price, ch24, chart_sig, ai_sig, fused)

        # ── Execution ──
        if fused["final_signal"] in ["STRONG BUY", "STRONG SELL"]:
            execute_trade(
                coin_id=coin_id,
                ticker=ticker,
                action=fused["final_signal"],
                price=price
            )
            # Send Notification immediately after execution
            send_discord_alert(
                coin_id=coin_id, 
                ticker=ticker, 
                action=fused["final_signal"], 
                price=price,
                reason=f"Technical: {chart_sig['event']} | Sentiment: {ai_sig['verdict']}"
            )

        all_results.append({
            "coin":       coin_id,
            "ticker":     ticker,
            "price":      price,
            "change_24h": round(ch24, 2) if ch24 else None,
            "chart":      chart_sig,
            "sentiment":  ai_sig,
            "decision":   fused,
            "timestamp":  datetime.now().isoformat(),
        })

        # Rate limit between coins
        if coin_id != list(COINS.keys())[-1]:
            print(f"\n  ⏸️  Waiting 12s (API rate limit)...")
            time.sleep(12)

    # Summary table
    print(f"\n{'═'*58}")
    print(f"  📋  SUMMARY")
    print(f"{'═'*58}")
    print(f"  {'Coin':<10} {'Chart':<12} {'AI':<12} {'Decision':<16} Confidence")
    print(f"  {'─'*56}")
    for r in all_results:
        print(f"  {r['ticker']:<10} "
              f"{r['chart']['verdict']:<12} "
              f"{r['sentiment']['verdict']:<12} "
              f"{r['decision']['final_signal']:<16} "
              f"{r['decision']['confidence']}")
    print(f"{'═'*58}\n")
    print("  ⚠️  DISCLAIMER: Educational use only. Not financial advice.")
    print("     Always use stop-losses. Never risk more than 1-2% per trade.\n")

    # Save results
    out_path = "/Users/asoribabackend/.gemini/antigravity/scratch/ai-trading-bot/sentiment_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"  📁 Results saved to sentiment_results.json\n")

    return all_results


if __name__ == "__main__":
    run_bot()
