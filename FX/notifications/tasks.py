import hashlib
import hmac
import json

import requests
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import NotificationEvent, WebhookDelivery


@shared_task(bind=True, autoretry_for=(requests.RequestException,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def deliver_webhook(self, delivery_id):
    delivery = WebhookDelivery.objects.select_related("subscription", "event").get(id=delivery_id)
    if delivery.status == "D" or delivery.attempts >= 5:
        delivery.status = "D"
        delivery.last_error = "maximum delivery attempts exceeded"
        delivery.save(update_fields=["status", "last_error", "updated_at"])
        return
    if not delivery.subscription.is_active:
        delivery.status = "D"
        delivery.last_error = "webhook subscription is inactive"
        delivery.save(update_fields=["status", "last_error", "updated_at"])
        return
    event = delivery.event
    body = json.dumps({
        "id": str(event.id), "type": event.category, "title": event.title,
        "message": event.message, "payload": event.payload,
        "created_at": event.created_at.isoformat(),
    }, separators=(",", ":")).encode()
    from integrations.crypto import decrypt_secret
    subscription = delivery.subscription
    secret = decrypt_secret(subscription.secret_ciphertext, subscription.secret_nonce, subscription.secret_key_version) if subscription.secret_ciphertext else decrypt_secret(subscription.secret or "")
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    delivery.attempts = min(delivery.attempts + 1, 32767)
    try:
        response = requests.post(
            delivery.subscription.url, data=body,
            headers={"Content-Type": "application/json", "X-Codestra-Event": event.category,
                     "X-Codestra-Event-Id": str(event.id), "X-Codestra-Signature-Version": "HMAC-SHA256",
                     "X-Codestra-Signature-256": f"sha256={signature}"},
            timeout=getattr(settings, "WEBHOOK_TIMEOUT_SECONDS", 10), allow_redirects=False,
        )
        delivery.response_code = response.status_code
        response.raise_for_status()
        delivery.status = "S"
        delivery.delivered_at = timezone.now()
        delivery.last_error = ""
    except requests.RequestException as exc:
        delivery.status = "D" if delivery.attempts >= 5 else "F"
        delivery.last_error = str(exc)[:500]
        delivery.save()
        raise
    delivery.save()


@shared_task
def purge_expired_notifications():
    cutoff = timezone.now() - timezone.timedelta(days=getattr(settings, "NOTIFICATION_RETENTION_DAYS", 90))
    deleted, _ = NotificationEvent.objects.filter(created_at__lt=cutoff).delete()
    return deleted
