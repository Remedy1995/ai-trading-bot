import requests
import json
import os
from datetime import datetime

# ─────────────────────────────────────────────
#  NOTIFICATION CONFIGURATION
# ─────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

def send_open_trades_summary(open_trades: dict):
    """
    Sends a Discord summary of all currently open trades.
    Called once per hour so you always know what the bot is holding.
    """
    if not DISCORD_WEBHOOK_URL or not open_trades:
        return False

    fields = []
    for symbol, trade in open_trades.items():
        if trade.get("status") != "OPEN":
            continue
        buy_price     = trade.get("buy_price", 0)
        current_price = trade.get("current_price", buy_price)
        tp            = trade.get("take_profit", 0)
        sl            = trade.get("stop_loss", 0)
        highest       = trade.get("highest_price", buy_price)
        trail_atr     = trade.get("trail_atr", 0)
        trail_stop    = round(max(sl, highest - 2 * trail_atr), 6) if trail_atr else sl
        pnl_pct       = ((current_price - buy_price) / buy_price * 100) if buy_price else 0
        pnl_emoji     = "📈" if pnl_pct >= 0 else "📉"

        fields.append({
            "name": f"{pnl_emoji} {symbol}",
            "value": (
                f"**P&L:** `{pnl_pct:+.2f}%`\n"
                f"**Entry:** `${buy_price:,.4f}`\n"
                f"**TP:** `${tp:,.4f}`\n"
                f"**Trail Stop:** `${trail_stop:,.4f}`"
            ),
            "inline": True
        })

    if not fields:
        return False

    payload = {
        "username": "AI Trading Terminal",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712139.png",
        "embeds": [{
            "title": f"⏳ Open Trades Update — {len(fields)} Active",
            "description": "Hourly summary of all currently open positions.",
            "color": 16776960,  # Yellow
            "fields": fields,
            "footer": {
                "text": f"Updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }]
    }

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        print(f"  📱 Open trades summary sent to Discord.")
        return True
    except Exception as e:
        print(f"  ❌ Failed to send open trades summary: {e}")
        return False


def send_discord_alert(coin_id: str, ticker: str, action: str, price: float, reason: str = ""):
    """
    Sends a rich embed message to a Discord channel via Webhook.
    """
    if not DISCORD_WEBHOOK_URL:
        # print("  ⚠️  Discord Webhook URL not set. Skipping notification.")
        return False

    emoji = "🟢 BUY" if "BUY" in action else "🔴 SELL" if "SELL" in action else "⚪ HOLD"
    color = 5763719 if "BUY" in action else 15548997 if "SELL" in action else 16776960 # Emerald, Rose, Yellow

    payload = {
        "username": "AI Trading Terminal",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712139.png", # Robot icon
        "embeds": [
            {
                "title": f"{emoji} Signal for {coin_id.upper()} ({ticker})",
                "description": f"**Action:** {action}\n**Price:** ${price:,.2f}",
                "color": color,
                "fields": [
                    {
                        "name": "Reasoning",
                        "value": reason if reason else "Technical & AI Sentiment crossed thresholds.",
                        "inline": False
                    }
                ],
                "footer": {
                    "text": f"Executed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }
        ]
    }

    try:
        response = requests.post(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        print(f"  📱 Notification sent to Discord for {ticker}.")
        return True
    except Exception as e:
        print(f"  ❌ Failed to send Discord notification: {e}")
        return False
