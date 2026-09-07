"""Durable compatibility security commands; rejected commands never commit."""
import json
import uuid
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import (
    IdempotencyConflict,
    begin_idempotent_request,
    complete_idempotent_request,
)
from integrations.permissions import organization_for_request

COMMAND_PARAMETERS = [
    OpenApiParameter("Idempotency-Key", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Request-ID", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=True),
    OpenApiParameter("X-Correlation-ID", OpenApiTypes.UUID, OpenApiParameter.HEADER, required=False),
]
VERSIONED_COMMAND_PARAMETERS = COMMAND_PARAMETERS + [
    OpenApiParameter("If-Match", OpenApiTypes.STR, OpenApiParameter.HEADER, required=True),
]


def _version(target):
    return "NONE" if target is None else target.updated_at.isoformat().replace("+00:00", "Z")


def _locked_target(view, request):
    if hasattr(view, "get_command_object"):
        # A missing singleton has no row to lock. Serialize its initial creation
        # on its persistent owner, across different keys and tenant selections.
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        target = view.get_command_object()
    else:
        target = view.get_object()
        if target is None:
            # Missing/out-of-tenant users are not creatable policy singletons.
            raise NotFound("Resource not found.")
    if target is not None:
        target = target.__class__._default_manager.select_for_update().get(pk=target.pk)
    return target


def durable_security_command(action, *, versioned=False):
    """Keep authorization, version checks, mutation, replay and audit atomic."""
    def decorate(handler):
        @wraps(handler)
        @transaction.atomic
        def wrapped(view, request, *args, **kwargs):
            key = request.headers.get("Idempotency-Key", "").strip()
            request_id = request.headers.get("X-Request-ID", "").strip()
            if not key or len(key) > 255 or not request_id or len(request_id) > 128:
                return Response({"detail": "Idempotency-Key and X-Request-ID are required"}, status=400)
            try:
                uuid.UUID(request_id)
                correlation_id = uuid.UUID(request.headers.get("X-Correlation-ID") or request_id)
            except (TypeError, ValueError):
                return Response({"detail": "request and correlation identifiers must be UUIDs"}, status=400)
            organization = organization_for_request(request)
            expected_version = request.headers.get("If-Match", "").strip()
            if versioned and not expected_version:
                return Response({"detail": "If-Match is required"}, status=428)
            payload = {
                "api_version": "legacy-v1", "route": kwargs,
                "body": request.data, "expected_version": expected_version,
            }
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
                # Do not turn permission, validation, or database errors into a
                # missing row. Exceptions must unwind the atomic command.
                target = _locked_target(view, request)
                if expected_version != _version(target):
                    transaction.set_rollback(True)
                    return Response({"detail": "VERSION_CONFLICT"}, status=409)

            response = handler(view, request, *args, **kwargs)
            if response.status_code >= 400:
                # Some legacy serializers mutate during validation. Roll back
                # the entire command, not just its idempotency record.
                transaction.set_rollback(True)
                return response
            body = json.loads(json.dumps(getattr(response, "data", {}), cls=DjangoJSONEncoder))
            if versioned and isinstance(body, dict) and response.status_code != 204:
                version_target = target
                if version_target is None:
                    version_target = view.get_command_object()
                if version_target is None:
                    raise RuntimeError("Successful security command has no versioned resource")
                version_target.refresh_from_db()
                body["version"] = _version(version_target)
            resource_id = str(kwargs.get("user_id") or kwargs.get("pk") or request.user.pk)
            ApplicationAuditEvent.objects.create(
                actor_ref=str(request.user.pk), action=action, resource_type="security_control",
                resource_id=resource_id, request_id=request_id, correlation_id=correlation_id,
                context={"tenant_ref": str(organization.pk)}, reason="security command",
                occurred_at=timezone.now(),
            )
            complete_idempotent_request(
                record, status=response.status_code, body=body,
                resource_type="security_control", resource_id=resource_id,
            )
            response.data = body
            return response
        parameters = VERSIONED_COMMAND_PARAMETERS if versioned else COMMAND_PARAMETERS
        return extend_schema(parameters=parameters)(wrapped)
    return decorate
