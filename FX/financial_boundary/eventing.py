"""Durable, disabled-by-default application financial event mechanics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import hashlib
import json
import re
import uuid
from typing import Callable

from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from .models import DeadLetterEvent, FinancialAuditEvent, FinancialOutboxEvent, ProcessedEvent


EVENT_TYPE_RE = re.compile(r"^financial\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\.v[1-9][0-9]*$")
DENIED_PAYLOAD_KEYS = {
    "password", "secret", "token", "private_key", "seed", "mnemonic",
    "authorization", "client_key", "bank_account_number", "raw_provider_response",
}
AUDIT_ACTIONS = {
    "reservation.requested", "reservation.released", "settlement.requested",
    "deposit_intent.requested", "withdrawal.requested", "withdrawal.cancelled",
    "transfer.requested", "provider_operation.denied", "compliance_gate.denied",
    "security_gate.denied",
    "financial_halt.requested", "financial_halt.approved",
}


class EventContractError(ValueError):
    pass


class EventReplayConflict(EventContractError):
    pass


def canonical_payload(payload: dict) -> tuple[dict, str]:
    if not isinstance(payload, dict):
        raise EventContractError("payload must be an object")

    def inspect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in DENIED_PAYLOAD_KEYS:
                    raise EventContractError("payload contains prohibited secret material")
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    inspect(payload)
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as exc:
        raise EventContractError("payload must be canonical JSON") from exc
    return json.loads(encoded), hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FinancialEventEnvelope:
    event_id: uuid.UUID
    event_type: str
    schema_version: int
    occurred_at: object
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None
    tenant_ref: uuid.UUID
    payload: dict

    def __post_init__(self):
        for field in ("event_id", "correlation_id", "tenant_ref"):
            object.__setattr__(self, field, uuid.UUID(str(getattr(self, field))))
        if self.causation_id is not None:
            object.__setattr__(self, "causation_id", uuid.UUID(str(self.causation_id)))
        if not EVENT_TYPE_RE.fullmatch(self.event_type):
            raise EventContractError("event_type is not a versioned financial event")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool) or self.schema_version < 1:
            raise EventContractError("schema_version must be a positive integer")
        if not self.event_type.endswith(f".v{self.schema_version}"):
            raise EventContractError("event_type version and schema_version disagree")
        if not isinstance(self.occurred_at, datetime) or not timezone.is_aware(self.occurred_at):
            raise EventContractError("occurred_at must be an aware datetime")
        payload, _ = canonical_payload(self.payload)
        object.__setattr__(self, "payload", payload)

    @property
    def payload_hash(self):
        return canonical_payload(self.payload)[1]


def enqueue_financial_event(envelope: FinancialEventEnvelope) -> FinancialOutboxEvent:
    if not connection.in_atomic_block:
        raise RuntimeError("financial outbox writes require transaction.atomic")
    return FinancialOutboxEvent.objects.create(
        **asdict(envelope), payload_hash=envelope.payload_hash,
        next_attempt_at=timezone.now(),
    )


def consume_financial_event(envelope: FinancialEventEnvelope, handler: Callable[[FinancialEventEnvelope], None]) -> bool:
    """Return True for the first committed effect and False for an exact duplicate."""
    try:
        with transaction.atomic():
            ProcessedEvent.objects.create(
                event_id=envelope.event_id, event_type=envelope.event_type,
                tenant_ref=envelope.tenant_ref, payload_hash=envelope.payload_hash,
            )
            handler(envelope)
        return True
    except IntegrityError:
        existing = ProcessedEvent.objects.filter(event_id=envelope.event_id).first()
        if existing is None:
            raise
        if (
            existing.event_type != envelope.event_type
            or existing.tenant_ref != envelope.tenant_ref
            or existing.payload_hash != envelope.payload_hash
        ):
            raise EventReplayConflict("event_id was replayed with different tenant, type, or payload")
        return False


def record_dead_letter(envelope: FinancialEventEnvelope, failure_type: str, safe_error_reference: str):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,63}", failure_type):
        raise EventContractError("failure_type must be a safe bounded code")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", safe_error_reference):
        raise EventContractError("safe_error_reference is invalid")
    dead, created = DeadLetterEvent.objects.get_or_create(
        event_id=envelope.event_id,
        defaults={"failure_type": failure_type, "retry_count": 1, "safe_error_reference": safe_error_reference},
    )
    if not created:
        DeadLetterEvent.objects.filter(pk=dead.pk).update(
            retry_count=F("retry_count") + 1, failure_type=failure_type,
            safe_error_reference=safe_error_reference, last_failed_at=timezone.now(),
        )
        dead.refresh_from_db()
    return dead


def claim_outbox_batch(*, limit: int = 100, lease_seconds: int = 30):
    if not 1 <= limit <= 500 or not 1 <= lease_seconds <= 300:
        raise ValueError("outbox claim bounds exceeded")
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            FinancialOutboxEvent.objects.select_for_update(skip_locked=True)
            .filter(status=FinancialOutboxEvent.Status.PENDING, next_attempt_at__lte=now)
            .order_by("created_at")[:limit]
        )
        for row in rows:
            row.status = FinancialOutboxEvent.Status.IN_FLIGHT
            row.attempts += 1
            row.lease_expires_at = now + timedelta(seconds=lease_seconds)
            row.save(update_fields=["status", "attempts", "lease_expires_at"])
    return rows


def release_expired_claims() -> int:
    now = timezone.now()
    return FinancialOutboxEvent.objects.filter(
        status=FinancialOutboxEvent.Status.IN_FLIGHT, lease_expires_at__lte=now,
    ).update(status=FinancialOutboxEvent.Status.PENDING, lease_expires_at=None)


def mark_outbox_published(event_id: uuid.UUID):
    now = timezone.now()
    updated = FinancialOutboxEvent.objects.filter(
        event_id=event_id, status=FinancialOutboxEvent.Status.IN_FLIGHT,
    ).update(status=FinancialOutboxEvent.Status.PUBLISHED, published_at=now, lease_expires_at=None)
    if updated != 1:
        raise EventContractError("outbox event is not held by a publisher")


def append_financial_audit(*, action: str, tenant_ref, correlation_id, payload: dict,
                           account_ref=None, actor_ref=None, subject_ref=""):
    if action not in AUDIT_ACTIONS:
        raise EventContractError("unsupported financial audit action")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{0,128}", subject_ref):
        raise EventContractError("audit subject reference must be opaque and non-PII")
    safe_payload, payload_hash = canonical_payload(payload)
    return FinancialAuditEvent.objects.create(
        action=action, tenant_ref=tenant_ref, account_ref=account_ref,
        actor_ref=actor_ref, correlation_id=correlation_id, subject_ref=subject_ref,
        payload_hash=payload_hash, safe_metadata=safe_payload,
    )
