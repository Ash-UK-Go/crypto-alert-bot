import requests
from datetime import datetime, timezone, timedelta
import os

# CONFIG
IFTTT_WEBHOOK_URL = 'https://maker.ifttt.com/trigger/crypto_alert/with/key/dyQNTFV24rbWaW9oQKFPeZ'
API_KEY = "Sm2KBpkX6WoK_XWcQU7FembI8ZSQX_85"

# TOKENS TO MONITOR
tokens = ["MATIC", "USDT", "ETH", "LINK", "AAVE", "WBTC", "DAI"]

# ENTRY PRICES (your average buy prices in GBP)
entry_prices = {
    "MATIC": 0.17,
    "USDT": 0.75,
    "ETH": 1900.0,
    "LINK": 11.5,
    "AAVE": 165.0,
    "WBTC": 77800.0,
    "DAI": 0.77
}

# PROFIT THRESHOLD
profit_target = 0.04  # 4% profit target for alert

# TIMESTAMP
now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=1)))

# FETCH PRICES FROM POLYGON.IO

def get_prices():
    url = f"https://api.polygon.io/v2/snapshot/locale/global/markets/crypto/tickers?apiKey={API_KEY}"
    try:
        res = requests.get(url).json()
        prices = {}
        for t in res.get("tickers", []):
            symbol = t['ticker'].split(":")[-1].split("-")[0]
            if symbol in tokens:
                prices[symbol] = {
                    "current": t['lastTrade']['p'],
                    "open": t['day']['o'],
                    "high": t['day']['h'],
                    "low": t['day']['l']
                }
        return prices
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return {}

# ALERT TO TELEGRAM VIA IFTTT

def send_alert(title, details):
    payload = {
        "value1": title,
        "value2": details,
        "value3": now.strftime("%b %d, %Y at %I:%M%p")
    }
    requests.post(IFTTT_WEBHOOK_URL, json=payload)

# CHECK CONDITIONS

def check_alerts():
    prices = get_prices()
    for token in tokens:
        if token not in prices:
            continue

        current = prices[token]["current"]
        open_price = prices[token]["open"]
        high = prices[token]["high"]
        low = prices[token]["low"]
        entry = entry_prices[token]

        # 1. Price Surge
        if (current - open_price) / open_price >= 0.05:
            send_alert(f"📈 {token} Surge Alert", f"+5% in last 3h\nFrom £{open_price:.2f} → £{current:.2f}")

        # 2. Price Drop
        if (open_price - current) / open_price >= 0.05:
            send_alert(f"📉 {token} Drop Alert", f"-5% in last 3h\nFrom £{open_price:.2f} → £{current:.2f}")

        # 3. Profit Target Hit
        if current >= entry * (1 + profit_target):
            send_alert(
                f"🎯 {token} Target Profit Hit",
                f"Price: £{entry:.2f} → £{current:.2f}\nTarget: £{entry * (1 + profit_target):.2f}"
            )

        # 4. Range Swing
        range_ = high - low
        if current >= high - 0.1 * range_:
            send_alert(f"📈 {token} Near Day High", f"Current: £{current:.2f} vs High: £{high:.2f}")
        elif current <= low + 0.1 * range_:
            send_alert(f"📉 {token} Near Day Low", f"Current: £{current:.2f} vs Low: £{low:.2f}")

# Run once
if __name__ == '__main__':
    check_alerts()
