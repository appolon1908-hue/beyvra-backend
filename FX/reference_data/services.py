import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import MarketDataObservation, ProviderSymbolMapping, ReferenceDataAudit


def _hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def resolve_provider_symbol(*, provider_id, provider_symbol, product="MARKET_DATA", at=None):
    at = at or timezone.now()
    mappings = ProviderSymbolMapping.objects.filter(
        provider_id=provider_id,
        provider_symbol=provider_symbol,
        product=product,
        effective_from__lte=at,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=at))
    if mappings.count() != 1:
        raise ValidationError("Provider symbol does not resolve to exactly one canonical instrument.")
    return mappings.select_related("instrument").get()


@transaction.atomic
def record_market_observation(*, provider_id, provider_symbol, data_type, provider_event_id, observed_at, payload_safe, received_at=None, supersedes=None):
    mapping = resolve_provider_symbol(provider_id=provider_id, provider_symbol=provider_symbol, at=observed_at)
    observation = MarketDataObservation.objects.create(
        instrument=mapping.instrument,
        provider_id=provider_id,
        provider_symbol=provider_symbol,
        data_type=data_type,
        provider_event_id=provider_event_id,
        observed_at=observed_at,
        received_at=received_at or timezone.now(),
        payload_hash=_hash(payload_safe),
        payload_safe=payload_safe,
        mapping=mapping,
        supersedes=supersedes,
    )
    ReferenceDataAudit.objects.create(
        event_type="MARKET_DATA_OBSERVED" if supersedes is None else "MARKET_DATA_CORRECTED",
        entity_type="MARKET_DATA_OBSERVATION",
        entity_ref=str(observation.observation_id),
        occurred_at=timezone.now(),
        evidence_hash=_hash({"observation": observation.observation_id, "payload_hash": observation.payload_hash}),
        metadata_safe={"provider_id": provider_id, "data_type": data_type, "instrument_id": str(mapping.instrument_id)},
    )
    return observation
