import uuid
import json

from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes

from apps.foundation.services import (
    IdempotencyConflict,
    begin_idempotent_request,
    complete_idempotent_request,
)

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
        return None, Response({"code": "COMMAND_HEADERS_REQUIRED"}, status=400)
    if require_version and not expected_version:
        return None, Response({"code": "PRECONDITION_REQUIRED"}, status=428)
    try:
        correlation_id = uuid.UUID(request.headers.get("X-Correlation-ID") or request_id)
    except (TypeError, ValueError):
        return None, Response({"code": "INVALID_CORRELATION_ID"}, status=400)
    return (key, request_id, correlation_id, expected_version), None


def begin_command(request, *, key, payload):
    try:
        record, created = begin_idempotent_request(
            key=key,
            tenant_ref="platform",
            actor_ref=request.user.pk,
            endpoint=request.path,
            method=request.method,
            request_data={"api_version": "v1", **payload},
        )
    except IdempotencyConflict:
        return None, None, Response({"code": "IDEMPOTENCY_CONFLICT"}, status=409)
    if not created:
        if record.response_status is None or record.response_body is None:
            return None, None, Response({"code": "COMMAND_IN_PROGRESS"}, status=409)
        return None, None, Response(record.response_body, status=record.response_status)
    return record, created, None


def complete_command(record, *, status, body, resource_type, resource_id):
    body = json.loads(json.dumps(body, cls=DjangoJSONEncoder))
    complete_idempotent_request(
        record,
        status=status,
        body=body,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return body
