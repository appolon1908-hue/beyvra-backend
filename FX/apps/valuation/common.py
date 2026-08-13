import hashlib
import json

from django.utils import timezone

from .models import ValuationAudit

POLICY_VERSION = "SIMULATION_VALUATION_V1"
LOT_POLICY = "SIMULATION_FIFO_V1"


def audit(*, tenant_ref, action, resource, evidence, actor_ref="system"):
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    return ValuationAudit.objects.create(tenant_ref=tenant_ref, actor_ref=actor_ref, action=action, resource_type=resource.__class__.__name__, resource_ref=str(resource.pk), evidence_hash=digest, occurred_at=timezone.now())

