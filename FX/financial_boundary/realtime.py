"""Tenant-safe financial projection sequencing and deterministic gap recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import uuid
from typing import Callable

from django.db import transaction
from django.utils import timezone

from .eventing import EventContractError, canonical_payload
from .models import FinancialProjectionCursor


FINANCIAL_REALTIME_TOPICS = {
    "wallet.updated.v1": "/api/v1/wallets/",
    "deposit.updated.v1": "/api/v1/deposits/",
    "withdrawal.updated.v1": "/api/v1/withdrawals/",
    "transfer.updated.v1": "/api/v1/transfers/",
}


class FinancialSequenceConflict(EventContractError):
    pass


@dataclass(frozen=True)
class FinancialProjectionEvent:
    event_id: uuid.UUID
    event_type: str
    tenant_ref: uuid.UUID
    subject_ref: str
    sequence: int
    occurred_at: datetime
    payload: dict

    def __post_init__(self):
        object.__setattr__(self, "event_id", uuid.UUID(str(self.event_id)))
        object.__setattr__(self, "tenant_ref", uuid.UUID(str(self.tenant_ref)))
        if self.event_type not in FINANCIAL_REALTIME_TOPICS:
            raise EventContractError("unsupported financial realtime event")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise EventContractError("financial sequence must be a positive integer")
        if not isinstance(self.occurred_at, datetime) or not timezone.is_aware(self.occurred_at):
            raise EventContractError("occurred_at must be an aware datetime")
        if not self.subject_ref or len(self.subject_ref) > 64 or not self.subject_ref.isdecimal():
            raise EventContractError("subject_ref must be a server-derived user identifier")
        payload, _ = canonical_payload(self.payload)
        if "user_id" in payload or "tenant_ref" in payload:
            raise EventContractError("financial event identity cannot be supplied in payload")
        object.__setattr__(self, "payload", payload)


@dataclass(frozen=True)
class ProjectionResult:
    status: str
    last_sequence: int
    expected_sequence: int
    snapshot_endpoint: str | None = None


def private_financial_channel(event_type: str, subject_ref) -> str:
    if event_type not in FINANCIAL_REALTIME_TOPICS:
        raise EventContractError("unsupported financial realtime event")
    subject = str(subject_ref)
    if not subject.isdecimal():
        raise EventContractError("subject_ref must be server-derived")
    return f"{event_type}:{subject}"


def apply_projection_event(
    event: FinancialProjectionEvent,
    reducer: Callable[[dict, dict], dict],
) -> ProjectionResult:
    with transaction.atomic():
        cursor, _ = FinancialProjectionCursor.objects.select_for_update().get_or_create(
            tenant_ref=event.tenant_ref,
            subject_ref=event.subject_ref,
            event_type=event.event_type,
        )
        expected = cursor.last_sequence + 1
        if event.sequence == cursor.last_sequence:
            if cursor.last_event_id == event.event_id:
                return ProjectionResult("DUPLICATE", cursor.last_sequence, expected)
            raise FinancialSequenceConflict("same sequence was reused by a different event")
        if event.sequence < expected:
            return ProjectionResult("STALE", cursor.last_sequence, expected)
        if event.sequence > expected:
            return ProjectionResult(
                "GAP_RECOVERY_REQUIRED", cursor.last_sequence, expected,
                FINANCIAL_REALTIME_TOPICS[event.event_type],
            )
        projection, projection_hash = canonical_payload(reducer(dict(cursor.projection), event.payload))
        cursor.projection = projection
        cursor.projection_hash = projection_hash
        cursor.last_sequence = event.sequence
        cursor.last_event_id = event.event_id
        cursor.save(update_fields=[
            "projection", "projection_hash", "last_sequence", "last_event_id", "updated_at",
        ])
        return ProjectionResult("APPLIED", cursor.last_sequence, cursor.last_sequence + 1)


def replace_projection_from_snapshot(
    *, tenant_ref, subject_ref, event_type: str, snapshot: dict,
) -> ProjectionResult:
    if event_type not in FINANCIAL_REALTIME_TOPICS:
        raise EventContractError("unsupported financial realtime event")
    tenant = uuid.UUID(str(tenant_ref))
    subject = str(subject_ref)
    if str(snapshot.get("tenant_ref")) != str(tenant) or str(snapshot.get("subject_ref")) != subject:
        raise EventContractError("snapshot authority does not match authenticated scope")
    sequence = snapshot.get("sequence")
    version = snapshot.get("version")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
        raise EventContractError("snapshot sequence is invalid")
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise EventContractError("snapshot version is invalid")
    projection, projection_hash = canonical_payload(snapshot.get("projection"))
    with transaction.atomic():
        cursor, _ = FinancialProjectionCursor.objects.select_for_update().get_or_create(
            tenant_ref=tenant, subject_ref=subject, event_type=event_type,
        )
        if sequence < cursor.last_sequence or version < cursor.snapshot_version:
            raise FinancialSequenceConflict("snapshot would move projection backwards")
        cursor.last_sequence = sequence
        cursor.last_event_id = None
        cursor.snapshot_version = version
        cursor.projection = projection
        cursor.projection_hash = projection_hash
        cursor.save(update_fields=[
            "last_sequence", "last_event_id", "snapshot_version", "projection",
            "projection_hash", "updated_at",
        ])
    return ProjectionResult("SNAPSHOT_REPLACED", sequence, sequence + 1)
