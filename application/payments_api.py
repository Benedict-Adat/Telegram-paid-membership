import requests
from application import data as config


cb_url = "https://api.commerce.coinbase.com/charges"
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-CC-Api-Key": config.coinbase_api_key,
    "X-CC-Version": "2018-03-22"
}


def create_deposit_charge(chat_id, idempotency_key):
    if not config.coinbase_api_key:
        raise RuntimeError("COINBASE_API_KEY is required to create payment charges")
    data = {
        "name": "Deposit",
        "description": f"Deposit-{chat_id}",
        "pricing_type": "no_price",
        "redirect_url": config.redirect_url,
        "cancel_url": config.cancel_url,
        "metadata": {
            "payment_reference": idempotency_key,
            "user_chat_id": str(chat_id),
        },
    }
    response = requests.post(cb_url, json=data, headers=headers, timeout=15)
    response.raise_for_status()
    charge = response.json().get("data", {})
    charge_code = charge.get("code")
    hosted_url = charge.get("hosted_url")
    if not charge_code or not hosted_url:
        raise ValueError(
            "Coinbase Commerce response did not include a charge code and hosted URL"
        )
    return charge_code, hosted_url
