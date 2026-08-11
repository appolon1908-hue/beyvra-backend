"""Canonical multiplexed WebSocket gateway for the trading workspace."""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import parse_qs

import aiohttp
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from integrations.models import OrganizationMembership
from provider_governance.service import ProviderNotAvailable, resolve_provider
from trade.market_data import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS

logger = logging.getLogger(__name__)
CANONICAL_SYMBOLS = {"BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "BNB-USD": "BNBUSDT", "SOL-USD": "SOLUSDT", "XRP-USD": "XRPUSDT"}


@database_sync_to_async
def _tenant_for_user(user_id: int, requested: str | None = None) -> str:
    memberships = OrganizationMembership.objects.filter(user_id=user_id)
    if requested and memberships.filter(organization_id=requested).exists():
        return str(requested)
    membership = memberships.order_by("id").values_list("organization_id", flat=True).first()
    return str(membership) if membership else "default"


@database_sync_to_async
def _market_provider_approved(symbol: str) -> bool:
    try:
        resolve_provider(provider_id="binance", provider_type="MARKET_DATA", product="REALTIME_CANDLES", symbol=symbol, region="GLOBAL")
        return True
    except ProviderNotAvailable:
        return False


class CanonicalGatewayConsumer(AsyncJsonWebsocketConsumer):
    """Multiplex market and demo events over one authenticated connection."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Channels may call disconnect after a rejected handshake.  Keep the
        # teardown path safe even when connect() returned before initializing
        # per-connection state (for example an expired ticket under load).
        self.tenant_id = "default"
        self.subscriptions: set[str] = set()
        self.market_tasks: dict[str, asyncio.Task] = {}
        self.sequence = defaultdict(int)

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        query = parse_qs(self.scope.get("query_string", b"").decode())
        self.tenant_id = await _tenant_for_user(user.id, query.get("organization_id", [None])[0])
        await self.accept()
        await self.send_json({"type": "gateway.ready", "version": 1, "tenant": self.tenant_id})

    async def disconnect(self, close_code):
        for task in self.market_tasks.values():
            task.cancel()
        if self.market_tasks:
            await asyncio.gather(*self.market_tasks.values(), return_exceptions=True)
        user = self.scope.get("user")
        if user and user.is_authenticated:
            await self.channel_layer.group_discard(f"trades_updates_{self.tenant_id}_{user.id}", self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        if action == "ping":
            await self.send_json({"type": "pong"})
            return
        if action == "resume":
            await self.send_json({"type": "resume.ack", "channels": sorted(self.subscriptions)})
            return
        if action == "subscribe":
            channels = content.get("channels", [])
            if not isinstance(channels, list):
                await self.send_json({"type": "error", "code": "INVALID_CHANNELS"})
                return
            added = []
            for channel in channels:
                if not isinstance(channel, str) or not self._valid_channel(channel):
                    await self.send_json({"type": "subscription.error", "channel": channel, "code": "FORBIDDEN_CHANNEL"})
                    continue
                if channel in self.subscriptions:
                    continue
                self.subscriptions.add(channel)
                added.append(channel)
                if channel.startswith("demo."):
                    await self.channel_layer.group_add(f"trades_updates_{self.tenant_id}_{self.scope['user'].id}", self.channel_name)
                # A candle stream also publishes its quote projection. Avoid a
                # second provider socket when both channels are requested.
                if channel.startswith("market.candle:") or (
                    channel.startswith("market.quote:")
                    and f"market.candle:{channel.split(':', 1)[1]}:1m" not in self.subscriptions
                ):
                    if channel.startswith("market.candle:"):
                        symbol = channel.split(":")[1]
                        quote_task = self.market_tasks.pop(f"market.quote:{symbol}", None)
                        if quote_task:
                            quote_task.cancel()
                    self.market_tasks.setdefault(channel, asyncio.create_task(self._stream_market(channel)))
            await self.send_json({"type": "subscription.ack", "added": added, "channels": sorted(self.subscriptions)})
            return
        if action == "unsubscribe":
            channels = content.get("channels", [])
            removed = []
            for channel in channels if isinstance(channels, list) else []:
                if channel not in self.subscriptions:
                    continue
                self.subscriptions.remove(channel)
                removed.append(channel)
                task = self.market_tasks.pop(channel, None)
                if task:
                    task.cancel()
            await self.send_json({"type": "subscription.ack", "removed": removed, "channels": sorted(self.subscriptions)})
            return
        await self.send_json({"type": "error", "code": "UNKNOWN_ACTION"})

    def _valid_channel(self, channel: str) -> bool:
        if channel in {"demo.order", "demo.execution", "demo.position", "notification", "market.status", "market.compat.crypto", "market.compat.stocks"}:
            return True
        parts = channel.split(":")
        if len(parts) == 2 and parts[0] in {"portfolio.balance", "portfolio.profit_loss"}:
            return parts[1] == str(self.scope["user"].id)
        if channel.startswith("compat."):
            return channel in {"compat.market-data", "compat.news", "compat.account", "compat.platform"}
        if len(parts) == 2 and parts[0] == "market.quote":
            return parts[1] in SUPPORTED_SYMBOLS or parts[1] in CANONICAL_SYMBOLS
        if len(parts) == 3 and parts[0] == "market.candle":
            return (parts[1] in SUPPORTED_SYMBOLS or parts[1] in CANONICAL_SYMBOLS) and parts[2] in SUPPORTED_INTERVALS
        return False

    async def _stream_market(self, channel: str):
        parts = channel.split(":")
        instrument_id = parts[1]
        symbol = CANONICAL_SYMBOLS.get(instrument_id, instrument_id)
        interval = parts[2] if len(parts) == 3 else "1m"
        if symbol not in {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}:
            await self._emit("market.status", {"status": "unavailable", "symbol": symbol})
            return
        if not await _market_provider_approved(symbol):
            await self._emit("market.status", {"status": "unavailable", "symbol": instrument_id, "reason": "PROVIDER_NOT_AVAILABLE"})
            return
        url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
        delay = 1
        try:
            while channel in self.subscriptions:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.ws_connect(url, heartbeat=20, receive_timeout=60) as upstream:
                            await self._emit("market.status", {"status": "connected", "symbol": symbol, "interval": interval})
                            delay = 1
                            async for message in upstream:
                                if channel not in self.subscriptions:
                                    return
                                if message.type != aiohttp.WSMsgType.TEXT:
                                    continue
                                payload = json.loads(message.data)
                                candle = payload.get("k")
                                if not candle:
                                    continue
                                data = {"type": "candle", "symbol": instrument_id, "interval": interval, "closed": bool(candle["x"]), "time": int(candle["t"] / 1000), "open": str(candle["o"]), "high": str(candle["h"]), "low": str(candle["l"]), "close": str(candle["c"]), "volume": str(candle["v"])}
                                await self._emit(channel, data)
                                await self._emit(f"market.quote:{instrument_id}", {"bid": data["close"], "ask": data["close"], "mid": data["close"], "time": data["time"]})
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.info("market gateway reconnect: %s", type(exc).__name__)
                    await self._emit("market.status", {"status": "disconnected", "symbol": symbol, "retry_in": delay})
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
        finally:
            self.market_tasks.pop(channel, None)

    async def _emit(self, channel, data):
        if self.sequence[channel] == 0 and isinstance(data, dict) and isinstance(data.get("time"), int):
            self.sequence[channel] = data["time"]
        else:
            self.sequence[channel] += 1
        if channel.startswith("market.quote:"):
            event_type = "market.quote.updated.v1"
        elif channel.startswith("market.candle:"):
            event_type = "market.candle.updated.v1"
        elif channel.startswith("demo.order"):
            event_type = "demo.order.updated.v1"
        elif channel.startswith("demo.execution"):
            event_type = "demo.execution.updated.v1"
        elif channel.startswith("demo.position"):
            event_type = "demo.position.updated.v1"
        elif channel.startswith("notification"):
            event_type = "notification.updated.v1"
        elif channel.startswith("compliance."):
            event_type = channel.rsplit(".", 1)[0] if channel.rsplit(".", 1)[-1].isdigit() else channel
        else:
            event_type = "market.status.changed.v1"
        now = datetime.now(timezone.utc).isoformat()
        instrument_id = channel.split(":")[1] if channel.startswith("market.") and ":" in channel else None
        await self.send_json({"event_id": f"{self.channel_name}:{channel}:{self.sequence[channel]}", "event_type": event_type, "schema_version": 1, "event_version": 1, "type": event_type, "version": 1, "channel": channel, "instrument_id": instrument_id, "sequence": self.sequence[channel], "occurred_at": now, "server_timestamp": now, "server_time": now, "source": "approved-provider", "payload": data, "data": data})

    async def send_price_update(self, event):
        await self._emit("demo.order", event.get("message", {}))
