"""Persistence boundary for already-governed canonical market events."""
from django.db import transaction

from .market_authority import Candle, MarketStatus, Quote, TradeTick
from .models import CanonicalMarketStatus, CanonicalQuote, CanonicalTradeTick


def _provenance(value):
    return {"provider_id":value.provider_id,"provider_message_type":value.provider_message_type,"provider_timestamp":value.provider_timestamp.isoformat(),"received_at":value.received_at.isoformat(),"normalizer_version":value.normalizer_version,"source_type":value.source_type,"raw_message_hash":value.raw_message_hash}


@transaction.atomic
def persist_event(event):
    """Idempotently persist a normalized event; raw provider payloads are excluded."""
    if isinstance(event, Quote):
        return CanonicalQuote.objects.get_or_create(provider_id=event.provider_id,instrument_id=event.instrument_id,provider_timestamp=event.provider_timestamp,sequence=event.sequence or "",defaults={"bid":event.bid,"ask":event.ask,"bid_size":event.bid_size,"ask_size":event.ask_size,"last":event.last,"received_at":event.received_at,"delayed":event.delayed,"suspect":event.suspect,"provenance":_provenance(event.provenance)})
    if isinstance(event, TradeTick):
        identity=event.trade_id or event.sequence or event.provenance.raw_message_hash
        if not identity: raise ValueError("stable trade identity required")
        return CanonicalTradeTick.objects.get_or_create(provider_id=event.provider_id,instrument_id=event.instrument_id,trade_id=identity,defaults={"price":event.price,"size":event.size,"provider_timestamp":event.provider_timestamp,"received_at":event.received_at,"venue":event.venue,"sequence":event.sequence or "","conditions":list(event.conditions),"provenance":_provenance(event.provenance)})
    if isinstance(event, MarketStatus):
        return CanonicalMarketStatus.objects.create(instrument_id=event.instrument_id,status=event.status.value,halt_status_available=event.halt_status_available,provider_timestamp=event.provider_timestamp,received_at=event.received_at,provider_id=event.provider_id,provenance=_provenance(event.provenance)), True
    if isinstance(event, Candle): raise ValueError("candle persistence uses the historical/backfill store")
    raise TypeError("unsupported canonical event")
