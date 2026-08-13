from django.urls import re_path

from .consumers import RealWalletStreamConsumer


websocket_urlpatterns = [
    re_path(r"ws/v1/real-wallet/$", RealWalletStreamConsumer.as_asgi()),
]
