# 🚀 Autonomous AI Crypto Trading Bot

A high-performance algorithmic spot trading daemon built on Python, CCXT, and Next.js. The bot autonomously scans 5-minute chart intervals 24/7, searching for strict mathematical "Heavy Buy" structures before executing live market orders and tracking Take-Profits and Stop-Losses effortlessly via a beautifully designed real-time graphical web dashboard.

---

## 🧠 The "Math-to-Hunt, AI-to-Veto" Strategy
The system uses a two-stage filter specifically architected to filter out chaotic market noise and act purely on deep, verified algorithmic signals.

### 1. The Multi-Confluence Mathematical Engine (7 Indicators)
To even be considered for an entry position, a coin must natively process through 7 distinct mathematical indicators. It requires a hard algorithmic score of at least **4 out of 7** strictly bullish alignments:
1. **Exponential Moving Average (EMA) Stack:** Short-term EMAs (9, 21) must perfectly cross above long-term EMAs (50, 200).
2. **Current Price Momentum:** The real-time live price must natively sit above both the EMA 21 and EMA 50 simultaneously.
3. **RSI (Relative Strength Index):** Must be sitting healthily in the "expansion" zone (40–65%) preventing the bot from buying over-bought or heavily crashed assets.
4. **MACD Histogram:** MACD line must boldly cross above its signal line, showing expanding upward MACD momentum.
5. **Bollinger Bands:** Price must sit comfortably in the upper median of the `%B` band width (0.5 – 0.95), riding bullish momentum safely below the absolute top squeeze.
6. **ADX & DI+ Trend Strength:** The ADX must definitively read above 20, with the positive direction index `+DI` overpowering the bearish `-DI` structure.
7. **Volume OBV:** On-Balance Volume must be securely trending upward and breaking out over its 20-day moving average.

### 2. The Groq Llama 3.1 70B AI Veto
Because mathematical indicators are strictly "rear-view looking," they cannot detect catastrophic breaking news occurring in the real world (e.g. CEO arrested, exchange hacked). As soon as the mathematical indicators trigger a `STRONG_BUY` signal, the bot automatically freezes and securely queries the ultra-fast Groq Language Model (`Llama-3.1-70b-versatile`).

The AI acts as your safety veto. It takes the current crypto coin and cross-references its behavior against general web technical/sentiment analysis and answers purely as a professional risk analyst. If the AI detects poor sentiment and returns a `BEARISH` verdict, the trade is instantly cancelled.

---

## ⏳ Trade Exits (The Waiting Game)
Once an entry passes the Math and the AI Veto, it is securely dropped into the "Open Trades" basket. The bot draws two strict physical price lines based upon the dynamically calculated Volatility Average True Range (ATR):
* **Take Profit Ceiling:** Your "Win" payout.
* **Stop Loss Floor:** Your safety net.

The bot will relentlessly hold the active bag until the real-world, global market price physically floats high enough to touch the Ceiling, or drops low enough to trigger the Floor. The time between a Buy trigger and a final exit can span anywhere from 5 minutes to multiple hours depending on global volume.

---

## 🛠️ Installation & Getting Started

### 1. Install Global Requirements
Ensure you are running **Python 3.10+** and **Node 18+**.
```bash
# Install Python dependencies
pip install pandas numpy ccxt requests python-dotenv

# Install NextJS Frontend dependencies
cd dashboard
npm install
```

### 2. Add your AI API Key
Create a `.env` file mechanically hidden in the root of the project to cleanly host your Groq API credentials.
```bash
# .env
GROQ_API_KEY=gsk_your_groq_api_token_here
```

### 3. Spin up the Dashboard
In a secondary terminal window, build the blazing-fast production NextJS UI.
```bash
cd dashboard
npm run build
npm start
```
*Your UI will immediately host live on `http://localhost:3000` with the 🟢 "Bot Status" system.*

### 4. Ignite the Python Daemon
In your main terminal window, simply launch the 24/7 daemon file.
```bash
python3 continuous_bot.py
```
The bot will silently boot, read the `.env` token securely into its isolated engine context, seamlessly scrape the market, execute AI sentiment checks, manage any hanging trades perfectly, and broadcast its JSON history dynamically across your NextJS Dashboard every 5 minutes!
