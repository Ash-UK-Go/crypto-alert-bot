import requests
from datetime import datetime, timezone, timedelta
from web3 import Web3

# CONFIG
IFTTT_WEBHOOK_URL = 'https://maker.ifttt.com/trigger/crypto_alert/with/key/dyQNTFV24rbWaW9oQKFPeZ'
WALLET_ADDRESS = '0x9E8ca6e7e4A612909ED892DC69Bd69325a497E73'
POLYGON_RPC = 'https://polygon-rpc.com'
GAS_FEE = 0.01  # Estimated fixed gas fee

# Web3 Setup
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))

# Base purchase prices in GBP
base_prices = {
    'ETH': 2485.82,
    'USDT': 1.00,
    'POL': 0.23,
    'LINK': 15.57,
    'AAVE': 262.36,
    'WBTC': 106055.56,
    'DAI': 1.00
}

# Token metadata
token_data = {
    'USDT': {'address': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 'decimals': 6, 'id': 'tether'},
    'ETH': {'address': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619', 'decimals': 18, 'id': 'ethereum'},
    'MATIC': {'address': '0x0000000000000000000000000000000000001010', 'decimals': 18, 'id': 'matic-network'},
    'LINK': {'address': '0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39', 'decimals': 18, 'id': 'chainlink'},
    'AAVE': {'address': '0xd6df932a45c0f255f85145f286ea0b292b21c90b', 'decimals': 18, 'id': 'aave'},
    'WBTC': {'address': '0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6', 'decimals': 8, 'id': 'wrapped-bitcoin'},
    'DAI': {'address': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063', 'decimals': 18, 'id': 'dai'}
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

# Get GBP prices from CoinGecko
def fetch_prices():
    ids = ','.join([token_data[s]['id'] for s in token_data])
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=gbp'
    res = requests.get(url).json()

    prices = {}
    for sym, data in token_data.items():
        coingecko_id = data['id']
        if coingecko_id in res and 'gbp' in res[coingecko_id]:
            prices[sym] = res[coingecko_id]['gbp']
        else:
            print(f"Warning: Could not fetch GBP price for {sym} (CoinGecko ID: {coingecko_id}). Skipping.")
    return prices

# Send IFTTT alert
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

# Main function
def run_bot():
    try:
        prices = fetch_prices()
        for symbol in base_prices:
            if symbol not in prices:
                print(f"Skipping profit calculation for {symbol} as price data is missing.")
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
        print(f"Error: {e}")

run_bot()
