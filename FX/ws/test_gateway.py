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

            canonical = WebsocketCommunicator(application, f"/ws/v2/?ws_ticket={self.ticket()}")
            connected, _ = await canonical.connect()
            self.assertTrue(connected)
            ready = await canonical.receive_json_from()
            self.assertEqual(ready["version"], 2)
            self.assertNotIn("deprecation", ready)
            await canonical.disconnect()

            communicator = WebsocketCommunicator(application, f"/ws/v1/?ws_ticket={self.ticket()}")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            self.assertEqual((await communicator.receive_json_from())["type"], "gateway.ready")
            await communicator.send_json_to({"action": "subscribe", "channels": ["market.BTCUSDT.candle.1m", "market.BTCUSDT.candle.1m"]})
            ack = await communicator.receive_json_from()
            self.assertEqual(ack["added"], ["market.BTCUSDT.candle.1m"])
            await communicator.send_json_to({"action": "subscribe", "channels": ["market.BTCUSDT.candle.1m", "market.BTCUSDT.candle.1m"]})
            self.assertEqual((await communicator.receive_json_from())["added"], [])
            await communicator.send_json_to({"action": "subscribe", "channels": ["market.BTC-USD.candle.1m", "market.BTC-USD.quote"]})
            canonical = await communicator.receive_json_from()
            self.assertEqual(canonical["added"], ["market.BTC-USD.candle.1m", "market.BTC-USD.quote"])
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

    def test_v2_route_and_event_envelope_contract(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/v2/?ws_ticket={self.ticket()}")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            await communicator.send_json_to({"action": "subscribe", "channels": ["demo.order"]})
            await communicator.receive_json_from()
            await communicator.send_input({"type": "send_price_update", "message": {"state": "OPEN"}})
            event = await communicator.receive_json_from()
            for key in ("event_id", "event_type", "schema_version", "sequence", "server_timestamp", "payload"):
                self.assertIn(key, event)
            self.assertEqual(event["event_type"], "demo.order.updated.v1")
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_realtime_provider_gate_denies_before_outbound_connection(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/v1/?ws_ticket={self.ticket()}")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            await communicator.send_json_to({"action": "subscribe", "channels": ["market.BTC-USD.candle.1m"]})
            self.assertEqual((await communicator.receive_json_from())["added"], ["market.BTC-USD.candle.1m"])
            unavailable = await communicator.receive_json_from(timeout=2)
            self.assertEqual(unavailable["data"]["reason"], "PROVIDER_NOT_AVAILABLE")
            await communicator.disconnect()

        with patch("ws.gateway.aiohttp.ClientSession.ws_connect") as outbound:
            async_to_sync(scenario)()
            outbound.assert_not_called()
