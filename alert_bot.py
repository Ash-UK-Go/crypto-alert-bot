# alert_bot.py
import requests
import time
import json
import datetime
import pytz
import os

# --- Load Configuration from config.json ---
try:
    with open('config.json') as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    exit(1)

# --- Fetch API Keys from Environment Variables (SECURE WAY) ---
CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not CMC_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("Missing environment variables. Please set CMC_API_KEY and TELEGRAM_BOT_TOKEN.")
    exit(1)

# --- Extract settings ---
TELEGRAM_CHAT_ID = config.get('telegram_chat_id')
TRACKED_TOKENS_CONFIG = config.get('tracked_tokens', {})
ENTRY_PRICES = {symbol: data.get('entry_price') for symbol, data in TRACKED_TOKENS_CONFIG.items()}
TOKENS_TO_MONITOR = list(TRACKED_TOKENS_CONFIG.keys())

ALERT_THRESHOLDS = config.get('alert_thresholds', {})
TARGET_PROFIT_PERCENT = ALERT_THRESHOLDS.get('target_profit_percent', 4) / 100
PRICE_SURGE_PERCENT = ALERT_THRESHOLDS.get('price_surge_percent', 5)
PRICE_DROP_PERCENT = ALERT_THRESHOLDS.get('price_drop_percent', 5)

TRADING_HOURS = config.get('trading_hours', {})
START_HOUR = TRADING_HOURS.get('start_hour', 8)
END_HOUR = TRADING_HOURS.get('end_hour', 18)
TRADING_DAYS = [
    0 if d == "Monday" else 1 if d == "Tuesday" else 2 if d == "Wednesday" else
    3 if d == "Thursday" else 4 if d == "Friday" else 5 if d == "Saturday" else 6
    for d in TRADING_HOURS.get('days', [])
]

HEADERS = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': CMC_API_KEY
}
CMC_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'
MONITOR_TIMEZONE = pytz.timezone('Europe/London')

# Simulated Wallet
mock_wallet = {
    "USDT": 30,
    "POL": 120,
    "ETH": 0.05,
    "WBTC": 0.0003,
    "LINK": 5,
    "AAVE": 0.12,
    "DAI": 10
}

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Error sending alert: {e}")

def fetch_token_data(symbol):
    cmc_symbol = TRACKED_TOKENS_CONFIG.get(symbol, {}).get('cmc_symbol')
    if not cmc_symbol:
        return None
    try:
        res = requests.get(CMC_URL, headers=HEADERS, params={
            'symbol': cmc_symbol,
            'convert': 'GBP'
        }).json()
        return res['data'][cmc_symbol]
    except:
        return None

def check_prices_and_trigger_alerts():
    now = datetime.datetime.now(MONITOR_TIMEZONE)
    if now.weekday() not in TRADING_DAYS or not (START_HOUR <= now.hour < END_HOUR):
        return

    for symbol in TOKENS_TO_MONITOR:
        data = fetch_token_data(symbol)
        if not data:
            continue

        quote = data.get('quote', {}).get('GBP', {})
TEST_MODE = True  # 🔁 Set to False after test run

if TEST_MODE:
    test_prices = {
        "POL": 0.198,
        "USDT": 0.74,
        "ETH": 1920.00,
        "WBTC": 87001.00,
        "LINK": 13.20,
        "DAI": 0.72,
        "AAVE": 96.10
    }
    test_changes_3h = {
        "POL": 6.5, "USDT": 0.2, "ETH": -5.3, "WBTC": 5.5,
        "LINK": 5.7, "DAI": -5.1, "AAVE": 5.0
    }
    test_changes_24h = {
        "POL": 8, "USDT": 0.5, "ETH": 1, "WBTC": 10,
        "LINK": 5, "DAI": -2, "AAVE": 12
    }

    current_price = test_prices.get(symbol, quote.get('price'))
    change_3h = test_changes_3h.get(symbol, 0)
    change_24h = test_changes_24h.get(symbol, 0)
else:
    current_price = quote.get('price')
    change_3h = quote.get('percent_change_3h', 0)
    change_24h = quote.get('percent_change_24h', 0)

        msg_parts = []

        # Price Surge/Drop Alerts
        if change_3h is not None and current_price is not None:
            if change_3h >= PRICE_SURGE_PERCENT:
                msg_parts.append(f"⬆️ *{symbol}* is up {change_3h:.2f}% in 3h! Current: £{current_price:.2f}")
            if change_3h <= -PRICE_DROP_PERCENT:
                msg_parts.append(f"⬇️ *{symbol}* down {abs(change_3h):.2f}% in 3h! Current: £{current_price:.2f}")

        # Target Profit
        if entry_price is not None and current_price is not None:
            if current_price >= entry_price * (1 + TARGET_PROFIT_PERCENT):
                profit = (current_price - entry_price) * holding
                msg_parts.append(f"🎯 Profit Target Hit: +£{profit:.2f}\nToken: {symbol}\nHolding: {holding}\nPrice: £{entry_price} → £{current_price:.2f}\nBase: £{entry_price}\n✅ Consider Booking")

        # BUY Logic
        buy_price = TRACKED_TOKENS_CONFIG[symbol].get('buy_price')
        sell_price = TRACKED_TOKENS_CONFIG[symbol].get('sell_price')
        min_usdt = TRACKED_TOKENS_CONFIG[symbol].get('min_usdt_balance', 0)
        min_holding = TRACKED_TOKENS_CONFIG[symbol].get('min_token_holding', 0)

        if buy_price is not None and current_price is not None and current_price <= buy_price and usdt_balance >= min_usdt:
            qty = round(min_usdt / current_price, 2)
            msg_parts.append(f"🟢 Buy Alert: {symbol} at £{current_price:.3f}\nTarget: Buy ~{qty} {symbol} using £{min_usdt}\nNext Sell Target: ≥ £{sell_price}\n➡️ Suggested Swap: {min_usdt} USDT → {symbol}")

        # SELL Logic
        if sell_price is not None and current_price is not None and current_price >= sell_price and holding >= min_holding:
            value = holding * current_price
            profit_pct = ((current_price - buy_price) / buy_price) * 100 if buy_price else 0
            msg_parts.append(f"🔴 Sell Alert: {symbol} at £{current_price:.3f}\nHolding: {holding} ≈ £{value:.2f}\nProfit Zone: 🎯 ~{profit_pct:.1f}%\n➡️ Suggested Swap: {holding} {symbol} → USDT")

        if msg_parts:
            message = f"🚨 *Crypto Alert* 🚨\n\n" + '\n\n'.join(msg_parts)
            send_telegram_alert(message)

# --- Main Loop ---
if __name__ == '__main__':
    while True:
        try:
            check_prices_and_trigger_alerts()
            time.sleep(60)
        except Exception as e:
            print(f"Unhandled error: {e}")
            time.sleep(300)
