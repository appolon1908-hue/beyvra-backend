from decimal import Decimal
from django.utils import timezone
from apps.trading.models import ExecutionProviderCapability, ExecutionProviderRecord, ExecutionVenue, VenueCapability

CAPABILITY_SOURCES = {"OFFICIAL_PROVIDER_DOC", "PAPER_ACCOUNT_PROBE", "MANUAL_APPROVAL", "FIX_SESSION_PROFILE"}


class BrokerCapabilityAuthority:
    def list(self, mode=None):
        rows = ExecutionProviderRecord.objects.all().order_by("priority", "provider_id")
        return rows.filter(mode=mode) if mode else rows

    def supports(self, provider, *, asset_class, capability, venue=None, at=None):
        at = at or timezone.now()
        return ExecutionProviderCapability.objects.filter(provider=provider, asset_class=asset_class,
            capability_type=capability, enabled=True, verified_at__lte=at, effective_from__lte=at
        ).filter(effective_to__isnull=True).filter(venue=venue if venue else None).exists()


class VenueCapabilityAuthority:
    def validate(self, venue, *, asset_class, order_type, time_in_force, quantity, price=None, at=None):
        at = at or timezone.now()
        if not venue.routing_enabled or venue.status != "ACTIVE": return ["VENUE_NOT_ROUTABLE"]
        cap = VenueCapability.objects.filter(venue=venue, asset_class=asset_class, order_type=order_type,
            time_in_force=time_in_force, effective_from__lte=at, effective_to__isnull=True).first()
        if not cap: return ["VENUE_CAPABILITY_UNSUPPORTED"]
        quantity = Decimal(str(quantity)); reasons = []
        if quantity < cap.minimum_quantity or quantity % cap.quantity_increment: reasons.append("INVALID_QUANTITY_INCREMENT")
        if price is not None and Decimal(str(price)) % cap.price_increment: reasons.append("INVALID_PRICE_INCREMENT")
        return reasons


def seed_fixture_capabilities():
    now = timezone.now()
    venue, _ = ExecutionVenue.objects.get_or_create(venue_id="BEYVRA-SIM", defaults={"display_name":"Beyvra Simulation Venue",
        "venue_type":"INTERNAL", "timezone":"UTC", "status":"ACTIVE", "routing_enabled":True, "paper_supported":True,
        "active":True, "asset_classes":["CRYPTO","EQUITY","ETF"], "order_types":["MARKET","LIMIT","STOP","STOP_LIMIT"],
        "metadata":{"simulation":True,"external":False}})
    providers = []
    for code, name, mode, priority in (("simulation","Beyvra Simulation","SIMULATION",10),("paper-a","Deterministic Paper A","PAPER",20),("paper-b","Deterministic Paper B","PAPER",30)):
        provider, _ = ExecutionProviderRecord.objects.get_or_create(provider_id=code, defaults={"display_name":name,
            "provider_type":"SIMULATION" if mode=="SIMULATION" else "BROKER_API", "environment":mode, "priority":priority,
            "governance_state":"PAPER_APPROVED", "paper_supported":True, "live_supported":False, "fix_supported":False,
            "api_supported":mode=="PAPER", "mode":mode, "enabled":True, "health":"HEALTHY",
            "supported_asset_classes":["CRYPTO","EQUITY","ETF"], "supported_order_types":["MARKET","LIMIT","STOP","STOP_LIMIT"],
            "supported_venues":[venue.venue_id], "capabilities":{"network":False,"fixture":True,"submit":True,"cancel":True,"replace":True,"partial_fills":True}})
        providers.append(provider)
        for asset in ("CRYPTO","EQUITY","ETF"):
            for capability in ("MARKET_ORDER","LIMIT_ORDER","STOP_ORDER","STOP_LIMIT_ORDER","CANCEL","REPLACE","DAY","GTC","PARTIAL_FILL","PAPER_TRADING"):
                ExecutionProviderCapability.objects.get_or_create(provider=provider, asset_class=asset, venue=venue,
                    capability_type=capability, source_version="fixture-v1", defaults={"enabled":True,"source":"MANUAL_APPROVAL",
                    "effective_from":now,"verified_at":now,"metadata_safe":{"fixture":True}})
            for order_type in ("MARKET","LIMIT","STOP","STOP_LIMIT"):
                VenueCapability.objects.get_or_create(venue=venue, asset_class=asset, order_type=order_type, time_in_force="DAY",
                    source_version="fixture-v1", defaults={"session_type":"REGULAR","minimum_quantity":Decimal("0.0001"),
                    "quantity_increment":Decimal("0.0001"),"price_increment":Decimal("0.01"),"effective_from":now})
    return providers, venue
