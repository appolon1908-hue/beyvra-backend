from django.urls import re_path
from wsnotifications.consumers import market, trades, admin, users



websocket_urlpatterns = [
    re_path('ws/market/', market.MarketDataConsumer.as_asgi()),
    re_path('ws/trades/', trades.TradeConsumer.as_asgi()),
    re_path('ws/admin/', admin.AdminDataConsumer.as_asgi()),
    re_path('ws/users/', users.UserConsumer.as_asgi()),
    re_path('ws/price_alerts_threshold/', users.PriceThresholdConsumer.as_asgi())
]