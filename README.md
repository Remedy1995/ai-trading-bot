# 🤖 AI Trading Bot

A robust, multi-layer cryptocurrency trading bot that uses a combination of **Technical Analysis (Moving Averages & RSI)** and **AI Sentiment Analysis (Perplexity)** to generate trading signals for Bitcoin, Ethereum, and Solana.

This system includes a full backtesting engine and a beautiful, real-time sleek dashboard to monitor the signals!

---

## 📁 Project Overview

The system is broken down into three main Python files, and a Next.js web dashboard:

1. `trading_bot.py`: The core live signal engine based on the 50-day vs 200-day Moving Average (Golden Cross/Death Cross).
2. `bot_with_sentiment.py`: An advanced **v2 bot** that requires BOTH a technical chart signal AND a confirming AI news sentiment signal before trading.
3. `backtest.py`: The historical simulator. It runs the strategy against the last 2 years of market data to output win rates, maximum drawdowns, and Sharpe ratios.
4. `dashboard/`: A Next.js (React) front-end web app to visualize all of the bot's outputs.

---

## 🚀 Quick Start Guide: How to Run the Bot

### Prerequisites
Make sure you have Python 3 installed, as well as the required dependencies:
```bash
pip3 install requests pandas numpy
```

### 1. Run the Live Strategy (Basic)
This script fetches real-time prices and moving averages via the free CoinGecko API. 
```bash
python3 trading_bot.py
```
*Tip: It automatically saves the signals to `bot_results.json` so the dashboard can read them.*

### 2. Run the Backtesting Simulator
Want to see how the bot would have performed over the last two years? Run the backtester. It simulates starting with $10,000 and applies a strict stop-loss/take-profit risk management profile.
```bash
python3 backtest.py
```
*Tip: Watch it calculate the P&L and grade the strategy (e.g. B+, C+). Results are saved to `backtest_results.json`.*

### 3. Run the Dual-Confirmation AI Bot (Advanced)
This version queries **Perplexity AI** to get the latest news on a coin and pairs the AI's "vibe" verdict with the technical chart crossover.

**Important:** You must have a free Perplexity API key to use the AI component.

First, export your API key to your terminal:
```bash
export PERPLEXITY_API_KEY="your-api-key-here"
```

Then run the dual-layer bot:
```bash
python3 bot_with_sentiment.py
```
*If you run this without an API key, the AI Sentiment column will simply say "UNAVAILABLE" and default to HOLD.*

---

## 📈 Viewing the Live Web Dashboard

To see the bot's decisions inside incredibly clean, dark-mode technical charts and tables:

1. Open a new terminal tab.
2. Navigate into the dashboard folder:
```bash
cd dashboard
```
3. Install the web dependencies (you only have to do this once):
```bash
npm install
```
4. Start the dashboard server:
```bash
npm run dev
```
5. Open your browser and go to: [http://localhost:3000](http://localhost:3000)

> **Note:** Whenever you run `python3 trading_bot.py` or `python3 backtest.py`, the JSON files update under the hood. All you have to do is refresh the browser dashboard to see the new data!

---

## ⚙️ How the Bot Runs Under the Hood

The bot is designed as a **stateless, cron-friendly script**:
1. **Fetch**: It pulls the latest daily/hourly candlesticks for the specified coins via the CoinGecko API.
2. **Technical Analysis**: It computes the 50-day MA, 200-day MA, and RSI(14) locally using `pandas`.
3. **Sentiment Analysis**: It hits the Perplexity AI API to parse recent news and get a "vibe check".
4. **Decision Fusion**: It runs identical logic on both layers. If the chart says "Buy" and AI says "Buy", the final output is `STRONG BUY`.
5. **Execution & Alert**: If a valid signal triggers, it pushes an order to the connected exchange (via `ccxt`) and fires a webhook cleanly to Discord.
6. **State Save**: Finally, it overwrites the `.json` report files so the React dashboard accurately displays the latest run status.

---

## 💡 Recommended Next Steps for Production

To take this from a testing script to a fully autonomous system, consider these additions:

1. **Deploy on a Cloud Server (VPS)**
   Host this repository on an AWS EC2 or DigitalOcean Droplet so it doesn't rely on your laptop being awake.

2. **Automate with Cron or GitHub Actions**
   Set up a cron job to automatically run the bot every day (or every 4 hours):
   ```bash
   # Opens cron editor
   crontab -e
   
   # Add this line to run the bot at 8:00 AM every day
   0 8 * * * cd /path/to/ai-trading-bot && /usr/bin/python3 bot_with_sentiment.py
   ```

3. **Turn off SIMULATION_MODE (Proceed with Caution)**
   In `exchange_execution.py`, change `SIMULATION_MODE = True` to `False`. Ensure your exchange API keys are exported in the environment. *Only do this when you are ready to trade real money.*

4. **Expand Supported Assets**
   Currently, the bot traces BTC, ETH, and SOL. Edit the `COINS` dictionary in `bot_with_sentiment.py` to add assets like `XRP`, `ADA`, or custom altcoins.

---

## ⚠️ Disclaimer
**This project is for educational purposes only.** Do not connect this to real exchange APIs without thorough testing. Always use stop-losses and never risk more than 1-2% of your portfolio per trade!
