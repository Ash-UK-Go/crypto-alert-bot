import requests
import time
import json
import datetime
import pytz
import os
from web3 import Web3

# --- Load Configuration from config.json ---
try:
    with open('config.json') as f:
        config = json.load(f)
except Exception as e:
    print(f"Error loading config: {e}")
    exit(1)

# --- Environment Variables ---
CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not CMC_API_KEY or not TELEGRAM_BOT_TOKEN:
    print("Missing environment variables. Please set CMC_API_KEY and TELEGRAM_BOT_TOKEN.")
    exit(1)

# --- Configuration ---
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

# --- Web3 Setup ---
polygon_rpc = config.get("polygon_rpc")
wallet_address = Web3.to_checksum_address(config.get("polygon_wallet"))
web3 = Web3(Web3.HTTPProvider(polygon_rpc))

erc20_abi = [{
    "constant": True,
    "inputs": [{"name": "_owner", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "balance", "type": "uint256"}],
    "type": "function"
}]

token_contracts = {
    "USDT": ("0x3813e82e6f7098b9583FC0F33a962D02018B6803", 6),
    "ETH": ("0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", 18),
    "WBTC": ("0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", 8),
    "LINK": ("0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39", 18),
    "DAI": ("0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", 18),
    "AAVE": ("0xd6df932a45c0f255f85145f286ea0b292b21c90b", 18)
}

def get_live_wallet_balances():
    balances = {}
    for symbol, (address, decimals) in token_contracts.items():
        contract = web3.eth.contract(address=Web3.to_checksum_address(address), abi=erc20_abi)
        try:
            balance = contract.functions.balanceOf(wallet_address).call()
            balances[symbol] = balance / (10 ** decimals)
        except Exception as e:
            print(f"Error fetching {symbol} balance: {e}")
            balances[symbol] = 0

    try:
        matic_raw = web3.eth.get_balance(wallet_address)
        balances["POL"] = matic_raw / (10 ** 18)
    except Exception as e:
        print(f"Error fetching POL balance: {e}")
        balances["POL"] = 0

    return balances

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

    wallet = get_live_wallet_balances()

    for symbol in TOKENS_TO_MONITOR:
        data = fetch_token_data(symbol)
        if not data:
            continue

        quote = data.get('quote', {}).get('GBP', {})
        current_price = quote.get('price')
        change_3h = quote.get('percent_change_3h', 0)
        change_24h = quote.get('percent_change_24h', 0)

        entry_price = ENTRY_PRICES.get(symbol)
        holding = wallet.get(symbol, 0)
        usdt_balance = wallet.get("USDT", 0)

        msg_parts = []

        if change_3h >= PRICE_SURGE_PERCENT:
            msg_parts.append(f"\u2197\ufe0f *{symbol}* is up {change_3h:.2f}% in 3h! Current: £{current_price:.2f}")
        if change_3h <= -PRICE_DROP_PERCENT:
            msg_parts.append(f"⬇\ufe0f *{symbol}* down {abs(change_3h):.2f}% in 3h! Current: £{current_price:.2f}")

        if entry_price and current_price >= entry_price * (1 + TARGET_PROFIT_PERCENT):
            profit_pct = ((current_price - entry_price) / entry_price) * 100
            profit_gbp = (current_price - entry_price) * holding
            msg_parts.append(f"💰 *{symbol}* hit target profit ({TARGET_PROFIT_PERCENT*100:.0f}%)!\nCurrent: £{current_price:.2f} vs Entry: £{entry_price:.2f}\nProfit: +{profit_pct:.2f}% (£{profit_gbp:.2f})\n✅ Consider Booking")

        range_top = current_price / (1 - change_24h / 100)
        range_bottom = current_price / (1 + change_24h / 100)
        if current_price >= range_bottom + 0.9 * (range_top - range_bottom):
            msg_parts.append(f"📈 *{symbol}* near top 10% of 24h range (£{current_price:.2f})")
        elif current_price <= range_bottom + 0.1 * (range_top - range_bottom):
            msg_parts.append(f"🔽 *{symbol}* near bottom 10% of 24h range (£{current_price:.2f})")

        buy_price = TRACKED_TOKENS_CONFIG[symbol].get('buy_price')
        sell_price = TRACKED_TOKENS_CONFIG[symbol].get('sell_price')
        min_usdt = TRACKED_TOKENS_CONFIG[symbol].get('min_usdt_balance', 0)
        min_holding = TRACKED_TOKENS_CONFIG[symbol].get('min_token_holding', 0)

        if buy_price and current_price <= buy_price and usdt_balance >= min_usdt:
            qty = round(min_usdt / current_price, 2)
            msg_parts.append(f"🟢 Buy Alert: {symbol} at £{current_price:.3f}\nTarget: Buy ~{qty} {symbol} using £{min_usdt:.2f}\nNext Sell Target: ≥ £{sell_price}")

        if sell_price and current_price >= sell_price and holding >= min_holding:
            value = holding * current_price
            profit_pct = ((current_price - buy_price) / buy_price) * 100 if buy_price else 0
            msg_parts.append(f"🔴 Sell Alert: {symbol} at £{current_price:.3f}\nHolding: {holding:.4f} ≈ £{value:.2f}\nProfit Zone: 🎯 ~{profit_pct:.1f}%")

        if msg_parts:
            message = f"🚨 *Crypto Alert!* 🚨\n\n" + "\n\n".join(msg_parts)
            send_telegram_alert(message)

if __name__ == '__main__':
    while True:
        try:
            check_prices_and_trigger_alerts()
            time.sleep(60)
        except Exception as e:
            print(f"Unhandled error: {e}")
            time.sleep(300)
