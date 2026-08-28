from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from users.models import User


import logging
import hashlib

logger = logging.getLogger(__name__)


@database_sync_to_async
def get_user(user_id: int) -> User:
    try:
        user = User.objects.get(id=user_id)
        return user
    except User.DoesNotExist:
        return AnonymousUser()


class CustomTokenAuthMiddleware(BaseMiddleware):
    """
    Authentication middleware for channels
    """

    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        """Checks if a 'ticket' query param is in the header and authorize a user

        Returns:
            User: django user
        """
        # TODO: make only one socket connection per client
        # if a user logs in another device invalidate the other sockets

        if not self._origin_allowed(scope):
            logger.warning("websocket origin rejected")
            scope["user"] = AnonymousUser()
            return await super().__call__(scope, receive, send)

        # get ticket from query param
        query_string = scope["query_string"].decode("utf-8")
        query_params = dict(parse_qs(query_string))
        tickets = query_params.get("ws_ticket", [])
        if tickets:
            ws_ticket = tickets[0]
            # get user id from redis cache
            ticket_payload = cache.get(ws_ticket, "None")
            cache.delete(ws_ticket)
            user_id = ticket_payload.get("user_id") if isinstance(ticket_payload, dict) else ticket_payload
            if isinstance(ticket_payload, dict):
                scope["realtime_ticket"] = {
                    "tenant_id": ticket_payload.get("tenant_id"),
                    "user_id": ticket_payload.get("user_id"),
                }
        else:
            user_id = "None"
        if user_id == "None":
            logger.warning("websocket ticket rejected: cache miss ticket_hash=%s", hashlib.sha256(ws_ticket.encode()).hexdigest()[:12] if tickets else "missing")
            scope["user"] = AnonymousUser()
        else:
            scope["user"] = await get_user(user_id)
            if not scope["user"].is_authenticated:
                logger.warning("websocket ticket rejected: user lookup failed ticket_hash=%s", hashlib.sha256(ws_ticket.encode()).hexdigest()[:12])

        return await super().__call__(scope, receive, send)

    def _origin_allowed(self, scope):
        origin = None
        for key, value in scope.get("headers", []):
            if key == b"origin":
                origin = value.decode("utf-8", errors="replace").rstrip("/")
                break
        if not origin:
            return True
        allowed = {item.rstrip("/") for item in getattr(settings, "CORS_ALLOWED_ORIGINS", [])}
        allowed.update(item.rstrip("/") for item in getattr(settings, "CSRF_TRUSTED_ORIGINS", []))
        allowed.add(getattr(settings, "PUBLIC_SITE_URL", "").rstrip("/"))
        allowed.add(getattr(settings, "FRONTEND_URL", "").rstrip("/"))
        return origin in {item for item in allowed if item}
