"""Bridge normalized JetStream events to the private Centrifugo publish API.

This process has no business authority: it only forwards validated envelopes.
Orders, balances and settlements remain owned by PostgreSQL services.
"""

import asyncio
import json
import os
import ssl
import urllib.request
import logging

from django.core.management.base import BaseCommand


logger = logging.getLogger(__name__)


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
                if stream == "TRADING_EVENTS":
                    event_type = str(envelope.get("event_type", ""))
                    payload = envelope.get("payload", {})
                    account_ref = payload.get("account_ref") if isinstance(payload, dict) else None
                    if isinstance(account_ref, str) and account_ref.startswith("sim:"):
                        category = "execution" if event_type.startswith(("trading.execution.", "trading.trade.")) or "filled" in event_type else "position" if event_type.startswith("trading.position.") or "balance_projection" in event_type else "order"
                        channel = f"simulation.{category}.{account_ref}"
                        envelope = {
                            **envelope,
                            "type": event_type,
                            "event_version": envelope.get("schema_version", 1),
                            "channel": channel,
                            "sequence": msg.metadata.sequence.stream,
                            "data": payload,
                        }
                if not isinstance(channel, str) or envelope.get("type") != "event":
                    if stream != "TRADING_EVENTS":
                        await msg.ack()
                        continue
                body = json.dumps({"channel": channel, "data": envelope}).encode()
                request = urllib.request.Request(
                    api_url, data=body, method="POST",
                    headers={"Content-Type": "application/json", "X-API-Key": api_key},
                )
                response = await asyncio.to_thread(urllib.request.urlopen, request, timeout=2)
                result = json.loads(response.read())
                if result.get("error"):
                    raise RuntimeError(f"CENTRIFUGO_PUBLISH_{result['error'].get('code', 'FAILED')}")
                await msg.ack()
            except Exception as exc:
                logger.error("realtime bridge publish failed: %s", type(exc).__name__)
                continue


async def _run():
    from nats.aio.client import Client as NATS

    nc = NATS()
    tls_context = None
    ca_file = os.getenv("NATS_TLS_CA_FILE")
    if ca_file:
        tls_context = ssl.create_default_context(cafile=ca_file)
        cert_file = os.getenv("NATS_TLS_CERT_FILE")
        key_file = os.getenv("NATS_TLS_KEY_FILE")
        if cert_file and key_file:
            tls_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    await nc.connect(os.getenv("NATS_URL", "nats://nats:4222"), tls=tls_context)
    js = nc.jetstream()
    try:
        await js.add_stream(name="TRADING_EVENTS", subjects=["trading.>"])
    except Exception:
        pass
    api_url = os.getenv("CENTRIFUGO_PUBLISH_URL", "http://centrifugo:8000/api/publish")
    api_key = os.getenv("CENTRIFUGO_API_KEY", "")
    streams = (
        ("MARKET_TICKS", "market.tick.*"), ("MARKET_QUOTES", "market.quote.*"),
        ("MARKET_CANDLES", "market.candle.*.*"), ("MARKET_ORDERBOOK", "market.orderbook.*"),
        ("MARKET_TRADES", "market.trade.*"), ("NEWS_EVENTS", "news.>"),
        ("PRIVATE_ACCOUNT_EVENTS", "private.>"), ("SYSTEM_EVENTS", "system.>"),
        ("TRADING_EVENTS", "trading.>"),
    )
    await asyncio.gather(*(_bridge_stream(js, stream, subject, api_url, api_key) for stream, subject in streams))


class Command(BaseCommand):
    help = "Forward validated V2 JetStream envelopes to Centrifugo."

    def handle(self, *args, **options):
        if os.getenv("NATS_JETSTREAM_ENABLED", "false").lower() != "true":
            self.stdout.write("V2 bridge disabled")
            return
        asyncio.run(_run())
