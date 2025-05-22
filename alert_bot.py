import requests
import time
import json
import datetime
import pytz

# Load config
with open('config.json') as f:
    config = json.load(f)

CMC_API_KEY = config['CMC_API_KEY']
TELEGRAM_BOT_TOKEN = config['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = config['TELEGRAM_CHAT_ID']
ENTRY_PRICES = config['ENTRY_PRICES']
TARGET_PROFIT_PERCENT = config['TARGET_PROFIT_PERCENT'] / 100

TOKENS = list(ENTRY_PRICES.keys())

HEADERS = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': CMC_API_KEY
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
        change_24h = quote.get('percent_change_24h', 0)

        try:
            price_24h_ago = price / (1 + change_24h / 100)
        except ZeroDivisionError:
            price_24h_ago = price

        high_24h_approx = max(price, price_24h_ago)
        low_24h_approx = min(price, price_24h_ago)

        msg_parts = []

        # Price surge
        if change_3h >= 5:
            msg_parts.append(f"⬆ {token} is up {change_3h:.2f}% in last 3h — momentum rally?")

        # Price drop
        if change_3h <= -5:
            msg_parts.append(f"⬇ {token} dropped {abs(change_3h):.2f}% in last 3h — buy the dip?")

        # Target profit
        entry = ENTRY_PRICES.get(token)
        if entry and price >= entry * (1 + TARGET_PROFIT_PERCENT):
            msg_parts.append(f"💰 {token} hit target profit (£{price:.2f}) vs entry £{entry:.2f}")

        # Range swing (approximated)
        top_threshold = low_24h_approx + 0.9 * (high_24h_approx - low_24h_approx)
        bottom_threshold = low_24h_approx + 0.1 * (high_24h_approx - low_24h_approx)

        if price >= top_threshold:
            msg_parts.append(f"⬆ {token} near top 10% of 24h range (£{price:.2f})")
        elif price <= bottom_threshold:
            msg_parts.append(f"⬇ {token} near bottom 10% of 24h range (£{price:.2f})")

        if msg_parts:
            message = f"[{token}] Alerts at {now.strftime('%H:%M')}
" + '\n'.join(msg_parts)
            send_telegram_alert(message)

if __name__ == '__main__':
    while True:
        check_prices_and_trigger_alerts()
        time.sleep(60)  # Check every 60 seconds
