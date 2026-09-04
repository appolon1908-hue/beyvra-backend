from django.db import transaction
from django.utils import timezone

from .common import audit, evidence_hash, publish
from .models import PostTradeException


class PostTradeExceptionService:
    @classmethod
    def open(cls, *, trade, exception_type, severity="HIGH", evidence=None):
        row, created = PostTradeException.objects.get_or_create(trade=trade, exception_type=exception_type, state__in=("OPEN", "ASSIGNED", "INVESTIGATING", "ESCALATED"), defaults={"tenant_ref": trade.tenant_ref, "account_ref": trade.account_ref, "severity": severity, "detected_at": timezone.now(), "evidence_hash": evidence_hash(evidence or {"trade_id": str(trade.id), "exception_type": exception_type})})
        if created:
            audit(tenant_ref=trade.tenant_ref, actor_ref="system", action="post_trade.exception.opened", resource_type="post_trade_exception", resource_ref=row.id, evidence={"type": exception_type})
            publish(trade=trade, event_type="post_trade.exception.opened.v1", payload={"exception_id": str(row.id), "severity": severity})
        return row

    @staticmethod
    @transaction.atomic
    def assign(row, *, actor_ref, reason=""):
        row = PostTradeException.objects.select_for_update().get(pk=row.pk)
        if row.state not in ("OPEN", "ESCALATED"): raise ValueError("INVALID_EXCEPTION_TRANSITION")
        row.assigned_to = actor_ref; row.state = "ASSIGNED"
        if row.severity == "CRITICAL" and not row.requested_by: row.requested_by = actor_ref
        row.save(update_fields=("assigned_to", "state", "requested_by", "updated_at"))
        audit(tenant_ref=row.tenant_ref, actor_ref=actor_ref, action="post_trade.exception.assigned", resource_type="post_trade_exception", resource_ref=row.id, evidence={"state": row.state}, reason=reason)
        return row

    @staticmethod
    @transaction.atomic
    def escalate(row, *, actor_ref, reason=""):
        row = PostTradeException.objects.select_for_update().get(pk=row.pk)
        if row.state not in ("OPEN", "ASSIGNED", "INVESTIGATING"): raise ValueError("INVALID_EXCEPTION_TRANSITION")
        row.state = "ESCALATED"; row.save(update_fields=("state", "updated_at"))
        audit(tenant_ref=row.tenant_ref, actor_ref=actor_ref, action="post_trade.exception.escalated", resource_type="post_trade_exception", resource_ref=row.id, evidence={"state": row.state}, reason=reason)
        return row

    @staticmethod
    @transaction.atomic
    def resolve(row, *, actor_ref, resolution_code, reason=""):
        row = PostTradeException.objects.select_for_update().get(pk=row.pk)
        if row.state == "RESOLVED": raise ValueError("INVALID_EXCEPTION_TRANSITION")
        if row.severity == "CRITICAL" and (not row.requested_by or row.requested_by == actor_ref):
            raise ValueError("SELF_APPROVAL_FORBIDDEN")
        row.state = "RESOLVED"; row.resolved_at = timezone.now(); row.resolution_code = resolution_code; row.approved_by = actor_ref
        row.save(update_fields=("state", "resolved_at", "resolution_code", "approved_by", "updated_at"))
        audit(tenant_ref=row.tenant_ref, actor_ref=actor_ref, action="post_trade.exception.resolved", resource_type="post_trade_exception", resource_ref=row.id, evidence={"resolution_code": resolution_code}, reason=reason)
        if row.trade: publish(trade=row.trade, event_type="post_trade.exception.resolved.v1", payload={"exception_id": str(row.id)})
        return row
