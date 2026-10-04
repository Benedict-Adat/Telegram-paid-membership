import requests
from application import data as config


cb_url = "https://api.commerce.coinbase.com/charges"
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-CC-Api-Key": config.coinbase_api_key,
    "X-CC-Version": "2018-03-22"
}


def create_deposit_charge(chat_id):
    if not config.coinbase_api_key:
        raise RuntimeError("COINBASE_API_KEY is required to create payment charges")
    data = {
        "name": "Deposit",
        "description": f"Deposit-{chat_id}",
        "pricing_type": "no_price",
        "redirect_url": config.redirect_url,
        "cancel_url": config.cancel_url,
    }
    response = requests.post(cb_url, json=data, headers=headers, timeout=15)
    if response.status_code == 401:
        return False
    response.raise_for_status()
    hosted_url = response.json().get("data", {}).get("hosted_url")
    if not hosted_url:
        raise ValueError("Coinbase Commerce response did not include a hosted URL")
    return hosted_url
