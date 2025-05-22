import requests
import time
import json
import datetime
import pytz
import os

# Load config
with open('config.json') as f:
    config = json.load(f)

{
  "CMC_API_KEY": "f9732761-8d27-48c0-97c7-b4118ce2df35",
  "TELEGRAM_BOT_TOKEN": "7592488628:AAHeRfSkzy7i5aZlroaQcXxnL-b8ujcHzlY",
  "TELEGRAM_CHAT_ID": "7613643961",
  "ENTRY_PRICES": {
    "POL": 0.182,
    "USDT": 0.738,
    "ETH": 1969.53,
    "WBTC": 82543.21,
    "LINK": 12.28,
    "DAI": 0.74,
    "AAVE": 84.00
  },
  "TARGET_PROFIT_PERCENT": 4
}

TOKENS = ["POL", "USDT", "DAI", "LINK", "WBTC", "ETH", "AAVE"]

HEADERS = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': "f9732761-8d27-48c0-97c7-b4118ce2df35"
}

BASE_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'

INDIAN_TZ = pytz.timezone('Europe/London')

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    requests.post(url, data=payload)

def fetch_token_data(symbol):
    try:
        response = requests.get(BASE_URL, headers=HEADERS, params={'symbol': symbol, 'convert': 'GBP'})
        return response.json()['data'][symbol]
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def check_prices_and_trigger_alerts():
    now = datetime.datetime.now(INDIAN_TZ)
    if now.weekday() > 4 or not (8 <= now.hour < 18):
        return  # Skip if not Mon–Fri, 8am–6pm

    for token in TOKENS:
        data = fetch_token_data(token)
        if not data:
            continue

        quote = data['quote']['GBP']
        price = quote['price']
        change_3h = quote.get('percent_change_3h', 0)
        low_24h = quote['low_24h']
        high_24h = quote['high_24h']

        msg_parts = []

        # Price surge
        if change_3h >= 5:
            msg_parts.append(f"\u2B06 {token} is up {change_3h:.2f}% in last 3h \u2014 momentum rally?")

        # Price drop
        if change_3h <= -5:
            msg_parts.append(f"\u2B07 {token} dropped {abs(change_3h):.2f}% in last 3h \u2014 buy the dip?")

        # Target profit
        entry = ENTRY_PRICES.get(token)
        target_pct = TARGET_PROFIT_PCT.get(token, 0.04)
        if entry and price >= entry * (1 + target_pct):
            msg_parts.append(f"\uD83D\uDCB0 {token} hit target profit (\u00A3{price:.2f}) vs entry \u00A3{entry:.2f}")

        # Range swing
        if high_24h != low_24h:
            top_threshold = low_24h + 0.9 * (high_24h - low_24h)
            bottom_threshold = low_24h + 0.1 * (high_24h - low_24h)

            if price >= top_threshold:
                msg_parts.append(f"\u2B06 {token} near top 10% of 24h range (\u00A3{price:.2f})")
            elif price <= bottom_threshold:
                msg_parts.append(f"\u2B07 {token} near bottom 10% of 24h range (\u00A3{price:.2f})")

        if msg_parts:
            message = f"[{token}] Alerts at {now.strftime('%H:%M')}\n" + '\n'.join(msg_parts)
            send_telegram_alert(message)

if __name__ == '__main__':
    while True:
        check_prices_and_trigger_alerts()
        time.sleep(60)  # Check every 60 seconds
