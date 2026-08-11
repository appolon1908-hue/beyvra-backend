from django.urls import path

from .consumers import PrivateNotificationConsumer

websocket_urlpatterns = [path("ws/v2/", PrivateNotificationConsumer.as_asgi())]
