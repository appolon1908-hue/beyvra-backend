"""Append-only, maker/checker financial halt authority; no activation path."""

from __future__ import annotations

import hashlib
import re
import uuid

from django.db import connection, transaction

from .eventing import append_financial_audit
from .models import FinancialHaltApproval, FinancialHaltRequest


FINANCIAL_VIEWER = "financial_viewer"
FINANCIAL_OPERATIONS = "financial_operations"
FINANCIAL_MANAGER = "financial_manager"

_MUTATIONS = frozenset({"DEPOSIT", "WITHDRAWAL", "TRANSFER", "RESERVATION", "SETTLEMENT"})
_ALLOWED = {
    FinancialHaltRequest.State.ACTIVE: _MUTATIONS,
    FinancialHaltRequest.State.WITHDRAWALS_HALTED: _MUTATIONS - {"WITHDRAWAL"},
    FinancialHaltRequest.State.FUNDING_HALTED: _MUTATIONS - {"DEPOSIT"},
    FinancialHaltRequest.State.READ_ONLY: frozenset(),
    FinancialHaltRequest.State.ALL_MUTATIONS_HALTED: frozenset(),
}


class HaltDenied(PermissionError):
    code = "FINANCIAL_OPERATION_HALTED"


class HaltAuthorizationDenied(PermissionError):
    code = "FINANCIAL_ROLE_REQUIRED"


class HaltTransitionDenied(ValueError):
    code = "INVALID_HALT_TRANSITION"


def _roles(value) -> frozenset[str]:
    if not isinstance(value, (set, frozenset, tuple, list)):
        raise HaltAuthorizationDenied("financial role required")
    return frozenset(str(role) for role in value)


def _actor_uuid(actor_id: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra-financial-actor:{actor_id}")


def _validate_actor(actor_id: int):
    if not isinstance(actor_id, int) or isinstance(actor_id, bool) or actor_id < 1:
        raise HaltAuthorizationDenied("financial actor required")


def current_halt_state(tenant_ref) -> str:
    tenant = uuid.UUID(str(tenant_ref))
    approval = (
        FinancialHaltApproval.objects.select_related("request")
        .filter(request__tenant_ref=tenant)
        .order_by("-approved_at", "-approval_id")
        .first()
    )
    return approval.request.proposed_state if approval else FinancialHaltRequest.State.ACTIVE


def assert_financial_operation_allowed(*, tenant_ref, operation: str):
    if operation not in _MUTATIONS:
        raise ValueError("unknown financial operation")
    state = current_halt_state(tenant_ref)
    if operation not in _ALLOWED[state]:
        raise HaltDenied("financial operation halted")
    return state


@transaction.atomic
def request_financial_halt(*, tenant_ref, proposed_state: str, requested_by: int,
                           roles, reason_code: str, correlation_id) -> FinancialHaltRequest:
    _validate_actor(requested_by)
    if not _roles(roles).intersection({FINANCIAL_OPERATIONS, FINANCIAL_MANAGER}):
        raise HaltAuthorizationDenied("financial operations role required")
    if proposed_state not in _ALLOWED or proposed_state == FinancialHaltRequest.State.ACTIVE:
        raise HaltTransitionDenied("halt request must reduce capability")
    if not isinstance(reason_code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", reason_code):
        raise HaltTransitionDenied("invalid safe reason code")
    tenant = uuid.UUID(str(tenant_ref))
    correlation = uuid.UUID(str(correlation_id))
    request = FinancialHaltRequest.objects.create(
        tenant_ref=tenant, proposed_state=proposed_state, requested_by=requested_by,
        reason_code=reason_code, policy_version="financial-halt-v1",
        correlation_id=correlation,
    )
    append_financial_audit(
        action="financial_halt.requested", tenant_ref=tenant,
        actor_ref=_actor_uuid(requested_by), correlation_id=correlation,
        subject_ref=f"halt.{request.request_id}",
        payload={"proposed_state": proposed_state, "reason_code": reason_code},
    )
    return request


def _advisory_lock(tenant_ref: uuid.UUID):
    key = int.from_bytes(hashlib.sha256(tenant_ref.bytes).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [key])


@transaction.atomic
def approve_financial_halt(*, request_id, approved_by: int, roles,
                           correlation_id) -> FinancialHaltApproval:
    _validate_actor(approved_by)
    if FINANCIAL_MANAGER not in _roles(roles):
        raise HaltAuthorizationDenied("financial manager role required")
    request = FinancialHaltRequest.objects.select_for_update().get(request_id=request_id)
    if request.requested_by == approved_by:
        raise HaltAuthorizationDenied("maker cannot approve own halt request")
    existing = FinancialHaltApproval.objects.filter(request=request).first()
    if existing:
        return existing
    _advisory_lock(request.tenant_ref)
    current = current_halt_state(request.tenant_ref)
    proposed_allowed = _ALLOWED[request.proposed_state]
    current_allowed = _ALLOWED[current]
    if proposed_allowed == current_allowed or not proposed_allowed.issubset(current_allowed):
        raise HaltTransitionDenied("halt transition does not reduce capability")
    correlation = uuid.UUID(str(correlation_id))
    approval = FinancialHaltApproval.objects.create(
        request=request, approved_by=approved_by, correlation_id=correlation,
    )
    append_financial_audit(
        action="financial_halt.approved", tenant_ref=request.tenant_ref,
        actor_ref=_actor_uuid(approved_by), correlation_id=correlation,
        subject_ref=f"halt.{request.request_id}",
        payload={"state": request.proposed_state, "reason_code": request.reason_code},
    )
    return approval
