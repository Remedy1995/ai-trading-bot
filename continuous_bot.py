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
from enhanced_bot import build_all_indicators, score_confluence, trade_levels, ATR_TRAIL_MULT
from notifier import send_discord_alert, send_open_trades_summary

# ─────────────────────────────────────────────────────────────────
#  1. BOT CONFIGURATION (24/7 DAEMON MODE)
# ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# In Docker the shared volume is mounted at /app/data; locally files sit next to the script
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
STATE_FILE      = os.path.join(DATA_DIR, "open_trades.json")
STATS_FILE      = os.path.join(DATA_DIR, "trade_stats.json")
SETTINGS_FILE   = os.path.join(DATA_DIR, "settings.json")
HISTORY_FILE    = os.path.join(DATA_DIR, "trade_history.txt")
RESULTS_FILE    = os.path.join(DATA_DIR, "enhanced_results.json")
BOT_STATE_FILE  = os.path.join(DATA_DIR, "bot_state.json")  # Single source of truth for dashboard

POLL_INTERVAL_SEC = 60 * 5               # Check the market every 5 minutes
TRADE_AMOUNT_USD = 25.0                 # $25 per trade — safe for $100+ balance (4 trades max = $100)
TIMEFRAME = '1h'
MAX_DAILY_LOSS_USD = 10.0               # Stop entering new trades if daily losses hit this
MAX_OPEN_TRADES = 4                     # Max 4 simultaneous trades (4 × $12 = $48 fits $50 balance)
TIMEFRAME_TO_SECONDS = {'5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}

# Mid-trade score re-evaluation
# If the confluence score drops to or below this threshold WHILE in a trade,
# the bot will exit early to lock in any available profit.
MIN_SCORE_TO_HOLD = 2   # ≤ 2/7 → signals have deteriorated; exit if in profit

# Groq AI Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL   = "llama-3.1-70b-versatile"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

# Your Exchange configuration
EXCHANGE_ID = os.environ.get("EXCHANGE_NAME", "binance") # binance, coinbase, kraken
API_KEY = os.environ.get("EXCHANGE_API_KEY", "")
API_SECRET = os.environ.get("EXCHANGE_API_SECRET", "")
SIMULATION_MODE = os.environ.get("SIMULATION_MODE", "true").lower() != "false"  # Set SIMULATION_MODE=false in .env for live trading

# Fallback coin list — used if CoinGecko dynamic fetch fails
COINS_FALLBACK = {
    "BTC/USDT": "bitcoin",
    "ETH/USDT": "ethereum",
    "SOL/USDT": "solana",
    "WIF/USDT": "dogwifhat",
    "DOGE/USDT": "dogecoin"
}

# Dynamic universe settings
COIN_UNIVERSE_SIZE   = 20       # How many top coins to scan
MIN_VOLUME_24H_USD   = 500_000_000  # Skip coins with < $500M daily volume (low liquidity)

# ─────────────────────────────────────────────────────────────────
#  2. DYNAMIC COIN UNIVERSE
# ─────────────────────────────────────────────────────────────────

# CoinGecko ID → CCXT symbol mapping for common coins
_COINGECKO_TO_CCXT = {
    "bitcoin": "BTC/USDT", "ethereum": "ETH/USDT", "tether": None,
    "binancecoin": "BNB/USDT", "solana": "SOL/USDT", "ripple": "XRP/USDT",
    "usd-coin": None, "staked-ether": None, "cardano": "ADA/USDT",
    "avalanche-2": "AVAX/USDT", "dogecoin": "DOGE/USDT", "tron": "TRX/USDT",
    "chainlink": "LINK/USDT", "polkadot": "DOT/USDT", "matic-network": "MATIC/USDT",
    "shiba-inu": "SHIB/USDT", "litecoin": "LTC/USDT", "uniswap": "UNI/USDT",
    "near": "NEAR/USDT", "internet-computer": "ICP/USDT", "aptos": "APT/USDT",
    "optimism": "OP/USDT", "arbitrum": "ARB/USDT", "dogwifhat": "WIF/USDT",
    "pepe": "PEPE/USDT", "sui": "SUI/USDT", "injective-protocol": "INJ/USDT",
}

def fetch_dynamic_coins() -> dict:
    """
    Fetches the top COIN_UNIVERSE_SIZE coins from CoinGecko by market cap,
    filters out stablecoins and low-volume coins, and returns a
    {CCXT_SYMBOL: coingecko_id} dict ready to scan.
    Falls back to COINS_FALLBACK on any error.
    """
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 40,  # Fetch more than needed to allow for filtering
            "page": 1,
            "sparkline": False,
        }
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        coins = r.json()

        result = {}
        for coin in coins:
            cg_id = coin.get("id", "")
            volume = coin.get("total_volume", 0) or 0
            ccxt_symbol = _COINGECKO_TO_CCXT.get(cg_id)

            # Skip stablecoins (no mapping), low volume, or already have enough
            if ccxt_symbol is None or volume < MIN_VOLUME_24H_USD:
                continue

            result[ccxt_symbol] = cg_id
            if len(result) >= COIN_UNIVERSE_SIZE:
                break

        if result:
            print(f"  🌍 [UNIVERSE] Scanning {len(result)} coins: {', '.join(result.keys())}")
            return result
        else:
            print(f"  ⚠️  [UNIVERSE] Dynamic fetch returned no coins — using fallback list.")
            return COINS_FALLBACK

    except Exception as e:
        print(f"  ⚠️  [UNIVERSE] CoinGecko fetch failed ({e}) — using fallback list.")
        return COINS_FALLBACK


# ─────────────────────────────────────────────────────────────────
#  3. EXCHANGE AND MEMORY SETUP
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
    default_stats = {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "total_pnl_usd": 0.0,
        "total_fees_usd": 0.0,
        "net_pnl_usd": 0.0,
        "total_invested_usd": 0.0,
        "cumulative_gains_usd": 0.0,
        "cumulative_losses_usd": 0.0,
        "today_loss_usd": 0.0,
        "today_date": ""
    }
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r') as f:
            data = json.load(f)
            # Merge with default to ensure new keys exist
            for k, v in default_stats.items():
                if k not in data:
                    data[k] = v
            return data
    return default_stats

def save_stats(stats):
    """Saves the bot's aggregate stats to disk."""
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=4)

def log_trade_history(message):
    """Appends all permanent trade executions to a simple text file for easy reading."""
    from datetime import datetime
    with open(HISTORY_FILE, "a") as f:
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        f.write(f"[{now_str}] {message}\n")


# ─────────────────────────────────────────────────────────────────
#  4. FAST DATA FETCHING (No Rate Limits)
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

def check_higher_timeframe(exchange, symbol: str) -> dict:
    """
    Dynamic Higher Timeframe (HTF) filter — scales with the active TIMEFRAME.

    5m  trading → checks 1h  (makes sure bigger trend isn't bearish)
    15m trading → checks 1h
    1h  trading → checks 4h  (makes sure 4h trend isn't bearish)
    4h  trading → skips check (4h is already the big picture)
    1d  trading → skips check (daily is already the big picture)

    This prevents entering a signal that fights the broader trend.
    """
    # Map each trading timeframe to its higher timeframe
    htf_map = { '5m': '1h', '15m': '1h', '1h': '4h' }
    htf = htf_map.get(TIMEFRAME)

    # On 4h or 1d, no higher timeframe check needed — already the big picture
    if not htf:
        print(f"  📈 [MTF] {TIMEFRAME} is a high timeframe — no HTF check needed. Proceeding.")
        return {"score": 0, "verdict": "SKIPPED", "allowed": True}

    try:
        df_htf = fetch_ohlcv(exchange, symbol, timeframe=htf, limit=250)
        if df_htf.empty or len(df_htf) < 200:
            print(f"  ⚠️  [MTF] Not enough {htf} data for {symbol} — skipping HTF check, proceeding.")
            return {"score": 0, "verdict": "UNKNOWN", "allowed": True}

        df_htf   = build_all_indicators(df_htf)
        conf_htf = score_confluence(df_htf)
        score_htf   = conf_htf["score"]
        verdict_htf = conf_htf["verdict"]

        # Block entry if the HTF is net bearish or neutral-bearish (score < 0)
        # Must be neutral (0) or better — don't fight the bigger trend
        allowed = score_htf >= 0
        status  = "✅ ALIGNED" if allowed else "❌ CONFLICTING"
        print(f"  📈 [MTF {htf}] Score: {score_htf}/7 ({verdict_htf}) — {status}")
        return {"score": score_htf, "verdict": verdict_htf, "allowed": allowed}
    except Exception as e:
        print(f"  ⚠️  [MTF] {htf} check failed ({e}) — proceeding without HTF filter.")
        return {"score": 0, "verdict": "UNKNOWN", "allowed": True}


def get_fear_and_greed() -> dict:
    """
    Fetches the Crypto Fear & Greed Index from alternative.me (free, no API key).
    Returns a dict with 'value' (0-100) and 'label' (e.g. 'Extreme Fear').
    Falls back to neutral on any error.
    """
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=1", timeout=8)
        r.raise_for_status()
        data = r.json()["data"][0]
        return {"value": int(data["value"]), "label": data["value_classification"]}
    except Exception:
        return {"value": 50, "label": "Unknown"}


def get_coin_24h_change(exchange, symbol: str) -> float:
    """Fetches the 24h price change % for a symbol directly from the exchange."""
    try:
        ticker = exchange.fetch_ticker(symbol)
        return round(ticker.get("percentage", 0.0) or 0.0, 2)
    except Exception:
        return 0.0


def get_ai_sentiment(coin_name: str, ticker: str, exchange=None, symbol: str = "") -> dict:
    """
    Asks Groq AI (Llama 3.1) for market sentiment using REAL live data as context:
      - Crypto Fear & Greed Index (alternative.me)
      - 24h price change from the exchange
    This prevents the AI from reasoning on stale training data alone.
    """
    if not GROQ_API_KEY:
        return {"verdict": "NEUTRAL", "reason": "No API Key"}

    # Fetch real-time market context
    fng = get_fear_and_greed()
    change_24h = get_coin_24h_change(exchange, symbol) if (exchange and symbol) else 0.0

    # Interpret Fear & Greed for the prompt
    if fng["value"] <= 25:
        fng_interpretation = "extremely fearful — historically a contrarian buy zone, but also signals panic selling"
    elif fng["value"] <= 45:
        fng_interpretation = "fearful — market is risk-off, momentum is weak"
    elif fng["value"] <= 55:
        fng_interpretation = "neutral — no strong crowd directional bias"
    elif fng["value"] <= 75:
        fng_interpretation = "greedy — momentum is strong but watch for overextension"
    else:
        fng_interpretation = "extremely greedy — high reversal risk, market may be near a top"

    prompt = f"""You are a professional crypto market analyst providing context to a trading bot.

LIVE MARKET DATA (right now):
- Asset: {coin_name} ({ticker})
- 24h Price Change: {change_24h:+.2f}%
- Crypto Fear & Greed Index: {fng["value"]}/100 ({fng["label"]}) — {fng_interpretation}

Our 7-indicator technical system has triggered a STRONG BUY signal.
Your job is NOT to veto the trade. Instead, assess the macro sentiment and return
an adjustment to help calibrate how strong the technical signal needs to be:

- BULLISH macro: technical signal is confirmed by sentiment — normal threshold applies
- NEUTRAL macro: no strong opinion either way — normal threshold applies
- BEARISH macro: sentiment is against the trade — a stronger technical signal is preferred

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
            {"role": "system", "content": "You are a concise, data-driven crypto risk analyst. Valid JSON only. Never add text outside the JSON."},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": 150,
        "temperature": 0.1,
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
        verdict = parsed.get("sentiment", "NEUTRAL").upper()
        reason  = parsed.get("key_reason", "")
        print(f"  📊 [AI CONTEXT] F&G: {fng['value']} ({fng['label']}) | 24h: {change_24h:+.2f}% | Verdict: {verdict}")
        return {"verdict": verdict, "reason": reason}
    except Exception as e:
        return {"verdict": "NEUTRAL", "reason": f"API Error: {e}"}

# ─────────────────────────────────────────────────────────────────
#  5. ADVANCED ORDER EXECUTION & MANAGEMENT
# ─────────────────────────────────────────────────────────────────
def get_actual_balance(exchange, symbol):
    """
    Fetches the sellable balance for the base asset of a symbol from Binance.
    Uses 'free' balance first. If free is too small (locked in a stop order),
    falls back to 'total' balance so we can still sell.
    """
    try:
        base_asset = symbol.split('/')[0]
        balance = exchange.fetch_balance()
        free  = float(balance.get(base_asset, {}).get('free',  0.0) or 0.0)
        total = float(balance.get(base_asset, {}).get('total', 0.0) or 0.0)
        # Prefer free; fall back to total if free is essentially zero
        return free if free > 1e-9 else total
    except Exception as e:
        print(f"  ⚠️  Could not fetch {symbol} balance: {e}")
        return 0.0


def execute_sell(exchange, symbol, amount, reason):
    """
    Executes a market sell. Cancels any open stop orders first to free locked
    balance, then sells. Never crashes the daemon.

    Key fix: after rounding to exchange step-size, verify the amount is above the
    exchange minimum.  If it is below minimum (dust), treat the trade as closed so
    the bot stops retrying endlessly.
    """
    if SIMULATION_MODE or not exchange:
        print(f"  [SIMULATION] SOLD {amount:.6f} {symbol} ({reason})")
        return True

    try:
        # Cancel any open stop orders first — they lock the asset and block selling
        try:
            open_orders = exchange.fetch_open_orders(symbol)
            for order in open_orders:
                exchange.cancel_order(order['id'], symbol)
                print(f"  🗑️  Cancelled open stop order {order['id']} for {symbol}")
        except Exception as cancel_err:
            print(f"  ⚠️  Could not cancel open orders for {symbol}: {cancel_err}")

        # Fetch the freed balance
        actual_amount = get_actual_balance(exchange, symbol)
        if actual_amount <= 0:
            print(f"  ⚠️  [{reason}] No balance found for {symbol} — treating as already sold.")
            return True

        # Round to exchange step-size
        market = exchange.market(symbol)
        sell_amount = float(exchange.amount_to_precision(symbol, actual_amount))

        # Hard floor: if precision rounding reduced amount to zero — pure dust
        if sell_amount <= 0:
            print(f"  ⚠️  [{reason}] {symbol} rounded to 0 after precision. Marking closed.")
            log_trade_history(f"DUST CLOSE ({reason}): {symbol} — amount rounded to zero")
            return True

        # Check against exchange minimum order amount (e.g. XRP min=0.1, BNB min=0.001)
        min_amount = ((market.get('limits') or {}).get('amount') or {}).get('min') or 0
        if min_amount and sell_amount < min_amount:
            print(f"  ⚠️  [{reason}] {symbol} sell_amount {sell_amount} below exchange minimum {min_amount}. Marking closed.")
            log_trade_history(f"DUST CLOSE ({reason}): {symbol} — amount {sell_amount} below exchange min {min_amount}")
            return True

        # Use sell_amount (not actual_amount) for the notional check — avoids
        # mismatch where actual passes $1 but rounded sell amount falls below notional
        current_price_now = exchange.fetch_ticker(symbol).get('last') or 0
        order_value = sell_amount * current_price_now
        if order_value < 2.0:
            print(f"  ⚠️  [{reason}] {symbol} order value ${order_value:.4f} < $2. Marking closed.")
            log_trade_history(f"DUST CLOSE ({reason}): {symbol} — order value ${order_value:.4f}")
            return True

        # Attempt the sell — wrap in its own try so failures here don't cause a retry
        try:
            exchange.create_market_order(symbol, 'sell', sell_amount)
            print(f"  ✅ [{reason}] Sold {sell_amount} {symbol} successfully.")
            return True
        except Exception as sell_err:
            # Only treat as unrecoverable dust if order value is very small (< 15% of trade size)
            # Larger positions that fail to sell should retry — likely a temporary API/network issue
            dust_threshold = TRADE_AMOUNT_USD * 0.15
            if order_value < dust_threshold:
                print(f"  ⚠️  [{reason}] {symbol} sell error on small position (${order_value:.2f}): {sell_err}. Marking closed.")
                log_trade_history(f"DUST CLOSE ({reason}): {symbol} — sell error on ${order_value:.2f} position: {sell_err}")
                return True
            raise  # full-size position — propagate so outer except logs and retries

    except Exception as e:
        print(f"  ❌ [{reason}] Sell failed for {symbol}: {e}. Will retry next cycle.")
        log_trade_history(f"SELL FAILED ({reason}): {symbol} — {e}")
        return False


def manage_open_trade(exchange, symbol, trade_info, current_price, current_score: int = None):
    """
    Hybrid Exit Handler — Fixed TP + Trailing Stop + Mid-Trade Score Re-Evaluation.

    Exit hierarchy (checked in order):
    1. Fixed TP       — sells when price hits the target, guaranteed profit
    2. Hard SL        — fixed floor, fires instantly on crash
    3. Trailing Stop  — rising stop that locks in profit as price climbs
    4. Score Exit     — if confluence score drops to ≤ MIN_SCORE_TO_HOLD AND
                        the trade is in profit → exit early rather than risk
                        giving back gains while waiting for a TP the market
                        no longer supports.
    """
    hard_sl    = trade_info["stop_loss"]
    tp_price   = trade_info["take_profit"]
    buy_price  = trade_info["buy_price"]
    amount     = trade_info["amount"]
    trail_atr  = trade_info.get("trail_atr", 0)

    # Ratchet highest price up (never down)
    highest = max(trade_info.get("highest_price", buy_price), current_price)
    trade_info["highest_price"] = highest

    # Trailing stop = highest price reached minus 2×ATR — rises with price, never drops
    trail_stop = highest - (ATR_TRAIL_MULT * trail_atr) if trail_atr > 0 else hard_sl
    # Trailing stop can only ever be above the hard SL
    effective_stop = max(trail_stop, hard_sl)

    pnl = ((current_price - buy_price) / buy_price) * 100 if buy_price else 0

    # 1. Fixed Take Profit Hit? → sell immediately, lock in guaranteed profit
    if current_price >= tp_price:
        print(f"  🎯 [TAKE PROFIT] {symbol} hit target ${tp_price:.4f}! Selling at ${current_price:.4f}.")
        if execute_sell(exchange, symbol, amount, "TAKE PROFIT"):
            return "CLOSED_TAKE_PROFIT"
        return "OPEN"

    # 2. Hard Stop Loss Hit? (flash crash protection)
    if current_price <= hard_sl:
        print(f"  🔴 [HARD STOP TRIGGERED] {symbol} dropped to ${current_price:.4f}! Protecting capital.")
        if execute_sell(exchange, symbol, amount, "STOP LOSS"):
            return "CLOSED_STOP_LOSS"
        return "OPEN"

    # 3. Trailing Stop Hit? (price pulled back from peak before reaching TP)
    # Only fire if trade is at least 1% in profit — ensures fees (~0.2%) are covered
    # and we're locking in a real gain, not a dust win that fees will erase.
    if current_price <= effective_stop and highest > buy_price:
        if pnl >= 1.0:
            print(f"  🟢 [TRAILING STOP] {symbol} peaked at ${highest:.4f}, pulled back to ${current_price:.4f}. P&L: {pnl:+.2f}%. Locking in profit.")
            if execute_sell(exchange, symbol, amount, "TRAILING STOP"):
                return "CLOSED_TAKE_PROFIT"
        else:
            print(f"  ⏸️  [TRAILING STOP HELD] {symbol} trail triggered but only {pnl:+.2f}% — waiting for 1% min before exiting.")
        return "OPEN"

    # 4. Mid-Trade Score Re-Evaluation
    #    Signals have reversed since entry. If the trade is in profit, exit now
    #    to protect gains rather than waiting for a TP the market no longer supports.
    #    If the trade is flat or at a loss, leave the hard SL to handle it — forcing
    #    an early loss exit here would only make things worse.
    if current_score is not None and current_score <= MIN_SCORE_TO_HOLD:
        if pnl > 0:
            print(
                f"  ⚠️  [SCORE EXIT] {symbol} confluence dropped to {current_score}/7 "
                f"(threshold ≤{MIN_SCORE_TO_HOLD}). "
                f"Trade is +{pnl:.2f}% in profit — exiting early to lock gains."
            )
            if execute_sell(exchange, symbol, amount, "SCORE EXIT"):
                return "CLOSED_SCORE_EXIT"
            return "OPEN"
        elif pnl <= 0:
            print(
                f"  ⚠️  [SCORE EXIT] {symbol} confluence dropped to {current_score}/7 "
                f"but trade is {pnl:.2f}% — holding position; SL will protect capital."
            )

    # Still running
    print(f"  ⏳ [IN TRADE] {symbol}: P&L {pnl:+.2f}% | Score: {current_score}/7 | Price: ${current_price:.4f} | TP: ${tp_price:.4f} | Trail stop: ${effective_stop:.4f}")
    return "OPEN"


def place_exchange_stop(exchange, symbol, amount, sl_price):
    """
    Places a hard stop-loss sell order directly on the exchange.
    This protects the position even if the bot crashes or goes offline.
    Falls back silently in simulation mode or if the exchange doesn't support it.
    """
    if SIMULATION_MODE or not exchange:
        print(f"  [SIMULATION] Stop-loss order would be placed at ${sl_price:.4f}")
        return

    try:
        # Round amount to exchange step-size precision before placing the stop order
        # Without this, Binance rejects the order silently, leaving the position unprotected
        stop_amount = float(exchange.amount_to_precision(symbol, amount))
        market = exchange.market(symbol)
        min_amount = float((market.get('limits') or {}).get('amount', {}).get('min') or 0)
        if stop_amount < min_amount:
            print(f"  ⚠️  [EXCHANGE STOP] Amount {stop_amount} below exchange min {min_amount} — skipping exchange stop (bot will manage in-loop).")
            return

        # Try stop_market first (Futures), fall back to stop_loss_limit (Spot)
        try:
            exchange.create_order(symbol, 'stop_market', 'sell', stop_amount, None, {'stopPrice': sl_price})
            print(f"  🛡️  [EXCHANGE STOP] Hard stop-market placed at ${sl_price:.4f}")
        except Exception:
            limit_price = round(sl_price * 0.995, 8)  # Slightly below stop to ensure fill
            exchange.create_order(symbol, 'stop_loss_limit', 'sell', stop_amount, limit_price, {'stopPrice': sl_price})
            print(f"  🛡️  [EXCHANGE STOP] Hard stop-limit placed at ${sl_price:.4f} (limit: ${limit_price:.4f})")
    except Exception as e:
        print(f"  ⚠️  [EXCHANGE STOP] Could not place stop order — monitor manually! Error: {e}")
        log_trade_history(f"WARNING: Failed to place exchange stop for {symbol} at ${sl_price:.4f}. Manual monitoring required. Error: {e}")


def ensure_spot_balance(exchange, amount_usd: float) -> bool:
    """
    Checks if Spot wallet has enough USDT to trade.
    If not, redeems exactly what is needed from Binance Flexible Earn.
    Returns True if balance is ready, False if redemption failed.
    """
    try:
        balance = exchange.fetch_balance()
        spot_free = float(balance['USDT']['free'])

        if spot_free >= amount_usd:
            print(f"  💰 [BALANCE] Spot USDT: ${spot_free:.2f} — sufficient. No redemption needed.")
            return True

        # Not enough in Spot — try to redeem from Flexible Earn
        shortfall = round(amount_usd - spot_free + 0.5, 2)  # small buffer
        print(f"  💰 [BALANCE] Spot USDT: ${spot_free:.2f} — need ${amount_usd:.2f}. Redeeming ${shortfall:.2f} from Earn...")

        try:
            # Fetch the actual USDT Flexible Earn product ID — don't hardcode it
            positions = exchange.sapi_get_simple_earn_flexible_position({'asset': 'USDT'})
            rows = positions.get('rows', [])
            if not rows:
                print(f"  ⚠️  [BALANCE] No USDT Flexible Earn position found. Fund Spot manually.")
                return spot_free >= (amount_usd * 0.5)
            product_id = rows[0]['productId']
            earn_balance = float(rows[0].get('totalAmount', 0))
            print(f"  💰 [BALANCE] Found Earn product {product_id} with ${earn_balance:.2f} USDT.")

            if earn_balance < shortfall:
                print(f"  ⚠️  [BALANCE] Earn only has ${earn_balance:.2f} — redeeming all available.")
                shortfall = round(earn_balance, 2)

            # Binance Simple Earn Flexible redemption
            exchange.sapi_post_simple_earn_flexible_redeem({
                'productId': product_id,
                'amount':    str(shortfall),
                'type':      'FAST',      # FAST = instant redemption
            })
            print(f"  ✅ [BALANCE] Redeemed ${shortfall:.2f} from Earn. Waiting for Spot balance to update...")
            import time as _time
            _time.sleep(3)  # brief wait for Binance to settle the redemption
            return True
        except Exception as earn_err:
            print(f"  ⚠️  [BALANCE] Earn redemption failed: {earn_err}. Checking if Spot balance is still usable...")
            # Even if redemption fails, try the trade anyway — maybe balance updated
            return spot_free >= (amount_usd * 0.5)  # allow if at least half available

    except Exception as e:
        print(f"  ⚠️  [BALANCE] Balance check failed: {e}. Proceeding with trade attempt.")
        return True  # don't block trade on balance check failure


def execute_market_buy(exchange, symbol, action, current_price, sl_price, tp_price):
    """Enters the market when all conditions are met."""
    amount = TRADE_AMOUNT_USD / current_price

    if SIMULATION_MODE:
        print(f"  [SIMULATION] ✅ BOUGHT {amount:.4f} {symbol} @ ${current_price:.2f}")
        return amount

    # Ensure Spot wallet has enough USDT — redeem from Earn if needed
    if not ensure_spot_balance(exchange, TRADE_AMOUNT_USD):
        print(f"  ❌ [BALANCE] Could not secure ${TRADE_AMOUNT_USD} in Spot. Skipping trade.")
        return None

    try:
        # Validate buy amount meets exchange minimums BEFORE submitting
        exchange.load_markets()
        market = exchange.market(symbol)
        buy_amount = float(exchange.amount_to_precision(symbol, amount))
        min_amount = float((market.get('limits') or {}).get('amount', {}).get('min') or 0)
        min_cost   = float((market.get('limits') or {}).get('cost',   {}).get('min') or 0)
        cost       = buy_amount * current_price

        if buy_amount < min_amount:
            print(f"  ❌ [BUY SKIPPED] {symbol}: calculated amount {buy_amount} < exchange min {min_amount}. "
                  f"Increase TRADE_AMOUNT_USD or skip this coin.")
            return None
        if min_cost and cost < min_cost:
            print(f"  ❌ [BUY SKIPPED] {symbol}: order cost ${cost:.2f} < exchange min cost ${min_cost:.2f}.")
            return None

        print(f"  ⚡ Executing LIVE Market BUY for {symbol}...")
        order = exchange.create_market_order(symbol, 'buy', buy_amount)
        actual_amount = order.get('filled', buy_amount)
        print(f"  ✅ SUCCESS! Buy order complete.")
        return actual_amount
    except Exception as e:
        print(f"  ❌ FAILED to execute buy: {e}")
        return None

# ─────────────────────────────────────────────────────────────────
#  6. THE 24/7 CONTINUOUS LOOP (DAEMON)
# ─────────────────────────────────────────────────────────────────
def run_continuous_daemon():
    global POLL_INTERVAL_SEC, TIMEFRAME, TRADE_AMOUNT_USD
    print("\n" + "═" * 60)
    print("  🚀 STARTING 24/7 CONTINUOUS TRADING DAEMON")
    print("  Monitoring real-time prices & checking Indicators.")
    print(f"  Interval: Every {int(POLL_INTERVAL_SEC/60)} minutes.")
    print("═" * 60)

    # Tracks which coins are currently in BUY_WATCH state.
    # Prevents spamming the same alert every 5 minutes.
    # A coin is removed when it drops below 3/7 so it can re-alert if it recovers.
    buy_watch_active = set()
    last_open_trades_alert = 0  # tracks when we last sent the hourly open trades summary

    # Per-coin re-entry cooldown after a stop loss.
    # Maps symbol → unix timestamp of the stop-out. Bot won't re-enter until
    # the cooldown expires (3 candle-lengths), preventing revenge trading.
    stop_loss_cooldown: dict = {}
    COOLDOWN_CANDLES = 3  # wait 3 candles before re-entering a stopped-out coin

    # Initialise settings.json with 1h default on first run or if missing
    # User can still override anytime via the dashboard UI
    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'w') as f:
            json.dump({"timeframe": "1h", "trade_amount": TRADE_AMOUNT_USD}, f, indent=2)
        print("  ⚙️  [INIT] settings.json created — default timeframe: 1h, trade amount: $12")
    else:
        try:
            with open(SETTINGS_FILE, 'r') as f:
                _s = json.load(f)
            # If still on old 5m default, upgrade to 1h automatically
            if _s.get("timeframe") == "5m":
                _s["timeframe"] = "1h"
                with open(SETTINGS_FILE, 'w') as f:
                    json.dump(_s, f, indent=2)
                print("  ⚙️  [INIT] Upgraded default timeframe from 5m → 1h")
        except Exception:
            pass

    exchange = get_exchange()
    if not exchange and not SIMULATION_MODE:
        print("CRITICAL: Cannot start without Exchange API keys in live mode.")
        return

    while True:
        # Load Dynamic Settings from Dashboard
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)

                current_tf = settings.get("timeframe", "1h")
                if current_tf != TIMEFRAME:
                    print(f"  ⚙️ [SETTING CHANGE] Switching timeframe to {current_tf}")
                    TIMEFRAME = current_tf

                new_amount = float(settings.get("trade_amount", TRADE_AMOUNT_USD))
                if new_amount != TRADE_AMOUNT_USD:
                    print(f"  ⚙️ [SETTING CHANGE] Trade amount updated: ${TRADE_AMOUNT_USD} → ${new_amount}")
                    TRADE_AMOUNT_USD = new_amount

            except Exception as e:
                print(f"  [Warn] Failed to load {SETTINGS_FILE}: {e}")

        state = load_state()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        today_str = datetime.now().strftime('%Y-%m-%d')

        # Reset daily loss tracker if a new day has started
        stats = load_stats()
        if stats.get("today_date") != today_str:
            stats["today_loss_usd"] = 0.0
            stats["today_date"] = today_str
            save_stats(stats)
            print(f"  📅 New trading day — daily loss counter reset.")

        # Circuit breaker check
        daily_loss = stats.get("today_loss_usd", 0.0)
        circuit_open = daily_loss >= MAX_DAILY_LOSS_USD
        if circuit_open:
            print(f"  🛑 [CIRCUIT BREAKER] Daily loss limit hit (${daily_loss:.2f} / ${MAX_DAILY_LOSS_USD:.2f}). No new trades today.")

        print(f"\n[{now_str}] 🔍 Scanning markets ({TIMEFRAME})...")

        # Refresh coin universe every cycle (catches new high-cap entrants)
        active_coins = fetch_dynamic_coins()

        cycle_results = []
        for symbol, coin_name in active_coins.items():

            
            current_price = get_current_price(exchange, symbol)
            if not current_price: continue

            # --- A. Check if we are already in a trade ---
            trade_active = False
            if symbol in state and state[symbol]['status'] == 'OPEN':
                trade_active = True
                # Fetch latest score BEFORE managing the trade so the score exit
                # can act on it within the same cycle.
                # We do a lightweight indicator build here; the full df build
                # follows below for the dashboard output.
                _df_score = fetch_ohlcv(exchange, symbol, timeframe=TIMEFRAME, limit=250)
                _current_score = None
                if not _df_score.empty and len(_df_score) >= 200:
                    try:
                        _df_score = build_all_indicators(_df_score)
                        _conf_now = score_confluence(_df_score)
                        _current_score = _conf_now["score"]
                        print(f"  📊 [MID-TRADE SCORE] {symbol}: {_current_score}/7 (entry threshold was 4/7)")
                    except Exception as _se:
                        print(f"  ⚠️  [MID-TRADE SCORE] Could not score {symbol}: {_se}")

                new_status = manage_open_trade(exchange, symbol, state[symbol], current_price, _current_score)
                # Persist updated highest_price so trailing stop survives bot restarts
                save_state(state)

                if new_status != "OPEN":
                    # Trade closed. Calculate PNL using the actual exit price.
                    # Use current_price as best available proxy (manage_open_trade
                    # only fires the sell when price crosses the level, so slippage is minimal).
                    buy_price  = state[symbol]['buy_price']
                    amount     = state[symbol].get('amount', TRADE_AMOUNT_USD / buy_price if buy_price else 0)
                    exit_price = current_price   # actual market price that triggered the close

                    trade_pnl_usd = (exit_price - buy_price) * amount
                    # Binance charges 0.1% on buy and 0.1% on sell = 0.2% round trip
                    trade_fees_usd = (buy_price * amount * 0.001) + (exit_price * amount * 0.001)
                    net_trade_pnl_usd = trade_pnl_usd - trade_fees_usd
                    is_win = net_trade_pnl_usd > 0
                    result_str = "🟢 WON" if is_win else "🔴 LOST"

                    stats = load_stats()
                    stats["total_trades"] += 1
                    stats["total_fees_usd"] = stats.get("total_fees_usd", 0.0) + trade_fees_usd
                    stats["net_pnl_usd"]    = stats.get("net_pnl_usd",    0.0) + net_trade_pnl_usd

                    if is_win:
                        stats["wins"] += 1
                        stats["cumulative_gains_usd"] += trade_pnl_usd
                    else:
                        stats["losses"] += 1
                        stats["cumulative_losses_usd"] += abs(trade_pnl_usd)
                        stats["today_loss_usd"] = stats.get("today_loss_usd", 0.0) + abs(trade_pnl_usd)

                        # Record stop-loss cooldown — block re-entry for 3 candles
                        if "STOP_LOSS" in new_status:
                            stop_loss_cooldown[symbol] = time.time()
                            candle_secs = TIMEFRAME_TO_SECONDS.get(TIMEFRAME, 3600)
                            cooldown_mins = (COOLDOWN_CANDLES * candle_secs) // 60
                            print(f"  🕐 [COOLDOWN] {symbol} stopped out — blocked from re-entry for {cooldown_mins} min.")

                    stats["total_pnl_usd"] += trade_pnl_usd
                    save_stats(stats)

                    if symbol in state:
                        del state[symbol]
                    save_state(state)

                    # Build a human-readable exit reason for Discord/history
                    exit_reason_map = {
                        "CLOSED_TAKE_PROFIT": "🎯 TAKE PROFIT",
                        "CLOSED_STOP_LOSS":   "🔴 STOP LOSS",
                        "CLOSED_SCORE_EXIT":  "⚠️  SCORE EXIT (signals reversed)",
                    }
                    exit_label = exit_reason_map.get(new_status, new_status)

                    send_discord_alert(symbol, coin_name, f"EXIT: {exit_label} | {result_str} | Gross: ${trade_pnl_usd:.2f} | Fees: ${trade_fees_usd:.3f} | Net: ${net_trade_pnl_usd:.2f}", exit_price)
                    log_trade_history(f"{result_str} ({exit_label}): {symbol} @ ${exit_price:.6f}. (Bought at ${buy_price:.6f}) - Gross: ${trade_pnl_usd:.2f} | Fees: ${trade_fees_usd:.3f} | Net: ${net_trade_pnl_usd:.2f}")

            # --- B. Fetch Chart Data & Analyze ---
            # Reuse the already-fetched + indicator-built df if we scored mid-trade,
            # otherwise fetch fresh. Avoids a double Binance API call per open trade.
            if trade_active and '_df_score' in dir() and not _df_score.empty and len(_df_score) >= 200 and 'ema9' in _df_score.columns:
                df = _df_score
            else:
                df = fetch_ohlcv(exchange, symbol, timeframe=TIMEFRAME, limit=250)
                if df.empty or len(df) < 200:
                    print(f"  ⚠️ Not enough data for {symbol}, skipping.")
                    continue
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
                    "open":      round(float(r["open"]),      4),
                    "high":      round(float(r["high"]),      4),
                    "low":       round(float(r["low"]),       4),
                    "close":     round(float(r["close"]),     4),
                    "volume":    round(float(r["vol_proxy"]), 2),
                    "ema9":      round(float(r["ema9"]),      4),
                    "ema21":     round(float(r["ema21"]),     4),
                    "ema50":     round(float(r["ema50"]),     4),
                    "ema200":    round(float(r["ema200"]),    4),
                    "bb_upper":  round(float(r["bb_upper"]),  4),
                    "bb_mid":    round(float(r["bb_mid"]),    4),
                    "bb_lower":  round(float(r["bb_lower"]),  4),
                    "rsi":       round(float(r["rsi"]),       2),
                    "macd":      round(float(r["macd"]),      6),
                    "macd_sig":  round(float(r["macd_sig"]),  6),
                    "macd_hist": round(float(r["macd_hist"]), 6),
                    "adx":       round(float(r["adx"]),       2),
                    "plus_di":   round(float(r["plus_di"]),   2),
                    "minus_di":  round(float(r["minus_di"]),  2),
                    "obv":       round(float(r["obv"]),       2),
                    "obv_ema":   round(float(r["obv_ema"]),   2),
                }
                for _, r in df.tail(100).iterrows()
            ]

            cycle_results.append({
                "coin":          coin_name.lower(),
                "ticker":        symbol.split('/')[0],  # e.g. "BTC" not "BITCOIN"
                "symbol":        symbol,   # e.g. ETH/USDT — used by dashboard to match state.json
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

            if verdict == "STRONG_BUY" and circuit_open:
                print(f"  ⛔ [CIRCUIT BREAKER] Skipping {symbol} STRONG_BUY — daily loss limit active.")
                continue

            open_trade_count = len([x for x in state.values() if x.get("status") == "OPEN"])
            if verdict == "STRONG_BUY" and open_trade_count >= MAX_OPEN_TRADES:
                print(f"  ⛔ [MAX TRADES] Already have {open_trade_count} open trades. Skipping {symbol}.")
                continue

            if verdict == "STRONG_BUY":
                # Re-entry cooldown check — skip if this coin stopped out recently
                if symbol in stop_loss_cooldown:
                    candle_secs    = TIMEFRAME_TO_SECONDS.get(TIMEFRAME, 3600)
                    cooldown_secs  = COOLDOWN_CANDLES * candle_secs
                    elapsed        = time.time() - stop_loss_cooldown[symbol]
                    if elapsed < cooldown_secs:
                        remaining_min = int((cooldown_secs - elapsed) / 60)
                        print(f"  🕐 [COOLDOWN] {symbol} skipped — {remaining_min} min cooldown remaining after stop loss.")
                        continue
                    else:
                        del stop_loss_cooldown[symbol]  # Cooldown expired, allow entry

                print(f"\n  🎯 [SIGNAL TRIGGERED] {symbol} hit STRONG BUY requirements!")
                buy_watch_active.discard(symbol)  # Graduated from watch to trade

                # --- MULTI-TIMEFRAME CONFIRMATION (4h must not be bearish) ---
                htf = check_higher_timeframe(exchange, symbol)
                if not htf["allowed"]:
                    print(f"  🚫 [MTF BLOCK] HTF trend is bearish (score {htf['score']}/7). Skipping {TIMEFRAME} signal.")
                    continue

                # --- AI ADVISORY (raises bar in bearish macro, never blocks outright) ---
                ticker = symbol.split('/')[0]
                print(f"  🧠 [AI ADVISORY] Checking macro sentiment for {coin_name}...")
                ai_sentiment = get_ai_sentiment(coin_name, ticker, exchange=exchange, symbol=symbol)
                ai_verdict = ai_sentiment.get('verdict', 'NEUTRAL')
                raw_score = conf["score"]

                # BEARISH macro → need score >= 5 to enter (stronger confirmation required)
                # BULLISH/NEUTRAL macro → normal 4/7 threshold applies
                required_score = 5 if ai_verdict == "BEARISH" else 4

                if raw_score < required_score:
                    print(f"  ⚠️  [AI ADVISORY] Macro is {ai_verdict} — need {required_score}/7, got {raw_score}/7. Skipping.")
                    print(f"     Reason: {ai_sentiment.get('reason')}")
                    continue
                else:
                    print(f"  ✅ [AI ADVISORY] Macro: {ai_verdict} | Score {raw_score}/7 >= {required_score} required. Proceeding.")

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
                        "trail_atr": levels["atr"],        # ATR at entry — drives the trailing stop distance
                        "highest_price": current_price,    # Will ratchet up as price climbs
                        "timestamp": now_str
                    }
                    save_state(state)

                    # Place hard stop on exchange — protects capital if bot goes offline
                    place_exchange_stop(exchange, symbol, amount_filled, sl_price)
                    
                    # Add to cumulative invested amount
                    stats = load_stats()
                    stats["total_invested_usd"] += (current_price * amount_filled)
                    save_stats(stats)
                    
                    send_discord_alert(
                        symbol, coin_name, "🟢 ENTER LONG", current_price, 
                        reason=f"TP: ${tp_price:.2f} | SL: ${sl_price:.2f} | Score: {conf['score']}/7"
                    )
                    log_trade_history(f"🟡 OPENED LONG: {symbol} @ ${current_price:.6f} (TP: ${tp_price:.6f} | SL: ${sl_price:.6f})")

            
            elif verdict == "BUY_WATCH":
                # Score is 3/7 — setup is developing, not yet actionable
                if symbol not in buy_watch_active:
                    buy_watch_active.add(symbol)
                    print(f"  👀 [BUY_WATCH] {symbol} is developing (3/7 score). Watching closely...")
                    send_discord_alert(
                        symbol, coin_name,
                        f"👀 BUY_WATCH — Score 3/7. Setup developing, not yet a trade.",
                        current_price,
                        reason=f"Needs 1 more bullish indicator to trigger. Current price: ${current_price:.4f}"
                    )
                else:
                    print(f"  👀 [BUY_WATCH] {symbol} still at 3/7. Monitoring...")

            else:
                # Score < 3 — clear from watchlist so it can re-alert if it returns
                if symbol in buy_watch_active:
                    buy_watch_active.discard(symbol)
                    print(f"  [{symbol}] Dropped below BUY_WATCH. Removed from watchlist.")
                else:
                    print(f"  [{symbol}] Status: Waiting. Score: {conf['score']}/7 (Needs 4/7). Current: ${current_price:.2f}")

        # --- D. Save to Dashboard & Sleep until next cycle ---
        stats = load_stats()
        
        open_trades_list = [x for x in state.values() if x.get("status") == "OPEN"]
        stats["open_trades"] = len(open_trades_list)
        
        # We no longer overwrite total_invested_usd here, as it's tracked cumulatively on entry.


        output = {
            "strategy": "Continuous 24/7 Multi-Confluence",
            "min_signals": 4,
            "results":  cycle_results,
            "aggregate_stats": stats,
            "generated": now_str,
        }
        with open(RESULTS_FILE, "w") as f:
            json.dump(output, f, indent=2, default=str)

        # Fetch live USDT balance from Binance
        try:
            balance_data = exchange.fetch_balance()
            usdt_free  = round(balance_data['USDT']['free'],  2)
            usdt_total = round(balance_data['USDT']['total'], 2)
        except Exception:
            usdt_free  = None
            usdt_total = None

        # Single source of truth — combines everything the dashboard needs into one file
        bot_state = {
            "generated":   now_str,
            "signals":     cycle_results,
            "open_trades": state,
            "stats":       stats,
            "balance": {
                "usdt_free":  usdt_free,
                "usdt_total": usdt_total,
            },
        }
        with open(BOT_STATE_FILE, "w") as f:
            json.dump(bot_state, f, indent=2, default=str)

        # Send hourly open trades summary to Discord
        import time as _time
        open_trades_only = {k: v for k, v in state.items() if v.get("status") == "OPEN"}
        if open_trades_only:
            now_ts = _time.time()
            if now_ts - last_open_trades_alert >= 3600:  # once per hour
                # Attach latest price to each trade for P&L display
                for sym, trade in open_trades_only.items():
                    for r in cycle_results:
                        if r.get("symbol") == sym:
                            trade["current_price"] = r.get("current_price", trade.get("buy_price", 0))
                send_open_trades_summary(open_trades_only)
                last_open_trades_alert = now_ts

        print(f"\n[DASHBOARD UI UPDATED] The NextJS web interface charts have been seeded!")
        print(f"💤 Cycle complete. Sleeping for {int(POLL_INTERVAL_SEC/60)} minutes...")
        time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    run_continuous_daemon()
