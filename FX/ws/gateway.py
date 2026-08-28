"""Canonical multiplexed WebSocket gateway for the trading workspace."""

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import parse_qs

import aiohttp
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from prometheus_client import Counter

from integrations.models import OrganizationMembership
from operations.services import notification_group, tenant_for
from provider_governance.service import ProviderNotAvailable, resolve_provider
from trade.market_data import SUPPORTED_INTERVALS, SUPPORTED_SYMBOLS

logger = logging.getLogger(__name__)
CANONICAL_SYMBOLS = {"BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT", "BNB-USD": "BNBUSDT", "SOL-USD": "SOLUSDT", "XRP-USD": "XRPUSDT"}
FORBIDDEN_BROWSER_PUBLISH_ACTIONS = {
    "publish",
    "broadcast",
    "emit",
    "push",
    "send_market",
    "send_news",
    "inject_event",
}
legacy_ws_connections = Counter(
    "legacy_ws_connections_total",
    "Connections to compatibility WebSocket routes",
    ("route", "client_version", "environment"),
)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (TypeError, ValueError, AttributeError):
        return False
    return True


@database_sync_to_async
def _tenant_for_user(user_id: int, requested: str | None = None) -> str:
    memberships = OrganizationMembership.objects.filter(user_id=user_id)
    if requested and memberships.filter(organization_id=requested).exists():
        return str(requested)
    membership = memberships.order_by("id").values_list("organization_id", flat=True).first()
    if membership:
        return str(membership)
    from users.models import User

    user = User.objects.get(pk=user_id)
    return tenant_for(user)


@database_sync_to_async
def _market_provider_approved(symbol: str) -> bool:
    try:
        resolve_provider(provider_id="binance", provider_type="MARKET_DATA", product="REALTIME_CANDLES", symbol=symbol, region="GLOBAL")
        return True
    except ProviderNotAvailable:
        return False


@database_sync_to_async
def _resolve_realtime_instrument(reference: str) -> tuple[str, str] | None:
    """Resolve a public channel reference through the backend instrument master.

    UUID is the canonical realtime identity. Canonical symbols remain accepted
    as a compatibility input, but provider symbols are never returned as the
    event's instrument identity.
    """
    from reference_data.models import Instrument

    try:
        instrument_id = uuid.UUID(reference)
    except (TypeError, ValueError, AttributeError):
        instrument_id = None

    instruments = Instrument.objects.filter(status=Instrument.Status.ACTIVE)
    instrument = (
        instruments.filter(instrument_id=instrument_id).first()
        if instrument_id is not None
        else instruments.filter(canonical_symbol=reference.upper()).first()
    )
    if instrument is None:
        return None
    mapping = (
        instrument.provider_mappings.filter(
            provider_id="binance",
            product="MARKET_DATA",
            effective_to__isnull=True,
        )
        .order_by("effective_from")
        .first()
    )
    if mapping is None:
        return None
    return str(instrument.instrument_id), mapping.provider_symbol


def _serialize_news_article(article):
    return {
        "article_id": article.article_id,
        "news_id": article.article_id,
        "provider_id": article.provider_id,
        "provider_article_id": article.provider_article_id,
        "headline": article.headline,
        "summary": article.summary,
        "content_preview": article.content_preview,
        "source_name": article.publisher,
        "source_id": article.source_id,
        "source_url": article.source_url,
        "article_url": article.canonical_url,
        "image_url": article.image_url,
        "published_at": article.published_at.isoformat(),
        "received_at": article.received_at.isoformat(),
        "language": article.language,
        "countries": article.countries,
        "categories": article.categories,
        "instrument_refs": article.affected_instruments,
        "keywords": article.keywords,
        "sentiment": article.sentiment,
        "provider_timestamp": article.provider_timestamp.isoformat() if article.provider_timestamp else None,
        "delayed": article.delayed,
        "stale": False,
        "provenance": {
            "provider_id": article.provider_id,
            "normalizer_version": article.normalizer_version,
        },
    }


def _serialize_economic_event(event):
    return {
        "event_id": event.event_id,
        "provider_id": event.provider_id,
        "title": event.title,
        "country": event.country,
        "currency": event.currency,
        "importance": event.importance,
        "scheduled_at": event.scheduled_at.isoformat(),
        "actual_at": event.actual_at.isoformat() if event.actual_at else None,
        "previous_value": event.previous_value,
        "forecast_value": event.forecast_value,
        "actual_value": event.actual_value,
        "unit": event.unit,
        "affected_instruments": event.affected_instruments,
        "status": event.status,
    }


@database_sync_to_async
def _fetch_news_channel_events(channel: str, seen_ids: set[str], limit: int = 25):
    from news_app.models import EconomicCalendarEvent, NewsArticle

    if channel == "news.economic":
        rows = EconomicCalendarEvent.objects.order_by("-scheduled_at", "event_id")[:limit]
        return [
            {
                "id": event.event_id,
                "channel": channel,
                "event_type": "news.economic.updated.v1",
                "occurred_at": event.actual_at or event.scheduled_at,
                "data": _serialize_economic_event(event),
            }
            for event in rows
            if event.event_id not in seen_ids
        ]

    articles = NewsArticle.objects.exclude(status=NewsArticle.Status.RETRACTED).order_by("-published_at", "article_id")[: limit * 4]
    symbol = channel.split(".", 1)[1].upper() if channel.startswith("news.") and channel != "news.market" else None
    events = []
    for article in articles:
        if article.article_id in seen_ids:
            continue
        if symbol and symbol not in {str(item).upper() for item in article.affected_instruments}:
            continue
        events.append(
            {
                "id": article.article_id,
                "channel": channel,
                "event_type": "news.article.updated.v1",
                "occurred_at": article.published_at,
                "data": _serialize_news_article(article),
            }
        )
        if len(events) >= limit:
            break
    return events


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
        self.news_tasks: dict[str, asyncio.Task] = {}
        self.sequence = defaultdict(int)

    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        query = parse_qs(self.scope.get("query_string", b"").decode())
        self.tenant_id = await _tenant_for_user(user.id, query.get("organization_id", [None])[0])
        ticket_tenant = (self.scope.get("realtime_ticket") or {}).get("tenant_id")
        if ticket_tenant and ticket_tenant != self.tenant_id:
            await self.close(code=4403)
            return
        route = self.scope.get("path", "")
        legacy = route.startswith("/ws/v1/")
        if legacy:
            headers = dict(self.scope.get("headers", []))
            legacy_ws_connections.labels(
                route="/ws/v1/",
                client_version=headers.get(b"x-client-version", b"unknown").decode(errors="replace")[:64],
                environment=getattr(settings, "ENVIRONMENT", "unknown"),
            ).inc()
        await self.accept()
        self.notification_group = notification_group(self.tenant_id, user.id)
        await self.channel_layer.group_add(self.notification_group, self.channel_name)
        ready = {"type": "gateway.ready", "version": 2, "tenant": self.tenant_id}
        if legacy:
            ready["deprecation"] = True
            ready["successor"] = "/ws/v2/"
        await self.send_json(ready)

    async def disconnect(self, close_code):
        for task in self.market_tasks.values():
            task.cancel()
        for task in self.news_tasks.values():
            task.cancel()
        if self.market_tasks:
            await asyncio.gather(*self.market_tasks.values(), return_exceptions=True)
        if self.news_tasks:
            await asyncio.gather(*self.news_tasks.values(), return_exceptions=True)
        user = self.scope.get("user")
        if user and user.is_authenticated:
            await self.channel_layer.group_discard(f"trades_updates_{self.tenant_id}_{user.id}", self.channel_name)
            await self.channel_layer.group_discard(self.notification_group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("action")
        action_key = action.lower() if isinstance(action, str) else action
        if action_key in FORBIDDEN_BROWSER_PUBLISH_ACTIONS:
            await self.send_json({"type": "error", "code": "FORBIDDEN_PUBLISH", "status": 403})
            return
        if action_key == "ping":
            await self.send_json({"type": "pong"})
            return
        if action_key == "resume":
            await self.send_json({"type": "resume.ack", "channels": sorted(self.subscriptions)})
            return
        if action_key == "subscribe":
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
                if ".candle." in channel or (
                    channel.endswith(".quote")
                    and f"market.{channel.split('.')[1]}.candle.1m" not in self.subscriptions
                ):
                    if ".candle." in channel:
                        symbol = channel.split(".")[1]
                        quote_task = self.market_tasks.pop(f"market.{symbol}.quote", None)
                        if quote_task:
                            quote_task.cancel()
                    self.market_tasks.setdefault(channel, asyncio.create_task(self._stream_market(channel)))
                if channel.startswith("news."):
                    self.news_tasks.setdefault(channel, asyncio.create_task(self._stream_news(channel)))
            await self.send_json({"type": "subscription.ack", "added": added, "channels": sorted(self.subscriptions)})
            return
        if action_key == "unsubscribe":
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
                task = self.news_tasks.pop(channel, None)
                if task:
                    task.cancel()
            await self.send_json({"type": "subscription.ack", "removed": removed, "channels": sorted(self.subscriptions)})
            return
        await self.send_json({"type": "error", "code": "UNKNOWN_ACTION"})

    def _valid_channel(self, channel: str) -> bool:
        if channel in {"demo.order", "demo.execution", "demo.position", "notification", "market.status"}:
            return True
        parts = channel.split(":")
        if len(parts) == 2 and parts[0] in {"portfolio.balance", "portfolio.profit_loss"}:
            return parts[1] == str(self.scope["user"].id)
        dotted = channel.split(".")
        if len(dotted) == 3 and dotted[0] == "market" and dotted[2] == "quote":
            return dotted[1] in SUPPORTED_SYMBOLS or dotted[1] in CANONICAL_SYMBOLS or _is_uuid(dotted[1])
        if len(dotted) == 4 and dotted[0] == "market" and dotted[2] == "candle":
            return (dotted[1] in SUPPORTED_SYMBOLS or dotted[1] in CANONICAL_SYMBOLS or _is_uuid(dotted[1])) and dotted[3] in SUPPORTED_INTERVALS
        if channel in {"news.market", "news.economic"}:
            return True
        if len(dotted) == 2 and dotted[0] == "news":
            return bool(dotted[1]) and len(dotted[1]) <= 64
        return False

    async def _stream_market(self, channel: str):
        parts = channel.split(".")
        requested_reference = parts[1]
        resolved = await _resolve_realtime_instrument(requested_reference)
        if resolved is None:
            # Temporary compatibility for stacks not yet seeded with the
            # reference authority. UUID references never bypass authority.
            if _is_uuid(requested_reference):
                await self._emit("market.status", {"status": "unavailable", "reason": "INSTRUMENT_NOT_FOUND"}, instrument_id=requested_reference)
                return
            instrument_id = requested_reference
            symbol = CANONICAL_SYMBOLS.get(requested_reference, requested_reference)
        else:
            instrument_id, symbol = resolved
        interval = parts[3] if len(parts) == 4 else "1m"
        if symbol not in {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}:
            await self._emit("market.status", {"status": "unavailable"}, instrument_id=instrument_id)
            return
        if not await _market_provider_approved(symbol):
            await self._emit("market.status", {"status": "unavailable", "reason": "PROVIDER_NOT_AVAILABLE"}, instrument_id=instrument_id)
            return
        url = f"wss://stream.binance.com:9443/ws/{symbol.lower()}@kline_{interval}"
        delay = 1
        try:
            while channel in self.subscriptions:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.ws_connect(url, heartbeat=20, receive_timeout=60) as upstream:
                            await self._emit("market.status", {"status": "connected", "interval": interval}, instrument_id=instrument_id)
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
                                await self._emit(channel, data, instrument_id=instrument_id)
                                await self._emit(f"market.{instrument_id}.quote", {"bid": data["close"], "ask": data["close"], "mid": data["close"], "time": data["time"]}, instrument_id=instrument_id)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.info("market gateway reconnect: %s", type(exc).__name__)
                    await self._emit("market.status", {"status": "disconnected", "retry_in": delay}, instrument_id=instrument_id)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 30)
        finally:
            self.market_tasks.pop(channel, None)

    async def _stream_news(self, channel: str):
        seen_ids: set[str] = set()
        poll_seconds = max(5, int(getattr(settings, "NEWS_REALTIME_POLL_SECONDS", 15)))
        try:
            while channel in self.subscriptions:
                events = await _fetch_news_channel_events(channel, seen_ids)
                for event in reversed(events):
                    seen_ids.add(event["id"])
                    await self._emit(
                        event["channel"],
                        event["data"],
                        event_type=event["event_type"],
                        occurred_at=event["occurred_at"],
                    )
                await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            self.news_tasks.pop(channel, None)

    async def _emit(self, channel, data, *, instrument_id=None, event_type=None, occurred_at=None):
        if self.sequence[channel] == 0 and isinstance(data, dict) and isinstance(data.get("time"), int):
            self.sequence[channel] = data["time"]
        else:
            self.sequence[channel] += 1
        if event_type:
            pass
        elif channel == "demo.order":
            event_type = "demo.order.updated.v1"
        elif channel == "demo.execution":
            event_type = "demo.execution.updated.v1"
        elif channel == "demo.position":
            event_type = "demo.position.updated.v1"
        elif channel.startswith("news."):
            event_type = "news.article.updated.v1" if channel != "news.economic" else "news.economic.updated.v1"
        else:
            event_type = "market.quote.updated.v1" if channel.endswith(".quote") else "market.candle.updated.v1" if ".candle." in channel else "market.status.changed.v1"
        now = datetime.now(timezone.utc).isoformat()
        occurred = occurred_at.isoformat() if hasattr(occurred_at, "isoformat") else now
        instrument_id = instrument_id or (channel.split(".")[1] if channel.startswith("market.") and channel.count(".") >= 2 else None)
        await self.send_json({"event_id": f"{self.channel_name}:{channel}:{self.sequence[channel]}", "event_type": event_type, "event_version": 1, "schema_version": 1, "type": event_type, "version": 1, "channel": channel, "instrument_id": instrument_id, "sequence": self.sequence[channel], "occurred_at": occurred, "server_timestamp": now, "server_time": now, "source": "approved-provider", "payload": data, "data": data})

    async def send_price_update(self, event):
        await self._emit("demo.order", event.get("message", {}))

    async def simulation_update(self, event):
        message = event.get("message", {})
        event_type = str(message.get("event_type", "trading.order.updated.v1"))
        channel = "demo.execution" if "trade." in event_type or "filled" in event_type else "demo.position" if "position." in event_type or "balance_projection" in event_type else "demo.order"
        await self._emit(channel, message)

    async def notification_created(self, event):
        await self.send_json(
            {"type": "notification.created", "notification": event["notification"]}
        )
