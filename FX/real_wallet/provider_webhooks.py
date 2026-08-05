import hashlib
import json
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from .models import ProviderWebhookReceipt


class ProviderWebhookRejected(ValueError):
    pass


@transaction.atomic
def receive_provider_webhook(*, connection, provider_event_id, event_type, payload, signature_verified):
    if not signature_verified:
        raise ProviderWebhookRejected("provider signature verification failed")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    receipt, created = ProviderWebhookReceipt.objects.get_or_create(
        connection=connection, provider_event_id=provider_event_id,
        defaults={
            "event_type": event_type, "payload_hash": hashlib.sha256(raw).hexdigest(),
            "raw_payload": payload, "status": "RECEIVED", "received_at": timezone.now(),
        },
    )
    return receipt, created


def mark_provider_webhook_processed(receipt_id):
    receipt = ProviderWebhookReceipt.objects.get(pk=receipt_id)
    receipt.status = "PROCESSED"
    receipt.processed_at = timezone.now()
    receipt.last_error = ""
    receipt.save(update_fields=["status", "processed_at", "last_error", "updated_at"])
    return receipt


def mark_provider_webhook_retry(receipt_id, error):
    receipt = ProviderWebhookReceipt.objects.get(pk=receipt_id)
    receipt.status = "RETRY"
    receipt.last_error = error[:255]
    receipt.save(update_fields=["status", "last_error", "updated_at"])
    return receipt
