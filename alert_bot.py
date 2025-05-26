# alert_bot.py
import requests
import time
import json
import datetime
import pytz
import os
from web3 import Web3

# --- Load config.json ---
try:
    with open('config.json') as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    exit(1)

# --- Env vars ---
CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not CMC_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("Missing CMC_API_KEY or TELEGRAM_BOT_TOKEN.")
    exit(1)

# --- Config data ---
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

# --- Web3 Polygon wallet setup ---
polygon_rpc = config.get("polygon_rpc")
w3 = Web3(Web3.HTTPProvider(polygon_rpc))
wallet_address = Web3.to_checksum_address(config.get("polygon_wallet"))

ERC20_ABI = [{
    "constant": True,
    "inputs": [{"name": "_owner", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "balance", "type": "uint256"}],
    "type": "function"
}]

TOKEN_CONTRACTS = {
    "USDT": ("0x3813e82e6f7098b9583FC0F33a962D02018B6803", 6),
    "POL":  ("0x0000000000000000000000000000000000001010", 18),
    "ETH":  ("0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", 18),
    "WBTC": ("0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", 8),
    "LINK": ("0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39", 18),
    "DAI":  ("0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", 18),
    "AAVE": ("0xd6df932a45c0f255f85145f286ea0b292b21c90b", 18)
}

def get_token_balances():
    balances = {}
    for symbol, (contract_address, decimals) in TOKEN_CONTRACTS.items():
        try:
            contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=ERC20_ABI)
            balance = contract.functions.balanceOf(wallet_address).call()
            balances[symbol] = balance / (10 ** decimals)
        except Exception:
            balances[symbol] = 0
    return balances

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
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

    live_balances = get_token_balances()

    for symbol in TOKENS_TO_MONITOR:
        data = fetch_token_data(symbol)
        if not data:
            continue

        quote = data.get('quote', {}).get('GBP', {})
        current_price = quote.get('price')
        change_3h = quote.get('percent_change_3h', 0)
        change_24h = quote.get('percent_change_24h', 0)

        entry_price = ENTRY_PRICES.get(symbol)
        holding = live_balances.get(symbol, 0)
        usdt_balance = live_balances.get("USDT", 0)

        msg_parts = []

        # Surge/Drop alerts
        if change_3h >= PRICE_SURGE_PERCENT:
            msg_parts.append(f"📈 *{symbol}* up {change_3h:.2f}% in 3h! (£{current_price:.2f})")
        if change_3h <= -PRICE_DROP_PERCENT:
            msg_parts.append(f"📉 *{symbol}* down {abs(change_3h):.2f}% in 3h! (£{current_price:.2f})")

        # Profit alert (holding > 0)
        if entry_price and holding > 0 and current_price >= entry_price * (1 + TARGET_PROFIT_PERCENT):
            gain_pct = ((current_price - entry_price) / entry_price) * 100
            profit_gbp = (current_price - entry_price) * holding
            msg_parts.append(
                f"💰 *{symbol}* hit target profit ({TARGET_PROFIT_PERCENT*100:.0f}%)!\n"
                f"Current: £{current_price:.2f} vs Entry: £{entry_price:.2f}\n"
                f"Profit: +{gain_pct:.2f}% (£{profit_gbp:.2f})\n"
                f"✅ Consider Booking"
            )

        # 24h range analysis
        high_approx = current_price / (1 + change_24h / 100) if change_24h != -100 else current_price
        low_approx = min(current_price, high_approx)
        range_diff = abs(current_price - low_approx)
        if range_diff > 0.001:
            top_threshold = low_approx + 0.9 * range_diff
            bottom_threshold = low_approx + 0.1 * range_diff
            if current_price >= top_threshold:
                msg_parts.append(f"📊 *{symbol}* near top 10% of 24h range (£{current_price:.2f})")
            elif current_price <= bottom_threshold:
                msg_parts.append(f"📉 *{symbol}* near bottom 10% of 24h range (£{current_price:.2f})")

        # Buy/Sell logic
        conf = TRACKED_TOKENS_CONFIG.get(symbol, {})
        buy_price = conf.get('buy_price')
        sell_price = conf.get('sell_price')
        min_usdt = conf.get('min_usdt_balance', 0)
        min_holding = conf.get('min_token_holding', 0)

        if buy_price and current_price <= buy_price and usdt_balance >= min_usdt:
            qty = round(min_usdt / current_price, 2)
            msg_parts.append(
                f"🟢 *Buy Alert*: {symbol} at £{current_price:.3f}\n"
                f"Buy ~{qty} {symbol} using £{min_usdt}\n"
                f"Next Target: ≥ £{sell_price}"
            )

        if sell_price and current_price >= sell_price and holding >= min_holding:
            value = holding * current_price
            profit_pct = ((current_price - buy_price) / buy_price * 100) if buy_price else 0
            msg_parts.append(
                f"🔴 *Sell Alert*: {symbol} at £{current_price:.3f}\n"
                f"Holding: {holding:.4f} ≈ £{value:.2f}\n"
                f"Profit Zone: 🎯 ~{profit_pct:.1f}%"
            )

        if msg_parts:
            message = f"🚨 *Crypto Alert!* 🚨\n\n" + '\n\n'.join(msg_parts)
            send_telegram_alert(message)

# --- Main loop ---
if __name__ == '__main__':
    print("--- Crypto Alert Bot Running with Live Wallet Balances ---")
    while True:
        try:
            check_prices_and_trigger_alerts()
            time.sleep(60)
        except Exception as e:
            print(f"Error in loop: {e}")
            time.sleep(300)
