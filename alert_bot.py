import requests
import time
import json
import datetime
import pytz
import os # Import os for environment variables

# --- Load Configuration from config.json ---
try:
    with open('config.json') as f:
        config = json.load(f)
    print("Configuration loaded successfully from config.json.")
except FileNotFoundError:
    print("Error: config.json not found. Please create it in the same directory.")
    exit(1) # Exit if config file is missing
except json.JSONDecodeError:
    print("Error: Invalid JSON in config.json. Please check its format.")
    exit(1) # Exit if config file is malformed

# --- Fetch API Keys from Environment Variables (SECURE WAY) ---
CMC_API_KEY = os.getenv('CMC_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Ensure essential environment variables are set
if not CMC_API_KEY:
    print("Error: CMC_API_KEY environment variable not set. Bot cannot function.")
    exit(1) # Exit if CMC_API_KEY is missing
if not TELEGRAM_BOT_TOKEN:
    print("Error: TELEGRAM_BOT_TOKEN environment variable not set. Bot cannot send alerts.")
    exit(1) # Exit if TELEGRAM_BOT_TOKEN is missing

# --- Configuration from config.json ---
# Telegram Chat ID (not sensitive, can be in config)
TELEGRAM_CHAT_ID = config.get('telegram_chat_id') 
if not TELEGRAM_CHAT_ID:
    print("Error: 'telegram_chat_id' not found in config.json. Bot cannot send alerts.")
    exit(1) # Exit if chat ID is missing

# Extract tracked tokens and their entry prices
TRACKED_TOKENS_CONFIG = config.get('tracked_tokens', {})
if not TRACKED_TOKENS_CONFIG:
    print("Warning: No 'tracked_tokens' found in config.json. Bot will not monitor any tokens.")
    
# Create a simpler dictionary for entry prices based on the tracked_tokens config
ENTRY_PRICES = {symbol: data.get('entry_price') for symbol, data in TRACKED_TOKENS_CONFIG.items()}
# List of internal symbols (e.g., 'POL', 'USDT') that the bot will iterate through
TOKENS_TO_MONITOR = list(TRACKED_TOKENS_CONFIG.keys()) 

# Extract alert thresholds
ALERT_THRESHOLDS = config.get('alert_thresholds', {})
TARGET_PROFIT_PERCENT = ALERT_THRESHOLDS.get('target_profit_percent', 4) / 100 # Convert to decimal
PRICE_SURGE_PERCENT = ALERT_THRESHOLDS.get('price_surge_percent', 5)
PRICE_DROP_PERCENT = ALERT_THRESHOLDS.get('price_drop_percent', 5)

# Extract trading hours
TRADING_HOURS_CONFIG = config.get('trading_hours', {})
START_HOUR = TRADING_HOURS_CONFIG.get('start_hour', 8)
END_HOUR = TRADING_HOURS_CONFIG.get('end_hour', 18)
# Map day names from config to Python's weekday numbers (Monday=0, Sunday=6)
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
BASE_URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest'

# --- Timezone Setup ---
# Use Europe/London as specified in the user's config
MONITOR_TIMEZONE = pytz.timezone('Europe/London') 

# --- Functions ---

def send_telegram_alert(message):
    """Sends a formatted message to the configured Telegram chat."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown' # Enable Markdown formatting for bold, etc.
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Telegram alert sent.")
    except requests.exceptions.RequestException as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error sending Telegram alert: {e}")
    except Exception as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] An unexpected error occurred while sending Telegram alert: {e}")

def fetch_token_data(symbol_from_config):
    """
    Fetches cryptocurrency data from CoinMarketCap for a given symbol.
    Uses the cmc_symbol defined in config.json.
    """
    cmc_symbol = TRACKED_TOKENS_CONFIG.get(symbol_from_config, {}).get('cmc_symbol')
    if not cmc_symbol:
        print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error: No CMC symbol defined for '{symbol_from_config}' in config.json. Skipping.")
        return None

    params = {'symbol': cmc_symbol, 'convert': 'GBP'}
    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=10) # Add timeout
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        data = response.json()

        # Check for CoinMarketCap API specific errors in the response
        if data.get('status', {}).get('error_code') != 0:
            error_message = data.get('status', {}).get('error_message', 'Unknown API error')
            print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] CMC API Error for '{cmc_symbol}' (Code: {data.get('status', {}).get('error_code')}): {error_message}. Skipping.")
            return None

        # Ensure the expected symbol data is present in the API response
        if cmc_symbol in data['data']:
            return data['data'][cmc_symbol]
        else:
            print(f"⚠️ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Warning: No data found for CMC symbol '{cmc_symbol}' in API response. This might indicate an invalid symbol or temporary issue. Skipping.")
            return None

    except requests.exceptions.Timeout:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Request to CMC timed out for '{cmc_symbol}'.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Network or API request error fetching data for '{cmc_symbol}': {e}. Skipping.")
        return None
    except json.JSONDecodeError: # Catches JSON decoding error
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error decoding JSON response for '{cmc_symbol}' from CMC API.")
        print(f"Response content: {response.text if 'response' in locals() else 'No response'}. Skipping.")
        return None
    except Exception as e: # Catch any other unexpected errors
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] An unexpected error occurred while fetching '{cmc_symbol}' data: {e}. Skipping.")
        return None

def check_prices_and_trigger_alerts():
    """Main function to fetch prices, calculate conditions, and send alerts."""
    now = datetime.datetime.now(MONITOR_TIMEZONE)
    current_time_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # --- Trading Hours and Days Check ---
    # Check if current day is a trading day
    if now.weekday() not in TRADING_DAYS:
        print(f"[{current_time_str}] Skipping check: Not a trading day ({now.strftime('%A')}).")
        return
        
    # Check if current hour is within trading hours
    if not (START_HOUR <= now.hour < END_HOUR):
        print(f"[{current_time_str}] Skipping check: Outside trading hours ({now.hour}:00 - {END_HOUR}:00).")
        return

    print(f"[{current_time_str}] Initiating price check for {len(TOKENS_TO_MONITOR)} tokens...")

    for token_symbol_internal in TOKENS_TO_MONITOR:
        data = fetch_token_data(token_symbol_internal)
        if not data: # If data fetching failed, skip this token
            continue

        quote = data.get('quote', {}).get('GBP', {})
        current_price = quote.get('price')
        
        if current_price is None:
            print(f"[{current_time_str}] ⚠️ Warning: Current price for '{token_symbol_internal}' is missing in CMC response. Skipping.")
            continue

        change_3h = quote.get('percent_change_3h', 0)
        change_24h = quote.get('percent_change_24h', 0)

        # Calculate approximate price 24 hours ago for range analysis
        # Handle cases where change_24h might be exactly -100 (token lost all value)
        try:
            price_24h_ago = current_price / (1 + change_24h / 100) if change_24h != -100 else current_price
        except ZeroDivisionError: # Should theoretically be handled by != -100, but as a safeguard
            price_24h_ago = current_price

        high_24h_approx = max(current_price, price_24h_ago)
        low_24h_approx = min(current_price, price_24h_ago)

        msg_parts = [] # List to accumulate alert messages for this token

        # --- Alert Conditions ---

        # 1. Price surge alert
        if change_3h >= PRICE_SURGE_PERCENT:
            msg_parts.append(f"⬆️ *{token_symbol_internal}* is up {change_3h:.2f}% in last 3h! Current: £{current_price:,.2f}")

        # 2. Price drop alert
        if change_3h <= -PRICE_DROP_PERCENT:
            msg_parts.append(f"⬇️ *{token_symbol_internal}* dropped {abs(change_3h):.2f}% in last 3h! Current: £{current_price:,.2f}")

        # 3. Target profit alert
        entry_price = ENTRY_PRICES.get(token_symbol_internal)
        if entry_price is not None and entry_price > 0: # Ensure entry_price is valid and positive
            if current_price >= entry_price * (1 + TARGET_PROFIT_PERCENT):
                profit_amount = (current_price - entry_price) / entry_price * 100
                msg_parts.append(f"💰 *{token_symbol_internal}* hit target profit ({TARGET_PROFIT_PERCENT*100:.0f}%)! Current: £{current_price:,.2f} vs Entry: £{entry_price:.2f} (+{profit_amount:.2f}%)")

        # 4. Near 24h range top/bottom (approximated)
        range_diff = high_24h_approx - low_24h_approx
        if range_diff > 0.001: # Avoid division by zero or very small ranges
            # Thresholds for top/bottom 10% of the range
            top_threshold = low_24h_approx + 0.9 * range_diff
            bottom_threshold = low_24h_approx + 0.1 * range_diff

            if current_price >= top_threshold:
                msg_parts.append(f"📈 *{token_symbol_internal}* near top 10% of 24h range (£{current_price:,.2f})")
            elif current_price <= bottom_threshold:
                msg_parts.append(f"📉 *{token_symbol_internal}* near bottom 10% of 24h range (£{current_price:,.2f})")

        # Send combined alert if any conditions were met
        if msg_parts:
            # FIXED: SyntaxError by explicitly adding '\n' for newline
            message = f"🚨 *Crypto Alert!* 🚨\n\n" + '\n'.join(msg_parts)
            send_telegram_alert(message)
        else:
            print(f"[{current_time_str}] No alerts triggered for '{token_symbol_internal}'. Current Price: £{current_price:,.2f}")


# --- Main execution block ---
if __name__ == '__main__':
    print("--- Crypto Alert Bot Starting ---")
    
    # Initial checks for configuration before entering main loop
    if not TOKENS_TO_MONITOR:
        print("❌ No tokens configured to monitor. Please check 'tracked_tokens' in config.json.")
        exit(1)

    while True:
        try:
            check_prices_and_trigger_alerts()
            # Sleep for 60 seconds (1 minute) before the next check
            print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] Sleeping for 60 seconds...")
            time.sleep(60)
        except Exception as e:
            print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] An unhandled error occurred in the main loop: {e}")
            print("Attempting to continue after 5 minutes...")
            time.sleep(300) # Sleep longer on unhandled errors before retrying
