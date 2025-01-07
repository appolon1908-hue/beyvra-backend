from django.urls import re_path
from .consumers import AssetConsumer, CryptoMarketDataConsumer, StockMarketDataConsumer, CurrentBalanceConsumer, ProfitLossConsumer

websocket_urlpatterns = [
    re_path(r"ws/crypto-market-data/$", CryptoMarketDataConsumer.as_asgi()),
    re_path(r"ws/stock-market-data/$", StockMarketDataConsumer.as_asgi()),
    
    re_path(r"ws/asset-data/(?P<user_id>\d+)/$", AssetConsumer.as_asgi()),
    re_path(r"ws/current-balance/(?P<user_id>\d+)/$", CurrentBalanceConsumer.as_asgi()),
    re_path(r"ws/profit-loss/(?P<user_id>\d+)/$", ProfitLossConsumer.as_asgi()),
]