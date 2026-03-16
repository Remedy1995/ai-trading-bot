import requests
import json
import os
from datetime import datetime

# ─────────────────────────────────────────────
#  NOTIFICATION CONFIGURATION
# ─────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

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
