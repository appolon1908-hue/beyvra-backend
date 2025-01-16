from django.urls import re_path
from ws.consumers import WebsocketConsumer

websocket_urlpatterns = [
    re_path("ws/external-api/", WebsocketConsumer.as_asgi()),
]
