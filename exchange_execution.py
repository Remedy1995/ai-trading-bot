import os
import time

# ─────────────────────────────────────────────
#  EXCHANGE CONFIGURATION
# ─────────────────────────────────────────────
# To trade real money, you need to install ccxt:
# pip3 install ccxt
try:
    import ccxt
except ImportError:
    ccxt = None

API_KEY = os.environ.get("EXCHANGE_API_KEY", "")
API_SECRET = os.environ.get("EXCHANGE_API_SECRET", "")
EXCHANGE_NAME = os.environ.get("EXCHANGE_NAME", "binance") # e.g., 'binance', 'coinbase', 'kraken'

# Safety switch: Set to False ONLY when you are ready to trade real money.
SIMULATION_MODE = True  

def get_client():
    """Initializes the exchange client using CCXT."""
    if SIMULATION_MODE:
        return None
        
    if not API_KEY or not API_SECRET:
        print("  ⚠️  WARNING: Exchange API keys not found. Forcing SIMULATION MODE.")
        return None
        
    if not ccxt:
        print("  ⚠️  WARNING: 'ccxt' library not installed. Run 'pip install ccxt'. Forcing SIMULATION MODE.")
        return None
    
    try:
        # Dynamically load the exchange class (e.g., ccxt.binance, ccxt.coinbase)
        exchange_class = getattr(ccxt, EXCHANGE_NAME)
        exchange = exchange_class({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
        })
        return exchange
    except Exception as e:
        print(f"  ❌ Failed to initialize {EXCHANGE_NAME} client: {e}")
        return None

def execute_trade(coin_id: str, ticker: str, action: str, price: float = None):
    """
    Executes a real market order on the exchange.
    action: "STRONG BUY" or "STRONG SELL"
    """
    exchange = get_client()
    
    # Standardize symbol notation (e.g., "BTC/USDT")
    symbol = f"{ticker}/USDT"
    
    # ── RISK MANAGEMENT CONFIG ──
    # How much USD to spend per trade. 
    TRADE_AMOUNT_USD = 100.0  
    
    if action == "STRONG BUY":
        side = "buy"
        if price:
            quantity = TRADE_AMOUNT_USD / price
        else:
            print("  ❌ Cannot execute BUY: Price unknown.")
            return False
            
        print(f"\n  ⚡ INITIATING TRADE ⚡")
        print(f"  Action: BUY Market Order for {quantity:.5f} {symbol} (~${TRADE_AMOUNT_USD})")
        
    elif action == "STRONG SELL":
        side = "sell"
        quantity = 0  # We will calculate this based on balance
        print(f"\n  ⚡ INITIATING TRADE ⚡")
        print(f"  Action: SELL Market Order to liquidate {symbol} position.")
    else:
        return False

    # ── SIMULATION MODE (Safety Net) ──
    if not exchange:
        print(f"  [SIMULATION] The bot *would* have executed a {side.upper()} order for {symbol}.")
        print(f"  To enable real trading:\n  1. export EXCHANGE_API_KEY='...' \n  2. export EXCHANGE_API_SECRET='...'\n  3. Set SIMULATION_MODE = False in exchange_execution.py")
        return True

    # ── REAL EXECUTION (LIVE MONEY) ──
    try:
        # If selling, we need to know exactly how much of the coin we actually own
        if side == "sell":
            balance = exchange.fetch_balance()
            if ticker in balance['free']:
                quantity = balance['free'][ticker]
            else:
                quantity = 0
                
            if quantity <= 0:
                print(f"  ❌ Cannot SELL: You don't have any {ticker} in your account balance.")
                return False
                
            print(f"  Selling entire {ticker} balance: {quantity}")

        # Execute the Market Order
        order = exchange.create_market_order(symbol, side, quantity)
        
        print(f"  ✅ SUCCESS: {side.upper()} order executed for {symbol}!")
        print(f"  Order ID: {order.get('id')}")
        return True

    except Exception as e:
        print(f"  ❌ FAILED to execute {side.upper()} order on {symbol}: {str(e)}")
        return False

