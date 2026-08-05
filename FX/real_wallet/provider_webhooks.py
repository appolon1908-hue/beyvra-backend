import hashlib
import json

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import ProviderWebhookReceipt


class ProviderWebhookRejected(ValueError):
    pass


@transaction.atomic
def receive_provider_webhook(*, connection, provider_event_id, event_type, payload, signature_verified):
    if not signature_verified:
        raise ProviderWebhookRejected("provider signature verification failed")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    payload_hash = hashlib.sha256(raw).hexdigest()
    try:
        receipt, created = ProviderWebhookReceipt.objects.get_or_create(
            connection=connection, provider_event_id=provider_event_id,
            defaults={
                "event_type": event_type, "payload_hash": payload_hash,
                "raw_payload": payload, "status": "RECEIVED", "received_at": timezone.now(),
            },
        )
    except IntegrityError:
        # A concurrent delivery may win the unique constraint; reconcile it
        # inside a fresh transaction instead of returning a 500.
        receipt = ProviderWebhookReceipt.objects.get(connection=connection, provider_event_id=provider_event_id)
        created = False
    if not created and receipt.payload_hash != payload_hash:
        raise ProviderWebhookRejected("provider event payload does not match the original receipt")
    return receipt, created


@transaction.atomic
def mark_provider_webhook_processed(receipt_id):
    receipt = ProviderWebhookReceipt.objects.select_for_update().get(pk=receipt_id)
    if receipt.status == "PROCESSED":
        return receipt
    if receipt.status not in {"RECEIVED", "RETRY"}:
        raise ProviderWebhookRejected("provider receipt is not processable")
    receipt.status = "PROCESSED"
    receipt.processed_at = timezone.now()
    receipt.last_error = ""
    receipt.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
    return receipt


@transaction.atomic
def mark_provider_webhook_retry(receipt_id, error):
    receipt = ProviderWebhookReceipt.objects.select_for_update().get(pk=receipt_id)
    if receipt.status == "PROCESSED":
        raise ProviderWebhookRejected("processed provider receipt cannot be retried")
    receipt.status = "RETRY"
    receipt.last_error = error[:255]
    receipt.save(update_fields=["status", "last_error", "updated_at"])
    return receipt
