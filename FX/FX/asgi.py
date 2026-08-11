"""
ASGI config for FX project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FX.settings")

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa
from django.urls import re_path
from wsnotifications.routing import websocket_urlpatterns as wsnotifications_websocket_urlpatterns
from portfolio.routing import websocket_urlpatterns as portfolio_websocket_urlpatterns  # noqa
from ws.routing import websocket_urlpatterns as ws_websocket_urlpatterns  # noqa
from ws.channels_auth import CustomTokenAuthMiddleware  # noqa
from real_wallet.routing import websocket_urlpatterns as real_wallet_websocket_urlpatterns
from ws.gateway import CanonicalGatewayConsumer

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": CustomTokenAuthMiddleware(
            URLRouter(
                [
                    re_path(r"ws/v2/$", CanonicalGatewayConsumer.as_asgi()),
                    re_path(r"ws/v2/connection/websocket$", CanonicalGatewayConsumer.as_asgi()),
                    re_path(r"ws/v1/$", CanonicalGatewayConsumer.as_asgi()),
                ]
                + portfolio_websocket_urlpatterns
                + ws_websocket_urlpatterns
                + wsnotifications_websocket_urlpatterns
                + real_wallet_websocket_urlpatterns
            )
        ),
    }
)
