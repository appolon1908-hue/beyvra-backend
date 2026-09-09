import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import IdempotencyConflict, begin_idempotent_request, complete_idempotent_request
from integrations.permissions import organization_for_request

COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = COMMAND_PARAMETERS + [
    OpenApiParameter("If-Match", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
]


def command_context(request, *, require_version=False):
    key = request.headers.get("Idempotency-Key", "").strip()
    request_id = request.headers.get("X-Request-ID", "").strip()
    expected_version = request.headers.get("If-Match", "").strip()
    if not key or len(key) > 255 or not request_id or len(request_id) > 128:
        return None, Response({"detail": "Idempotency-Key and X-Request-ID are required"}, status=400)
    if require_version and not expected_version:
        return None, Response({"detail": "If-Match is required"}, status=428)
    try:
        correlation_id = uuid.UUID(request.headers.get("X-Correlation-ID") or request_id)
    except (TypeError, ValueError):
        return None, Response({"detail": "correlation identifier must be a UUID"}, status=400)
    return (key, request_id, correlation_id, expected_version), None


def begin_command(request, *, key, payload):
    organization = organization_for_request(request)
    try:
        record, created = begin_idempotent_request(
            key=key, tenant_ref=organization.pk, actor_ref=request.user.pk,
            endpoint=request.path, method=request.method,
            request_data={"api_version": "v1", **payload},
        )
    except IdempotencyConflict:
        return None, None, Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
    if not created:
        if record.response_status is None or record.response_body is None:
            return None, None, Response({"detail": "command result is not yet available"}, status=409)
        return None, None, Response(record.response_body, status=record.response_status)
    return organization, record, None


def complete_command(record, *, request, organization, correlation_id, action, status, body, resource_id):
    body = json.loads(json.dumps(body, cls=DjangoJSONEncoder))
    ApplicationAuditEvent.objects.create(
        actor_ref=str(request.user.pk), action=action, resource_type="bank_account",
        resource_id=str(resource_id), request_id=request.headers["X-Request-ID"][:128],
        correlation_id=correlation_id, context={"tenant_ref": str(organization.pk)},
        reason="beneficiary command", occurred_at=timezone.now(),
    )
    complete_idempotent_request(record, status=status, body=body, resource_type="bank_account", resource_id=resource_id)
    return body
