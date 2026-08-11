from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase

from ws.channels_auth import CustomTokenAuthMiddleware


async def _noop(*args, **kwargs):
    return None


class WebSocketTicketSecurityTests(TransactionTestCase):
    reset_sequences = True

    def test_ticket_authenticates_once_then_is_consumed(self):
        user = get_user_model().objects.create_user(
            email="websocket@example.com", password="test-pass", phone_number="+12025550151"
        )
        cache.set("one-time-ticket", user.id, 120)

        async def inner(scope, receive, send):
            return scope["user"].is_authenticated

        middleware = CustomTokenAuthMiddleware(inner)
        first_scope = {"query_string": b"ws_ticket=one-time-ticket"}
        second_scope = {"query_string": b"ws_ticket=one-time-ticket"}

        self.assertTrue(async_to_sync(middleware)(first_scope, _noop, _noop))
        self.assertFalse(async_to_sync(middleware)(second_scope, _noop, _noop))

    def test_missing_or_expired_ticket_is_anonymous(self):
        async def inner(scope, receive, send):
            return scope["user"].is_authenticated

        middleware = CustomTokenAuthMiddleware(inner)
        cache.set("expired-ticket", 999999, 0)

        self.assertFalse(
            async_to_sync(middleware)(
                {"query_string": b"ws_ticket=expired-ticket"}, _noop, _noop
            )
        )
        self.assertFalse(
            async_to_sync(middleware)({"query_string": b""}, _noop, _noop)
        )
