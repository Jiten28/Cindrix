"""Crypto price lookup via CoinGecko."""

from typing import Optional

import requests

# So "btc" and "bitcoin" both resolve.
_ALIASES = {
    "btc": "bitcoin",
    "eth": "ethereum",
    "doge": "dogecoin",
    "sol": "solana",
    "ada": "cardano",
    "xrp": "ripple",
}


def get_crypto_price(coin: str, vs_currency: str = "usd") -> Optional[str]:
    coin_id = _ALIASES.get(coin.strip().lower(), coin.strip().lower())
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": vs_currency}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        if coin_id not in js:
            return None
        price = js[coin_id][vs_currency]
        return f"The current price of {coin_id.capitalize()} is {price:,} {vs_currency.upper()}."
    except Exception:
        return None
