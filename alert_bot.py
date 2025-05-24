
import requests
import time
import json
import datetime
import pytz
import os

# --- Load Configuration ---
try:
    with open('config.json') as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    exit(1)

CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not CMC_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("Missing env vars. Set CMC_API_KEY and TELEGRAM_BOT_TOKEN.")
    exit(1)

TELEGRAM_CHAT_ID = config.get('telegram_chat_id')
TRACKED_TOKENS_CONFIG = config.get('tracked_tokens', {})
ENTRY_PRICES = {s: d.get('entry_price') for s, d in TRACKED_TOKENS_CONFIG.items()}
TOKENS = list(TRACKED_TOKENS_CONFIG.keys())

ALERT_THRESHOLDS = config.get('alert_thresholds', {})
TARGET_PROFIT = ALERT_THRESHOLDS.get('target_profit_percent', 4) / 100
PRICE_SURGE = ALERT_THRESHOLDS.get('price_surge_percent', 5)
PRICE_DROP = ALERT_THRESHOLDS.get('price_drop_percent', 5)

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
TZ = pytz.timezone('Europe/London')

mock_wallet = {
    "USDT": 30,
    "POL": 120,
    "ETH": 0.05,
    "WBTC": 0.0003,
    "LINK": 5,
    "AAVE": 0.12,
    "DAI": 10
}

def send_telegram_alert(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Error sending alert: {e}")

def fetch_token_data(symbol):
    cmc = TRACKED_TOKENS_CONFIG[symbol].get('cmc_symbol')
    try:
        res = requests.get(CMC_URL, headers=HEADERS, params={ 'symbol': cmc, 'convert': 'GBP' }, timeout=10).json()
        return res['data'][cmc]
    except:
        return None

def check_prices():
    now = datetime.datetime.now(TZ)
    if now.weekday() not in TRADING_DAYS or not (START_HOUR <= now.hour < END_HOUR):
        return

    for token in TOKENS:
        data = fetch_token_data(token)
        if not data:
            continue

        q = data.get('quote', {}).get('GBP', {})
        p = q.get('price')
        c3 = q.get('percent_change_3h', 0)
        c24 = q.get('percent_change_24h', 0)

        entry = ENTRY_PRICES.get(token)
        buy_price = TRACKED_TOKENS_CONFIG[token].get('buy_price')
        sell_price = TRACKED_TOKENS_CONFIG[token].get('sell_price')
        min_usdt = TRACKED_TOKENS_CONFIG[token].get('min_usdt_balance', 0)
        min_holding = TRACKED_TOKENS_CONFIG[token].get('min_token_holding', 0)

        holding = mock_wallet.get(token, 0)
        usdt = mock_wallet.get("USDT", 0)

        msgs = []

        if c3 >= PRICE_SURGE:
            msgs.append(f"⬆️ *{token}* is up {c3:.2f}% in 3h! Current: £{p:.2f}")
        if c3 <= -PRICE_DROP:
            msgs.append(f"⬇️ *{token}* down {abs(c3):.2f}% in 3h! Current: £{p:.2f}")

        if entry and p >= entry * (1 + TARGET_PROFIT):
            gain = (p - entry) * holding
            msgs.append(f"🎯 Profit Target Hit: +£{gain:.2f}\nToken: {token}\nHolding: {holding}\nPrice: £{entry} → £{p:.2f}\nBase: £{entry}\n✅ Consider Booking")

        if buy_price and p <= buy_price and usdt >= min_usdt:
            qty = round(min_usdt / p, 2)
            msgs.append(f"🟢 Buy Alert: {token} at £{p:.3f}\nTarget: Buy ~{qty} {token} using £{min_usdt}\nNext Sell Target: ≥ £{sell_price}\n➡️ Suggested Swap: {min_usdt} USDT → {token}")

        if sell_price and p >= sell_price and holding >= min_holding:
            total = holding * p
            profit_pct = ((p - buy_price) / buy_price * 100) if buy_price else 0
            msgs.append(f"🔴 Sell Alert: {token} at £{p:.3f}\nHolding: {holding} ≈ £{total:.2f}\nProfit Zone: 🎯 ~{profit_pct:.1f}%\n➡️ Suggested Swap: {holding} {token} → USDT")

        if msgs:
            full_msg = f"🚨 *Crypto Alert* 🚨\n\n" + '\n\n'.join(msgs)
            send_telegram_alert(full_msg)
        else:
            print(f"[{now.strftime('%H:%M:%S')}] No alerts for {token}. Price: £{p:.2f}")

if __name__ == '__main__':
    print("✅ Crypto Alert Bot Started")
    while True:
        try:
            check_prices()
            time.sleep(60)
        except Exception as e:
            print(f"Unhandled error: {e}")
            time.sleep(300)
