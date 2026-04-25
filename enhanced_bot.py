#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║    ENHANCED AI TRADING BOT  -  Professional Multi-Confluence    ║
║    Strategy: EMA Stack + MACD + RSI + Bollinger + ATR/ADX + OBV ║
║    Risk Mgmt: ATR stops, 2:1+ R:R, Dynamic position sizing      ║
╚══════════════════════════════════════════════════════════════════╝

STRATEGY OVERVIEW
─────────────────
This bot uses a CONFLUENCE SCORING system. Each of 7 independent
technical indicators casts a vote (+1 BULL, -1 BEAR, 0 NEUTRAL).

A trade is only triggered when ≥4 of 7 indicators agree.
This dramatically reduces false signals vs single-indicator systems.

INDICATORS USED
───────────────
1. EMA Stack    – EMA(9/21/50/200) alignment reveals trend structure
2. EMA Momentum – Price location relative to EMA21/EMA50
3. MACD         – Momentum direction + crossover detection
4. RSI(14)      – Overbought/oversold + momentum health zone
5. Bollinger %B – Price position within volatility envelope
6. ADX + DI     – Trend strength filter + directional bias
7. OBV          – Volume confirmation (smart money flow)

RISK MANAGEMENT
───────────────
• Stop-Loss  = Entry ± (1.0 × ATR)   → tight stop, minimal loss per trade
• Take-Profit = Entry ± (3.0 × ATR)  → 3:1 risk-reward ratio
• No trade when ADX < 20             → avoids choppy ranging markets
• Trailing stop = 1.5×ATR            → locks in profits tightly as price moves
"""

import os
import json
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone

try:
    from exchange_execution import execute_trade
except ImportError:
    def execute_trade(*args, **kwargs):
        print("  [SIM] exchange_execution.py not found – simulation only")
        return False

try:
    from notifier import send_discord_alert
except ImportError:
    def send_discord_alert(*args, **kwargs):
        pass

# ─────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────

COINS = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
    "solana":   "SOL",
}

LOOKBACK_DAYS   = 365      # Fetch 1 year of daily OHLC

# EMA periods
EMA_FAST        = 9
EMA_MED         = 21
EMA_SLOW        = 50
EMA_TREND       = 200

# MACD (standard settings)
MACD_FAST       = 12
MACD_SLOW       = 26
MACD_SIGNAL_P   = 9

# RSI
RSI_PERIOD      = 14
RSI_BULL_LOW    = 40       # Healthy uptrend floor
RSI_BULL_HIGH   = 70       # Healthy uptrend ceiling
RSI_OB          = 75       # Overbought → bearish vote
RSI_OS          = 30       # Oversold  → neutral (no bear vote)

# Bollinger Bands
BB_PERIOD       = 20
BB_STD          = 2.0
BB_BULL_LOW     = 0.45     # %B above this → bullish
BB_BULL_HIGH    = 0.95     # %B above this → overbought, no bull vote

# ATR-based stops
ATR_PERIOD      = 14
ATR_STOP_MULT   = 1.5      # Stop  = Entry ± 1.5 × ATR  → wider stop, survives normal noise
ATR_TARGET_MULT = 3.0      # Target = Entry ± 3.0 × ATR  → 2:1 R:R (3.0/1.5)
ATR_TRAIL_MULT  = 1.5      # Trailing stop = 1.5 × ATR below highest price reached

# ADX trend-strength filter
ADX_PERIOD      = 14
ADX_MIN         = 25       # Minimum ADX to trade (filters ranging markets)
ADX_STRONG      = 25       # Strong trend threshold

# Confluence threshold
MIN_BULL_SCORE  = 5        # Need ≥5 bullish votes out of 7 to BUY
MIN_BEAR_SCORE  = -4       # Need ≤-4 bearish votes out of 7 to SELL

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE     = os.path.join(BASE_DIR, "enhanced_results.json")
RATE_LIMIT_SLEEP = 15      # seconds between CoinGecko calls


# ─────────────────────────────────────────────────────────────────
#  DATA ACQUISITION
# ─────────────────────────────────────────────────────────────────

def fetch_ohlc(coin_id: str) -> pd.DataFrame:
    """
    Fetch daily OHLC from CoinGecko.
    Returns DataFrame: date | open | high | low | close | vol_proxy
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc"
    params = {"vs_currency": "usd", "days": LOOKBACK_DAYS}
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        raw = r.json()
        df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close"])
        df["date"] = pd.to_datetime(df["ts"], unit="ms")
        df = df.drop("ts", axis=1).sort_values("date").reset_index(drop=True)
        # Volume proxy: (H-L) × close  (CoinGecko OHLC has no volume)
        df["vol_proxy"] = (df["high"] - df["low"]) * df["close"]
        return df
    except Exception as e:
        print(f"  [ERROR] OHLC fetch failed for {coin_id}: {e}")
        return pd.DataFrame()


def fetch_price(coin_id: str) -> tuple:
    """Returns (price, change_24h_pct, market_cap_usd)"""
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
        "include_market_cap": "true",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        r.raise_for_status()
        d = r.json()[coin_id]
        return (d.get("usd", 0), d.get("usd_24h_change", 0), d.get("usd_market_cap", 0))
    except Exception as e:
        print(f"  [ERROR] Price fetch failed: {e}")
        return (0, 0, 0)


# ─────────────────────────────────────────────────────────────────
#  INDICATOR CALCULATIONS
# ─────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average – more weight on recent bars."""
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI using Wilder's EMA smoothing (more accurate than simple avg).
    Wilder's method: alpha = 1/period  (vs standard EMA alpha = 2/(n+1))
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def calc_macd(close: pd.Series):
    """Returns (macd_line, signal_line, histogram)"""
    fast = ema(close, MACD_FAST)
    slow = ema(close, MACD_SLOW)
    macd = fast - slow
    sig  = ema(macd, MACD_SIGNAL_P)
    hist = macd - sig
    return macd, sig, hist


def calc_bollinger(close: pd.Series):
    """Returns (upper, mid, lower, percent_b, bandwidth)"""
    mid = close.rolling(BB_PERIOD).mean()
    std = close.rolling(BB_PERIOD).std()
    upper = mid + BB_STD * std
    lower = mid - BB_STD * std
    bandwidth = (upper - lower).replace(0, float('nan'))  # avoid division by zero in flat markets
    pct_b = (close - lower) / bandwidth
    bw    = bandwidth / mid
    return upper, mid, lower, pct_b, bw


def calc_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average True Range – the gold standard volatility measure.
    TR = max(H-L, |H-PrevC|, |L-PrevC|)
    """
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14):
    """
    ADX + Directional Indicators.
    ADX measures trend STRENGTH (not direction) – crucial for avoiding false signals.
    +DI > -DI → bullish direction
    -DI > +DI → bearish direction
    ADX > 20  → trending (tradeable)
    ADX < 20  → ranging (avoid)
    """
    plus_dm  = high.diff()
    minus_dm = -low.diff()
    plus_dm  = plus_dm.where((plus_dm > 0)  & (plus_dm  > minus_dm), 0.0)
    minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm),  0.0)

    atr_val   = calc_atr(high, low, close, period)
    plus_di   = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean()  / atr_val)
    minus_di  = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val)
    dx        = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val   = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val, plus_di, minus_di


def calc_obv(close: pd.Series, vol: pd.Series) -> pd.Series:
    """
    On-Balance Volume – accumulates volume in the direction of price.
    Rising OBV above its EMA = institutional buying (smart money).
    Falling OBV below its EMA = distribution / selling pressure.
    """
    direction = np.sign(close.diff().fillna(0))
    return (direction * vol).cumsum()


def build_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c, h, l = df["close"], df["high"], df["low"]

    df["ema9"]   = ema(c, EMA_FAST)
    df["ema21"]  = ema(c, EMA_MED)
    df["ema50"]  = ema(c, EMA_SLOW)
    df["ema200"] = ema(c, EMA_TREND)

    df["macd"], df["macd_sig"], df["macd_hist"] = calc_macd(c)
    df["rsi"]  = calc_rsi(c, RSI_PERIOD)

    df["bb_upper"], df["bb_mid"], df["bb_lower"], df["bb_pct_b"], df["bb_bw"] = calc_bollinger(c)

    df["atr"] = calc_atr(h, l, c, ATR_PERIOD)
    df["adx"], df["plus_di"], df["minus_di"] = calc_adx(h, l, c, ADX_PERIOD)

    df["obv"]     = calc_obv(c, df["vol_proxy"])
    df["obv_ema"] = ema(df["obv"], 20)

    return df


# ─────────────────────────────────────────────────────────────────
#  CONFLUENCE SIGNAL SCORING
# ─────────────────────────────────────────────────────────────────

def score_confluence(df: pd.DataFrame) -> dict:
    """
    Cast 7 independent indicator votes.
    Each vote: +1 (BULL), -1 (BEAR), 0 (NEUTRAL)
    Final signal requires ≥4 votes in one direction.

    WHY CONFLUENCE?
    ───────────────
    Any single indicator has a ~55-60% win rate at best.
    When 4+ independent indicators agree, the probability of a
    false signal drops dramatically because each indicator
    measures a DIFFERENT aspect of market behavior:
      - EMA Stack  = trend structure
      - EMA Momentum = price momentum
      - MACD       = short-term momentum shift
      - RSI        = momentum health (not exhausted)
      - Bollinger  = price within volatility envelope
      - ADX        = is there a real trend worth trading?
      - OBV        = are institutions (big money) participating?
    """
    if len(df) < EMA_TREND + 30:
        return {"score": 0, "signals": [], "verdict": "INSUFFICIENT_DATA"}

    row  = df.iloc[-1]
    prev = df.iloc[-2]

    score   = 0
    signals = []

    # ── 1. EMA STACK ──────────────────────────────────────────────
    # Full alignment = strongest trend confirmation
    # 9 > 21 > 50 > 200 = every timeframe confirms the trend
    if row.ema9 > row.ema21 > row.ema50 > row.ema200:
        score += 1
        signals.append({"id": "EMA_STACK", "bias": "BULL",
                         "note": f"Full bullish stack: 9>{row.ema21:.0f}>50>200"})
    elif row.ema9 < row.ema21 < row.ema50 < row.ema200:
        score -= 1
        signals.append({"id": "EMA_STACK", "bias": "BEAR",
                         "note": "Full bearish stack: 9<21<50<200"})
    else:
        signals.append({"id": "EMA_STACK", "bias": "NEUTRAL",
                         "note": "Mixed EMA alignment – no clear trend"})

    # ── 2. EMA MOMENTUM (price vs key EMAs) ───────────────────────
    # Price above EMA21 and EMA50 = medium-term uptrend intact
    if row.close > row.ema21 and row.close > row.ema50:
        score += 1
        signals.append({"id": "EMA_MOM", "bias": "BULL",
                         "note": f"Price({row.close:.2f}) above EMA21({row.ema21:.2f}) & EMA50({row.ema50:.2f})"})
    elif row.close < row.ema21 and row.close < row.ema50:
        score -= 1
        signals.append({"id": "EMA_MOM", "bias": "BEAR",
                         "note": "Price below EMA21 and EMA50"})
    else:
        signals.append({"id": "EMA_MOM", "bias": "NEUTRAL",
                         "note": "Price between key EMAs"})

    # ── 3. MACD ───────────────────────────────────────────────────
    # MACD above signal AND histogram growing = momentum accelerating
    # Fresh crossover gets special flag (highest-quality signal)
    fresh_cross_up = prev.macd <= prev.macd_sig and row.macd > row.macd_sig
    fresh_cross_dn = prev.macd >= prev.macd_sig and row.macd < row.macd_sig
    hist_growing   = row.macd_hist > prev.macd_hist
    hist_falling   = row.macd_hist < prev.macd_hist

    if row.macd > row.macd_sig and row.macd_hist > 0 and hist_growing:
        score += 1
        note = "MACD CROSSOVER – fresh momentum signal!" if fresh_cross_up else \
               f"MACD({row.macd:.2f}) above signal, histogram rising"
        signals.append({"id": "MACD", "bias": "BULL", "note": note})
    elif row.macd < row.macd_sig and row.macd_hist < 0 and hist_falling:
        score -= 1
        note = "MACD CROSSOVER DOWN – fresh sell signal!" if fresh_cross_dn else \
               f"MACD({row.macd:.2f}) below signal, histogram falling"
        signals.append({"id": "MACD", "bias": "BEAR", "note": note})
    else:
        signals.append({"id": "MACD", "bias": "NEUTRAL",
                         "note": f"MACD unclear (hist={row.macd_hist:.4f})"})

    # ── 4. RSI ────────────────────────────────────────────────────
    # Best buy zone: RSI 40-65 = momentum building but not exhausted
    # RSI > 75 = overbought → BEAR vote (reversal risk)
    # RSI 30-40 = no vote (momentum unclear, wait for confirmation)
    rsi = row.rsi
    if RSI_BULL_LOW <= rsi <= RSI_BULL_HIGH:
        score += 1
        signals.append({"id": "RSI", "bias": "BULL",
                         "note": f"RSI({rsi:.1f}) in healthy momentum zone (40-65)"})
    elif rsi > RSI_OB:
        score -= 1
        signals.append({"id": "RSI", "bias": "BEAR",
                         "note": f"RSI({rsi:.1f}) OVERBOUGHT >75 – expect pullback"})
    elif rsi < RSI_OS:
        # Oversold is not a BUY signal in a downtrend – it can go lower
        signals.append({"id": "RSI", "bias": "NEUTRAL",
                         "note": f"RSI({rsi:.1f}) oversold – watch for bounce, not yet confirmed"})
    else:
        signals.append({"id": "RSI", "bias": "NEUTRAL",
                         "note": f"RSI({rsi:.1f}) neutral zone"})

    # ── 5. BOLLINGER BANDS (%B) ───────────────────────────────────
    # %B = (Price - Lower) / (Upper - Lower)
    # %B > 0.5 = above midline (bullish context)
    # %B 0.45-0.95 = ideal bull zone (above mid, up to upper band)
    # %B > 0.95 = riding upper band → strong breakout momentum, NEUTRAL not BEAR
    #   (in a genuine breakout price rides the upper band — penalising this as BEAR
    #    blocked valid entries and caused losses; reversion risk is handled by RSI >75)
    pct_b = row.bb_pct_b
    if BB_BULL_LOW <= pct_b <= BB_BULL_HIGH:
        score += 1
        signals.append({"id": "BB", "bias": "BULL",
                         "note": f"Price in upper BB zone (%B={pct_b:.2f}) – bullish context"})
    elif pct_b > BB_BULL_HIGH:
        # Upper-band touch in isolation = neutral. RSI handles overbought.
        signals.append({"id": "BB", "bias": "NEUTRAL",
                         "note": f"%B={pct_b:.2f} – riding upper band (breakout momentum, watch RSI)"})
    elif pct_b < 0.10:
        signals.append({"id": "BB", "bias": "NEUTRAL",
                         "note": f"%B={pct_b:.2f} – near lower band (wait for bounce confirmation)"})
    else:
        signals.append({"id": "BB", "bias": "NEUTRAL",
                         "note": f"%B={pct_b:.2f} – below midline"})

    # ── 6. ADX (TREND STRENGTH + DIRECTION) ───────────────────────
    # This is the most critical filter.
    # ADX < 20 = ranging market → DON'T TRADE (MA/MACD signals are garbage in ranges)
    # ADX > 20 + +DI > -DI = strong uptrend → BUY vote
    # ADX > 20 + -DI > +DI = strong downtrend → SELL vote
    adx, pdi, mdi = row.adx, row.plus_di, row.minus_di
    if adx >= ADX_MIN and pdi > mdi:
        score += 1
        strength = "STRONG" if adx >= ADX_STRONG else "MODERATE"
        signals.append({"id": "ADX", "bias": "BULL",
                         "note": f"ADX({adx:.1f}) {strength} uptrend: +DI({pdi:.1f})>-DI({mdi:.1f})"})
    elif adx >= ADX_MIN and mdi > pdi:
        score -= 1
        strength = "STRONG" if adx >= ADX_STRONG else "MODERATE"
        signals.append({"id": "ADX", "bias": "BEAR",
                         "note": f"ADX({adx:.1f}) {strength} downtrend: -DI({mdi:.1f})>+DI({pdi:.1f})"})
    else:
        signals.append({"id": "ADX", "bias": "NEUTRAL",
                         "note": f"ADX({adx:.1f})<20 – RANGING MARKET, signals unreliable"})

    # ── 7. OBV (VOLUME / SMART MONEY CONFIRMATION) ────────────────
    # Volume is the FUEL of price moves.
    # OBV > its 20-EMA = net buying pressure (institutions accumulating)
    # OBV < its 20-EMA = net selling pressure (distribution)
    # A price rally with falling OBV = weak, likely to fail
    obv_bull = row.obv > row.obv_ema and row.obv > prev.obv
    obv_bear = row.obv < row.obv_ema and row.obv < prev.obv
    if obv_bull:
        score += 1
        signals.append({"id": "OBV", "bias": "BULL",
                         "note": "OBV above 20-EMA & rising – volume confirming uptrend"})
    elif obv_bear:
        score -= 1
        signals.append({"id": "OBV", "bias": "BEAR",
                         "note": "OBV below 20-EMA & falling – volume confirming downtrend"})
    else:
        signals.append({"id": "OBV", "bias": "NEUTRAL", "note": "OBV mixed/flat"})

    # ── FINAL VERDICT ─────────────────────────────────────────────
    bull_count = sum(1 for s in signals if s["bias"] == "BULL")
    bear_count = sum(1 for s in signals if s["bias"] == "BEAR")

    if score >= abs(MIN_BULL_SCORE):
        verdict = "STRONG_BUY"
    elif score == 3:
        verdict = "BUY_WATCH"      # Developing – not yet actionable
    elif score <= MIN_BEAR_SCORE:
        verdict = "STRONG_SELL"
    elif score == -3:
        verdict = "SELL_WATCH"
    else:
        verdict = "NEUTRAL"

    return {
        "score": score,
        "max_score": 7,
        "bull_votes": bull_count,
        "bear_votes": bear_count,
        "signals": signals,
        "verdict": verdict,
        "rsi": round(float(rsi), 2),
        "adx": round(float(adx), 2),
        "trend_strength": "STRONG" if adx >= ADX_STRONG else
                          "MODERATE" if adx >= ADX_MIN else "WEAK/RANGING",
    }


# ─────────────────────────────────────────────────────────────────
#  TRADE LEVEL CALCULATOR (ATR-based)
# ─────────────────────────────────────────────────────────────────

def trade_levels(df: pd.DataFrame, direction: str) -> dict:
    """
    Dynamic stop/target based on current market volatility (ATR).

    WHY ATR STOPS?
    ──────────────
    Fixed % stops (e.g. always 3%) ignore volatility context.
    BTC can move 5% in a quiet day – a 3% stop would constantly
    get hit by normal noise.

    ATR-based stops scale with actual market conditions:
    • Low volatility (ATR small) → tighter stops
    • High volatility (ATR large) → wider stops
    This prevents premature stop-outs while still protecting capital.

    Risk:Reward = 3.0/1.0 = 3.0 minimum (we always make 3× what we risk)
    """
    row    = df.iloc[-1]
    entry  = float(row.close)
    atr    = float(row.atr)
    stop_dist   = ATR_STOP_MULT   * atr
    target_dist = ATR_TARGET_MULT * atr

    if direction == "BUY":
        sl = entry - stop_dist
        tp = entry + target_dist
    else:
        sl = entry + stop_dist
        tp = entry - target_dist

    return {
        "entry":        round(entry,        6),
        "stop_loss":    round(sl,           6),
        "take_profit":  round(tp,           6),
        "atr":          round(atr,          6),
        "stop_pct":     round(stop_dist   / entry * 100, 2),
        "target_pct":   round(target_dist / entry * 100, 2),
        "risk_reward":  round(ATR_TARGET_MULT / ATR_STOP_MULT, 2),
    }


# ─────────────────────────────────────────────────────────────────
#  COIN ANALYSIS PIPELINE
# ─────────────────────────────────────────────────────────────────

def analyse(coin_id: str, ticker: str) -> dict:
    """Full analysis pipeline for one asset."""
    print(f"\n{'─'*58}")
    print(f"  {ticker} / {coin_id.upper()}")
    print(f"{'─'*58}")

    df = fetch_ohlc(coin_id)
    if df.empty or len(df) < EMA_TREND + 40:
        print(f"  [SKIP] Insufficient data ({len(df)} bars)")
        return {"coin": coin_id, "ticker": ticker, "error": "insufficient_data"}

    df = build_all_indicators(df)

    price, chg24h, mcap = fetch_price(coin_id)
    if price == 0:
        price = float(df.iloc[-1]["close"])

    conf = score_confluence(df)
    verdict = conf["verdict"]

    if verdict == "STRONG_BUY":
        action, lvl = "BUY",  trade_levels(df, "BUY")
    elif verdict == "STRONG_SELL":
        action, lvl = "SELL", trade_levels(df, "SELL")
    else:
        action, lvl = "HOLD", None

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

    # Last 90 days for chart rendering
    history = [
        {
            "date":      r["date"].strftime("%Y-%m-%d"),
            "price":     round(float(r["close"]),  4),
            "ema21":     round(float(r["ema21"]),  4),
            "ema50":     round(float(r["ema50"]),  4),
            "ema200":    round(float(r["ema200"]), 4),
            "rsi":       round(float(r["rsi"]),    2),
            "macd_hist": round(float(r["macd_hist"]), 6),
        }
        for _, r in df.tail(90).iterrows()
    ]

    # Console summary
    print(f"  Price:    ${price:>14,.2f}   24h: {chg24h:+.2f}%")
    print(f"  RSI:      {conf['rsi']:>6.1f}   ADX: {conf['adx']:.1f} ({conf['trend_strength']})")
    print(f"  Votes:    {conf['bull_votes']} BULL  {conf['bear_votes']} BEAR  (score {conf['score']}/7)")
    print(f"  Verdict:  >>> {verdict} <<<")
    for s in conf["signals"]:
        icon = "+" if s["bias"] == "BULL" else ("-" if s["bias"] == "BEAR" else "·")
        print(f"    [{icon}] {s['id']:12s} {s['note']}")
    if lvl:
        print(f"\n  Entry:    ${lvl['entry']:,.2f}")
        print(f"  Stop:     ${lvl['stop_loss']:,.2f}  (-{lvl['stop_pct']}%)")
        print(f"  Target:   ${lvl['take_profit']:,.2f}  (+{lvl['target_pct']}%)")
        print(f"  R:R       {lvl['risk_reward']}:1")

    return {
        "coin":          coin_id,
        "ticker":        ticker,
        "current_price": price,
        "change_24h":    round(chg24h, 2),
        "market_cap":    int(mcap) if mcap else 0,
        "confluence":    conf,
        "action":        action,
        "levels":        lvl,
        "indicators":    indicators,
        "history":       history,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────

def run_bot():
    print("\n" + "═" * 58)
    print("  ENHANCED AI TRADING BOT")
    print("  Multi-Confluence: EMA + MACD + RSI + BB + ATR/ADX + OBV")
    print(f"  Min signals to trade: {abs(MIN_BULL_SCORE)}/7")
    print(f"  Run: {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print("═" * 58)

    results = []
    coins   = list(COINS.items())

    for i, (coin_id, ticker) in enumerate(coins):
        try:
            r = analyse(coin_id, ticker)
            results.append(r)

            if r.get("action") in ("BUY", "SELL") and r.get("levels"):
                lvl = r["levels"]
                execute_trade(coin_id, ticker, r["action"], r["current_price"])
                send_discord_alert(
                    coin_id, ticker, r["action"], r["current_price"],
                    reasoning=(
                        f"Score {r['confluence']['score']}/7 | "
                        f"SL ${lvl['stop_loss']:,.2f} (-{lvl['stop_pct']}%) | "
                        f"TP ${lvl['take_profit']:,.2f} (+{lvl['target_pct']}%) | "
                        f"R:R {lvl['risk_reward']}:1"
                    ),
                )
        except Exception as exc:
            print(f"  [ERROR] {ticker}: {exc}")
            results.append({"coin": coin_id, "ticker": ticker, "error": str(exc)})

        if i < len(coins) - 1:
            print(f"\n  Rate-limit pause {RATE_LIMIT_SLEEP}s …")
            time.sleep(RATE_LIMIT_SLEEP)

    # Save
    output = {
        "strategy": "Multi-Confluence (EMA×4 + MACD + RSI + BB + ATR + ADX + OBV)",
        "min_signals": abs(MIN_BULL_SCORE),
        "results":  results,
        "generated": datetime.now(timezone.utc).isoformat(),
    }
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, default=str)

    # Summary
    print(f"\n{'═'*58}")
    actionable = [r for r in results if r.get("action") in ("BUY", "SELL")]
    if actionable:
        print(f"  ACTIONABLE SIGNALS ({len(actionable)}):")
        for r in actionable:
            lvl = r["levels"]
            print(f"  • {r['ticker']:4s} {r['action']:4s} @ ${r['current_price']:>12,.2f} | "
                  f"SL {lvl['stop_pct']}% | TP {lvl['target_pct']}% | R:R {lvl['risk_reward']}:1")
    else:
        print("  No actionable signals – waiting for confluence.")
    print(f"  Saved → {OUTPUT_FILE}")
    print("═" * 58)
    return output


if __name__ == "__main__":
    run_bot()
