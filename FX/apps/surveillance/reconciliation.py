from apps.foundation.models import ApplicationAuditEvent, OutboxEvent, ProcessedEvent
from apps.trading.models import SimulatedTrade, TradingOrder

from .models import SurveillanceAudit, SurveillanceCase, SurveillanceEvent, TradingRestriction


def reconcile_surveillance():
    violations = []
    active = TradingRestriction.objects.filter(status="ACTIVE")
    for restriction in active:
        orders = TradingOrder.objects.filter(tenant_ref=restriction.tenant_ref, created_at__gte=restriction.effective_from).exclude(state="REJECTED")
        if restriction.scope_type == "ACCOUNT": orders = orders.filter(account_ref=restriction.scope_ref)
        if restriction.scope_type == "INSTRUMENT": orders = orders.filter(instrument_id=restriction.scope_ref)
        if restriction.restriction_type in {"BLOCK_NEW_ORDERS", "BLOCK_INSTRUMENT"}:
            for order in orders:
                violations.append({"check": "RESTRICTED_ORDER_ACCEPTED", "resource_ref": str(order.id)})
        if not SurveillanceAudit.objects.filter(resource_type="trading_restriction", resource_ref=str(restriction.id)).exists():
            violations.append({"check": "RESTRICTION_AUDIT_GAP", "resource_ref": str(restriction.id)})
    critical = SurveillanceEvent.objects.filter(severity="CRITICAL")
    for event in critical:
        if not event.cases.exists(): violations.append({"check": "CRITICAL_EVENT_WITHOUT_CASE", "resource_ref": str(event.id)})
        if not SurveillanceAudit.objects.filter(resource_type="surveillance_event", resource_ref=str(event.id)).exists(): violations.append({"check": "EVENT_AUDIT_GAP", "resource_ref": str(event.id)})
    for case in SurveillanceCase.objects.all():
        if not case.events.exists(): violations.append({"check": "CASE_WITHOUT_EVENTS", "resource_ref": str(case.id)})
    event_ids = {str(v) for v in SurveillanceEvent.objects.values_list("id", flat=True)}
    outbox_ids = set(OutboxEvent.objects.filter(aggregate_type="surveillance_event").values_list("aggregate_id", flat=True))
    for missing in event_ids - outbox_ids: violations.append({"check": "OUTBOX_GAP", "resource_ref": missing})
    return {"status": "PASS" if not violations else "FAIL", "violations": violations, "checks": 7}
