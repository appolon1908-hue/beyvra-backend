from django.urls import re_path
from wsnotifications.consumers import market, trade, admin


ws_notificationswebsocket_urlpatterns = [
    re_path('ws/market/', market.MarketDataConsumer.as_asgi()), ##Now working
    re_path('ws/trades/', trade.TradeConsumer.as_asgi()),
    re_path('ws/admin/', admin.AdminConsumer.as_asgi()),
]