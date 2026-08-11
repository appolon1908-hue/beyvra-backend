import json
from asgiref.sync import sync_to_async

from .service import resolve_provider


async def publish_governed_event(*, jetstream, provider_id, product, symbol, region, subject, envelope):
    """Publish only after authoritative governance resolution.

    Credential contents are neither loaded nor included in the event envelope.
    """
    await sync_to_async(resolve_provider, thread_sensitive=True)(
        provider_id=provider_id,
        provider_type="MARKET_DATA",
        product=product,
        symbol=symbol,
        region=region,
    )
    if not subject.startswith("market."):
        raise ValueError("invalid governed market subject")
    await jetstream.publish(subject, json.dumps(envelope, separators=(",", ":")).encode())
