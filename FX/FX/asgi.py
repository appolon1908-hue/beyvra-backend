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
from wsnotifications.routing import websocket_urlpatterns as wsnotifications_websocket_urlpatterns
from portfolio.routing import websocket_urlpatterns as portfolio_websocket_urlpatterns  # noqa
from ws.routing import websocket_urlpatterns as ws_websocket_urlpatterns  # noqa
from ws.channels_auth import CustomTokenAuthMiddleware  # noqa

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": CustomTokenAuthMiddleware(
            URLRouter(
                portfolio_websocket_urlpatterns + ws_websocket_urlpatterns + wsnotifications_websocket_urlpatterns
            )
        ),
    }
)
