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
    print("Configuration loaded successfully from config.json.")
except FileNotFoundError:
    print("Error: config.json not found. Please create it in the same directory as alert_bot.py.")
    exit(1)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in config.json: {e}. Please check its format.")
    exit(1)

# --- Fetch API Keys from Environment Variables (SECURE & REQUIRED) ---
# These are CRITICAL and must be set on Render's dashboard under Environment Variables.
CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not CMC_API_KEY:
    print("Error: CMC_API_KEY environment variable not set. Bot cannot function without it.")
    exit(1)
if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot send alerts without it.")
    exit(1)

# --- Extract settings from config.json ---
TELEGRAM_CHAT_ID = config.get('telegram_chat_id') 
if not TELEGRAM_CHAT_ID:
    print("Error: 'telegram_chat_id' not found in config.json. Bot cannot send alerts.")
    exit(1)

TRACKED_TOKENS_CONFIG = config.get('tracked_tokens', {})
if not TRACKED_TOKENS_CONFIG:
    print("Warning: No 'tracked_tokens' found in config.json. Bot will not monitor any tokens.")
    
ENTRY_PRICES = {symbol: data.get('entry_price') for symbol, data in TRACKED_TOKENS_CONFIG.items()}
TOKENS_TO_MONITOR = list(TRACKED_TOKENS_CONFIG.keys()) 

ALERT_THRESHOLDS = config.get('alert_thresholds', {})
TARGET_PROFIT_PERCENT = ALERT_THRESHOLDS.get('target_profit_percent', 4) / 100 
PRICE_SURGE_PERCENT = ALERT_THRESHOLDS.get('price_surge_percent', 5)
PRICE_DROP_PERCENT = ALERT_THRESHOLDS.get('price_drop_percent', 5)

TRADING_HOURS_CONFIG = config.get('trading_hours', {})
START_HOUR = TRADING_HOURS_CONFIG.get('start_hour', 8)
END_HOUR = TRADING_HOURS_CONFIG.get('end_hour', 18)
TRADING_DAYS = [
    0 if d == "Monday" else \
    1 if d == "Tuesday" else \
    2 if d == "Wednesday" else \
    3 if d == "Thursday" else \
    4 if d == "Friday" else \
    5 if d == "Saturday" else \
    6 for d in TRADING_HOURS_CONFIG.get('days', [])
]

# --- CoinMarketCap API Setup ---
HEADERS = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': CMC_API_KEY
}
CMC_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'

# --- Timezone Setup ---
MONITOR_TIMEZONE = pytz.timezone('Europe/London') 

# --- Simulated Wallet (Hardcoded for current functionality) ---
# If you plan to integrate real wallet balances, this section will need significant modification.
mock_wallet = {
    "USDT": 30.0,
    "POL": 120.0, 
    "ETH": 0.05,
    "WBTC": 0.0003,
    "LINK": 5.0,
    "AAVE": 0.12,
    "DAI": 10.0
}

# --- TEST MODE Flag ---
# Set to True for testing with predefined prices/changes, False for live CMC data.
TEST_MODE = True 

# --- Functions ---

def send_telegram_alert(message):
    """Sends a formatted message to the configured Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown' 
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        response.raise_for_status() 
        print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Telegram alert sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error sending Telegram alert: {e}")
    except Exception as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] An unexpected error occurred while sending Telegram alert: {e}")

def fetch_token_data(symbol_internal):
    """
    Fetches cryptocurrency data from CoinMarketCap for a given internal symbol.
    Uses the cmc_symbol defined in config.json for the actual API call.
    """
    if TEST_MODE:
        # In TEST_MODE, we don't fetch real data, so return dummy data structure
        # This prevents API calls and uses the test_prices/changes directly.
        # However, it still needs to return a structure that 'quote.get' can process.
        # This dummy structure will be overridden by test_prices/changes later.
        return {'quote': {'GBP': {'price': 1.0, 'percent_change_3h': 0, 'percent_change_24h': 0}}}

    token_info = TRACKED_TOKENS_CONFIG.get(symbol_internal, {})
    cmc_symbol = token_info.get('cmc_symbol')
    
    if not cmc_symbol:
        print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error: No 'cmc_symbol' defined for internal symbol '{symbol_internal}' in config.json. Skipping.")
        return None

    params = {'symbol': cmc_symbol, 'convert': 'GBP'}
    try:
        response = requests.get(CMC_URL, headers=HEADERS, params=params, timeout=15)
        response.raise_for_status() 
        data = response.json()

        if data.get('status', {}).get('error_code') != 0:
            error_message = data.get('status', {}).get('error_message', 'Unknown API error')
            print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] CMC API Error for '{cmc_symbol}' (Code: {data.get('status', {}).get('error_code')}): {error_message}. Skipping.")
            return None

        if cmc_symbol in data['data']:
            return data['data'][cmc_symbol]
        else:
            print(f"⚠️ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Warning: No data found for CMC symbol '{cmc_symbol}' in API response for internal symbol '{symbol_internal}'. This might indicate an invalid symbol or temporary issue. Skipping.")
            return None

    except requests.exceptions.Timeout:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Request to CMC timed out while fetching data for '{cmc_symbol}'.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Network or API request error fetching data for '{cmc_symbol}': {e}. Skipping.")
        return None
    except json.JSONDecodeError:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error decoding JSON response for '{cmc_symbol}' from CMC API. Skipping.")
        return None
    except Exception as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] An unexpected error occurred while fetching '{cmc_symbol}' data: {e}. Skipping.")
        return None

def check_prices_and_trigger_alerts():
    """Main function to fetch prices, calculate conditions, and send alerts."""
    now = datetime.datetime.now(MONITOR_TIMEZONE)
    current_time_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # --- Trading Hours and Days Check ---
    if now.weekday() not in TRADING_DAYS:
        print(f"[{current_time_str}] Skipping check: Not a trading day ({now.strftime('%A')}).")
        return
        
    if not (START_HOUR <= now.hour < END_HOUR):
        print(f"[{current_time_str}] Skipping check: Outside trading hours ({now.hour}:00).")
        return

    print(f"[{current_time_str}] Initiating price check for {len(TOKENS_TO_MONITOR)} tokens...")

    # Define test data if TEST_MODE is active
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
        "POL": 8.0, "USDT": 0.5, "ETH": 1.0, "WBTC": 10.0,
        "LINK": 5.0, "DAI": -2.0, "AAVE": 12.0
    }

    for symbol in TOKENS_TO_MONITOR:
        data = fetch_token_data(symbol)
        if not data and not TEST_MODE: # If not in test mode AND data fetch failed
            continue

        quote = data.get('quote', {}).get('GBP', {}) # Will be dummy data if in TEST_MODE

        # Determine current_price, change_3h, change_24h based on TEST_MODE or live data
        if TEST_MODE:
            current_price = test_prices.get(symbol, quote.get('price')) # Use test price, fallback to dummy
            change_3h = test_changes_3h.get(symbol, 0)
            change_24h = test_changes_24h.get(symbol, 0)
        else:
            current_price = quote.get('price')
            change_3h = quote.get('percent_change_3h', 0)
            change_24h = quote.get('percent_change_24h', 0)

        if current_price is None:
            print(f"[{current_time_str}] ⚠️ Warning: Current price for '{symbol}' is missing. Skipping further checks for this token.")
            continue

        # Calculate approximate price 24 hours ago for range analysis
        try:
            # Avoid division by zero if change_24h is -100
            price_24h_ago = current_price / (1 + change_24h / 100) if change_24h != -100 else current_price
        except ZeroDivisionError:
            price_24h_ago = current_price

        high_24h_approx = max(current_price, price_24h_ago)
        low_24h_approx = min(current_price, price_24h_ago)

        entry_price = ENTRY_PRICES.get(symbol)
        holding = mock_wallet.get(symbol, 0) 
        usdt_balance = mock_wallet.get("USDT", 0)

        msg_parts = [] 

        # --- Alert Conditions ---

        # 1. Price Surge/Drop Alerts (3-hour change)
        if change_3h >= PRICE_SURGE_PERCENT:
            msg_parts.append(f"⬆️ *{symbol}* is up {change_3h:.2f}% in 3h! Current: £{current_price:,.2f}")
        if change_3h <= -PRICE_DROP_PERCENT:
            msg_parts.append(f"⬇️ *{symbol}* down {abs(change_3h):.2f}% in 3h! Current: £{current_price:,.2f}")

        # 2. Target Profit Alert (based on entry_price)
        if entry_price is not None and entry_price > 0: 
            if current_price >= entry_price * (1 + TARGET_PROFIT_PERCENT):
                profit_amount_percent = ((current_price - entry_price) / entry_price) * 100
                profit_gbp = (current_price - entry_price) * holding # Calculate actual GBP profit based on holding
                msg_parts.append(f"💰 *{symbol}* hit target profit ({TARGET_PROFIT_PERCENT*100:.0f}%)!\nCurrent: £{current_price:,.2f} vs Entry: £{entry_price:.2f}\nProfit: +{profit_amount_percent:.2f}% (+£{profit_gbp:,.2f})\n✅ Consider Booking")

        # 3. Near 24h range top/bottom (approximated)
        range_diff = high_24h_approx - low_24h_approx
        if range_diff > 0.001: 
            top_threshold = low_24h_approx + 0.9 * range_diff
            bottom_threshold = low_24h_approx + 0.1 * range_diff

            if current_price >= top_threshold:
                msg_parts.append(f"📈 *{symbol}* near top 10% of 24h range (£{current_price:,.2f})")
            elif current_price <= bottom_threshold:
                msg_parts.append(f"📉 *{symbol}* near bottom 10% of 24h range (£{current_price:,.2f})")

        # 4. BUY/SELL Logic (using new fields from config)
        token_specific_config = TRACKED_TOKENS_CONFIG.get(symbol, {})
        buy_price = token_specific_config.get('buy_price')
        sell_price = token_specific_config.get('sell_price')
        min_usdt_to_buy = token_specific_config.get('min_usdt_balance', 0.0) 
        min_token_holding_to_sell = token_specific_config.get('min_token_holding', 0.0) 

        # Buy Alert
        if buy_price is not None and current_price <= buy_price and usdt_balance >= min_usdt_to_buy and min_usdt_to_buy > 0:
            qty_to_buy = round(min_usdt_to_buy / current_price, 2) if current_price > 0 else 0
            msg_parts.append(f"🟢 *Buy Alert: {symbol}* at £{current_price:.3f}\nTarget: Buy ~{qty_to_buy} {symbol} using £{min_usdt_to_buy:.2f}\nNext Sell Target: ≥ £{sell_price if sell_price is not None else 'N/A'}")

        # Sell Alert
        if sell_price is not None and current_price >= sell_price and holding >= min_token_holding_to_sell and min_token_holding_to_sell > 0:
            value_of_holding = holding * current_price
            profit_pct = ((current_price - buy_price) / buy_price) * 100 if buy_price and buy_price > 0 else 0 # Calculate profit if buy_price exists
            msg_parts.append(f"🔴 *Sell Alert: {symbol}* at £{current_price:.3f}\nHolding: {holding:.4f} ≈ £{value_of_holding:.2f}\nProfit Zone: 🎯 ~{profit_pct:.1f}%")

        # Send combined alert if any conditions were met
        if msg_parts:
            message = f"🚨 *Crypto Alert!* 🚨\n\n" + '\n\n'.join(msg_parts) 
            send_telegram_alert(message)
        else:
            print(f"[{current_time_str}] No alerts triggered for '{symbol}'. Current Price: £{current_price:,.2f}")


# --- Main execution block ---
if __name__ == '__main__':
    print("--- Crypto Alert Bot Starting ---")
    
    if not TOKENS_TO_MONITOR and not TEST_MODE: # Only exit if no tokens and not in test mode (where dummy data might be used)
        print("❌ No tokens configured to monitor in config.json. Bot will exit.")
        exit(1)
    elif not TOKENS_TO_MONITOR and TEST_MODE:
        print("⚠️ No tokens configured in config.json, but TEST_MODE is ON. Bot will use hardcoded test data for alerts.")


    while True:
        try:
            check_prices_and_trigger_alerts()
            print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] Sleeping for 60 seconds...")
            time.sleep(60)
        except Exception as e:
            print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] An unhandled error occurred in the main loop: {e}")
            print("Attempting to continue after 5 minutes (300 seconds)...")
            time.sleep(300)
