import requests
from django.conf import settings
from django.core.cache import cache


class AlpacaMarketData:

    def __init__(self):
        self.api_key = settings.API_KEY_ALPACA
        self.secret_key = settings.SECRET_KEY_ALPACA

    def get_market_movers(self, request):

        url = f"https://data.alpaca.markets/v1beta1/screener/{request.query_params.get('market_type', 'crypto')}/movers?top={request.query_params.get('top', 10)}"  # noqa

        headers = {
            "accept": "application/json",
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

        redis_top_movers = (
            f"top_movers_{request.query_params.get('market_type', 'crypto')}_{request.query_params.get('top', 10)}"
        )
        cached_data = cache.get(redis_top_movers)
        if cached_data:
            return cached_data

        response = requests.get(url, headers=headers)
        cache.set(redis_top_movers, response.json(), 60)

        return response.json()
