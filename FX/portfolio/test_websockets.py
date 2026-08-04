import asyncio
import json
from unittest.mock import AsyncMock, patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase

from FX.asgi import application
from portfolio.consumers import LiveMarketDataConsumer
from portfolio.models import Asset, AssetBalance, AssetProfitLoss, AssetType
from integrations.models import Organization, OrganizationMembership


class DashboardWebSocketTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="dashboard-ws@example.com",
            password="test-pass",
            phone_number="+12025550161",
        )
        self.organization = Organization.objects.create(name="WebSocket test tenant")
        OrganizationMembership.objects.create(user=self.user, organization=self.organization, role="member")

    def ticket(self, value):
        cache.set(value, self.user.id, 120)
        return value

    def test_live_market_price_requires_authentication(self):
        async def scenario():
            communicator = WebsocketCommunicator(application, "/ws/market-data/")
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()

    def test_live_market_price_is_normalized(self):
        async def fake_relay(consumer):
            await consumer.send(
                text_data=json.dumps(
                    {
                        "type": "candle",
                        "symbol": "BTCUSDT",
                        "interval": "1m",
                        "closed": False,
                        "time": 1700000000,
                        "open": 100.0,
                        "high": 110.0,
                        "low": 90.0,
                        "close": 105.0,
                        "volume": 12.5,
                    }
                )
            )
            await asyncio.Event().wait()

        async def scenario():
            path = f"/ws/market-data/?ws_ticket={self.ticket('market-ticket')}&symbol=BTCUSDT&interval=1m"
            with patch.object(LiveMarketDataConsumer, "relay_market_data", fake_relay):
                communicator = WebsocketCommunicator(application, path)
                connected, close_code = await communicator.connect()
                self.assertTrue(connected, f"websocket rejected with close code {close_code}")
                self.assertEqual((await communicator.receive_json_from())["status"], "connecting")
                candle = await communicator.receive_json_from()
                self.assertEqual(candle["type"], "candle")
                self.assertEqual(candle["close"], 105.0)
                await communicator.disconnect()

        async_to_sync(scenario)()

    def test_live_market_provider_reconnects_after_failure(self):
        async def scenario():
            consumer = LiveMarketDataConsumer()
            consumer.symbol = "BTCUSDT"
            consumer.interval = "1m"
            consumer.send = AsyncMock()
            consumer.stream_once = AsyncMock(
                side_effect=[RuntimeError("provider offline"), asyncio.CancelledError()]
            )
            with patch("portfolio.consumers.asyncio.sleep", new=AsyncMock()) as sleep:
                with self.assertRaises(asyncio.CancelledError):
                    await consumer.relay_market_data()
            sleep.assert_awaited_once_with(1)
            self.assertEqual(consumer.stream_once.await_count, 2)
            disconnected = json.loads(consumer.send.await_args_list[0].kwargs["text_data"])
            self.assertEqual(disconnected["status"], "disconnected")

        async_to_sync(scenario)()

    def test_balance_update_is_user_scoped(self):
        asset_type = AssetType.objects.create(name="Crypto")
        asset = Asset.objects.create(
            user=self.user,
            name="Bitcoin",
            number_of_shares=1,
            initial_price=100,
            current_price=125,
            asset_type=asset_type,
        )
        AssetBalance.objects.create(asset=asset, current_balance=125)
        AssetProfitLoss.objects.create(asset=asset, profit_loss=25)

        async def scenario():
            path = f"/ws/current-balance/{self.user.id}/?ws_ticket={self.ticket('balance-ticket')}"
            communicator = WebsocketCommunicator(application, path)
            connected, close_code = await communicator.connect()
            self.assertTrue(connected, f"websocket rejected with close code {close_code}")
            message = await communicator.receive_json_from()
            self.assertEqual(message["current_balance"], 125)
            await communicator.disconnect()

        async_to_sync(scenario)()

    def test_trade_update_reaches_only_authenticated_user_group(self):
        async def scenario():
            path = f"/ws/trades/?ws_ticket={self.ticket('trade-ticket')}"
            communicator = WebsocketCommunicator(application, path)
            connected, close_code = await communicator.connect()
            self.assertTrue(connected, f"websocket rejected with close code {close_code}")
            await asyncio.sleep(0.05)
            await get_channel_layer().group_send(
                f"trades_updates_{self.organization.id}_{self.user.id}",
                {"type": "send_price_update", "message": {"trade_id": 42}},
            )
            message = await communicator.receive_json_from()
            self.assertEqual(message["data"]["trade_id"], 42)
            await communicator.disconnect()

        async_to_sync(scenario)()
