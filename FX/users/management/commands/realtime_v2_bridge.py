"""Bridge normalized JetStream events to the private Centrifugo publish API.

This process has no business authority: it only forwards validated envelopes.
Orders, balances and settlements remain owned by PostgreSQL services.
"""

import asyncio
import json
import os
import urllib.request

from django.core.management.base import BaseCommand


async def _bridge_stream(js, stream, subject, api_url, api_key):
    durable = f"codestra-v2-{stream.lower()}"
    try:
        await js.add_consumer(stream, durable_name=durable, filter_subject=subject, ack_policy="explicit")
    except Exception:
        pass
    sub = await js.pull_subscribe(subject, durable=durable, stream=stream)
    while True:
        try:
            messages = await sub.fetch(10, timeout=1)
        except TimeoutError:
            continue
        for msg in messages:
            try:
                envelope = json.loads(msg.data)
                channel = envelope.get("channel")
                if not isinstance(channel, str) or envelope.get("type") != "event":
                    await msg.ack()
                    continue
                body = json.dumps({"channel": channel, "data": envelope}).encode()
                request = urllib.request.Request(
                    api_url, data=body, method="POST",
                    headers={"Content-Type": "application/json", "X-API-Key": api_key},
                )
                await asyncio.to_thread(urllib.request.urlopen, request, timeout=2)
                await msg.ack()
            except Exception:
                continue


async def _run():
    from nats.aio.client import Client as NATS

    nc = NATS()
    await nc.connect(os.getenv("NATS_URL", "nats://nats:4222"))
    js = nc.jetstream()
    api_url = os.getenv("CENTRIFUGO_PUBLISH_URL", "http://centrifugo:8000/api/publish")
    api_key = os.getenv("CENTRIFUGO_API_KEY", "")
    streams = (
        ("MARKET_TICKS", "market.tick.*"), ("MARKET_QUOTES", "market.quote.*"),
        ("MARKET_CANDLES", "market.candle.*.*"), ("MARKET_ORDERBOOK", "market.orderbook.*"),
        ("MARKET_TRADES", "market.trade.*"), ("NEWS_EVENTS", "news.>"),
        ("PRIVATE_ACCOUNT_EVENTS", "private.>"), ("SYSTEM_EVENTS", "system.>"),
    )
    await asyncio.gather(*(_bridge_stream(js, stream, subject, api_url, api_key) for stream, subject in streams))


class Command(BaseCommand):
    help = "Forward validated V2 JetStream envelopes to Centrifugo."

    def handle(self, *args, **options):
        if os.getenv("NATS_JETSTREAM_ENABLED", "false").lower() != "true":
            self.stdout.write("V2 bridge disabled")
            return
        asyncio.run(_run())
