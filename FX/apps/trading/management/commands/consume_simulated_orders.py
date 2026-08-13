"""Consume canonical simulation order events from JetStream."""

import asyncio
import json
import os
import ssl

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from apps.trading.simulation_consumer import consume_order_created


async def run_consumer():
    from nats.aio.client import Client as NATS

    client = NATS()
    tls_context = None
    if ca_file := os.getenv("NATS_TLS_CA_FILE"):
        tls_context = ssl.create_default_context(cafile=ca_file)
        if cert_file := os.getenv("NATS_TLS_CERT_FILE"):
            tls_context.load_cert_chain(cert_file, os.getenv("NATS_TLS_KEY_FILE"))
    await client.connect(os.getenv("NATS_URL", "nats://nats:4222"), tls=tls_context)
    stream = client.jetstream()
    try:
        await stream.add_stream(name="TRADING_EVENTS", subjects=["trading.>"])
    except Exception:
        pass
    durable = "beyvra-simulated-execution-v1"
    try:
        await stream.add_consumer(
            "TRADING_EVENTS",
            durable_name=durable,
            filter_subject="trading.order.created.v1",
            ack_policy="explicit",
        )
    except Exception:
        pass
    subscription = await stream.pull_subscribe(
        "trading.order.created.v1",
        durable=durable,
        stream="TRADING_EVENTS",
    )
    try:
        while True:
            try:
                messages = await subscription.fetch(20, timeout=1)
            except TimeoutError:
                continue
            for message in messages:
                try:
                    await sync_to_async(consume_order_created, thread_sensitive=True)(json.loads(message.data))
                    await message.ack()
                except Exception:
                    await message.nak()
    finally:
        await client.drain()


class Command(BaseCommand):
    help = "Run the deterministic simulation-only execution consumer."

    def handle(self, *args, **options):
        if not os.getenv("SIMULATED_TRADING_ENABLED", "false").lower() == "true":
            self.stdout.write("Simulation execution consumer disabled")
            return
        asyncio.run(run_consumer())
