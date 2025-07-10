import requests
import time
import json
import datetime
import pytz
import os
from web3 import Web3 

# --- Load Configuration from config.json ---
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
try:
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    print(f"Configuration loaded successfully from {CONFIG_PATH}.")
except FileNotFoundError:
    print(f"Error: config.json not found at {CONFIG_PATH}. Please create it in the same directory as alert_bot.py.")
    exit(1)
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON in config.json: {e}. Please check its format.")
    exit(1)

# --- Fetch API Keys from Environment Variables (SECURE & REQUIRED) ---
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

# --- Polygon Wallet Live Fetch Setup ---
polygon_rpc = config.get("polygon_rpc")
if not polygon_rpc:
    print("Error: 'polygon_rpc' not found in config.json. Cannot fetch live wallet balances.")
    exit(1)

try:
    w3 = Web3(Web3.HTTPProvider(polygon_rpc))
    if not w3.is_connected():
        print(f"Error: Could not connect to Polygon RPC at {polygon_rpc}.")
        exit(1)
    print(f"Successfully connected to Polygon RPC: {polygon_rpc}")
except Exception as e:
    print(f"Error initializing Web3 with RPC '{polygon_rpc}': {e}")
    exit(1)

wallet_address = config.get("polygon_wallet")
if not wallet_address:
    print("Error: 'polygon_wallet' address not found in config.json. Cannot fetch live wallet balances.")
    exit(1)
try:
    wallet_address = Web3.to_checksum_address(wallet_address)
except ValueError:
    print(f"Error: Invalid 'polygon_wallet' address format in config.json: {wallet_address}")
    exit(1)

# Standard ERC-20 ABI for balanceOf function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

# Token contract addresses and decimals on Polygon Mainnet
# Confirmed POL address as per user's request.
TOKEN_CONTRACTS = {
    "USDT": ("0xc2132d05d31c914a87c6611c10748aeb04b58e8f", 6), # USDT (PoS) on Polygon
    "POL":  ("0x0000000000000000000000000000000000001010", 18), # MATIC (PoS) as per user's specific request
    "ETH":  ("0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", 18), # WETH (PoS) on Polygon
    "WBTC": ("0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", 8),  # WBTC (PoS) on Polygon
    "LINK": ("0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39", 18), # LINK (PoS) on Polygon
    "DAI":  ("0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", 18), # DAI (PoS) on Polygon
    "AAVE": ("0xd6df932a45c0f255f85145f286ea0b292b21c90b", 18)  # AAVE (PoS) on Polygon
}

def get_token_balances():
    """Fetches live token balances for the configured wallet from the Polygon blockchain."""
    balances = {}
    for symbol, (contract_address, decimals) in TOKEN_CONTRACTS.items():
        try:
            contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=ERC20_ABI)
            balance = contract.functions.balanceOf(wallet_address).call()
            balances[symbol] = balance / (10 ** decimals)
            print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Fetched {symbol} balance: {balances[symbol]:.6f}")
        except Exception as e:
            print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error fetching {symbol} balance for {contract_address}: {e}")
            balances[symbol] = 0 # Set to 0 if fetching fails
    return balances

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

        if 'data' not in data or cmc_symbol not in data['data']:
            print(f"⚠️ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Warning: No data found for CMC symbol '{cmc_symbol}' in API response for internal symbol '{symbol_internal}'. This might indicate an invalid symbol or temporary issue. Skipping.")
            return None
            
        return data['data'][cmc_symbol]

    except requests.exceptions.Timeout:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Request to CMC timed out while fetching data for '{cmc_symbol}'.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Network or API request error fetching data for '{cmc_symbol}': {e}. Skipping.")
        return None
    except json.JSONDecodeError:
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] Error decoding JSON response for '{cmc_symbol}' from CMC API. Skipping.")
        return None
    except Exception as e: # Catch any other unexpected errors
        print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%H:%M:%S')}] An unexpected error occurred while fetching '{cmc_symbol}' data: {e}. Skipping.")
        return None

# --- 24h Swing Alert Memory ---
swing_memory = {}

def should_send_swing_alert(symbol, current_price, price_24h_ago):
    """
    Determines if a 24h swing alert should be sent based on thresholds and memory.
    Calculates approximated 24h high/low from current price and 24h percentage change.
    """
    # Determine the approximated high and low over the last 24 hours
    current_24h_high = max(current_price, price_24h_ago)
    current_24h_low = min(current_price, price_24h_ago)
    
    range_diff = current_24h_high - current_24h_low
    
    message_parts = []
    
    # Avoid division by zero or very small ranges
    if range_diff <= 0.001: 
        return message_parts

    top_threshold = current_24h_low + 0.9 * range_diff
    bottom_threshold = current_24h_low + 0.1 * range_diff
    
    prev_zone = swing_memory.get(symbol, {}).get('last_zone', 'middle')

    if current_price >= top_threshold:
        if prev_zone != 'top':
            message_parts.append(f"\U0001F4C8 *{symbol}* near top 10% of 24h range (£{current_price:,.2f})")
            swing_memory[symbol] = {'last_zone': 'top'}
    elif current_price <= bottom_threshold:
        if prev_zone != 'bottom':
            message_parts.append(f"\U0001F4C9 *{symbol}* near bottom 10% of 24h range (£{current_price:,.2f})")
            swing_memory[symbol] = {'last_zone': 'bottom'}
    else:
        # If price is in the middle zone, reset the last_zone to 'middle'
        # This allows for a new top/bottom alert if it re-enters those zones later.
        swing_memory[symbol] = {'last_zone': 'middle'}

    return message_parts

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

    print(f"[{current_time_str}] Initiating price check for {len(TOKENS_TO_MONITOR)} tokens and fetching live wallet balances...")
    live_balances = get_token_balances()
    print(f"[{current_time_str}] Current Wallet Balances: {json.dumps(live_balances, indent=2)}")

    for symbol in TOKENS_TO_MONITOR: # 'symbol' here refers to the internal symbol like 'POL', 'USDT'
        data = fetch_token_data(symbol)
        if not data: # If data fetch failed for this token
            continue

        quote = data.get('quote', {}).get('GBP', {})
        current_price = quote.get('price')
        
        if current_price is None:
            print(f"[{current_time_str}] ⚠️ Warning: Current price for '{symbol}' is missing in CMC response data. Skipping further checks for this token.")
            continue

        change_3h = quote.get('percent_change_3h', 0)
        change_24h = quote.get('percent_change_24h', 0)

        # Calculate approximate price 24 hours ago
        try:
            # Handle cases where change_24h might be exactly -100 (token lost all value)
            # Or where (1 + change_24h / 100) is very close to zero, causing division by zero.
            divisor = (1 + change_24h / 100)
            price_24h_ago = current_price / divisor if abs(divisor) > 1e-9 else current_price 
        except ZeroDivisionError: 
            price_24h_ago = current_price

        entry_price = ENTRY_PRICES.get(symbol)
        holding = live_balances.get(symbol, 0.0) # Get holding from live wallet, default to 0.0
        usdt_balance = live_balances.get("USDT", 0.0) # Get USDT balance from live wallet, default to 0.0

        msg_parts = [] # List to accumulate alert messages for this token

        # --- Alert Conditions ---

        # 1. Price Surge/Drop Alerts (3-hour change)
        if change_3h >= PRICE_SURGE_PERCENT:
            msg_parts.append(f"🔺 *{symbol}* is up {change_3h:.2f}% in 3h! Current: £{current_price:,.2f}")
        elif change_3h <= -PRICE_DROP_PERCENT: # Use elif to avoid sending both if thresholds overlap due to rounding
            msg_parts.append(f"🔻 *{symbol}* dropped {abs(change_3h):.2f}% in 3h! Current: £{current_price:,.2f}")

        # 2. Target Profit Alert (based on entry_price)
        if entry_price is not None and entry_price > 0: 
            # Calculate current profit percentage relative to entry price
            current_profit_percent = ((current_price - entry_price) / entry_price) * 100
            if current_profit_percent >= (TARGET_PROFIT_PERCENT * 100):
                profit_gbp = (current_price - entry_price) * holding # Calculate actual GBP profit based on holding
                msg_parts.append(f"💰 *{symbol}* hit target profit ({TARGET_PROFIT_PERCENT*100:.0f}%)!\nCurrent: £{current_price:,.2f} vs Entry: £{entry_price:.2f}\nProfit: +{current_profit_percent:.2f}% (+£{profit_gbp:,.2f})\n✅ Consider Booking")

        # 3. 24h Swing Alert (using should_send_swing_alert with memory)
        msg_parts.extend(should_send_swing_alert(symbol, current_price, price_24h_ago))

        # 4. BUY/SELL Logic (using new fields from config)
        token_specific_config = TRACKED_TOKENS_CONFIG.get(symbol, {})
        buy_price = token_specific_config.get('buy_price')
        sell_price = token_specific_config.get('sell_price')
        min_usdt_to_buy = token_specific_config.get('min_usdt_balance', 0.0) 
        min_token_holding_to_sell = token_specific_config.get('min_token_holding', 0.0) 

        # Buy Alert
        # Ensure buy_price is set, current_price is at or below buy_price, and enough USDT to buy
        if buy_price is not None and current_price is not None and current_price <= buy_price and usdt_balance >= min_usdt_to_buy and min_usdt_to_buy > 0:
            qty_to_buy = round(min_usdt_to_buy / current_price, 2) if current_price > 0 else 0
            msg_parts.append(f"🟢 *Buy Alert: {symbol}* at £{current_price:.3f}\nTarget: Buy ~{qty_to_buy} {symbol} using £{min_usdt_to_buy:.2f}\nNext Sell Target: ≥ £{sell_price if sell_price is not None else 'N/A'}")

        # Sell Alert
        # Ensure sell_price is set, current_price is at or above sell_price, and enough token holding to sell
        if sell_price is not None and current_price is not None and current_price >= sell_price and holding >= min_token_holding_to_sell and min_token_holding_to_sell > 0:
            value_of_holding = holding * current_price
            # Calculate profit percentage only if buy_price is available and valid
            profit_pct = ((current_price - buy_price) / buy_price) * 100 if (buy_price is not None and buy_price > 0) else 0 
            msg_parts.append(f"🔴 *Sell Alert: {symbol}* at £{current_price:.3f}\nHolding: {holding:.4f} ≈ £{value_of_holding:.2f}\nProfit Zone: 🎯 ~{profit_pct:.1f}%")

        # Send combined alert if any conditions were met
        if msg_parts:
            message = "🚨 *Crypto Alert!* 🚨\n\n" + "\n\n".join(msg_parts)
            send_telegram_alert(message)
        else:
            print(f"[{current_time_str}] No alerts triggered for '{symbol}'. Current Price: £{current_price:,.2f}")


# --- Main execution block ---
if __name__ == '__main__':
    print("--- Crypto Alert Bot Starting with Live Wallet Balances ---")
    
    # Declare w3 as global at the very beginning of the main execution block
    # so that it can be reassigned within the except block without SyntaxError.
    
    if not TOKENS_TO_MONITOR: 
        print("❌ No tokens configured to monitor in config.json. Bot will exit.")
        exit(1)
    
    # Initial connection check to ensure Web3 is working before starting loop
    try:
        if not w3.is_connected():
            raise Exception("Initial Web3 connection failed.")
        print("Initial connection to Polygon RPC successful.")
    except Exception as e:
        print(f"Critical: Failed to connect to Polygon RPC on startup: {e}")
        exit(1)


    while True:
        try:
            check_prices_and_trigger_alerts()
            print(f"[{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] Sleeping for 60 seconds...")
            time.sleep(60)
        except Exception as e:
            print(f"❌ [{datetime.datetime.now(MONITOR_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}] An unhandled error occurred in the main loop: {e}")
            # Attempt to reconnect Web3 in case of network issues
            try:
                print("Attempting to re-establish Web3 connection...")
                w3 = Web3(Web3.HTTPProvider(polygon_rpc)) # w3 is now globally recognized here
                if not w3.is_connected():
                    raise Exception("Reconnection attempt failed.")
                print("Web3 reconnected successfully.")
            except Exception as reconnect_e:
                print(f"❌ Failed to reconnect Web3: {reconnect_e}")
            print("Attempting to continue after 5 minutes (300 seconds)...")
            time.sleep(300)
