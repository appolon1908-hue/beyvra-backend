import hashlib
import json

from django.utils import timezone

from apps.foundation.services import enqueue_event

from .models import PostTradeAudit


POLICY_VERSION = "post-trade-simulation-2026-08-v1"


def evidence_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def audit(*, tenant_ref, actor_ref, action, resource_type, resource_ref, evidence, reason="simulation"):
    return PostTradeAudit.objects.create(tenant_ref=tenant_ref, actor_ref=actor_ref, action=action, resource_type=resource_type, resource_ref=str(resource_ref), evidence_hash=evidence_hash(evidence), reason=reason, occurred_at=timezone.now())


def publish(*, trade, event_type, payload):
    return enqueue_event(aggregate_type="post_trade", aggregate_id=trade.id, event_type=event_type, payload={"trade_id": str(trade.id), "account_ref": trade.account_ref, "simulation": True, **payload}, tenant_ref=trade.tenant_ref)
