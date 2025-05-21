import requests
from datetime import datetime, timezone, timedelta
from web3 import Web3
import os

# CONFIG
IFTTT_WEBHOOK_URL = 'https://maker.ifttt.com/trigger/crypto_alert/with/key/dyQNTFV24rbWaW9oQKFPeZ'
WALLET_ADDRESS = '0x9E8ca6e7e4A612909ED892DC69Bd69325a497E73'
POLYGON_RPC = 'https://polygon-rpc.com'
CMC_API_KEY = os.getenv("CMC_API_KEY")
GAS_FEE = 0.01

# Web3 Setup
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

# Base purchase prices in GBP
base_prices = {
    'USDT': 16.43,
    'ETH': 16.61,
    'MATIC': 15.74,
    'LINK': 15.70,
    'AAVE': 15.70,
    'WBTC': 15.82,
    'DAI': 11.77,
    'POL': 15.60
}

# Token metadata (CoinMarketCap uses symbol, not ID)
token_data = {
    'USDT': {'address': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 'decimals': 6},
    'ETH': {'address': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619', 'decimals': 18},
    'MATIC': {'address': '0x0000000000000000000000000000000000001010', 'decimals': 18},
    'LINK': {'address': '0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39', 'decimals': 18},
    'AAVE': {'address': '0xd6df932a45c0f255f85145f286ea0b292b21c90b', 'decimals': 18},
    'WBTC': {'address': '0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6', 'decimals': 8},
    'DAI': {'address': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063', 'decimals': 18},
    'POL': {'address': '0xabc123abc123abc123abc123abc123abc123abcd', 'decimals': 18}  # Update POL token address
}

# Get balance from wallet
def get_balance(symbol):
    token = token_data[symbol]
    if symbol == 'MATIC':
        balance = w3.eth.get_balance(WALLET_ADDRESS)
    else:
        abi = [{"constant": True, "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"}]
        contract = w3.eth.contract(address=w3.to_checksum_address(token['address']), abi=abi)
        balance = contract.functions.balanceOf(WALLET_ADDRESS).call()
    return balance / (10 ** token['decimals'])

# Fetch GBP prices from CoinMarketCap
def fetch_prices():
    symbols = ','.join(token_data.keys())
    url = f'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbols}&convert=GBP'
    headers = {'X-CMC_PRO_API_KEY': CMC_API_KEY}
    res = requests.get(url, headers=headers)
    data = res.json()

    prices = {}
    for sym in token_data:
        try:
            prices[sym] = data['data'][sym]['quote']['GBP']['price']
        except:
            print(f"⚠️ Warning: No GBP price for {sym}")
    return prices

# Format and send alert to IFTTT
def send_alert(symbol, profit, base, current, amount):
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=1)))
    payload = {
        "value1": f"🎯 Profit Target Hit: +£{profit:.2f}",
        "value2": (
            f"Token: {symbol}\n"
            f"Holding: {amount:.4f}\n"
            f"Price: £{base:.2f} → £{current:,.2f}\n"
            f"Base: £{base:.2f}"
        ),
        "value3": "✅ Consider Booking"
    }
    requests.post(IFTTT_WEBHOOK_URL, json=payload)

# Run the bot once
def run_bot():
    try:
        prices = fetch_prices()
        for symbol in base_prices:
            if symbol not in prices:
                continue
            balance = get_balance(symbol)
            if balance == 0:
                continue
            current_price = prices[symbol]
            base_price = base_prices[symbol]
            profit = (current_price - base_price) * balance - GAS_FEE
            if profit >= 2:
                send_alert(symbol, profit, base_price, current_price, balance)
    except Exception as e:
        print(f"❌ Error: {e}")

run_bot()
