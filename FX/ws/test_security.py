from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings

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

    def test_structured_ticket_payload_is_single_use(self):
        user = get_user_model().objects.create_user(
            email="websocket-structured@example.com", password="test-pass", phone_number="+12025550152"
        )
        cache.set("structured-ticket", {"user_id": user.id, "tenant_id": "tenant-1"}, 60)

        async def inner(scope, receive, send):
            return scope["user"].is_authenticated and scope["realtime_ticket"]["tenant_id"] == "tenant-1"

        middleware = CustomTokenAuthMiddleware(inner)
        self.assertTrue(async_to_sync(middleware)({"query_string": b"ws_ticket=structured-ticket"}, _noop, _noop))
        self.assertFalse(async_to_sync(middleware)({"query_string": b"ws_ticket=structured-ticket"}, _noop, _noop))

    @override_settings(
        CORS_ALLOWED_ORIGINS=["https://beyvra.com"],
        CSRF_TRUSTED_ORIGINS=["https://beyvra.com"],
        PUBLIC_SITE_URL="https://beyvra.com",
        FRONTEND_URL="https://beyvra.com",
    )
    def test_browser_origin_must_be_allowlisted(self):
        user = get_user_model().objects.create_user(
            email="websocket-origin@example.com", password="test-pass", phone_number="+12025550153"
        )
        cache.set("origin-ticket", user.id, 60)

        async def inner(scope, receive, send):
            return scope["user"].is_authenticated

        middleware = CustomTokenAuthMiddleware(inner)
        self.assertFalse(async_to_sync(middleware)({"query_string": b"ws_ticket=origin-ticket", "headers": [(b"origin", b"https://evil.example")]}, _noop, _noop))
        cache.set("origin-ticket", user.id, 60)
        self.assertTrue(async_to_sync(middleware)({"query_string": b"ws_ticket=origin-ticket", "headers": [(b"origin", b"https://beyvra.com")]}, _noop, _noop))
