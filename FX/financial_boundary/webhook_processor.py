from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import json
import uuid
from typing import Callable

from django.db import transaction
from django.utils import timezone

from financial_boundary.eventing import (
    EventContractError,
    FinancialEventEnvelope,
    consume_financial_event,
)
from financial_boundary.models import ProviderWebhookInbox

WebhookHandler = Callable[[FinancialEventEnvelope], None]


@dataclass(frozen=True)
class WebhookProcessingResult:
    claimed: int = 0
    processed: int = 0
    duplicates: int = 0
    retried: int = 0
    dead_lettered: int = 0


def release_expired_webhook_leases() -> int:
    now = timezone.now()
    return ProviderWebhookInbox.objects.filter(
        status=ProviderWebhookInbox.Status.PROCESSING,
        lease_expires_at__lte=now,
    ).update(
        status=ProviderWebhookInbox.Status.PENDING,
        lease_owner="",
        lease_expires_at=None,
    )


def claim_webhook_batch(*, limit: int = 100, lease_seconds: int = 30, lease_owner=""):
    if not 1 <= limit <= 500 or not 1 <= lease_seconds <= 300:
        raise ValueError("webhook claim bounds exceeded")
    owner = str(lease_owner or uuid.uuid4())[:128]
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            ProviderWebhookInbox.objects.select_for_update(skip_locked=True)
            .filter(status=ProviderWebhookInbox.Status.PENDING, next_attempt_at__lte=now)
            .order_by("received_at")[:limit]
        )
        for row in rows:
            row.status = ProviderWebhookInbox.Status.PROCESSING
            row.attempts += 1
            row.lease_owner = owner
            row.lease_expires_at = now + timedelta(seconds=lease_seconds)
            row.save(update_fields=["status", "attempts", "lease_owner", "lease_expires_at"])
    return rows


def _envelope_from_inbox(row: ProviderWebhookInbox) -> FinancialEventEnvelope:
    if not row.encrypted_payload:
        raise EventContractError("webhook payload is unavailable")
    raw_body = bytes(row.encrypted_payload)
    if hashlib.sha256(raw_body).hexdigest() != row.payload_hash:
        raise EventContractError("webhook payload hash mismatch")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError) as exc:
        raise EventContractError("webhook payload is invalid") from exc
    event_type = payload.pop("event_type", None)
    if not isinstance(event_type, str):
        raise EventContractError("webhook event_type is invalid")
    event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra-provider:{row.provider}:{row.external_event_id}")
    return FinancialEventEnvelope(
        event_id=event_id,
        event_type=event_type,
        schema_version=1,
        occurred_at=row.signature_timestamp,
        correlation_id=uuid.uuid5(uuid.NAMESPACE_URL, f"beyvra-correlation:{row.provider}:{row.external_event_id}"),
        causation_id=None,
        tenant_ref=row.tenant_id,
        payload=payload,
    )


def _mark_processed(row: ProviderWebhookInbox):
    ProviderWebhookInbox.objects.filter(
        pk=row.pk,
        status=ProviderWebhookInbox.Status.PROCESSING,
    ).update(
        status=ProviderWebhookInbox.Status.PROCESSED,
        lease_owner="",
        lease_expires_at=None,
        processed_at=timezone.now(),
        failure_code="",
    )


def _mark_retry(row: ProviderWebhookInbox, failure_code: str):
    delay_seconds = min(300, 2 ** min(row.attempts, 8))
    ProviderWebhookInbox.objects.filter(
        pk=row.pk,
        status=ProviderWebhookInbox.Status.PROCESSING,
    ).update(
        status=ProviderWebhookInbox.Status.PENDING,
        lease_owner="",
        lease_expires_at=None,
        next_attempt_at=timezone.now() + timedelta(seconds=delay_seconds),
        failure_code=failure_code[:64],
    )


def _mark_dead_letter(row: ProviderWebhookInbox, failure_code: str):
    ProviderWebhookInbox.objects.filter(pk=row.pk).update(
        status=ProviderWebhookInbox.Status.DEAD_LETTER,
        lease_owner="",
        lease_expires_at=None,
        next_attempt_at=None,
        failure_code=failure_code[:64],
    )


def process_webhook_batch(
    *,
    limit: int = 100,
    lease_seconds: int = 30,
    max_attempts: int = 5,
    lease_owner="",
    handler: WebhookHandler | None = None,
) -> WebhookProcessingResult:
    release_expired_webhook_leases()
    rows = claim_webhook_batch(limit=limit, lease_seconds=lease_seconds, lease_owner=lease_owner)
    processed = duplicates = retried = dead_lettered = 0
    effect = handler or (lambda envelope: None)
    for row in rows:
        try:
            envelope = _envelope_from_inbox(row)
            first_effect = consume_financial_event(envelope, effect)
            _mark_processed(row)
            if first_effect:
                processed += 1
            else:
                duplicates += 1
        except Exception as exc:
            code = type(exc).__name__.upper()[:64]
            if row.attempts >= max_attempts or isinstance(exc, EventContractError):
                _mark_dead_letter(row, code)
                dead_lettered += 1
            else:
                _mark_retry(row, code)
                retried += 1
    return WebhookProcessingResult(
        claimed=len(rows),
        processed=processed,
        duplicates=duplicates,
        retried=retried,
        dead_lettered=dead_lettered,
    )
