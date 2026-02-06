# 🤖 SMA Monitor Bot

A real-time SMA (Simple Moving Average) crossover monitoring bot for Binance Future markets with Telegram interactive commands.

## 🚀 Features
- **Real-time Monitoring**: Tracks SMA periods (7, 25, 99) for BTC, ETH, XRP, and SOL.
- **Interactive Commands**: Control everything via Telegram.
- **Singleton Protection**: Prevents multiple instances from running simultaneously using file locking.
- **Dynamic Intervals**: Adjust report frequency on the fly.
- **Standardized Commands**: Reliable English commands with a user-friendly Korean interface.

## 🛠 Setup

### 1. Prerequisites
- Python 3.10+
- A Telegram Bot (created via @BotFather)

### 2. Installation
```bash
# Install dependencies
pip install ccxt pandas requests python-dotenv
```

### 3. Configuration
Copy `.env.template` to `.env` and fill in your credentials:
```bash
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

### 4. Running the Bot
```bash
python sma_monitor.py
```

## 🤖 Command Guide

### 📊 Report Settings
- `report on/off`: Enable/disable reports
- `interval [sec]`: Set report interval (e.g., `interval 60`)

### 🎯 Target Alerts
- `alert [number]`: Set specific alignment alert (1-6)
- `alert off`: Disable target alerts

### ⚙️ Other Commands
- `status`: Check current settings
- `now`: Send immediate report
- `help`: Show this guide

### 🕒 Timeframes
Type any supported timeframe to change: `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`.

## 📄 License
MIT License
