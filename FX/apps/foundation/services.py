import random
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .events import payload_hash
from .models import IdempotencyRecord, OutboxEvent, ProcessedEvent


class IdempotencyConflict(Exception):
    pass


def enqueue_event(*, aggregate_type, aggregate_id, event_type, payload, tenant_ref, correlation_id=None, causation_id=None, occurred_at=None):
    return OutboxEvent.objects.create(
        aggregate_type=aggregate_type, aggregate_id=str(aggregate_id), event_type=event_type,
        payload=payload, tenant_ref=str(tenant_ref), correlation_id=correlation_id or uuid.uuid4(),
        causation_id=causation_id, occurred_at=occurred_at or timezone.now(),
    )


def claim_outbox_batch(*, limit=100, lease_seconds=30):
    now = timezone.now()
    expired_claim = now - timedelta(seconds=lease_seconds)
    with transaction.atomic():
        eligible = Q(state=OutboxEvent.State.PENDING, next_attempt_at__isnull=True) | Q(state=OutboxEvent.State.PENDING, next_attempt_at__lte=now) | Q(state=OutboxEvent.State.CLAIMED, claimed_at__lte=expired_claim)
        rows = list(OutboxEvent.objects.select_for_update(skip_locked=True).filter(eligible).order_by("id")[:limit])
        for row in rows:
            row.state = OutboxEvent.State.CLAIMED
            row.claimed_at = now
            row.save(update_fields=("state", "claimed_at"))
    return rows


def mark_publish_result(event, *, error_code="", maximum_attempts=10):
    with transaction.atomic():
        row = OutboxEvent.objects.select_for_update().get(pk=event.pk)
        row.attempt_count += 1
        if not error_code:
            row.state = OutboxEvent.State.PUBLISHED
            row.published_at = timezone.now()
            row.last_error = ""
        elif row.attempt_count >= maximum_attempts:
            row.state = OutboxEvent.State.DEAD_LETTER
            row.last_error = error_code[:128]
        else:
            row.state = OutboxEvent.State.PENDING
            delay = min(300, 2 ** min(row.attempt_count, 8)) + random.random()
            row.next_attempt_at = timezone.now() + timedelta(seconds=delay)
            row.last_error = error_code[:128]
        row.save()
    return row


def consume_once(*, envelope, consumer_name, mutation):
    event_id = uuid.UUID(str(envelope["event_id"]))
    digest = payload_hash(envelope.get("payload", {}))
    try:
        with transaction.atomic():
            existing = ProcessedEvent.objects.select_for_update().filter(event_id=event_id, consumer_name=consumer_name).first()
            if existing:
                if existing.payload_hash != digest:
                    raise ValueError("EVENT_PAYLOAD_CONFLICT")
                return False
            mutation()
            ProcessedEvent.objects.create(event_id=event_id, consumer_name=consumer_name, payload_hash=digest)
            return True
    except IntegrityError:
        # A concurrent consumer won the unique (event_id, consumer_name) insert.
        # The losing transaction, including its mutation, has been rolled back.
        existing = ProcessedEvent.objects.get(event_id=event_id, consumer_name=consumer_name)
        if existing.payload_hash != digest:
            raise ValueError("EVENT_PAYLOAD_CONFLICT")
        return False


def canonical_request_hash(data):
    return payload_hash(data)


def begin_idempotent_request(*, key, tenant_ref, actor_ref, endpoint, method, request_data, ttl=timedelta(hours=24)):
    digest = canonical_request_hash(request_data)
    scope = dict(key=key, tenant_ref=str(tenant_ref), actor_ref=str(actor_ref), endpoint=endpoint, method=method.upper())
    with transaction.atomic():
        try:
            with transaction.atomic():
                record = IdempotencyRecord.objects.create(**scope, request_hash=digest, expires_at=timezone.now() + ttl)
            return record, True
        except IntegrityError:
            record = IdempotencyRecord.objects.select_for_update().get(**scope)
            if record.request_hash != digest:
                raise IdempotencyConflict("IDEMPOTENCY_CONFLICT")
            return record, False


def complete_idempotent_request(record, *, status, body, resource_type="", resource_id=""):
    record.response_status = status
    record.response_body = body
    record.resource_type = resource_type
    record.resource_id = str(resource_id)
    record.save(update_fields=("response_status", "response_body", "resource_type", "resource_id"))
