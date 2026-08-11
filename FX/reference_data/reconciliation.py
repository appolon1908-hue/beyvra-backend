from django.db.models import F, Q

from .models import Instrument, MarketDataObservation, ProviderSymbolMapping, ReferenceDataAudit


def run_reference_data_reconciliation():
    violations = []
    for mapping in ProviderSymbolMapping.objects.all().order_by("provider_id", "provider_symbol", "effective_from"):
        overlaps = ProviderSymbolMapping.objects.filter(
            provider_id=mapping.provider_id,
            product=mapping.product,
            provider_symbol=mapping.provider_symbol,
            effective_from__lt=mapping.effective_to or "9999-12-31T00:00:00Z",
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gt=mapping.effective_from)).exclude(pk=mapping.pk)
        if overlaps.exists():
            violations.append({"check": "PROVIDER_MAPPING_OVERLAP", "entity_ref": str(mapping.pk)})
    for instrument in Instrument.objects.all():
        current = instrument.versions.filter(effective_to__isnull=True).count()
        if current != 1:
            violations.append({"check": "CURRENT_INSTRUMENT_VERSION_COUNT", "entity_ref": str(instrument.instrument_id), "observed": current})
    for observation in MarketDataObservation.objects.exclude(mapping__instrument_id=F("instrument_id")):
        violations.append({"check": "MAPPING_INSTRUMENT_MISMATCH", "entity_ref": str(observation.observation_id)})
    for observation in MarketDataObservation.objects.filter(payload_hash=""):
        violations.append({"check": "MISSING_PAYLOAD_HASH", "entity_ref": str(observation.observation_id)})
    observation_refs = set(MarketDataObservation.objects.values_list("observation_id", flat=True))
    audited_refs = set(ReferenceDataAudit.objects.filter(entity_type="MARKET_DATA_OBSERVATION").values_list("entity_ref", flat=True))
    for observation_id in observation_refs:
        if str(observation_id) not in audited_refs:
            violations.append({"check": "MISSING_AUDIT", "entity_ref": str(observation_id)})
    return {"status": "PASS" if not violations else "FAIL", "checks": 5, "violations": violations}
