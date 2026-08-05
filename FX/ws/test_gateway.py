import uuid
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings

from FX.asgi import application


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}},
)
class CanonicalGatewayTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(email="gateway@example.com", password="test-pass")

    def ticket(self):
        value = f"gateway-{uuid.uuid4()}"
        cache.set(value, self.user.id, 120)
        return value

    def test_requires_ticket_and_deduplicates_subscriptions(self):
        async def scenario():
            unauthenticated = WebsocketCommunicator(application, "/ws/v1/")
            connected, code = await unauthenticated.connect()
            self.assertFalse(connected)
            self.assertEqual(code, 4401)

            communicator = WebsocketCommunicator(application, f"/ws/v1/?ws_ticket={self.ticket()}")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            self.assertEqual((await communicator.receive_json_from())["type"], "gateway.ready")
            await communicator.send_json_to({"action": "subscribe", "channels": ["market.candle:BTCUSDT:1m", "market.candle:BTCUSDT:1m"]})
            ack = await communicator.receive_json_from()
            self.assertEqual(ack["added"], ["market.candle:BTCUSDT:1m"])
            await communicator.send_json_to({"action": "subscribe", "channels": ["market.candle:BTCUSDT:1m", "market.candle:BTCUSDT:1m"]})
            self.assertEqual((await communicator.receive_json_from())["added"], [])
            await communicator.send_json_to({"action": "subscribe", "channels": ["wallet.deposit"]})
            denied = await communicator.receive_json_from()
            self.assertEqual(denied["code"], "FORBIDDEN_CHANNEL")
            await communicator.receive_json_from()
            await communicator.send_json_to({"action": "subscribe", "channels": [f"portfolio.balance:{self.user.id}"]})
            self.assertEqual((await communicator.receive_json_from())["added"], [f"portfolio.balance:{self.user.id}"])
            await communicator.send_json_to({"action": "subscribe", "channels": ["portfolio.balance:999999"]})
            denied_account = await communicator.receive_json_from()
            self.assertEqual(denied_account["code"], "FORBIDDEN_CHANNEL")
            await communicator.receive_json_from()
            await communicator.disconnect()

        with patch("ws.gateway.CanonicalGatewayConsumer._stream_market", new=AsyncMock()):
            async_to_sync(scenario)()
