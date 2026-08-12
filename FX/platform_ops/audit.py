import uuid
from django.utils import timezone
from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import enqueue_event


def record(*, request, action, resource_type, resource_id, reason_code, context=None):
    correlation = uuid.uuid4()
    event = ApplicationAuditEvent.objects.create(
        actor_ref=str(request.user.pk), action=action, resource_type=resource_type,
        resource_id=str(resource_id), request_id=request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128],
        correlation_id=correlation, context={"reason_code": reason_code, **(context or {})},
        reason=reason_code[:255], occurred_at=timezone.now(),
    )
    enqueue_event(aggregate_type=resource_type, aggregate_id=resource_id, event_type=f"platform.{action}.v1", payload={"resource_type": resource_type, "resource_id": str(resource_id), "reason_code": reason_code}, tenant_ref="platform", correlation_id=correlation)
    return event


def record_operator_action(*, actor, action, object_ref, reason_code, context=None):
    """Audit non-request service actions without weakening the event contract."""
    class Request:
        user = actor
        headers = {}
    return record(request=Request(), action=action, resource_type="platform_control", resource_id=object_ref, reason_code=reason_code, context=context)
