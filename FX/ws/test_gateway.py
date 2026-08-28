import uuid
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from FX.asgi import application
from news_app.models import EconomicCalendarEvent, NewsArticle
from ws.gateway import _fetch_news_channel_events


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
            await communicator.send_json_to({"action": "subscribe", "channels": ["news.market", "news.BTC-USD", "news.economic"]})
            self.assertEqual((await communicator.receive_json_from())["added"], ["news.market", "news.BTC-USD", "news.economic"])
            await communicator.disconnect()

        with patch("ws.gateway.CanonicalGatewayConsumer._stream_market", new=AsyncMock()), patch("ws.gateway.CanonicalGatewayConsumer._stream_news", new=AsyncMock()):
            async_to_sync(scenario)()

    def test_news_channels_are_validated_and_backed_by_database_rows(self):
        now = timezone.now()
        NewsArticle.objects.create(
            article_id="news-btc-1",
            provider_id="approved-news",
            provider_article_id="provider-news-btc-1",
            headline="BTC market headline",
            published_at=now,
            affected_instruments=["BTC-USD"],
        )
        NewsArticle.objects.create(
            article_id="news-eth-1",
            provider_id="approved-news",
            provider_article_id="provider-news-eth-1",
            headline="ETH market headline",
            published_at=now,
            affected_instruments=["ETH-USD"],
        )
        EconomicCalendarEvent.objects.create(
            event_id="econ-1",
            provider_id="approved-calendar",
            provider_event_id="provider-econ-1",
            title="Rate decision",
            scheduled_at=now,
            affected_instruments=["EUR-USD"],
        )

        symbol_events = async_to_sync(_fetch_news_channel_events)("news.BTC-USD", set())
        market_events = async_to_sync(_fetch_news_channel_events)("news.market", set())
        economic_events = async_to_sync(_fetch_news_channel_events)("news.economic", set())

        self.assertEqual([event["id"] for event in symbol_events], ["news-btc-1"])
        self.assertEqual({event["id"] for event in market_events}, {"news-btc-1", "news-eth-1"})
        self.assertEqual(economic_events[0]["event_type"], "news.economic.updated.v1")
        self.assertEqual(economic_events[0]["data"]["event_id"], "econ-1")

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

    def test_browser_clients_cannot_publish_trusted_market_or_news_events(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, f"/ws/v2/?ws_ticket={self.ticket()}")
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from()
            for action, channel in (("publish", "market.BTC-USD.quote"), ("send_news", "news.market")):
                await communicator.send_json_to({"action": action, "channel": channel, "payload": {"headline": "fake"}})
                event = await communicator.receive_json_from()
                self.assertEqual(event["status"], 403)
                self.assertEqual(event["code"], "FORBIDDEN_PUBLISH")
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
