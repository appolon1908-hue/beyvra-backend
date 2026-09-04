import json
import uuid
from functools import wraps

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema

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


def durable_security_command(action, *, versioned=False):
    """Make a legacy-compatible security mutation durable and auditable."""
    def decorate(handler):
        @wraps(handler)
        @transaction.atomic
        def wrapped(view, request, *args, **kwargs):
            key = request.headers.get("Idempotency-Key", "").strip()
            request_id = request.headers.get("X-Request-ID", "").strip()
            if not key or len(key) > 255 or not request_id or len(request_id) > 128:
                return Response({"detail": "Idempotency-Key and X-Request-ID are required"}, status=400)
            try:
                correlation_id = uuid.UUID(request.headers.get("X-Correlation-ID") or request_id)
            except (TypeError, ValueError):
                return Response({"detail": "correlation identifier must be a UUID"}, status=400)
            organization = organization_for_request(request)
            expected_version = request.headers.get("If-Match", "").strip()
            if versioned and not expected_version:
                return Response({"detail": "If-Match is required"}, status=428)
            payload = {"api_version": "legacy-v1", "route": kwargs, "body": request.data, "expected_version": expected_version}
            try:
                record, created = begin_idempotent_request(
                    key=key, tenant_ref=organization.pk, actor_ref=request.user.pk,
                    endpoint=request.path, method=request.method, request_data=payload,
                )
            except IdempotencyConflict:
                return Response({"detail": "IDEMPOTENCY_CONFLICT"}, status=409)
            if not created:
                if record.response_status is None:
                    return Response({"detail": "command result is not yet available"}, status=409)
                return Response(record.response_body, status=record.response_status)
            target = None
            if versioned:
                try:
                    target = view.get_command_object() if hasattr(view, "get_command_object") else view.get_object()
                except Exception:
                    target = None
                if target is not None:
                    target = target.__class__._default_manager.select_for_update().get(pk=target.pk)
                current_version = "NONE" if target is None else target.updated_at.isoformat().replace("+00:00", "Z")
                if target is not None and expected_version != current_version:
                    record.delete()
                    return Response({"detail": "VERSION_CONFLICT"}, status=409)
            response = handler(view, request, *args, **kwargs)
            if response.status_code >= 400:
                record.delete()
                return response
            body = json.loads(json.dumps(getattr(response, "data", {}), cls=DjangoJSONEncoder))
            if versioned and isinstance(body, dict) and response.status_code != 204:
                try:
                    version_target = target or (view.get_command_object() if hasattr(view, "get_command_object") else view.get_object())
                    version_target.refresh_from_db()
                    body["version"] = version_target.updated_at.isoformat().replace("+00:00", "Z")
                except Exception:
                    pass
            resource_id = str(kwargs.get("user_id") or kwargs.get("pk") or request.user.pk)
            ApplicationAuditEvent.objects.create(
                actor_ref=str(request.user.pk), action=action, resource_type="security_control",
                resource_id=resource_id, request_id=request_id, correlation_id=correlation_id,
                context={"tenant_ref": str(organization.pk)}, reason="security command", occurred_at=timezone.now(),
            )
            complete_idempotent_request(
                record, status=response.status_code, body=body,
                resource_type="security_control", resource_id=resource_id,
            )
            response.data = body
            return response
        return extend_schema(parameters=VERSIONED_COMMAND_PARAMETERS if versioned else COMMAND_PARAMETERS)(wrapped)
    return decorate
