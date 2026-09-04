from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from rest_framework.response import Response

from apps.foundation.models import ApplicationAuditEvent
from apps.foundation.services import (
    IdempotencyConflict,
    begin_idempotent_request,
    canonical_request_hash,
    complete_idempotent_request,
)


@dataclass(frozen=True)
class WorkspaceCommand:
    key: str
    request_id: str
    correlation_id: uuid.UUID
    expected_version: int | None


def error_body(code: str, **extra):
    return {"error": {"code": code, **extra}}


def parse_command(request, *, require_version: bool):
    key = str(request.headers.get("Idempotency-Key", "")).strip()
    request_id = str(request.headers.get("X-Request-ID", "")).strip()
    if not key or len(key) > 255 or not request_id or len(request_id) > 128:
        return None, Response(error_body("COMMAND_HEADERS_REQUIRED"), status=400)

    raw_version = request.data.get("version") if hasattr(request, "data") else None
    if raw_version in (None, ""):
        raw_version = request.query_params.get("version")
    expected_version = None
    if raw_version not in (None, ""):
        try:
            expected_version = int(raw_version)
        except (TypeError, ValueError):
            return None, Response(error_body("VERSION_INVALID"), status=400)
        if expected_version < 1:
            return None, Response(error_body("VERSION_INVALID"), status=400)
    if require_version and expected_version is None:
        return None, Response(error_body("VERSION_REQUIRED"), status=428)

    raw_correlation = str(
        request.headers.get("X-Correlation-ID") or request_id
    ).strip()
    try:
        correlation_id = uuid.UUID(raw_correlation)
    except (TypeError, ValueError):
        correlation_id = uuid.uuid5(uuid.NAMESPACE_URL, raw_correlation)

    return (
        WorkspaceCommand(
            key=key,
            request_id=request_id,
            correlation_id=correlation_id,
            expected_version=expected_version,
        ),
        None,
    )


def begin_command(
    request,
    *,
    organization,
    command: WorkspaceCommand,
    operation: str,
    resource_ref: str,
    payload: dict,
):
    semantic_request = {
        "api_version": "v1",
        "operation": operation,
        "resource_ref": str(resource_ref),
        "expected_version": command.expected_version,
        "payload": payload,
    }
    try:
        record, created = begin_idempotent_request(
            key=command.key,
            tenant_ref=organization.pk,
            actor_ref=request.user.pk,
            endpoint=request.path,
            method=request.method,
            request_data=semantic_request,
        )
    except IdempotencyConflict:
        return None, Response(error_body("IDEMPOTENCY_CONFLICT"), status=409)

    if created:
        return record, None
    if record.response_status is None:
        return None, Response(error_body("COMMAND_IN_PROGRESS"), status=409)
    body = record.response_body
    return None, Response(
        None if record.response_status == 204 else body,
        status=record.response_status,
    )


def complete_response(
    record,
    *,
    request,
    organization,
    command: WorkspaceCommand,
    status_code: int,
    body,
    resource_type: str,
    resource_id,
    action: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
):
    serializable_body = json.loads(
        json.dumps({} if body is None else body, cls=DjangoJSONEncoder)
    )
    if action:
        ApplicationAuditEvent.objects.create(
            actor_ref=str(request.user.pk),
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            before_hash=(
                canonical_request_hash(before) if before is not None else ""
            ),
            after_hash=canonical_request_hash(after) if after is not None else "",
            request_id=command.request_id,
            correlation_id=command.correlation_id,
            context={"tenant_ref": str(organization.pk)},
            reason="workspace command",
            occurred_at=timezone.now(),
        )
    complete_idempotent_request(
        record,
        status=status_code,
        body=serializable_body,
        resource_type=resource_type,
        resource_id=resource_id,
    )


def version_error(current_version: int):
    return Response(
        error_body("VERSION_CONFLICT", current_version=current_version),
        status=409,
    )
