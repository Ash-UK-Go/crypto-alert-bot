import requests
from datetime import datetime, timezone, timedelta
from web3 import Web3

# CONFIG
IFTTT_WEBHOOK_URL = 'https://maker.ifttt.com/trigger/crypto_alert/with/key/dyQNTFV24rbWaW9oQKFPeZ'
WALLET_ADDRESS = '0x9E8ca6e7e4A612909ED892DC69Bd69325a497E73'
POLYGON_RPC = 'https://polygon-rpc.com'
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
GAS_FEE = 0.01

# Tokens & Purchase Prices in GBP
base_prices = {
    'USDT': 16.43,
    'ETH': 16.61,
    'MATIC': 15.74,
    'LINK': 15.70,
    'AAVE': 15.70,
    'WBTC': 15.82,
    'DAI': 11.77
}

token_data = {
    'USDT': {'address': '0xc2132D05D31c914a87C6611C10748AEb04B58e8F', 'decimals': 6, 'id': 'tether'},
    'ETH': {'address': '0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619', 'decimals': 18, 'id': 'ethereum'},
    'MATIC': {'address': '0x0000000000000000000000000000000000001010', 'decimals': 18, 'id': 'matic'},
    'LINK': {'address': '0x53e0bca35ec356bd5dddfebbd1fc0fd03fabad39', 'decimals': 18, 'id': 'chainlink'},
    'AAVE': {'address': '0xd6df932a45c0f255f85145f286ea0b292b21c90b', 'decimals': 18, 'id': 'aave'},
    'WBTC': {'address': '0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6', 'decimals': 8, 'id': 'wrapped-bitcoin'},
    'DAI': {'address': '0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063', 'decimals': 18, 'id': 'dai'}
}

# Get token balance from wallet
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

# Fetch current prices from CoinGecko
def fetch_prices():
    ids = ','.join([token_data[s]['id'] for s in token_data])
    url = f'https://api.coingecko.com/api/v3/simple/price?ids={ids}&vs_currencies=gbp'
    res = requests.get(url).json()
    return {sym: res[data['id']]['gbp'] for sym, data in token_data.items()}

# Send Telegram alert via IFTTT
def send_alert(token, profit, base, current, amount):
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=1)))
    timestamp = now.strftime('%b %d, %Y at %I:%M %p')
    payload = {
        "value1": f"{timestamp} | {token}",
        "value2": f"📈 Profit: £{profit:.2f} | 🎯 Base: £{base:.2f} → £{current:.2f}",
        "value3": f"Holdings: {amount:.4f} {token} | ✅ Consider Booking"
    }
    requests.post(IFTTT_WEBHOOK_URL, json=payload)

# Run check
def run_bot():
    prices = fetch_prices()
    for token in base_prices:
        balance = get_balance(token)
        if balance == 0:
            continue
        profit = (prices[token] - base_prices[token]) * balance - GAS_FEE
        if profit >= 2.0:
            send_alert(token, profit, base_prices[token], prices[token], balance)

run_bot()