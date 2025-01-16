import logging
from celery import shared_task
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


logger = logging.getLogger(__name__)


@shared_task
def periodic_price_updates():
    url = 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd'
    headers = {"accept": "application/json", 'x-cg-demo-api-key': 'CG-NgaLHLy457wk81jkXajMRGdx' }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        coins_and_prices = [
            {"name": coin["name"], "price": coin["current_price"]}
            for coin in data
        ]
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "market_prices",
            {
                "type": "send_price_update",
                "message": coins_and_prices
            }
        )
        return data
    else:
        print(f"Failed to fetch data: {response.status_code}")
        return None